"""
Modules/export_xlsx.py

The dashboard as an Excel workbook, for people who want to keep working on the
numbers (or load them into Power BI / another BI tool). No model call.

    dashboard_to_xlsx(dash, title="Dashboard", *, insight=None, dataset=None,
                      filters=None, include_sql=True, generated_at=None) -> bytes

Workbook layout:
  Overview   title, dataset, date, filters, the key reading, every KPI value
  1 ... n    one sheet per chart/table panel: the data as a formatted Excel table
             (header, number formats, filters, frozen header) and, for bar / line
             / pie panels, a NATIVE Excel chart built on that data, so it stays
             editable in Excel
  SQL        the question and the validated SQL behind every panel
"""
import datetime as _dt
import io
import re

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from Modules.export_html import _kpi_text, _sorted, describe_filters
from Modules.visualisation import _looks_continuous, _readable_labels, build_visual_metadata

ACCENT = "E2231A"
INK = "1B1F2A"
MUTED = "6B7280"
HEADER_FILL = PatternFill("solid", fgColor="33415C")
MAX_ROWS = 100_000
MAX_CHART_POINTS = 25


def _sheet_name(n, title, used):
    """Excel sheet names: max 31 chars, no []:*?/\\ and unique."""
    base = re.sub(r"[\[\]:*?/\\]", " ", f"{n} {title}").strip()[:31] or f"Panel {n}"
    name, k = base, 2
    while name.lower() in used:
        suffix = f" ({k})"
        name = base[:31 - len(suffix)] + suffix
        k += 1
    used.add(name.lower())
    return name


def _is_id(column):
    name = str(column).lower()
    return name == "id" or name.endswith("_id") or name in ("year", "unit_number")


