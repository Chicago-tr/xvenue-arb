# Arb: Cross-Exchange Crypto Analytics

An end-to-end analytics platform for live crypto market data, built for trading research, market structure monitoring, and data engineering.

This project ingests bid/ask quotes from exchanges, stores them in PostgreSQL, computes minute-level bars and cross-exchange spread metrics with PySpark, and displays results through a Plotly Dash dashboard.

## Core capabilities

- Data quality safeguards like state management, duplicate detection, and logging
- Postgres-backed storage for market quotes and telemetry
- PySpark ETL creating 1-minute OHLC mid-price bars and cross-exchange spread metrics
- Regression residuals, z-scores, and volatility forecasting
- Dash dashboard for price, spread, regression, and latency analytics
- Docker Compose support for easy local deployment

## Quick start with Docker
1. Copy the example env file:
```bash
cp .env.example .env
```
2. Edit `.env` and set the required values.
3. Start the stack:
```bash
docker compose up --build
```
4. Open `http://127.0.0.1:8050` in your browser.

## Manual local setup
### Prerequisites
- Docker & Docker Compose
- Python 3.11+ / 3.12+
- Node.js 20+
- PostgreSQL 16
- PostgreSQL JDBC driver for Spark

### Install dependencies
```bash
python -m pip install -r python_service/requirements.txt
cd typescript_service && npm install && cd ..
```

### Configure environment
Copy `.env.example` to `.env` and update values such as `DB_URL`, `JDBC_URL`, and `PJAR`.

### Run locally
```bash
python main.py
```
This will start the orchestrator that:
* Launches API data collection processes.
* Triggers PySpark analytics jobs.
* Serves the Dash dashboards.

## Environment variables
- `PAIRS`: comma-separated symbols, e.g. `BTC-USD,ETH-USD,SOL-USD`
- `DB_URL`: Postgres connection URL for ingestion and dashboard
- `JDBC_URL`: JDBC URL for Spark Postgres access
- `DB_HOST`, `DB_PORT`, `DB_NAME`: Postgres connection details for ETL state updates
- `PJAR`: path to the PostgreSQL JDBC driver JAR

## Backtesting and execution simulation
The project now includes a walk-forward backtesting module for residual mean reversion with execution assumptions:
- rolling z-score signal generation from `cross_ex_regression`
- transaction cost modeling (`fee_bps`, slippage, spread crossing)
- latency-aware execution shift (`latency_bars`)
- inventory/position controls and turnover tracking
- out-of-sample evaluation via train/test split per symbol/exchange pair
- metrics including net PnL, Sharpe, max drawdown, win rate, and turnover

Run the backtest:
```bash
python python_service/src/backtest.py
```

Example with custom assumptions:
```bash
python python_service/src/backtest.py \
  --lookback-days 21 \
  --entry-candidates 1.5 2.0 2.5 3.0 \
  --fee-bps 2.0 \
  --slippage-bps 1.5 \
  --spread-cross-bps 1.0 \
  --latency-bars 1 \
  --position-size-usd 2000
```

Outputs are written to `python_service/output/`:
- `backtest_summary.csv` (group-level out-of-sample results)
- `backtest_bars.csv` (bar-level PnL/position timeline)
- `backtest_metrics.json` (aggregate portfolio metrics + config)


## Screenshots
Price & spread by exchange and cross-exchange spreads:
<img width="922" height="422" alt="homescreen" src="https://github.com/user-attachments/assets/620568d3-f2cf-48f4-83a5-51bdcfd16794" />

---
---
Rolling regression residuals and summary statistics:
<img width="922" height="422" alt="regression_residuals" src="https://github.com/user-attachments/assets/f7e236b6-772d-4c4b-ba7d-16ce0ecc1cf0" />

---
---
Residuals Z-score with standard deviation bars:
<img width="922" height="422" alt="spread_zscore" src="https://github.com/user-attachments/assets/71c5d795-740d-45f3-bda8-65860d2f58f6" />

---
---
GARCH volatility forecast and summary statistics:
<img width="922" height="422" alt="forecast_stats" src="https://github.com/user-attachments/assets/72b2c5f1-ac91-4b33-b5ab-b4d64b47680a" />

---
---
1-Minute Latency distribution and P50/P90/P99 by exchange:
<img width="922" height="422" alt="latency" src="https://github.com/user-attachments/assets/8879a920-693b-40ec-aba7-c212def2f71b" />

## Contributing
All contributions welcome, just fork the repo, create a feature branch, and open a pull request to ```main```.
