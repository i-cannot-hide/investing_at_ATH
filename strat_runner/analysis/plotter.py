import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.dates import MonthLocator, DateFormatter
from matplotlib.ticker import FuncFormatter


def plot_series(data, column, *, logy=True, figsize=(10, 5)):
    """Plot `column` over time.

    `data` may be a single DataFrame or a dict of label -> DataFrame
    to overlay multiple series.
    """
    series = {"_": data} if isinstance(data, pd.DataFrame) else data

    fig, ax = plt.subplots(figsize=figsize)
    for label, df in series.items():
        frame = df.copy()
        frame["time"] = pd.to_datetime(frame["time"])
        frame[column] = frame[column].astype(float)
        ax.plot(
            frame["time"],
            frame[column],
            label=None if label == "_" else label,
        )

    if logy:
        ax.set_yscale("log")
    ax.set_ylabel(f"{column} (log)" if logy else column)

    def format_number(y, _):
        if y <= 0:
            return ""
        return f"{y:,.0f}"

    ax.yaxis.set_major_formatter(FuncFormatter(format_number))
    ax.yaxis.set_minor_formatter(FuncFormatter(format_number))
    ax.xaxis.set_major_locator(MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(DateFormatter("%Y-%m-%d"))
    if len(series) > 1:
        ax.legend()
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.show()
