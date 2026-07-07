import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from db import engine

DEFAULT_ENTRY_BPS = 2.0
DEFAULT_EXIT_BPS = 1.0


def load_regression_data(symbol: str, hours: int = 24, limit: int = 1000) -> pd.DataFrame:
    query = f"""
    SELECT c.bar_ts,
           c.regression_residual_bps,
           COALESCE(c.regression_beta, 1.0) AS regression_beta,
           e1.exchange_name AS target_exchange,
           e2.exchange_name AS ref_exchange,
           b1.close_mid AS target_price,
           b2.close_mid AS ref_price
    FROM cross_ex_regression c
    JOIN symbols s ON c.symbol_id = s.id
    JOIN exchanges e1 ON c.target_exchange_id = e1.id
    JOIN exchanges e2 ON c.ref_exchange_id = e2.id
    LEFT JOIN bars_1m b1 ON b1.symbol_id = s.id
      AND b1.exchange_id = e1.id
      AND b1.bar_ts = c.bar_ts
    LEFT JOIN bars_1m b2 ON b2.symbol_id = s.id
      AND b2.exchange_id = e2.id
      AND b2.bar_ts = c.bar_ts
    WHERE s.symbol_code = %s
      AND c.bar_ts > NOW() - make_interval(hours => %s)
    ORDER BY c.bar_ts ASC
    LIMIT {int(limit)}
    """

    try:
        df = pd.read_sql(query, engine, params=(symbol, int(hours)))
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return df

    df["bar_ts"] = pd.to_datetime(df["bar_ts"])
    df["pair_label"] = df["target_exchange"] + " vs " + df["ref_exchange"]
    df["target_price"] = pd.to_numeric(df["target_price"], errors="coerce")
    df["ref_price"] = pd.to_numeric(df["ref_price"], errors="coerce")
    df["regression_beta"] = pd.to_numeric(df["regression_beta"], errors="coerce").fillna(1.0)
    df = df.dropna(subset=["regression_residual_bps", "target_price", "ref_price"])
    df = df.sort_values(["bar_ts", "pair_label"]).reset_index(drop=True)
    return df


def compute_signal_positions(df: pd.DataFrame, entry_bps: float, exit_bps: float) -> pd.DataFrame:
    df = df.copy().reset_index(drop=True)
    df["signal"] = 0
    current_signal = 0

    for idx, residual in df["regression_residual_bps"].items():
        if current_signal == 0:
            if residual <= -entry_bps:
                current_signal = 1
            elif residual >= entry_bps:
                current_signal = -1
        elif current_signal == 1:
            if residual >= -exit_bps:
                current_signal = 0
        elif current_signal == -1:
            if residual <= exit_bps:
                current_signal = 0

        df.at[idx, "signal"] = current_signal

    df["signal_type"] = df["signal"].map({1: "long", -1: "short", 0: "flat"})
    return df


def backtest_signal(df: pd.DataFrame, entry_bps: float = DEFAULT_ENTRY_BPS, exit_bps: float = DEFAULT_EXIT_BPS, cost_bps: float = 0.0, notional_usd: float = 10000.0) -> pd.DataFrame:
    """Simulate a mean-reversion spread strategy using regression residuals.

    The backtest uses the regression residual as the strategy signal.
    A positive residual means the target exchange is rich relative to the reference,
    so the strategy takes a short spread stance. A negative residual means the target
    exchange is cheap, so the strategy takes a long spread stance.

    The PnL is computed from the change in residual (spread) between bars.
    Positions are entered and exited on the same bar when the threshold
    condition is met, rather than delaying to the next bar.
    """
    if df.empty:
        return df

    df = df.copy().reset_index(drop=True)
    df = compute_signal_positions(df, float(entry_bps), float(exit_bps))
    df["position"] = df["signal"].astype(int)
    df["position_type"] = df["position"].map({1: "long", -1: "short", 0: "flat"})
    df["entry"] = (df["position"] != 0) & (df["position"].shift(1, fill_value=0) == 0)
    df["exit"] = (df["position"] == 0) & (df["position"].shift(1, fill_value=0) != 0)

    trade_ids = []
    current_trade = 0
    prev_position = 0
    for position in df["position"]:
        if prev_position == 0 and position != 0:
            current_trade += 1
        trade_ids.append(current_trade if position != 0 else 0)
        prev_position = position

    df["trade_id"] = df["pair_label"] + ":" + pd.Series(trade_ids).astype(str)
    df["residual_change_bps"] = df["regression_residual_bps"].shift(-1) - df["regression_residual_bps"]
    df["target_return_bps"] = (df["target_price"].shift(-1) - df["target_price"]) / df["target_price"] * 10000
    df["ref_return_bps"] = (df["ref_price"].shift(-1) - df["ref_price"]) / df["ref_price"] * 10000
    df["target_price_change"] = df["target_price"].shift(-1) - df["target_price"]
    df["ref_price_change"] = df["ref_price"].shift(-1) - df["ref_price"]
    df["pnl_bps"] = df["position"] * (df["target_return_bps"] - df["regression_beta"] * df["ref_return_bps"]).fillna(0.0)
    if cost_bps > 0:
        cost_flag = df["entry"].astype(float) + df["exit"].astype(float)
        df["pnl_bps"] -= cost_bps * cost_flag
    df["pnl_usd"] = df["pnl_bps"] / 10000.0 * notional_usd
    df["cum_pnl_bps"] = df["pnl_bps"].cumsum()
    df["cum_pnl_usd"] = df["pnl_usd"].cumsum()

    return df


