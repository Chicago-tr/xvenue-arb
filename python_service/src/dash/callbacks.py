import logging
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dash_table, html
from db import engine
from plotly.subplots import make_subplots
from scipy.optimize import minimize

logger = logging.getLogger(__name__)


# Need to split-up/refactor this file eventually.


# Dropdown callback
@callback(
    [
        Output("symbol-dropdown", "options"),
        Output("exchange-dropdown", "options"),
        Output("regression-symbol", "options"),
    ],
    Input("main-tabs", "value"),
)
def update_all_dropdowns(active_tab):
    symbols_df = pd.read_sql(
        "SELECT DISTINCT symbol_code FROM bars_1m b JOIN symbols s ON b.symbol_id = s.id ORDER BY symbol_code",
        engine,
    )
    symbols = [
        {"label": row.symbol_code, "value": row.symbol_code}
        for _, row in symbols_df.iterrows()
    ]

    exchanges_df = pd.read_sql(
        "SELECT exchange_name FROM exchanges ORDER BY exchange_name", engine
    )
    exchanges = [
        {"label": row.exchange_name, "value": row.exchange_name}
        for _, row in exchanges_df.iterrows()
    ]

    return symbols, exchanges, symbols


# Price spread callback
@callback(
    Output("price-spread-chart", "figure"),
    [
        Input("symbol-dropdown", "value"),
        Input("exchange-dropdown", "value"),
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("interval-component", "n_intervals"),
    ],
)
def update_price_spread_chart(symbol, exchanges, start_date, end_date, n_intervals):
    
    if not symbol:
        return go.Figure()

    if start_date and end_date:
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)
        days_back = max(1, (end_dt - start_dt).days or 1)
    else:
        days_back = 7

    query = f"""
        SELECT b.bar_ts,
                e.exchange_name,
                b.close_mid,
                b.avg_rel_spread_bps
        FROM bars_1m b
        JOIN exchanges e ON b.exchange_id = e.id
        JOIN symbols   s ON b.symbol_id = s.id
        WHERE s.symbol_code = %s
            AND b.bar_ts > NOW() - INTERVAL '{days_back} DAYS'
    """

    params = [symbol]

    if exchanges:
        placeholders = ",".join(["%s"] * len(exchanges))
        query += f"AND e.exchange_name IN ({placeholders})"
        params.extend(exchanges)

    query += " ORDER BY b.bar_ts, e.exchange_name"

    try:
        df = pd.read_sql(query, engine, params=tuple(params))
    except Exception as exc:
        logger.exception("Failed to load price/spread data")
        return go.Figure()

    if df.empty:
        return go.Figure()

    bar_ts_series = pd.to_datetime(df["bar_ts"])
    if bar_ts_series.dt.tz is None:
        df["bar_ts"] = bar_ts_series.dt.tz_localize("UTC").dt.tz_convert(
            "America/Chicago"
        )
    else:
        df["bar_ts"] = bar_ts_series.dt.tz_convert("America/Chicago")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for exch in df["exchange_name"].unique():
        exch_df = df[df["exchange_name"] == exch]
        fig.add_trace(
            go.Scatter(
                x=exch_df["bar_ts"], y=exch_df["close_mid"], name=f"{exch} Price"
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=exch_df["bar_ts"],
                y=exch_df["avg_rel_spread_bps"],
                name=f"{exch} Spread (bps)",
                line=dict(dash="dot"),
            ),
            secondary_y=True,
        )

    fig.update_layout(
        title=f"{symbol} - Price & Spread by Exchange",
        xaxis_title="Time",
        yaxis_title="Mid Price",
        yaxis2_title="Spread (bps)",
        uirevision=symbol,
    )
    return fig


