import dash
import dash.dcc as dcc
import dash.html as html
from latency_layout import latency_tab
from prices_layout import prices_tab
from regression_layout import regression_tab

app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "Crypto Analytics"

# import callbacks after app is created so @callback decorators can register
from callbacks import *  # Gets all callbacks

app.layout = html.Div(
    [
        html.H1(
            "Crypto Multi-Exchange Analytics",
            style={"textAlign": "center", "marginBottom": "30px"},
        ),
        dcc.Tabs(
            [
                dcc.Tab(label="Price & Spread", value="prices", children=[prices_tab]),
                dcc.Tab(
                    label="Regression Analysis",
                    value="regression",
                    children=[regression_tab],
                ),
                dcc.Tab(label="Latency", value="latency", children=[latency_tab]),
            ],
            id="main-tabs",
            value="prices",
        ),
    ]
)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
