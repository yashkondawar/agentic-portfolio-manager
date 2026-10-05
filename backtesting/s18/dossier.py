"""In-memory Excel dossier; generated evidence is stored in SQLite."""

from io import BytesIO

import pandas as pd
from openpyxl.styles import Font, PatternFill

from .book import TRADE_COLUMNS


def build_workbook(
    *, config, metrics, curve, trades, holdings, books, validation, warnings
):
    equity = pd.DataFrame(curve)
    indexed = equity.set_index(pd.to_datetime(equity["date"]))
    daily = indexed[["nav", "benchmark"]].pct_change(fill_method=None).iloc[1:]
    daily.index.name = "date"
    years = indexed.groupby(indexed.index.year)[["nav", "benchmark"]].last()
    previous = years.shift(1)
    previous.iloc[0] = indexed[["nav", "benchmark"]].iloc[0]
    yearly = (years / previous - 1).reset_index(names="year")
    rolling = {}
    for count in (3, 5):
        rows = []
        for end_date, values in indexed.iterrows():
            cutoff = end_date - pd.DateOffset(years=count)
            pos = indexed.index.searchsorted(cutoff, side="right") - 1
            if pos < 0:
                continue
            initial = indexed.iloc[pos]
            years_between = (end_date - indexed.index[pos]).days / 365.25
            rows.append(
                {
                    "start": str(indexed.index[pos].date()),
                    "end": str(end_date.date()),
                    "portfolio_cagr": (values["nav"] / initial["nav"])
                    ** (1 / years_between)
                    - 1,
                    "benchmark_cagr": (values["benchmark"] / initial["benchmark"])
                    ** (1 / years_between)
                    - 1,
                }
            )
        rolling[count] = pd.DataFrame(rows)
    summary = [
        {"setting": "combo", "value": config.combo},
        {"setting": "metal_mode", "value": config.metal_mode},
        {"setting": "golden_replay", "value": validation.get("status", "not run")},
        *[{"setting": k, "value": v} for k, v in metrics.items()],
        *[{"setting": "disclosure", "value": w} for w in warnings],
    ]
    sheets = {
        "Summary": pd.DataFrame(summary),
        "Equity_Curve": equity,
        "Positions": pd.DataFrame(holdings),
        "Trades": pd.DataFrame(trades, columns=TRADE_COLUMNS),
        "Yearly_Returns": yearly,
        "Rolling_3Y": rolling[3],
        "Rolling_5Y": rolling[5],
        "Daily_Returns_Portfolio": daily.reset_index(),
        "Tax_Ledger": pd.DataFrame([r for b in books for r in b.tax_ledger]),
        "Fills_and_Shadow_Costs": pd.DataFrame([r for b in books for r in b.fills]),
        "Replay_Validation": pd.DataFrame(validation.get("results", [])),
    }
    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
            sheet = writer.sheets[name]
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cell in sheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="17365D")
            for column in sheet.columns:
                width = max(len(str(c.value or "")) for c in list(column)[:100])
                sheet.column_dimensions[column[0].column_letter].width = min(
                    55, max(12, width + 2)
                )
            # Imported symbols are data, never workbook formulas.
            for row in sheet:
                for cell in row:
                    if cell.data_type == "f":
                        cell.data_type = "s"
    return stream.getvalue()