def summarize_backtest(df: pd.DataFrame) -> dict:
    empty = {"total_pnl": 0.0, "total_pnl_usd": 0.0, "sharpe": 0.0, "num_trades": 0,
             "avg_trade_bps": 0.0, "win_rate": 0.0, "max_drawdown": 0.0, "active_bars": 0}
    if df.empty:
        return empty

    total_pnl = float(df["pnl_bps"].fillna(0.0).sum())
    total_pnl_usd = float(df["pnl_usd"].fillna(0.0).sum())
    active_bars = int((df["position"] != 0).sum())

    pnl_series = df["pnl_bps"].fillna(0.0)
    std_pnl = pnl_series.std()
    bars_per_year = 365 * 24 * 60  # crypto 1-min bars
    sharpe = float((pnl_series.mean() / std_pnl) * np.sqrt(bars_per_year)) if std_pnl > 0 else 0.0

    trade_returns = (
        df[df["position"] != 0]
        .groupby([df["pair_label"], df["trade_id"]])["pnl_bps"]
        .sum()
        .replace(0, np.nan)
        .dropna()
    )
    num_trades = int(len(trade_returns))
    avg_trade_bps = float(trade_returns.mean()) if num_trades else 0.0
    win_rate = float((trade_returns > 0).sum() / num_trades * 100) if num_trades else 0.0
    df["cum_max"] = df["cum_pnl_bps"].cummax()
    max_drawdown = float((df["cum_max"] - df["cum_pnl_bps"]).max())

    return {
        "total_pnl": total_pnl,
        "total_pnl_usd": total_pnl_usd,
        "sharpe": sharpe,
        "num_trades": num_trades,
        "avg_trade_bps": avg_trade_bps,
        "win_rate": win_rate,
        "max_drawdown": max_drawdown,
        "active_bars": active_bars,
    }