# Cross spread callback
@callback(
    Output("cross-spread-chart", "figure"),
    [
        Input("symbol-dropdown", "value"),
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("interval-component", "n_intervals"),
    ],
)
def update_cross_spread_chart(symbol, start_date, end_date, n_intervals):
    if not symbol:
        return go.Figure()

    # UTC conversion again
    if start_date and end_date:
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)
        days_back = max(1, (end_dt - start_dt).days or 1)
    else:
        days_back = 7

    query = f"""
            SELECT c.bar_ts, c.cross_spread_bps
            FROM cross_ex_spread_1m c
            JOIN symbols s ON c.symbol_id = s.id
            WHERE s.symbol_code = %s
                AND c.bar_ts > NOW() - INTERVAL '{days_back} DAYS'
            ORDER BY c.bar_ts
        """

    try:
        df = pd.read_sql(query, engine, params=(symbol,))
    except Exception as exc:
        logger.exception("Failed to load cross spread data")
        return go.Figure()

    if df.empty:
        return go.Figure()
    # Converting from UTC to CDT time
    bar_ts_series = pd.to_datetime(df["bar_ts"])
    if bar_ts_series.dt.tz is None:
        df["bar_ts"] = bar_ts_series.dt.tz_localize("UTC").dt.tz_convert(
            "America/Chicago"
        )
    else:
        df["bar_ts"] = bar_ts_series.dt.tz_convert("America/Chicago")
    fig = px.line(
        df,
        x="bar_ts",
        y="cross_spread_bps",
        title=f"{symbol} - Cross-Exchange Spread (bps)",
    )
    fig.update_yaxes(title="Cross Spread (bps)")
    fig.update_layout(uirevision=symbol)
    fig.update_xaxes(title="Time")
    return fig


# Regression callback
@callback(
    [
        Output("regression-residuals", "figure"),
        Output("regression-zscore", "figure"),
        Output("regression-stats", "children", allow_duplicate=True),
    ],
    [Input("regression-symbol", "value"), Input("regression-time-hours", "value")],
    prevent_initial_call=True,
)
def update_regression_analysis(symbol, hours):
    if not symbol:
        empty_fig = go.Figure().add_annotation(text="Select symbol", showarrow=False)
        return empty_fig, empty_fig, html.Div("Select symbol")

    # For now if changing interval here, make sure to change below 2x
    query = """
    SELECT c.bar_ts, e1.exchange_name as target_exchange, e2.exchange_name as ref_exchange,
           c.regression_residual_bps, c.residual
    FROM cross_ex_regression c JOIN symbols s ON c.symbol_id = s.id
    JOIN exchanges e1 ON c.target_exchange_id = e1.id JOIN exchanges e2 ON c.ref_exchange_id = e2.id
    WHERE s.symbol_code = %s AND (
        (%s = 1 AND c.bar_ts > NOW() - INTERVAL '1 HOUR') OR
        (%s = 4 AND c.bar_ts > NOW() - INTERVAL '4 HOURS') OR
        (%s = 24 AND c.bar_ts > NOW() - INTERVAL '24 HOURS')
    ) ORDER BY c.bar_ts DESC LIMIT 5000
    """

    try:
        df = pd.read_sql(query, engine, params=(symbol, hours, hours, hours))

        bar_ts_series = pd.to_datetime(df["bar_ts"])
        if bar_ts_series.dt.tz is None:
            df["bar_ts"] = bar_ts_series.dt.tz_localize("UTC").dt.tz_convert(
                "America/Chicago"
            )
        else:
            df["bar_ts"] = bar_ts_series.dt.tz_convert("America/Chicago")
    except Exception as exc:
        logger.exception("Failed to load regression data")
        empty_fig = go.Figure().add_annotation(text="Query error", showarrow=False)
        return empty_fig, empty_fig, html.Div("Query error: unable to load data")

    if df.empty:
        empty_fig = go.Figure().add_annotation(text="No data", showarrow=False)
        return empty_fig, empty_fig, html.Div("No data")

    fig_residuals = px.line(
        df,
        x="bar_ts",
        y="regression_residual_bps",
        color="target_exchange",
        title=f"{symbol} Residuals ({hours}h)",
    )
    fig_residuals.add_hline(y=0, line_dash="dash", line_color="red")

    df["z_score"] = (
        df["regression_residual_bps"] - df["regression_residual_bps"].mean()
    ) / df["regression_residual_bps"].std()
    fig_zscore = px.line(
        df,
        x="bar_ts",
        y="z_score",
        color="target_exchange",
        title=f"{symbol} Spread Z-Score ({hours}h)",
    )
    fig_zscore.add_hline(y=2, line_dash="dash", line_color="red")
    fig_zscore.add_hline(y=-2, line_dash="dash", line_color="red")

    stats = (
        df.groupby(["target_exchange", "ref_exchange"])
        .agg({"regression_residual_bps": ["mean", "std"]})
        .round(3)
        .reset_index()
    )
    stats.columns = ["Target", "Reference", "Resid. Mean", "Resid. StdDev"]
    stats_table = dash_table.DataTable(
        data=stats.to_dict("records"),
        columns=[{"name": i, "id": i} for i in stats.columns],
        style_cell={"textAlign": "left", "padding": "12px"},
        style_data={"backgroundColor": "#f8f9fa"},
        style_header={"backgroundColor": "#e9ecef", "fontWeight": "bold"},
        style_table={"overflowX": "auto", "marginTop": "10px"},
    )

    return fig_residuals, fig_zscore, stats_table