def _excel_value(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.to_pydatetime()
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return value.item()                     # numpy scalar -> python
        except Exception:
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _write_table(ws, df, start_row=1, table_name="T1"):
    """Write df as a styled Excel table. Returns (first_row, last_row)."""
    columns = [str(c) for c in df.columns]
    for j, c in enumerate(columns, 1):
        cell = ws.cell(row=start_row, column=j, value=c.replace("_", " ").title())
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")
    for i, record in enumerate(df.itertuples(index=False), start_row + 1):
        for j, value in enumerate(record, 1):
            ws.cell(row=i, column=j, value=_excel_value(value))
    last = start_row + len(df)

    for j, c in enumerate(df.columns, 1):
        letter = get_column_letter(j)
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            fmt = "yyyy-mm-dd"
        elif pd.api.types.is_integer_dtype(df[c]) and not _is_id(c):
            fmt = "#,##0"
        elif pd.api.types.is_numeric_dtype(df[c]) and not _is_id(c):
            fmt = "#,##0.00"
        else:
            fmt = None
        if fmt:
            for row in range(start_row + 1, last + 1):
                ws[f"{letter}{row}"].number_format = fmt
        sample = [len(str(columns[j - 1]))] + [len(str(v)) for v in df[c].head(200).tolist()]
        ws.column_dimensions[letter].width = min(max(sample) + 3, 45)

    if len(df) >= 1:
        ref = f"A{start_row}:{get_column_letter(len(columns))}{last}"
        table = Table(displayName=table_name, ref=ref)
        table.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
        ws.add_table(table)
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    return start_row, last


def _add_chart(ws, df, item, first, last):
    """A native Excel chart on the sheet's own data (bar, line or pie)."""
    kind = item.get("kind")
    style = item.get("style")
    if kind not in ("bar", "line", "pie") or style in ("scatter", "histogram", "treemap"):
        return None
    meta = build_visual_metadata(df, kind, item.get("question", ""), title=item.get("title"))
    x, y = meta.get("x"), meta.get("y")
    if meta.get("chart") not in ("bar", "line", "pie") or x not in df.columns or y not in df.columns:
        return None
    if kind == "bar" and _looks_continuous(df, x, item.get("title", "")):
        return None          # a distribution: Excel has no binned chart from raw rows
    cols = list(df.columns)
    x_col, y_col = cols.index(x) + 1, cols.index(y) + 1
    n = min(last - first, MAX_CHART_POINTS)
    if n < 1:
        return None

    if kind == "pie":
        chart = PieChart()
    elif kind == "line":
        chart = LineChart()
        chart.y_axis.title = str(y).replace("_", " ").title()
        chart.x_axis.title = str(x).replace("_", " ").title()
    else:
        chart = BarChart()
        chart.type = "bar" if (style == "horizontal" or n >= 15) else "col"
        chart.y_axis.title = str(y).replace("_", " ").title()
        chart.x_axis.title = str(x).replace("_", " ").title()
        chart.legend = None
    if kind != "pie":
        # openpyxl 3.1 writes axes as hidden by default; Excel then shows none
        chart.x_axis.delete = False
        chart.y_axis.delete = False
        if kind == "bar" and chart.type == "bar":
            chart.x_axis.scaling.orientation = "maxMin"   # biggest bar on top, like the app
    chart.title = item.get("title", "")
    data = Reference(ws, min_col=y_col, min_row=first, max_row=first + n)
    labels = Reference(ws, min_col=x_col, min_row=first + 1, max_row=first + n)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(labels)
    chart.height, chart.width = 9, 16
    anchor = f"{get_column_letter(len(cols) + 2)}{first}"
    ws.add_chart(chart, anchor)
    return chart


def _panel_frame(df, item):
    """The data as written to the sheet: user sort applied, and for bar/pie a
    unique 'Label' column first when the plotted category repeats (routes)."""
    df = _sorted(df.copy(), item)
    kind = item.get("kind")
    if kind in ("bar", "pie"):
        meta = build_visual_metadata(df, kind, item.get("question", ""), title=item.get("title"))
        x, y = meta.get("x"), meta.get("y")
        if x in df.columns and y in df.columns and df[x].astype(str).duplicated().any():
            df.insert(0, "label", _readable_labels(df, x, y).values)
        if not item.get("sort") and y in df.columns:
            ascending = meta.get("sort_order") == "ascending"
            df = df.sort_values(y, ascending=ascending, na_position="last")
    return df.reset_index(drop=True)


def dashboard_to_xlsx(dash, title="Dashboard", *, insight=None, dataset=None, filters=None,
                      include_sql=True, generated_at=None):
    results = dash.get("results", [])
    wb = Workbook()
    ov = wb.active
    ov.title = "Overview"
    used = {"overview", "sql"}

    when = generated_at or _dt.datetime.now()
    ov["A1"] = "DEVOBOARD REPORT"
    ov["A1"].font = Font(bold=True, color=ACCENT, size=9)
    ov["A2"] = title
    ov["A2"].font = Font(bold=True, size=18, color=INK)
    info = [("Dataset", dataset or ""), ("Generated", when.strftime("%d %B %Y, %H:%M")),
            ("Filters", describe_filters(filters)), ("Request", dash.get("question") or "")]
    row = 4
    for key, value in info:
        if not value:
            continue
        ov.cell(row=row, column=1, value=key).font = Font(bold=True, color=MUTED)
        ov.cell(row=row, column=2, value=value)
        row += 1
    if insight:
        row += 1
        ov.cell(row=row, column=1, value="Key reading").font = Font(bold=True, color=MUTED)
        cell = ov.cell(row=row, column=2, value=insight)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        row += 1

    kpis = [r for r in results if (r.get("item") or {}).get("kind") == "kpi"]
    if kpis:
        row += 1
        ov.cell(row=row, column=1, value="KPI").font = Font(bold=True, color="FFFFFF")
        ov.cell(row=row, column=2, value="Value").font = Font(bold=True, color="FFFFFF")
        ov.cell(row=row, column=3, value="Detail").font = Font(bold=True, color="FFFFFF")
        for c in range(1, 4):
            ov.cell(row=row, column=c).fill = HEADER_FILL
        for k in kpis:
            row += 1
            item, df = k.get("item") or {}, k.get("df")
            if df is None or getattr(df, "empty", True) or k.get("error"):
                value, sub = "n/a", k.get("error") or "No data."
            else:
                meta = build_visual_metadata(df, "card", item.get("question", ""), title=item.get("title"))
                value, sub = _kpi_text(df, meta)
                raw = df[meta["y"]].iloc[0] if meta.get("y") in df.columns else None
                if sub is None and raw is not None and not pd.isna(raw):
                    value = _excel_value(raw)          # a real number, formatted below
            ov.cell(row=row, column=1, value=item.get("title", ""))
            cell = ov.cell(row=row, column=2, value=value)
            if isinstance(value, (int, float)):
                cell.number_format = "#,##0" if float(value).is_integer() else "#,##0.00"
            ov.cell(row=row, column=3, value=sub)

    row += 2
    ov.cell(row=row, column=1, value="Sheets").font = Font(bold=True, color=MUTED)
    contents_row = row
    ov.column_dimensions["A"].width = 30
    ov.column_dimensions["B"].width = 70
    ov.column_dimensions["C"].width = 30

    n = 0
    for panel in results:
        item = panel.get("item") or {}
        if item.get("kind") == "kpi":
            continue
        n += 1
        name = _sheet_name(n, item.get("title", ""), used)
        ws = wb.create_sheet(name)
        ws["A1"] = item.get("title", "")
        ws["A1"].font = Font(bold=True, size=14, color=INK)
        ws["A2"] = item.get("question", "")
        ws["A2"].font = Font(italic=True, color=MUTED)
        df = panel.get("df")
        if df is None or getattr(df, "empty", True) or panel.get("error"):
            ws["A4"] = panel.get("error") or "No data."
        else:
            frame = _panel_frame(df, item).head(MAX_ROWS)
            first, last = _write_table(ws, frame, start_row=4, table_name=f"Panel{n}")
            try:
                _add_chart(ws, frame, item, first, last)
            except Exception:
                pass                                   # the data is still there
        contents_row += 1
        link = ov.cell(row=contents_row, column=2, value=name)
        link.hyperlink = f"#'{name}'!A1"
        link.font = Font(color="1F5FBF", underline="single")

    if include_sql:
        sq = wb.create_sheet("SQL")
        headers = ["Panel", "Question", "Status", "SQL"]
        for j, h in enumerate(headers, 1):
            cell = sq.cell(row=1, column=j, value=h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = HEADER_FILL
        r = 1
        for panel in results:
            if not panel.get("sql"):
                continue
            r += 1
            item = panel.get("item") or {}
            sq.cell(row=r, column=1, value=item.get("title", ""))
            sq.cell(row=r, column=2, value=item.get("question", ""))
            sq.cell(row=r, column=3, value="failed" if panel.get("error") else "validated")
            cell = sq.cell(row=r, column=4, value=panel["sql"])
            for c in range(1, 5):
                sq.cell(row=r, column=c).alignment = Alignment(wrap_text=True, vertical="top")
        for letter, width in zip("ABCD", (30, 45, 12, 90)):
            sq.column_dimensions[letter].width = width
        sq.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
