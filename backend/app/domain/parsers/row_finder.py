from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional
from app.domain.entities import FinancialTable, TableRow
from app.domain.parsers.column_resolver import best_column_index

_NEGATIVE_PAT = re.compile(r"^\s*[\(\-]|[\)\-]\s*$")


def _parse_cell(raw: str) -> Optional[float]:
    """
    Convert a raw cell string to float, handling Brazilian number formats.

    Priority:
      1. "1.234,56"  → 1234.56   (BR: dot=thousands, comma=decimal)
      2. "1,234.56"  → 1234.56   (EN: comma=thousands, dot=decimal)
      3. "204,6"     → 204.6     (BR decimal without thousands dot — FIX v2.1)
      4. plain int / dot-decimal → strip separators
      5. parentheses → negative
    """
    if not raw or raw.strip() in ("-", "—", "", "–"):
        return None

    is_negative = bool(_NEGATIVE_PAT.search(raw))
    clean = raw.replace("(", "").replace(")", "").replace("%", "").strip()

    if re.search(r",\d{1,2}$", clean) and "." in clean:
        # "1.234,56" → 1234.56
        clean = clean.replace(".", "").replace(",", ".")
    elif re.search(r"\.\d{1,2}$", clean) and "," in clean:
        # "1,234.56" → 1234.56
        clean = clean.replace(",", "")
    elif re.search(r",\d{1,2}$", clean) and "." not in clean:
        # "204,6" → 204.6  (BR comma-decimal without thousands dot)
        clean = clean.replace(",", ".")
    else:
        # Plain integer or dot-only: strip separators
        clean = clean.replace(".", "").replace(",", "")

    try:
        value = float(clean)
    except ValueError:
        return None

    return -abs(value) if is_negative else value


def extract_value(row: TableRow, table: FinancialTable) -> Optional[float]:
    col_idx = best_column_index(table.columns)
    value_idx = col_idx - 1
    if value_idx < 0 or value_idx >= len(row.values):
        return None
    return _parse_cell(row.values[value_idx])


@dataclass(frozen=True)
class RowMatch:
    row: TableRow
    table: FinancialTable
    value: Optional[float]
    found_in: str


def find_row(patterns, *tables, label="") -> Optional[RowMatch]:
    from app.domain.parsers.column_resolver import _score_header
    candidates = []
    for arg_pos, table in enumerate(tables):
        if table is None:
            continue
        for pattern in patterns:
            matched_row = next((row for row in table.rows if pattern.search(row.label)), None)
            if matched_row is None:
                continue
            col_idx = best_column_index(table.columns)
            col_header = str(table.columns[col_idx]) if col_idx < len(table.columns) else ""
            score = _score_header(col_header)
            if table.from_destaques:
                score += 10_000
            candidates.append((
                score, -arg_pos,
                RowMatch(row=matched_row, table=table,
                         value=extract_value(matched_row, table),
                         found_in=table.title)
            ))
            break
    if not candidates:
        return None
    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return candidates[0][2]