@callback(
    [Output("volatility-forecast", "figure"), Output("garch-stats", "children")],
    [
        Input("regression-symbol", "value"),
        Input("regression-time-hours", "value"),
        State("regression-symbol", "value"),
    ],
    prevent_initial_call=True,
)
def garch_volatility_forecast(symbol, hours, symbol_state):
    if not symbol:
        empty_fig = go.Figure().add_annotation(text="Select symbol", showarrow=False)
        return empty_fig, html.Div()

    # For now if changing interval here, make sure to change below
    query = """
    SELECT c.bar_ts, AVG(c.regression_residual_bps) as residual_bps
    FROM cross_ex_regression c JOIN symbols s ON c.symbol_id = s.id
    WHERE s.symbol_code = %s AND (
        (%s = 1 AND c.bar_ts > NOW() - INTERVAL '1 HOUR') OR
        (%s = 4 AND c.bar_ts > NOW() - INTERVAL '4 HOURS') OR
        (%s = 24 AND c.bar_ts > NOW() - INTERVAL '24 HOURS')
    )
    GROUP BY c.bar_ts ORDER BY c.bar_ts ASC LIMIT 1000
    """

    df = pd.read_sql(query, engine, params=(symbol, hours, hours, hours))

    if df.empty or len(df) < 50:
        return go.Figure().add_annotation(text="Insufficient data"), html.Div()
    try:
        bar_ts_series = pd.to_datetime(df["bar_ts"])
        if bar_ts_series.dt.tz is None:
            df["bar_ts"] = bar_ts_series.dt.tz_localize("UTC").dt.tz_convert(
                "America/Chicago"
            )
        else:
            df["bar_ts"] = bar_ts_series.dt.tz_convert("America/Chicago")
    except Exception as exc:
        logger.exception("Failed to convert GARCH timestamps")
        return go.Figure().add_annotation(text="Timestamp conversion error"), html.Div()
    # Raw volatility (%)
    df["residual_bps"] = df["residual_bps"].abs()
    df["returns"] = np.log(df["residual_bps"] / df["residual_bps"].shift(1)).fillna(0)
    df["realized_vol"] = df["returns"].rolling(20, min_periods=5).std() * 100
    # This is the volatility of spread changes
    df["realized_vol"] = df["realized_vol"].fillna(df["realized_vol"].mean())

    if symbol in calibrated_params:
        omega = calibrated_params[symbol]["omega"]
        alpha = calibrated_params[symbol]["alpha"]
        beta = calibrated_params[symbol]["beta"]
        status = " (Calibrated)"
    else:
        # Defaults if calibration not done
        omega = 0.0005 * (df["realized_vol"].tail(50) ** 2).mean() / 10000
        alpha = 0.12
        beta = 0.82
        status = " (Manual)"

    current_vol_sq = (df["realized_vol"].iloc[-1] / 100) ** 2
    current_shock_sq = df["returns"].iloc[-1] ** 2

    forecast_vol = []
    vol_sq = current_vol_sq

    for i in range(24):
        if i == 0:
            vol_sq = omega + alpha * current_shock_sq + beta * current_vol_sq
        else:
            vol_sq = omega + alpha * vol_sq + beta * vol_sq

        if vol_sq <= 0 or np.isnan(vol_sq):
            forecast_vol.append(np.nan)
        else:
            forecast_vol.append(np.sqrt(vol_sq) * 100)

    forecast_times = pd.date_range(start=df["bar_ts"].iloc[-1], periods=24, freq="h")

    persistence = alpha + beta
    denom = 1 - persistence

    if denom <= 0 or np.isnan(denom) or omega <= 0 or np.isnan(omega):
        long_run_vol = np.nan
    else:
        long_run_vol = np.sqrt(omega / denom) * 100

    current_vol = df["realized_vol"].iloc[-1]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["bar_ts"],
            y=df["realized_vol"],
            mode="lines",
            name="Realized Vol (%) (20 period lookback)",
            line=dict(color="blue", width=2),
            connectgaps=True,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=forecast_times,
            y=forecast_vol,
            mode="lines",
            name="GARCH(1,1) Forecast",
            line=dict(color="red", width=2, dash="dash"),
        )
    )

    fig.update_layout(
        title=f"{symbol} Residual Spread Volatility & GARCH(1,1) Forecast",
        yaxis_title="Volatility (%)",
        hovermode="x unified",
    )

    current_time = datetime.now().strftime("%H:%M:%S")
    current_vol = df["realized_vol"].iloc[-1]
    h1_forecast = forecast_vol[0]
    h24_forecast = forecast_vol[-1]

    h1_dir = "↗ UP" if h1_forecast > current_vol else "↘ DOWN"
    h24_dir = "↗ UP" if h24_forecast > current_vol else "↘ DOWN"

    # Check if calibrated or manual
    status = "(Calibrated)" if symbol in calibrated_params else "(Manual)"

    garch_stats = {
        "Metric": [
            "Updated",
            "Current Vol",
            "H1 Forecast",
            "H24 Forecast",
            "Parameters",
            "Persistence",
        ],
        "Value": [
            current_time,
            f"{current_vol:.1f}%",
            f"{h1_forecast:.1f}% {h1_dir}",
            f"{h24_forecast:.1f}% {h24_dir}",
            status,
            f"{alpha + beta:.3f}",
        ],
    }

    stats = dash_table.DataTable(
        data=[
            {"Metric": row[0], "Value": row[1]}
            for row in zip(garch_stats["Metric"], garch_stats["Value"])
        ],
        columns=[{"name": i, "id": i} for i in ["Metric", "Value"]],
        style_cell={"textAlign": "left", "padding": "12px"},
        style_data={"backgroundColor": "#f8f9fa"},
        style_header={"backgroundColor": "#e9ecef", "fontWeight": "bold"},
        style_table={"overflowX": "auto", "marginTop": "10px"},
    )

    return fig, stats


