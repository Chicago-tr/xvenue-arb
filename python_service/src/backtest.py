import argparse
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


@dataclass
class BacktestConfig:
    lookback_days: int = 14
    z_window: int = 120
    z_min_periods: int = 30
    entry_candidates: tuple[float, ...] = (1.5, 2.0, 2.5, 3.0)
    exit_z: float = 0.5
    fee_bps: float = 2.0
    slippage_bps: float = 1.0
    spread_cross_bps: float = 1.0
    latency_bars: int = 1
    position_size_usd: float = 1_000.0
    max_inventory_units: int = 1
    train_fraction: float = 0.6
    min_rows_per_group: int = 120
    min_test_rows: int = 40
    periods_per_year: int = 525_600  # minute bars
    output_dir: str = "python_service/output"

    @property
    def transaction_cost_bps(self) -> float:
        return self.fee_bps + self.slippage_bps + self.spread_cross_bps


def load_regression_data(engine, lookback_days: int) -> pd.DataFrame:
    query = text(
        """
        SELECT
            c.bar_ts,
            s.symbol_code,
            e1.exchange_name AS target_exchange,
            e2.exchange_name AS ref_exchange,
            c.regression_residual_bps
        FROM cross_ex_regression c
        JOIN symbols s ON c.symbol_id = s.id
        JOIN exchanges e1 ON c.target_exchange_id = e1.id
        JOIN exchanges e2 ON c.ref_exchange_id = e2.id
        WHERE c.bar_ts > NOW() - (:lookback_days || ' days')::interval
        ORDER BY c.bar_ts ASC
        """
    )
    return pd.read_sql(query, engine, params={"lookback_days": lookback_days})


