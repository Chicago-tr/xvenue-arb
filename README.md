# ExchangeAgg

End-to-end analytics platform that processes live cryptocurrency data from multiple exchanges, transforms it with PySpark, and serves interactive Dash dashboards for data analytics such as: latency, spreads, and volatility.

## Features

- PySpark ETL pipeline for transforming live cryptocurrency quotes into OHLC bars and cross-exchange spread metrics.
- P50/P90/P99 API latency tracking across exchanges, plus rolling last 5m summary stats table.
- HTTP error rate monitoring and structured logging.
- Rolling regression residuals, spreads, and volatility forecasts computed via PySpark to power cross-exchange analytics.
- Interactive dashboards built with Plotly Dash for real-time visualization.
- Data quality safeguards including ETL state management, duplicate detection, and comprehensive logging.
- Modular design to support the easy addition of new exchanges or currency pairs.
- Multiprocessing orchestrator (main.py) coordinating API data collection, Spark analytics, and Dash dashboards.


## Architecture
The platform consists of three main components:
* **TypeScript collection service** that streams live quotes and metadata from multiple exchanges into PostgreSQL.
* **PySpark analytics jobs** that build OHLC bars, compute spreads, latency statistics, and rolling volatility / regression metrics.
* **Dash dashboards** that query PostgreSQL and present real-time and historical analytics for latency, spreads and data quality.
```mermaid
graph LR
    
    A[Data Collection<br/><br/>Exchange APIs,<br/>Bid/Ask, Latency, Status logging] --> B[PostgreSQL Storage<br/><br/>Create bars, Latency metrics, Quality checks<br/>]
    
    B --> C[SQL Aggregation<br/><br/>OHLC, P50/P90/P99<br/>distributions, etc.]
    
    C --> D[PySpark/Pandas<br/><br/>Analysis,<br/>Data validation]
    D --> E[Dash/Plotly<br/><br/>Flowing updates,<br/>Multi-chart layout<br/>]
    E --> F[Dashboard<br/><br/>Symbol filtering,<br/>Date ranges,<br/>Exchange selection,<br/>Cross-asset analytics]
    
    
    style A fill:#e1f5fe
    style F fill:#c8e6c9
    classDef title font-size:14px,font-weight:bold,color:#333
    class A,B,C,D,E,F title
```

## Quick Start (Local)
1. Clone the Repository
 ```bash
 git clone https://github.com/Chicago-tr/ExchangeAggregator.git
  ```
2. Install Dependencies
```bash
cd ExchangeAggregator
#Postgres
brew install postgresql@16
brew services start postgresql@16
createdb name_your_db

#Python deps
pip install -r python_service/requirements.txt

# TypeScript deps
cd typescript_service && npm install && cd ..
```
3. Configure environment variables such as DB_URL and DB_NAME (check .env.example)
   
4. Migrate database
```bash
npx drizzle-kit migrate
```

6. Run the platform
```bash
python main.py
```
This will start the orchestrator that:
* Launches API data collection processes.
* Triggers PySpark analytics jobs.
* Serves the Dash dashboards.

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