# Store calibrated parameters globally (across callbacks)
calibrated_params = {}


def garch_log_likelihood(params, returns):

    omega, alpha, beta = params
    T = len(returns)
    sigma2 = np.zeros(T)

    # Unconditional variance to initialize
    sigma2[0] = omega / (1 - alpha - beta) if (alpha + beta) < 1 else 0.01

    # GARCH recursion
    for t in range(1, T):
        sigma2[t] = omega + alpha * returns[t - 1] ** 2 + beta * sigma2[t - 1]
        sigma2[t] = max(sigma2[t], 0.0001)  # Floor variance

    # Log-likelihood (negative for minimization)
    nll = 0.5 * np.sum(np.log(2 * np.pi * sigma2) + (returns**2 / sigma2))
    return nll if np.isfinite(nll) else 1e10


@callback(
    Output("garch-calibration-status", "children"),
    Input("calibrate-garch-btn", "n_clicks"),
    [State("regression-symbol", "value"), State("regression-time-hours", "value")],
)
def calibrate_garch(n_clicks, symbol, hours):
    if n_clicks is None or not symbol:
        return ""

    # Can change calibration intervals here
    query = """
    SELECT c.bar_ts, AVG(regression_residual_bps) as residual_bps
    FROM cross_ex_regression c JOIN symbols s ON c.symbol_id = s.id
    WHERE s.symbol_code = %s AND (
        (%s = 1 AND bar_ts > NOW() - INTERVAL '1 HOUR') OR
        (%s = 4 AND bar_ts > NOW() - INTERVAL '4 HOURS') OR
        (%s = 24 AND bar_ts > NOW() - INTERVAL '24 HOURS')
    )
    GROUP BY bar_ts ORDER BY bar_ts ASC LIMIT 500
    """

    df = pd.read_sql(query, engine, params=(symbol, hours, hours, hours))

    if len(df) < 50:
        return html.Div("Insufficient data", style={"color": "red"})

    # Log returns
    df["returns"] = np.log(
        (df["residual_bps"].abs() + 1e-6) / (df["residual_bps"].abs().shift(1) + 1e-6)
    ).fillna(0)
    returns = df["returns"].values

    initial_params = [0.0001, 0.1, 0.8]
    result = minimize(
        garch_log_likelihood,
        initial_params,
        args=(returns,),
        bounds=[(1e-6, None), (0, 0.3), (0, 0.95)],
        method="L-BFGS-B",
    )

    if result.success:
        calibrated_params[symbol] = {
            "omega": result.x[0],
            "alpha": result.x[1],
            "beta": result.x[2],
        }
        return html.Div(
            [
                html.P(
                    f"✓ {symbol}: α={result.x[1]:.3f}, β={result.x[2]:.3f}",
                    style={"color": "green", "fontWeight": "bold"},
                )
            ],
            style={
                "padding": "10px",
                "backgroundColor": "#d4edda",
                "borderRadius": "4px",
            },
        )
    else:
        return html.Div("Calibration failed", style={"color": "red"})


