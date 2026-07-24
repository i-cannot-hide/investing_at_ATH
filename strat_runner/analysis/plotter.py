from decimal import Decimal, ROUND_HALF_UP
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative
from enum import Enum

from engine.journal import EntryType

# Plotly only accepts legend / legend2 / … as legend ids.
SERIES_LEGEND = "legend"
ENTRIES_LEGEND = "legend2"

_USD_SERIES_COLUMNS = {
    "equity",
    "available_usd",
    "frozen_usd",
    "total_usd",
}


class Scale(Enum):
    LOG = "log"
    LINEAR = "linear"

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
    EntryType.INTEREST.value: {
        "name": "interest",
        "symbol": "line-nw",
        "color": "#2e7d32",
        "size": 6,
        "line_color": "#2e7d32",
        "line_width": 2,
        "hover": "INTEREST",
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

_AGGREGATE_STYLE = {
    "name": "events",
    "symbol": "circle",
    "color": "#455a64",
    "size": 12,
    "line_color": "#000000",
    "line_width": 1,
    "hover": "EVENTS",
    "text_only": True,
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
        and column in {"price", "high", "low", "open", "close", "level"}
        and entry.get("price") is not None
        and pd.notna(entry.get("price"))
    ):
        return float(entry["price"])

    match = frame.loc[frame["time"] == entry["time"], column]
    if match.empty or pd.isna(match.iloc[0]):
        return None
    return float(match.iloc[0])


def _style_for_entry(entry: pd.Series) -> dict:
    entry_type = entry.get("type")
    style = _MARKER_STYLE.get(entry_type)
    if style is None:
        return _AGGREGATE_STYLE
    if entry_type == EntryType.ORDER_FILLED.value:
        return style.get(entry.get("side"), _AGGREGATE_STYLE)
    return style


def _format_number(value, *, max_decimals: int) -> str:
    """Format a number with at most ``max_decimals`` places (trim trailing zeros)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    quantized = Decimal(str(value)).quantize(
        Decimal("1").scaleb(-max_decimals),
        rounding=ROUND_HALF_UP,
    )
    text = f"{quantized:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _format_asset_amount(value, *, asset: str | None) -> str:
    """USD → 2 dp max; everything else (coins, prices) → 4 dp max."""
    max_decimals = 2 if (asset or "").upper() == "USD" else 4
    return _format_number(value, max_decimals=max_decimals)


def _series_y_hover_format(column: str) -> str:
    if column in _USD_SERIES_COLUMNS or column.endswith("_usd"):
        return ",.2f"
    return ",.4f"


def _hover_line(entry: pd.Series) -> str:
    entry_type = entry.get("type")
    if entry_type == EntryType.ORDER_FILLED.value:
        side = entry.get("side") or "?"
        qty = entry.get("quantity")
        price = entry.get("price")
        ticker = entry.get("ticker") or ""
        parts = [str(side)]
        if ticker:
            parts.append(str(ticker))
        if qty is not None and pd.notna(qty):
            parts.append(_format_asset_amount(qty, asset=ticker))
        if price is not None and pd.notna(price):
            # Fill prices are quote currency levels; keep 4 dp like other non-USD.
            parts.append(f"@ {_format_number(price, max_decimals=4)}")
        return " ".join(parts)
    if entry_type == EntryType.ORDER_CANCELLED.value:
        return f"CANCEL {entry.get('order_id') or ''}".strip()
    if entry_type == EntryType.DEPOSIT.value:
        currency = entry.get("currency") or ""
        amount = _format_asset_amount(entry.get("amount"), asset=currency)
        return f"DEPOSIT {amount} {currency}".strip()
    if entry_type == EntryType.INTEREST.value:
        ticker = entry.get("ticker") or ""
        amount = _format_asset_amount(entry.get("amount"), asset=ticker)
        return f"INTEREST {amount} {ticker}".strip()
    if entry_type == EntryType.WITHDRAWAL.value:
        currency = entry.get("currency") or ""
        amount = _format_asset_amount(entry.get("amount"), asset=currency)
        return f"WITHDRAWAL {amount} {currency}".strip()
    return str(entry_type or "event")


def _series_y_at(frame: pd.DataFrame, time, column: str) -> float | None:
    match = frame.loc[frame["time"] == time, column]
    if match.empty or pd.isna(match.iloc[0]):
        return None
    return float(match.iloc[0])


def aggregate_journal_markers(
    journal: pd.DataFrame,
    frame: pd.DataFrame,
    column: str,
) -> list[dict]:
    """Collapse same-day journal entries into one marker each.

    Single-entry days keep that entry's style and y. Multi-entry days use the
    aggregate style, series y, a count label, and a combined hover list.
    """
    if journal.empty:
        return []

    markers: list[dict] = []
    ordered = journal.sort_values("time", kind="mergesort")
    for time, group in ordered.groupby("time", sort=True):
        rows = [row for _, row in group.iterrows()]
        if len(rows) == 1:
            entry = rows[0]
            y = _marker_y(entry, frame, column)
            if y is None:
                continue
            style = _style_for_entry(entry)
            markers.append(
                {
                    "time": time,
                    "y": y,
                    "style": style,
                    "text": "",
                    "hover": _hover_line(entry),
                    "count": 1,
                }
            )
            continue

        y = _series_y_at(frame, time, column)
        if y is None:
            # Fall back to first entry that has a y.
            for entry in rows:
                y = _marker_y(entry, frame, column)
                if y is not None:
                    break
        if y is None:
            continue

        count = len(rows)
        lines = [f"{count} entries", *(_hover_line(entry) for entry in rows)]
        markers.append(
            {
                "time": time,
                "y": y,
                "style": _AGGREGATE_STYLE,
                "text": str(count),
                "hover": "<br>".join(lines),
                "count": count,
            }
        )
    return markers


def series_journal_customdata(
    times,
    markers: list[dict],
) -> list[str]:
    """Per-timestamp hover suffix for the series line (empty if no entries)."""
    by_time = {pd.Timestamp(marker["time"]): marker["hover"] for marker in markers}
    customdata: list[str] = []
    for time in times:
        hover = by_time.get(pd.Timestamp(time))
        customdata.append(f"<br>{hover}" if hover else "")
    return customdata


def _add_journal_traces(
    fig: go.Figure,
    markers: list[dict],
    *,
    shown_legend: set[str],
):
    """Draw journal markers only — hover details live on the series line."""
    if not markers:
        return

    by_name: dict[str, list[dict]] = {}
    for marker in markers:
        by_name.setdefault(marker["style"]["name"], []).append(marker)

    for name, group in by_name.items():
        style = group[0]["style"]
        show_legend = name not in shown_legend
        if show_legend:
            shown_legend.add(name)
        texts = [marker["text"] for marker in group]
        text_only = style.get("text_only", False)
        if text_only:
            mode = "text"
            textposition = "middle center"
        elif any(texts):
            mode = "markers+text"
            textposition = "top center"
        else:
            mode = "markers"
            textposition = "top center"
        fig.add_trace(
            go.Scatter(
                x=[marker["time"] for marker in group],
                y=[marker["y"] for marker in group],
                mode=mode,
                name=name,
                legend=ENTRIES_LEGEND,
                legendgroup=name,
                showlegend=show_legend,
                text=texts if text_only or any(texts) else None,
                textposition=textposition,
                textfont={"size": 12, "color": style["color"]},
                marker={
                    "symbol": style["symbol"],
                    "size": [
                        min(style["size"] + 2 * (marker["count"] - 1), 18)
                        for marker in group
                    ],
                    "color": style["color"],
                    "line": {
                        "width": style.get("line_width", 1),
                        "color": style.get("line_color", style["color"]),
                    },
                },
                # Keep markers out of x-unified hover (it otherwise sticks to
                # the nearest event day). Details are on the series hover.
                hoverinfo="skip",
            )
        )


def plot_series(
    data,
    column,
    *,
    journal: list[EntryType] | None = None,
    scale: Scale = Scale.LOG,
    figsize=(10, 5),
):
    """Plot `column` over time with an interactive Plotly chart.

    `data` may be a single DataFrame or a dict of label -> DataFrame
    to overlay multiple series. Hover a point to see its date and value.

    Pass `journal` as a list of `EntryType` values to overlay matching
    journal entries as markers on each series. Same-day entries are
    collapsed into one marker; hover on that date lists every entry.

    `scale` is ``Scale.LOG`` (default) or ``Scale.LINEAR``.
    """
    if not isinstance(scale, Scale):
        raise TypeError(f"scale must be Scale, got {type(scale)!r}")

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

        markers: list[dict] = []
        if entry_types:
            entries = flatten_journal(frame)
            if not entries.empty:
                entries = entries[entries["type"].isin(entry_types)]
                if not entries.empty:
                    markers = aggregate_journal_markers(entries, frame, column)

        fig.add_trace(
            go.Scatter(
                x=frame["time"],
                y=frame[column],
                mode="lines",
                name=name,
                legend=SERIES_LEGEND,
                line={"color": color},
                customdata=series_journal_customdata(frame["time"], markers),
                hovertemplate=(
                    f"<b>{name}</b><br>{column}: "
                    f"%{{y:{_series_y_hover_format(column)}}}%{{customdata}}"
                    f"<extra></extra>"
                ),
            )
        )

        if markers:
            _add_journal_traces(fig, markers, shown_legend=shown_legend)

    series_legend = {"orientation": "h", "yanchor": "top", "y": -0.38, "x": 0}
    layout = {
        "width": width,
        "height": height,
        "hovermode": "x unified",
        "margin": {"l": 60, "r": 20, "t": 30, "b": 100},
        SERIES_LEGEND: series_legend,
        "yaxis_title": f"{column} (log)" if scale is Scale.LOG else column,
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
    fig.update_yaxes(type=scale.value, tickformat=",.0f")
    fig.update_xaxes(tickformat="%Y-%m-%d", tickangle=-45)
    fig.show()
