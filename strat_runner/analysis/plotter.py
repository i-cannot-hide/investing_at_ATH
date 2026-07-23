import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative


def plot_series(data, column, *, logy=True, figsize=(10, 5)):
    """Plot `column` over time with an interactive Plotly chart.

    `data` may be a single DataFrame or a dict of label -> DataFrame
    to overlay multiple series. Hover a point to see its date and value.
    """
    series = {"_": data} if isinstance(data, pd.DataFrame) else data
    width = int(figsize[0] * 80)
    height = int(figsize[1] * 80)
    colors = qualitative.Plotly

    fig = go.Figure()
    for index, (label, df) in enumerate(series.items()):
        frame = df.copy()
        frame["time"] = pd.to_datetime(frame["time"])
        frame[column] = frame[column].astype(float)
        name = column if label == "_" else label
        color = colors[index % len(colors)]

        fig.add_trace(
            go.Scatter(
                x=frame["time"],
                y=frame[column],
                mode="lines",
                name=name,
                line={"color": color},
                hovertemplate=(
                    f"<b>{name}</b><br>"
                    "%{x|%Y-%m-%d}<br>"
                    f"{column}: %{{y:,.2f}}"
                    "<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        width=width,
        height=height,
        hovermode="x unified",
        margin={"l": 60, "r": 20, "t": 30, "b": 60},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        yaxis_title=f"{column} (log)" if logy else column,
        xaxis_title=None,
    )
    fig.update_yaxes(type="log" if logy else "linear", tickformat=",.0f")
    fig.update_xaxes(tickformat="%Y-%m-%d", tickangle=-45)
    fig.show()
