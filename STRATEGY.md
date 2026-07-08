# Strategy Methodology & Assumptions

This document explains the statistical arbitrage strategy implemented in the Signal
Backtest section of the dashboard: how the signal is constructed, how it is validated,
and what its known limitations are. It explains some of the reasoning behind the numbers.

## 1. Signal Construction

For each symbol (e.g. `BTC-USD`) and each ordered exchange pair (target, reference), a
rolling Ordinary Least Squares (OLS) regression is fit on 1-minute mid-price bars:

```
close_mid(target) ~ close_mid(reference)
```

using up to the trailing 500 bars (minimum 15 observations). The fitted slope is the
**hedge ratio (beta)**: how many units of the reference-exchange price move are
associated with one unit of target-exchange price move. The **residual** is the
difference between the target exchange's actual price and the price predicted by the
regression, expressed in basis points (bps) of the target price.

- **Residual > 0**: the target exchange is trading rich relative to the model's
  prediction given the reference exchange's price.
- **Residual < 0**: the target exchange is trading cheap relative to that prediction.

## 2. Trading Rules

The strategy treats the residual as a mean-reverting spread and trades its reversion:

| Condition | Action | Position |
|---|---|---|
| residual ≥ `+entry_bps` | Sell target, buy reference | Short spread |
| residual ≤ `-entry_bps` | Buy target, sell reference | Long spread |
| position open, residual reverts within `±exit_bps` | Close position | Flat |

Execution is same-bar: a threshold crossed on a given bar is filled at that bar's
closing price (see [Limitations](#5-known-limitations) for why this is optimistic).

PnL is computed using the hedge ratio, not a 1:1 notional split:

```
pnl_bps = position * (target_return_bps - beta * ref_return_bps)
```

This makes the position closer to market-neutral than a naive equal-notional pair
trade, since the reference leg is sized by the regression slope rather than assumed
to move 1-for-1 with the target.

## 3. Statistical Validation

Two checks are run to validate the strategy's core assumption — that the residual is
actually mean-reverting rather than randomly drifting — and to sanity-check whether the
observed edge generalizes beyond the exact sample window used.

### 3.1 Stationarity (Augmented Dickey-Fuller test)

An ADF test is run on the residual series. The null hypothesis is that the series has a
unit root (i.e., is a random walk / not mean-reverting). A p-value below 0.05 rejects
that null and supports treating the residual as stationary — a necessary condition for
a mean-reversion strategy to have a genuine statistical edge rather than being curve-fit
noise.

### 3.2 Half-life of mean reversion

Using an AR(1)/Ornstein-Uhlenbeck-style regression of the residual's period-over-period
change against its lagged level, the half-life (in bars) of a reversion back toward zero
is estimated. This is useful for sanity-checking the entry/exit thresholds: if the
half-life is, for example, 3 bars, holding a position for tens of bars while waiting for a
larger reversion would be inconsistent with the estimated dynamics.

### 3.3 Out-of-sample validation (train/test split)

The loaded window is split chronologically 70/30. The same entry/exit/cost/notional
parameters (no re-optimization) are backtested independently on both halves, and the
Sharpe/PnL/win-rate are shown side by side. Some performance decay from in-sample to
out-of-sample is normal; a large collapse is a signal that the parameters (or the
sample window itself) are overfit.

## 4. PnL, Cost, and Risk Metrics

- **Dollar PnL** = `pnl_bps / 10,000 * notional_usd` — a simple linear scaling of the
  bps result to a hypothetical position size, not a claim about available liquidity.
- **Transaction cost** is a flat bps charge applied on entry and exit, meant to
  represent the *combined* taker fee across both exchange legs for that event (see the
  input's tooltip for suggested realistic values by trading tier).
- **Sharpe ratio** is computed per-bar (including flat/zero-PnL bars) and annualized
  using `sqrt(bars_per_year)` for 1-minute bars. This is a useful metric for *comparing*
  parameter settings against each other, but the absolute value should be read with
  caution — it is calculated over all bars including long inactive stretches (which
  suppresses variance more than mean), so it will read higher than a
  trade-level or active-bars-only Sharpe would.
- **Max drawdown**, **win rate**, and **trade count** are also reported for a fuller
  picture beyond Sharpe alone.

## 5. Known Limitations

What this backtest does *not* model is as important as the
strategy logic itself:

- **Execution assumption**: fills are assumed at the bar's closing price with no
  latency between signal and execution. Real trading would introduce some delay
  (depending on infrastructure), plus slippage — the Latency tab in
  this dashboard is a step toward quantifying that gap, but it isn't fed back into the
  backtest PnL.
- **No order book depth / queue modeling**: the strategy only ever sees top-of-book mid
  prices, not available size at each level.
- **No position sizing or risk limits** beyond the entry/exit thresholds — there's no
  max notional cap, portfolio-level exposure limit, or stop-loss independent of the
  mean-reversion exit signal.
- **Static parameters**: the train/test split validates a single fixed parameter set;
  it is not a full walk-forward optimization across multiple rolling windows.
- **Single flat fee assumption**: transaction cost is one input across both exchanges,
  rather than calibrated per-exchange fee tiers.

