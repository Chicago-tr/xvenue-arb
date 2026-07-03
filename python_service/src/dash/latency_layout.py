import sys
from datetime import datetime, timedelta

from dash import dash_table, dcc, html

sys.path.append("..")


latency_tab = html.Div(
    [
        html.Div(
            [
                html.Div(
                    [
                        html.Label(
                            "Date Range:",
                            style={"marginBottom": "5px"},
                        ),
                        dcc.DatePickerRange(
                            id="latency-date-range",
                            start_date=datetime.now() - timedelta(days=1),
                            end_date=datetime.now(),
                            style={"width": "250px"},
                        ),
                        html.Label(
                            "Exchanges:",
                            style={"marginBottom": "5px"},
                        ),
                        dcc.Dropdown(
                            id="latency-exchange-select",
                            options=[
                                {"label": "All Exchanges", "value": "all"},
                                {"label": "Binance", "value": "binance"},
                                {"label": "Coinbase", "value": "coinbase"},
                            ],
                            value="all",
                            clearable=False,
                            style={"width": "300px"},
                        ),
                    ],
                    style={
                        "display": "flex",
                        "flexDirection": "column",
                        "marginBottom": "20px",
                    },
                ),
            ],
            style={"padding": "20px", "display": "flex", "alignItems": "flex-start"},
        ),
        dcc.Interval(
            id="latency-interval",
            interval=2 * 60 * 1000,
            n_intervals=0,  # 2min refresh
        ),
        dcc.Graph(id="latency-p99-chart"),
        html.Div(id="latency-table-title"),
        dash_table.DataTable(
            id="latency-stats-table",
            columns=[
                {"name": "Exchange", "id": "exchange"},
                {"name": "P50 (ms)", "id": "p50"},
                {"name": "P90 (ms)", "id": "p90"},
                {"name": "P99 (ms)", "id": "p99"},
                {"name": "Avg RTT (ms)", "id": "avg_rtt"},
                {"name": "HTTP Errors", "id": "http_errors"},
                {"name": "Error Rate", "id": "error_rate"},
            ],
            style_cell={"textAlign": "left", "padding": "12px"},
            style_data={"backgroundColor": "#f8f9fa"},
            style_header={"backgroundColor": "#e9ecef", "fontWeight": "bold"},
            style_table={"overflowX": "auto"},
            page_size=10,
        ),
    ],
    style={"padding": "20px"},
)
