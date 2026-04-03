from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class PeriodType(str, Enum):
    ANNUAL = "annual"; SEMIANNUAL = "semiannual"; QUARTERLY = "quarterly"

class SectorType(str, Enum):
    BANK = "bank"; INDUSTRIAL = "industrial"

class MetricStatus(str, Enum):
    GREEN = "green"; YELLOW = "yellow"; RED = "red"; UNAVAILABLE = "unavailable"

@dataclass(frozen=True)
class DocumentMeta:
    company: str; period: str; currency: str; doc_type: str
    period_type: PeriodType; annualization_factor: int

@dataclass(frozen=True)
class TableRow:
    label: str; values: tuple

@dataclass(frozen=True)
class FinancialTable:
    id: str; title: str; columns: tuple; rows: tuple; page: int
    confidence: float; from_destaques: bool = False; cols_expanded: bool = False

@dataclass(frozen=True)
class IncomeStatement:
    revenue: Optional[float]; gross_profit: Optional[float]; net_income: Optional[float]
    operating_income: Optional[float]; selling_expenses: Optional[float]
    ga_expenses: Optional[float]; da_expenses: Optional[float]
    interest_expenses: Optional[float]; operating_cash_flow: Optional[float]; capex: Optional[float]

@dataclass(frozen=True)
class BalanceSheet:
    total_assets: Optional[float]; current_assets: Optional[float]
    current_liabilities: Optional[float]; equity: Optional[float]; gross_debt: Optional[float]
    retained_earnings: Optional[float]; treasury_shares: Optional[float]

@dataclass(frozen=True)
class BankMetrics:
    mfb: Optional[float]; credit_cost: Optional[float]; admin_expenses: Optional[float]
    service_revenue: Optional[float]; roe: Optional[float]; roa: Optional[float]
    efficiency_ratio: Optional[float]; npl_ratio: Optional[float]; basel_ratio: Optional[float]
    has_buyback: bool

@dataclass(frozen=True)
class BuffettMetric:
    name: str; value: Optional[float]; formatted_value: str; benchmark: str
    explanation: str; formula: str; status: MetricStatus; points: int; max_points: int

@dataclass
class BuffettScore:
    total_points: int; max_points: int; score_100: int; label: str; sector: SectorType
    metrics: list = field(default_factory=list)

@dataclass
class AnalysisResult:
    meta: DocumentMeta; tables: list; income: IncomeStatement; balance: BalanceSheet
    bank_metrics: Optional[BankMetrics]; buffett: BuffettScore; sector: SectorType; debug_info: dict