def build_trade_book(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    trade_rows = []
    active_trades = df[df["position"] != 0]
    for trade_id, group in active_trades.groupby("trade_id", sort=False):
        entry = group.iloc[0]
        exit = group.iloc[-1]
        trade_rows.append(
            {
                "trade_id": trade_id,
                "direction": entry["position_type"],
                "entry_time": entry["bar_ts"],
                "exit_time": exit["bar_ts"],
                "entry_target_price": entry["target_price"],
                "exit_target_price": exit["target_price"],
                "entry_ref_price": entry["ref_price"],
                "exit_ref_price": exit["ref_price"],
                "entry_residual_bps": entry["regression_residual_bps"],
                "exit_residual_bps": exit["regression_residual_bps"],
                "duration_bars": len(group),
                "trade_pnl_bps": float(group["pnl_bps"].sum()),
                "trade_pnl_usd": float(group["pnl_usd"].sum()),
            }
        )

    trades = pd.DataFrame(trade_rows)
    if not trades.empty:
        trades["entry_time"] = pd.to_datetime(trades["entry_time"])
        trades["exit_time"] = pd.to_datetime(trades["exit_time"])
    return trades


def build_backtest_figure(df: pd.DataFrame, entry_bps: float = DEFAULT_ENTRY_BPS, exit_bps: float = DEFAULT_EXIT_BPS, cost_bps: float = 0.0, notional_usd: float = 10000.0) -> go.Figure:
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No backtest data", showarrow=False)
        return fig

    pair_label = df["pair_label"].iloc[0]
    trade_count = int(df["entry"].sum())
    target_name = pair_label.split(" vs ")[0] if " vs " in pair_label else "Target"
    ref_name = pair_label.split(" vs ")[1] if " vs " in pair_label else "Ref"
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.38, 0.18, 0.38],
    )

    fig.add_trace(
        go.Scatter(
            x=df["bar_ts"],
            y=df["regression_residual_bps"],
            mode="lines",
            name="Residual",
            line=dict(color="#1f77b4", width=2),
            hovertemplate="%{x}<br>Residual: %{y:.3f} bps",
        ),
        row=1,
        col=1,
    )

    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="#888",
        row=1,
        col=1,
        annotation_text="Zero",
        annotation_position="bottom left",
    )
    fig.add_hline(
        y=entry_bps,
        line_dash="dash",
        line_color="#d62728",
        row=1,
        col=1,
        annotation_text=f"Short entry: sell {target_name}",
        annotation_position="top right",
    )
    fig.add_hline(
        y=-entry_bps,
        line_dash="dash",
        line_color="#2ca02c",
        row=1,
        col=1,
        annotation_text=f"Long entry: buy {target_name}",
        annotation_position="bottom left",
    )
    fig.add_hline(
        y=exit_bps,
        line_dash="dot",
        line_color="#ff7f0e",
        row=1,
        col=1,
        annotation_text="Exit band",
        annotation_position="bottom right",
    )
    fig.add_hline(
        y=-exit_bps,
        line_dash="dot",
        line_color="#ff7f0e",
        row=1,
        col=1,
        annotation_text="Exit band",
        annotation_position="top left",
    )

    entry_long = df[df["entry"] & (df["position"] == 1)]
    entry_short = df[df["entry"] & (df["position"] == -1)]
    exits = df[df["exit"]]

    if not entry_long.empty:
        fig.add_trace(
            go.Scatter(
                x=entry_long["bar_ts"],
                y=entry_long["regression_residual_bps"],
                mode="markers",
                name=f"Long Entry (Buy {target_name})",
                marker=dict(symbol="triangle-up", color="#2ca02c", size=10),
                hovertemplate=f"%{{x}}<br>Long Entry<br>Buy {target_name} / Sell {ref_name}<br>Residual: %{{y:.3f}} bps",
            ),
            row=1,
            col=1,
        )
    if not entry_short.empty:
        fig.add_trace(
            go.Scatter(
                x=entry_short["bar_ts"],
                y=entry_short["regression_residual_bps"],
                mode="markers",
                name=f"Short Entry (Sell {target_name})",
                marker=dict(symbol="triangle-down", color="#d62728", size=10),
                hovertemplate=f"%{{x}}<br>Short Entry<br>Sell {target_name} / Buy {ref_name}<br>Residual: %{{y:.3f}} bps",
            ),
            row=1,
            col=1,
        )
    if not exits.empty:
        fig.add_trace(
            go.Scatter(
                x=exits["bar_ts"],
                y=exits["regression_residual_bps"],
                mode="markers",
                name="Exit",
                marker=dict(symbol="x", color="#9467bd", size=10),
                hovertemplate="%{x}<br>Exit<br>Residual: %{y:.3f} bps",
            ),
            row=1,
            col=1,
        )

    df["position_hover"] = df["position"].map({
        1: f"Long Spread: Buy {target_name} / Sell {ref_name}",
        -1: f"Short Spread: Sell {target_name} / Buy {ref_name}",
        0: "Flat",
    })
    fig.add_trace(
        go.Scatter(
            x=df["bar_ts"],
            y=df["position"],
            mode="lines",
            name=f"Position ({pair_label})",
            line=dict(color="#7f7f7f", width=3, shape="hv"),
            hovertemplate="%{x}<br>%{text}",
            text=df["position_hover"],
        ),
        row=2,
        col=1,
    )

    df = df.copy()
    df["cum_pnl_usd_plot"] = df["cum_pnl_usd"].shift(1).fillna(0.0)

    fig.add_trace(
        go.Scatter(
            x=df["bar_ts"],
            y=df["cum_pnl_usd_plot"],
            mode="lines+markers",
            name=f"Cumulative PnL USD ({pair_label})",
            line=dict(color="#17becf", width=2),
            marker=dict(size=4),
            hovertemplate="%{x}<br>Cumulative PnL: $%{y:.2f}",
        ),
        row=3,
        col=1,
    )

    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="#888",
        row=3,
        col=1,
    )

    final_pnl_usd = float(df["cum_pnl_usd"].iloc[-1])
    final_pnl_bps = float(df["cum_pnl_bps"].iloc[-1])
    cost_str = f", cost={cost_bps} bps/side" if cost_bps > 0 else ""
    title_text = (
        f"Backtest: {pair_label} | entry={entry_bps} bps, exit={exit_bps} bps{cost_str} | "
        f"${notional_usd:,.0f} notional | trades={trade_count} | PnL: ${final_pnl_usd:.2f} ({final_pnl_bps:.1f} bps)"
        f"<br><sup>Long Spread = Buy {target_name} / Sell {ref_name}  ·  "
        f"Short Spread = Sell {target_name} / Buy {ref_name}  ·  "
        f"Signal: mean-reversion on OLS regression residual</sup>"
    )
    if trade_count == 0:
        title_text += " — no trades generated with current thresholds"

    fig.update_layout(
        title=title_text,
        xaxis_title="Time",
        yaxis_title="OLS Residual (bps)",
        yaxis2_title="Spread Position",
        yaxis3_title=f"Cumulative PnL (USD, ${notional_usd:,.0f} notional)",
        legend=dict(orientation="h", y=1.03, x=0, xanchor="left"),
        template="plotly_white",
        height=760,
        margin=dict(t=120, b=50, l=70, r=70),
        annotations=[
            dict(
                x=0.98,
                y=0.92,
                xref="paper",
                yref="paper",
                text=f"{pair_label}: ${final_pnl_usd:.2f} ({final_pnl_bps:.1f} bps)",
                showarrow=False,
                font=dict(size=12, color="#222"),
                bgcolor="#ffffff",
                bordercolor="#222",
                borderwidth=1,
                opacity=0.85,
            ),
            dict(
                x=0.5,
                y=-0.15,
                xref="paper",
                yref="paper",
                text="Cumulative PnL is plotted at the end of each bar after the bar's execution.",
                showarrow=False,
                font=dict(size=11, color="#555"),
            ),
        ],
    )

    if trade_count == 0:
        fig.add_annotation(
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            text="No trades generated: reduce entry threshold or widen the sample",
            showarrow=False,
            font=dict(size=14, color="#d62728"),
            bgcolor="#ffffff",
            bordercolor="#d62728",
            borderwidth=1,
            opacity=0.9,
        )

    fig.update_yaxes(row=2, col=1, tickmode="array", tickvals=[-1, 0, 1], ticktext=["Short Spread", "Flat", "Long Spread"])
    return fig


