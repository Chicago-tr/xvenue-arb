# Arb: Cross-Exchange Crypto Analytics

An end-to-end analytics platform for live crypto market data, built to highlight trading research, execution risk monitoring, and data engineering.

This project ingests bid/ask quotes from Binance and Coinbase, stores them in PostgreSQL, computes minute-level bars and cross-exchange spread metrics with PySpark, and displays analytics through a Plotly Dash dashboard.

## Why this matters
- Demonstrates a full-stack trading analytics pipeline.
- Combines real-time data ingestion, ETL, quantitative analysis, and visualization.
- Highlights both signal research and operations-focused monitoring.

## Core capabilities
- Live price ingestion from Binance and Coinbase
- Postgres-backed storage for market quotes and latency telemetry
- PySpark ETL creating 1-minute OHLC mid-price bars and cross-exchange spread metrics
- Rolling regression residuals, z-scores, and volatility forecasting
- Dash dashboard for price/spread, regression, and latency analytics
- Docker Compose and local deployment support

## Architecture
The platform consists of three main components:
- **TypeScript ingestion service** that collects live quotes and stores them in PostgreSQL.
- **PySpark analytics jobs** that compute minute bars, cross-exchange spreads, and regression metrics.
- **Dash dashboards** that visualize market data, latency, and model signals.

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

## Environment variables
- `PAIRS`: comma-separated symbols, e.g. `BTC-USD,ETH-USD,SOL-USD`
- `DB_URL`: Postgres connection URL for ingestion and dashboard
- `JDBC_URL`: JDBC URL for Spark Postgres access
- `DB_HOST`, `DB_PORT`, `DB_NAME`: Postgres connection details for ETL state updates
- `PJAR`: path to the PostgreSQL JDBC driver JAR

## Screenshots
Price & spread by exchange and cross-exchange spreads:
<img width="922" height="422" alt="homescreen" src="https://github.com/user-attachments/assets/620568d3-f2cf-48f4-83a5-51bdcfd16794" />

---

Rolling regression residuals and summary statistics:
<img width="922" height="422" alt="regression_residuals" src="https://github.com/user-attachments/assets/620568d3-f2cf-48f4-83a5-51bdcfd16794" />

---

Residuals Z-score with standard deviation bars:
<img width="922" height="422" alt="spread_zscore" src="https://github.com/user-attachments/assets/71c5d795-740d-45f3-bda7-d2f58f6" />

---

GARCH volatility forecast and summary statistics:
<img width="922" height="422" alt="forecast_stats" src="https://github.com/user-attachments/assets/72b2c5f1-ac91-4b33-b5ab-b4d64b47680a" />

---

1-Minute latency distribution and P50/P90/P99 by exchange:
<img width="922" height="422" alt="latency" src="https://github.com/user-attachments/assets/8879a920-693b-40ec-aba7-c212def2f71b" />

## Contributing
All contributions welcome. Fork the repo, create a feature branch, and open a pull request to `main`.
