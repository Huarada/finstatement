from __future__ import annotations
import re
from functools import lru_cache

_ANNUAL_PAT = re.compile(r"12\s*[mM]\s*\d*|anual|exerc[íi]cio|12\s*meses|acumulado|\b12m\b", re.IGNORECASE)
_YEAR_SUFFIX_PAT = re.compile(r"^\s*(?:dez\s*\/?\s*)?(20\d{2})\s*(?:[\s\-–—].*)?$", re.IGNORECASE)
_QUARTER_PAT = re.compile(r"[1-4]\s*[tTqQ]\s*\d{2,4}|[qQ][1-4]\s*\d{2,4}|tri?m?e?s?t?r?e?|quarter", re.IGNORECASE)
_MMM_YY_PAT = re.compile(r"^(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\/(\d{2})$", re.IGNORECASE)
_FULL_DATE_PAT = re.compile(r"^(\d{1,2})[\/\-](\d{1,2})[\/\-](20\d{2})$")
_DELTA_PAT = re.compile(r"^[\s]*(?:var\.?\s*%?|%\s*$|delta|bps|p\.p\.|a\.a\.|\+\/-|[Δ\u0394]\s*(?:a\/a|t\/t|acm)|[Δ\u0394]%)", re.IGNORECASE)
_MONTH_RANK = {"jan":1,"fev":2,"mar":3,"abr":4,"mai":5,"jun":6,"jul":7,"ago":8,"set":9,"out":10,"nov":11,"dez":12}

def _year_of(text):
    m = re.search(r"\b(20\d{2})\b", text)
    return int(m.group(1)) if m else 0

def _score_header(header: str) -> float:
    h = header.strip()
    if not h: return -1.0
    if _DELTA_PAT.match(h): return -999.0
    if _ANNUAL_PAT.search(h):
        yr = _year_of(h)
        return 10.0 + (yr - 2000) * 0.01 if yr else 10.0
    if _YEAR_SUFFIX_PAT.match(h):
        yr = _year_of(h)
        return 9.0 + (yr - 2000) * 0.01 if yr else 9.0
    fd = _FULL_DATE_PAT.match(h)
    if fd:
        day, month, year = int(fd.group(1)), int(fd.group(2)), int(fd.group(3))
        return 7.0 + (year - 2000) * 0.1 + month * 0.01
    mm = _MMM_YY_PAT.match(h)
    if mm:
        yr2 = int(mm.group(2)); mo = _MONTH_RANK.get(mm.group(1).lower(), 0)
        return 6.0 + yr2 * 0.1 + mo * 0.01
    if _QUARTER_PAT.search(h): return 1.0
    return 5.0

@lru_cache(maxsize=512)
def best_column_index(columns: tuple) -> int:
    best_score = -1.0; best_idx = 1
    for i, col in enumerate(columns[1:], start=1):
        score = _score_header(str(col))
        if score < 0: continue
        if score > best_score:
            best_score = score; best_idx = i
    return best_idx