def build_sensitivity_heatmap(df: pd.DataFrame, cost_bps: float = 0.0) -> go.Figure:
    """Sweep entry/exit threshold combinations and plot annualized Sharpe as a heatmap."""
    entry_range = [1, 2, 3, 5, 7, 10, 15, 20]
    exit_range = [0.5, 1, 1.5, 2, 3, 5, 7]

    sharpe_grid = []
    trade_count_grid = []

    for ex in exit_range:
        row_sharpe = []
        row_trades = []
        for en in entry_range:
            if ex >= en:
                row_sharpe.append(np.nan)
                row_trades.append(0)
            else:
                result = backtest_signal(df, entry_bps=en, exit_bps=ex, cost_bps=cost_bps)
                stats = summarize_backtest(result)
                row_sharpe.append(stats.get("sharpe", 0.0))
                row_trades.append(stats.get("num_trades", 0))
        sharpe_grid.append(row_sharpe)
        trade_count_grid.append(row_trades)

    hover_text = [
        [
            f"Entry: {entry_range[j]} bps<br>Exit: {exit_range[i]} bps<br>Sharpe: {sharpe_grid[i][j]:.2f}<br>Trades: {int(trade_count_grid[i][j])}"
            if not np.isnan(sharpe_grid[i][j]) else "Invalid (exit ≥ entry)"
            for j in range(len(entry_range))
        ]
        for i in range(len(exit_range))
    ]

    fig = go.Figure(go.Heatmap(
        z=sharpe_grid,
        x=[str(e) for e in entry_range],
        y=[str(e) for e in exit_range],
        text=hover_text,
        hoverinfo="text",
        colorscale="RdYlGn",
        zmid=0,
        colorbar=dict(title="Sharpe"),
    ))
    fig.update_layout(
        title=f"Parameter Sensitivity: Annualized Sharpe by Entry/Exit Threshold (cost={cost_bps} bps/side)",
        xaxis_title="Entry threshold (bps)",
        yaxis_title="Exit threshold (bps)",
        template="plotly_white",
        height=420,
    )
    return fig
