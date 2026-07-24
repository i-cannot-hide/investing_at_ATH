import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative

from engine.journal import EntryType

# Plotly only accepts legend / legend2 / … as legend ids.
SERIES_LEGEND = "legend"
ENTRIES_LEGEND = "legend2"

_MARKER_STYLE = {
    EntryType.ORDER_FILLED.value: {
        "BUY": {
            "name": "buy",
            "symbol": "triangle-up",
            "color": "#00c853",
            "size": 10,
            "line_color": "#000000",
            "line_width": 1,
            "hover": "BUY",
        },
        "SELL": {
            "name": "sell",
            "symbol": "triangle-down",
            "color": "#d62728",
            "size": 10,
            "line_color": "#000000",
            "line_width": 1,
            "hover": "SELL",
        },
    },
    EntryType.ORDER_CANCELLED.value: {
        "name": "cancel",
        "symbol": "x",
        "color": "#7f7f7f",
        "size": 10,
        "hover": "CANCEL",
    },
    EntryType.DEPOSIT.value: {
        "name": "deposit",
        "symbol": "line-nw",
        "color": "#1b5e20",
        "size": 10,
        "line_color": "#1b5e20",
        "line_width": 2,
        "hover": "DEPOSIT",
    },
    EntryType.WITHDRAWAL.value: {
        "name": "withdrawal",
        "symbol": "line-ne",
        "color": "#8b0000",
        "size": 10,
        "line_color": "#8b0000",
        "line_width": 1,
        "hover": "WITHDRAWAL",
    },
}


def flatten_journal(steps: pd.DataFrame) -> pd.DataFrame:
    """Explode step `journal` lists into one row per entry."""
    rows: list[dict] = []
    frame = steps.copy()
    frame["time"] = pd.to_datetime(frame["time"])
    for _, step in frame.iterrows():
        for entry in step.get("journal") or []:
            rows.append({"time": step["time"], **entry})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _entry_type_values(journal: list[EntryType] | None) -> list[str]:
    if not journal:
        return []
    return [
        entry.value if isinstance(entry, EntryType) else str(entry) for entry in journal
    ]


def _marker_y(entry: pd.Series, frame: pd.DataFrame, column: str) -> float | None:
    """Y for a journal marker on the plotted series."""
    if (
        entry.get("type") == EntryType.ORDER_FILLED.value
        and column == "price"
        and entry.get("price") is not None
        and pd.notna(entry.get("price"))
    ):
        return float(entry["price"])

    match = frame.loc[frame["time"] == entry["time"], column]
    if match.empty or pd.isna(match.iloc[0]):
        return None
    return float(match.iloc[0])


def _add_journal_traces(
    fig: go.Figure,
    frame: pd.DataFrame,
    column: str,
    entry_types: list[str],
    *,
    shown_legend: set[str],
):
    journal = flatten_journal(frame)
    if journal.empty:
        return

    journal = journal[journal["type"].isin(entry_types)].copy()
    if journal.empty:
        return

    def add_markers(rows: pd.DataFrame, style: dict, extra_hover: str | None = None):
        if rows.empty:
            return
        ys = [_marker_y(row, frame, column) for _, row in rows.iterrows()]
        name = style["name"]
        show_legend = name not in shown_legend
        if show_legend:
            shown_legend.add(name)
        hover = style["hover"]
        if extra_hover:
            hover_template = f"{hover} %{{customdata}}<extra></extra>"
            customdata = rows[extra_hover]
        else:
            hover_template = f"{hover}<extra></extra>"
            customdata = None
        fig.add_trace(
            go.Scatter(
                x=rows["time"],
                y=ys,
                mode="markers",
                name=name,
                legend=ENTRIES_LEGEND,
                legendgroup=name,
                showlegend=show_legend,
                marker={
                    "symbol": style["symbol"],
                    "size": style["size"],
                    "color": style["color"],
                    "line": {
                        "width": style.get("line_width", 1),
                        "color": style.get("line_color", style["color"]),
                    },
                },
                hovertemplate=hover_template,
                customdata=customdata,
            )
        )

    if EntryType.ORDER_FILLED.value in entry_types:
        fills = journal[journal["type"] == EntryType.ORDER_FILLED.value]
        for side, style in _MARKER_STYLE[EntryType.ORDER_FILLED.value].items():
            side_rows = fills[fills["side"] == side] if not fills.empty else fills
            add_markers(
                side_rows,
                style,
                extra_hover="quantity" if "quantity" in side_rows.columns else None,
            )

    if EntryType.ORDER_CANCELLED.value in entry_types:
        cancels = journal[journal["type"] == EntryType.ORDER_CANCELLED.value]
        add_markers(cancels, _MARKER_STYLE[EntryType.ORDER_CANCELLED.value])

    if EntryType.DEPOSIT.value in entry_types:
        deposits = journal[journal["type"] == EntryType.DEPOSIT.value]
        add_markers(
            deposits,
            _MARKER_STYLE[EntryType.DEPOSIT.value],
            extra_hover="amount" if "amount" in deposits.columns else None,
        )

    if EntryType.WITHDRAWAL.value in entry_types:
        withdrawals = journal[journal["type"] == EntryType.WITHDRAWAL.value]
        add_markers(
            withdrawals,
            _MARKER_STYLE[EntryType.WITHDRAWAL.value],
            extra_hover="amount" if "amount" in withdrawals.columns else None,
        )


def plot_series(
    data,
    column,
    *,
    journal: list[EntryType] | None = None,
    logy=True,
    figsize=(10, 5),
):
    """Plot `column` over time with an interactive Plotly chart.

    `data` may be a single DataFrame or a dict of label -> DataFrame
    to overlay multiple series. Hover a point to see its date and value.

    Pass `journal` as a list of `EntryType` values to overlay matching
    journal entries as markers on each series.
    """
    series = {"_": data} if isinstance(data, pd.DataFrame) else data
    width = int(figsize[0] * 80)
    height = int(figsize[1] * 80)
    colors = qualitative.Plotly
    entry_types = _entry_type_values(journal)

    fig = go.Figure()
    shown_legend: set[str] = set()
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
                legend=SERIES_LEGEND,
                line={"color": color},
                hovertemplate=(
                    f"<b>{name}</b><br>{column}: %{{y:,.2f}}<extra></extra>"
                ),
            )
        )

        if entry_types:
            _add_journal_traces(
                fig,
                frame,
                column,
                entry_types,
                shown_legend=shown_legend,
            )

    series_legend = {"orientation": "h", "yanchor": "top", "y": -0.38, "x": 0}
    layout = {
        "width": width,
        "height": height,
        "hovermode": "x unified",
        "margin": {"l": 60, "r": 20, "t": 30, "b": 100},
        SERIES_LEGEND: series_legend,
        "yaxis_title": f"{column} (log)" if logy else column,
        "xaxis_title": None,
        "plot_bgcolor": "#fafafa",
        "paper_bgcolor": "#ffffff",
    }
    if shown_legend:
        entries_legend = {
            "orientation": "h",
            "yanchor": "top",
            "y": -0.8,
            "x": 0,
        }
        layout["margin"] = {"l": 60, "r": 20, "t": 30, "b": 140}
        layout[ENTRIES_LEGEND] = entries_legend
    fig.update_layout(**layout)
    fig.update_yaxes(type="log" if logy else "linear", tickformat=",.0f")
    fig.update_xaxes(tickformat="%Y-%m-%d", tickangle=-45)
    fig.show()
