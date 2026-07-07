from dash import dcc, html, dash_table

regression_tab = html.Div(
    [
        # Controls section with Calibrate button
        html.Div(
            [
                html.Label("Symbol:"),
                dcc.Dropdown(
                    id="regression-symbol",
                    options=[],
                    value=None,
                    style={"width": "200px"},
                ),
                html.Label("Time Window:"),
                dcc.Dropdown(
                    id="regression-time-hours",
                    options=[
                        {"label": "1 Hour", "value": 1},
                        {"label": "4 Hours", "value": 4},
                        {"label": "24 Hours", "value": 24},
                    ],
                    value=24,
                    style={
                        "width": "200px",
                    },
                ),
                html.Button(
                    "Calibrate GARCH",
                    id="calibrate-garch-btn",
                    style={
                        "padding": "8px 16px",
                        "backgroundColor": "#3498db",
                        "color": "white",
                        "border": "none",
                        "borderRadius": "4px",
                        "cursor": "pointer",
                        "fontSize": "14px",
                        "marginTop": "5px",
                    },
                ),
            ],
            style={
                "padding": "20px",
                "backgroundColor": "#f8f9fa",
                "marginBottom": "10px",
            },
        ),
        # Calibration status
        html.Div(id="garch-calibration-status", style={"padding": "0 20px 15px 20px"}),
        # Residuals chart + stats table
        html.Div(
            [
                dcc.Graph(id="regression-residuals"),
                html.Div(
                    id="regression-stats", style={"padding": "10px 20px 20px 20px"}
                ),
            ],
            style={"marginBottom": "30px"},
        ),
        # Z-score chart
        dcc.Graph(id="regression-zscore", style={"marginBottom": "30px"}),
        # Volatility forecast and GARCH stats table
        html.Div(
            [
                dcc.Graph(id="volatility-forecast"),
                html.Div(id="garch-stats", style={"padding": "10px 20px 20px 20px"}),
            ]
        ),
        html.H2("Signal Backtest", style={"marginTop": "40px", "marginBottom": "20px"}),
        html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Label("Signal entry threshold (bps): "),
                                html.Span(
                                    "(hover for info)",
                                    title="Open a short spread trade when residual exceeds this positive threshold, or a long spread trade when residual falls below the negative threshold.",
                                    style={"fontSize": "12px", "color": "#666", "marginRight": "6px"},
                                ),
                                dcc.Input(
                                    id="signal-entry-bps",
                                    type="number",
                                    value=2,
                                    min=1,
                                    step=1,
                                    style={"width": "120px", "marginRight": "20px"},
                                ),
                            ],
                            style={"display": "inline-flex", "alignItems": "center"},
                        ),
                        html.Div(
                            [
                                html.Label("Close when residual reaches (bps): "),
                                html.Span(
                                    "(hover for info)",
                                    title="Close the current spread trade when the residual reverts toward zero to this level.",
                                    style={"fontSize": "12px", "color": "#666", "marginRight": "6px"},
                                ),
                                dcc.Input(
                                    id="signal-exit-bps",
                                    type="number",
                                    value=1,
                                    min=1,
                                    step=1,
                                    style={"width": "120px", "marginRight": "20px"},
                                ),
                            ],
                            style={"display": "inline-flex", "alignItems": "center"},
                        ),
                        html.Div(
                            [
                                html.Label("Transaction cost (bps/event): "),
                                html.Span(
                                    "(hover for info)",
                                    title="Combined taker fee across both exchange legs, deducted on entry and again on exit. Each event involves two transactions (one per exchange), so this should be ~2x your per-exchange fee. e.g. 2 bps = ~1 bps/exchange/side, typical for an active trader. Retail (10 bps/exchange) → use 20 bps here.",
                                    style={"fontSize": "12px", "color": "#666", "marginRight": "6px"},
                                ),
                                dcc.Input(
                                    id="signal-cost-bps",
                                    type="number",
                                    value=2,
                                    min=0,
                                    step=0.5,
                                    style={"width": "100px", "marginRight": "20px"},
                                ),
                            ],
                            style={"display": "inline-flex", "alignItems": "center"},
                        ),
                        html.Div(
                            [
                                html.Label("Notional ($): "),
                                html.Span(
                                    "(hover for info)",
                                    title="Position size in USD used to compute dollar PnL. e.g. $10,000 means each 1 bps of spread captured = $1.",
                                    style={"fontSize": "12px", "color": "#666", "marginRight": "6px"},
                                ),
                                dcc.Input(
                                    id="signal-notional-usd",
                                    type="number",
                                    value=10000,
                                    min=1000,
                                    step=1000,
                                    style={"width": "110px", "marginRight": "20px"},
                                ),
                            ],
                            style={"display": "inline-flex", "alignItems": "center"},
                        ),
                        html.Label("Exchange Pair:"),
                        dcc.Dropdown(
                            id="signal-pair-dropdown",
                            options=[],
                            value=None,
                            clearable=False,
                            style={"width": "260px"},
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center", "gap": "20px", "padding": "20px", "backgroundColor": "#f8f9fa", "marginBottom": "10px"},
                ),
                dcc.Graph(id="signal-backtest-chart"),
                html.Div(id="signal-backtest-stats", style={"padding": "10px 20px 20px 20px"}),
                html.H3("Trade Log", style={"marginTop": "20px"}),
                dash_table.DataTable(
                    id="signal-trade-log",
                    columns=[
                        {"name": "Trade ID", "id": "trade_id"},
                        {"name": "Direction", "id": "direction"},
                        {"name": "Entry Time", "id": "entry_time"},
                        {"name": "Exit Time", "id": "exit_time"},
                        {"name": "Entry Residual", "id": "entry_residual_bps"},
                        {"name": "Exit Residual", "id": "exit_residual_bps"},
                        {"name": "Trade PnL (bps)", "id": "trade_pnl_bps"},
                        {"name": "Trade PnL ($)", "id": "trade_pnl_usd"},
                        {"name": "Duration (bars)", "id": "duration_bars"},
                    ],
                    data=[],
                    style_cell={"textAlign": "left", "padding": "8px"},
                    style_header={"backgroundColor": "#e9ecef", "fontWeight": "bold"},
                    style_table={"overflowX": "auto", "marginTop": "10px"},
                ),
                html.H3("Parameter Sensitivity", style={"marginTop": "30px"}),
                html.P(
                    "Sweeps entry/exit threshold combinations and shows the annualized Sharpe ratio. Uses the current symbol, time window, pair, and transaction cost.",
                    style={"color": "#666", "fontSize": "13px", "marginBottom": "10px"},
                ),
                html.Button(
                    "Run Sensitivity Analysis",
                    id="run-sensitivity-btn",
                    n_clicks=0,
                    style={"padding": "8px 16px", "backgroundColor": "#3498db", "color": "white",
                           "border": "none", "borderRadius": "4px", "cursor": "pointer", "marginBottom": "10px"},
                ),
                dcc.Graph(id="signal-sensitivity-heatmap"),
            ]
        ),
    ],
    style={"padding": "20px"},
)
