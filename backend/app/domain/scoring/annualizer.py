from __future__ import annotations
import re
from app.domain.entities import PeriodType

_QUARTERLY_PT = re.compile(
    r"\b[1-4][Tt][Qq]?\.?\s*(?:de\s*)?(?:19|20)?\d{2}\b"
    r"|\b(?:primeiro|segundo|terceiro|quarto)\s+trimestre\b"
    r"|\bper[ií]odo\s+de\s+tr[eê]s\s+meses\b"
    r"|\bthree\s+months?\s+ended\b"
    r"|\binterim\s+(?:financial|period)\b"
    r"|demonstra\w+\s+financeiras?\s+intermedi[aá]rias?",
    re.VERBOSE | re.IGNORECASE,
)
_SEMIANNUAL_PT = re.compile(
    r"\b[12][Ss]\d{2,4}\b|\b(?:primeiro|segundo)\s+semestre\b"
    r"|\bseis\s+meses\b|\bper[ií]odo\s+de\s+seis\s+meses\b|\bsix\s+months?\s+ended\b",
    re.VERBOSE | re.IGNORECASE,
)

def detect_period_type(text: str) -> PeriodType:
    if _QUARTERLY_PT.search(text): return PeriodType.QUARTERLY
    if _SEMIANNUAL_PT.search(text): return PeriodType.SEMIANNUAL
    return PeriodType.ANNUAL

def annualization_factor(period_type: PeriodType) -> int:
    return {PeriodType.ANNUAL: 1, PeriodType.SEMIANNUAL: 2, PeriodType.QUARTERLY: 4}[period_type]