def _rolling_zscore(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    rolling = series.rolling(window=window, min_periods=min_periods)
    mean = rolling.mean()
    std = rolling.std(ddof=0)
    z = (series - mean) / std.replace(0, np.nan)
    return z


def prepare_features(df: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    sort_cols = ["symbol_code", "target_exchange", "ref_exchange", "bar_ts"]
    data = df.sort_values(sort_cols).copy()
    group_cols = ["symbol_code", "target_exchange", "ref_exchange"]
    grouped = data.groupby(group_cols, group_keys=False)["regression_residual_bps"]
    data["z_score"] = grouped.transform(
        lambda s: _rolling_zscore(s, cfg.z_window, cfg.z_min_periods)
    )
    data["delta_residual_bps"] = grouped.diff().fillna(0.0)
    return data


def generate_desired_positions(
    z_scores: pd.Series, entry_z: float, exit_z: float
) -> pd.Series:
    state = 0
    desired = []
    for z in z_scores:
        if pd.isna(z):
            desired.append(state)
            continue

        if state == 0:
            if z >= entry_z:
                state = -1
            elif z <= -entry_z:
                state = 1
        elif abs(z) <= exit_z:
            state = 0

        desired.append(state)

    return pd.Series(desired, index=z_scores.index, dtype=float)


def compute_metrics(net_pnl_usd: pd.Series, turnover_units: pd.Series, cfg: BacktestConfig):
    pnl = net_pnl_usd.fillna(0.0)
    mean = pnl.mean()
    std = pnl.std(ddof=0)
    sharpe = 0.0 if std == 0 else float((mean / std) * math.sqrt(cfg.periods_per_year))

    equity = pnl.cumsum()
    drawdown = equity - equity.cummax()
    max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0

    non_zero = pnl[pnl != 0]
    win_rate = float((non_zero > 0).mean()) if not non_zero.empty else 0.0

    turnover_total = float(turnover_units.sum())
    trade_events = int((turnover_units > 0).sum())

    return {
        "total_net_pnl_usd": float(pnl.sum()),
        "mean_bar_pnl_usd": float(mean),
        "sharpe_annualized": sharpe,
        "max_drawdown_usd": max_drawdown,
        "win_rate": win_rate,
        "turnover_units": turnover_total,
        "trade_events": trade_events,
    }


def simulate_group(
    group: pd.DataFrame, entry_z: float, cfg: BacktestConfig
) -> tuple[pd.DataFrame, dict]:
    data = group.copy().sort_values("bar_ts")

    desired = generate_desired_positions(data["z_score"], entry_z, cfg.exit_z)
    desired = desired.clip(-cfg.max_inventory_units, cfg.max_inventory_units)
    executed = desired.shift(cfg.latency_bars).fillna(0.0)
    prev_position = executed.shift(1).fillna(0.0)

    turnover = (executed - executed.shift(1).fillna(0.0)).abs()
    gross_pnl_bps = prev_position * data["delta_residual_bps"]
    cost_bps = turnover * cfg.transaction_cost_bps
    net_pnl_bps = gross_pnl_bps - cost_bps
    net_pnl_usd = (net_pnl_bps / 10_000.0) * cfg.position_size_usd

    data["entry_z"] = entry_z
    data["desired_position"] = desired
    data["executed_position"] = executed
    data["turnover_units"] = turnover
    data["gross_pnl_bps"] = gross_pnl_bps
    data["cost_bps"] = cost_bps
    data["net_pnl_bps"] = net_pnl_bps
    data["net_pnl_usd"] = net_pnl_usd
    data["equity_usd"] = net_pnl_usd.cumsum()

    metrics = compute_metrics(net_pnl_usd, turnover, cfg)
    metrics["entry_z"] = float(entry_z)
    return data, metrics


def select_entry_threshold(train_df: pd.DataFrame, cfg: BacktestConfig) -> float:
    best_entry = cfg.entry_candidates[0]
    best_score = (-float("inf"), -float("inf"))
    for candidate in cfg.entry_candidates:
        _, metrics = simulate_group(train_df, candidate, cfg)
        score = (metrics["sharpe_annualized"], metrics["total_net_pnl_usd"])
        if score > best_score:
            best_score = score
            best_entry = candidate
    return best_entry


def run_walk_forward(df: pd.DataFrame, cfg: BacktestConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    group_cols = ["symbol_code", "target_exchange", "ref_exchange"]
    summaries: list[dict] = []
    all_test_rows: list[pd.DataFrame] = []

    for group_key, group in df.groupby(group_cols, sort=False):
        ordered = group.sort_values("bar_ts").reset_index(drop=True)
        if len(ordered) < cfg.min_rows_per_group:
            continue

        split_idx = int(len(ordered) * cfg.train_fraction)
        train_df = ordered.iloc[:split_idx]
        test_df = ordered.iloc[split_idx:]

        if len(test_df) < cfg.min_test_rows:
            continue

        chosen_entry = select_entry_threshold(train_df, cfg)
        simulated, test_metrics = simulate_group(test_df, chosen_entry, cfg)

        symbol, target_exchange, ref_exchange = group_key
        test_metrics.update(
            {
                "symbol_code": symbol,
                "target_exchange": target_exchange,
                "ref_exchange": ref_exchange,
                "train_rows": int(len(train_df)),
                "test_rows": int(len(test_df)),
            }
        )
        summaries.append(test_metrics)
        all_test_rows.append(simulated)

    if not summaries:
        return pd.DataFrame(), pd.DataFrame()

    summary_df = pd.DataFrame(summaries).sort_values(
        ["sharpe_annualized", "total_net_pnl_usd"], ascending=False
    )
    test_bars_df = pd.concat(all_test_rows, ignore_index=True)
    return summary_df, test_bars_df


def compute_portfolio_metrics(test_bars_df: pd.DataFrame, cfg: BacktestConfig) -> dict:
    if test_bars_df.empty:
        return {}
    portfolio = (
        test_bars_df.groupby("bar_ts", as_index=False)
        .agg(net_pnl_usd=("net_pnl_usd", "sum"), turnover_units=("turnover_units", "sum"))
        .sort_values("bar_ts")
    )
    metrics = compute_metrics(portfolio["net_pnl_usd"], portfolio["turnover_units"], cfg)
    metrics["bars"] = int(len(portfolio))
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Walk-forward backtest for cross-exchange residual mean reversion."
    )
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument("--z-window", type=int, default=120)
    parser.add_argument("--entry-candidates", type=float, nargs="+", default=[1.5, 2.0, 2.5, 3.0])
    parser.add_argument("--exit-z", type=float, default=0.5)
    parser.add_argument("--fee-bps", type=float, default=2.0)
    parser.add_argument("--slippage-bps", type=float, default=1.0)
    parser.add_argument("--spread-cross-bps", type=float, default=1.0)
    parser.add_argument("--latency-bars", type=int, default=1)
    parser.add_argument("--position-size-usd", type=float, default=1000.0)
    parser.add_argument("--max-inventory-units", type=int, default=1)
    parser.add_argument("--train-fraction", type=float, default=0.6)
    parser.add_argument("--output-dir", type=str, default="python_service/output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv()
    db_url = os.getenv("DB_URL")
    if not db_url:
        raise ValueError("No DB_URL in .env")

    cfg = BacktestConfig(
        lookback_days=args.lookback_days,
        z_window=args.z_window,
        entry_candidates=tuple(args.entry_candidates),
        exit_z=args.exit_z,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
        spread_cross_bps=args.spread_cross_bps,
        latency_bars=args.latency_bars,
        position_size_usd=args.position_size_usd,
        max_inventory_units=args.max_inventory_units,
        train_fraction=args.train_fraction,
        output_dir=args.output_dir,
    )

    engine = create_engine(db_url)
    raw = load_regression_data(engine, cfg.lookback_days)
    if raw.empty:
        print("No regression data found for selected window.")
        return 0

    data = prepare_features(raw, cfg)
    summary_df, test_bars_df = run_walk_forward(data, cfg)
    if summary_df.empty:
        print("Insufficient grouped data for walk-forward evaluation.")
        return 0

    portfolio_metrics = compute_portfolio_metrics(test_bars_df, cfg)
    aggregate = {
        "groups_evaluated": int(len(summary_df)),
        "portfolio_metrics": portfolio_metrics,
        "config": asdict(cfg),
    }

    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "backtest_summary.csv"
    bars_path = output_dir / "backtest_bars.csv"
    metrics_path = output_dir / "backtest_metrics.json"

    summary_df.to_csv(summary_path, index=False)
    test_bars_df.to_csv(bars_path, index=False)
    metrics_path.write_text(json.dumps(aggregate, indent=2))

    print(json.dumps(aggregate, indent=2))
    print(f"Saved summary: {summary_path}")
    print(f"Saved bar-level results: {bars_path}")
    print(f"Saved metrics: {metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