@callback(
    [
        Output("latency-p99-chart", "figure"),
        Output("latency-stats-table", "data"),
        Output("latency-table-title", "children"),
    ],
    [
        Input("latency-exchange-select", "value"),
        Input("latency-date-range", "start_date"),
        Input("latency-date-range", "end_date"),
        Input("latency-interval", "n_intervals"),
    ],
)
def update_latency_dashboard(exchange_filter, start_date, end_date, n_intervals):

    if start_date and end_date:
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)
        days_back = max(1, (end_dt - start_dt).days or 1)
    else:
        days_back = 1

    if exchange_filter == "all":
        where_clause = f"ingested_at > NOW() - INTERVAL '{days_back} DAYS'"
        params = []
    else:
        where_clause = (
            f"exchange = %s AND ingested_at > NOW() - INTERVAL '{days_back} DAYS'"
        )
        params = [exchange_filter]

    query = f"""
            SELECT date_trunc('hour', to_timestamp(client_send_ts/1000::bigint)) +
                   (EXTRACT(minute FROM to_timestamp(client_send_ts/1000::bigint)) / 5 * 5 * INTERVAL '1 minute') as time_bin,
                   exchange, COUNT(*) as request_count,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rtt_ms)::numeric, 1) as p50,
                   ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY rtt_ms)::numeric, 1) as p90,
                   ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY rtt_ms)::numeric, 1) as p99,
                   ROUND(AVG(rtt_ms)::numeric, 1) as avg_rtt
            FROM latency_metrics
            WHERE {where_clause}
            GROUP BY 1,2
            ORDER BY 1 ASC, 2
        """

    df = pd.read_sql(query, engine, params=tuple(params))

    if df.empty:
        empty_fig = go.Figure()
        empty_fig.add_annotation(
            text="No data", xref="paper", yref="paper", x=0.5, y=0.5
        )
        return empty_fig, [], "No data"

    time_series = pd.to_datetime(df["time_bin"])
    if time_series.dt.tz is None:
        df["time_bin"] = time_series.dt.tz_localize("UTC").dt.tz_convert(
            "America/Chicago"
        )
    else:
        df["time_bin"] = time_series.dt.tz_convert("America/Chicago")

    colors = ["#636efa", "#EF553B", "#00cc96", "#ab63fa", "#FFA15A", "#19d3f3"]
    fig = go.Figure()

    for i, exchange in enumerate(sorted(df["exchange"].unique())):
        exch_df = df[df["exchange"] == exchange]
        color = colors[i % len(colors)]

        fig.add_trace(
            go.Scatter(
                x=exch_df["time_bin"],
                y=exch_df["p99"],
                name=f"{exchange} P99",
                line=dict(color=color, width=3),
                mode="lines",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=exch_df["time_bin"],
                y=exch_df["p90"],
                name=f"{exchange} P90",
                line=dict(color=color, width=3, dash="dash"),
                mode="lines",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=exch_df["time_bin"],
                y=exch_df["p50"],
                name=f"{exchange} P50",
                line=dict(color=color, width=3, dash="dot"),
                mode="lines",
            )
        )
    # graph
    fig.update_layout(
        title="Exchange Latency Distribution (P50/P90/P99) - 1 Minute Buckets",
        xaxis_title="Time (CDT)",
        yaxis_title="Latency (ms)",
        hovermode="x unified",
        height=500,
        template="plotly_white",
        legend=dict(
            y=0.5,
            x=1.02,
            yanchor="middle",
            xanchor="left",
            bgcolor="rgba(255,255,255,0.95)",
        ),
        yaxis=dict(gridcolor="rgba(128,128,128,0.2)"),
        margin=dict(r=150),
    )

    table_data = []
    for exchange in sorted(df["exchange"].drop_duplicates()):
        exch_df = df[df["exchange"] == exchange]
        total_requests = int(exch_df["request_count"].sum())
        latest = exch_df.iloc[-1]

        error_query = f"""
            SELECT COUNT(CASE WHEN status_code >= 400 OR status_code = 0 THEN 1 END) as errors
            FROM latency_metrics WHERE {where_clause} AND exchange = %s
        """
        try:
            error_result = pd.read_sql(error_query, engine, params=params + [exchange])
            total_errors = (
                int(error_result["errors"].iloc[0]) if not error_result.empty else 0
            )
        except Exception as exc:
            logger.exception("Latency error query failed")
            total_errors = 0

        table_data.append(
            {
                "exchange": str(exchange),
                "total_requests": f"{total_requests:,}",
                "p50": f"{float(latest['p50']):.1f}",
                "p90": f"{float(latest['p90']):.1f}",
                "p99": f"{float(latest['p99']):.1f}",
                "avg_rtt": f"{float(latest['avg_rtt']):.1f}",
                "http_errors": f"{total_errors:,}",
                "error_rate": f"{(total_errors / total_requests * 100):.1f}%"
                if total_requests > 0
                else "0%",
            }
        )

    timeframe_label = f"{days_back} Day{'s' if days_back > 1 else ''}"
    table_title = html.H4(
        f"Latency Statistics (Last 5 Minutes)",
        style={"marginBottom": "10px", "color": "#495057", "fontWeight": "500"},
    )

    return fig, table_data, table_title
