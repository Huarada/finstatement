"""
Unit tests for the Buffett Score engine.

Tests the scoring logic for both industrial and bank branches
using synthetic FinancialEntity objects — no PDF needed.
"""
import sys
import os
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from app.domain.entities import (
    BalanceSheet,
    BankMetrics,
    IncomeStatement,
    MetricStatus,
)
from app.domain.scoring.buffett import score_bank, score_industrial


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _strong_industrial() -> tuple[IncomeStatement, BalanceSheet]:
    """A company with clearly excellent fundamentals (Buffett favourite)."""
    income = IncomeStatement(
        revenue=100_000,
        gross_profit=50_000,      # 50% gross margin ✅
        net_income=25_000,        # 25% net margin ✅
        operating_income=30_000,
        selling_expenses=5_000,
        ga_expenses=10_000,       # 10/50 = 20% SGA/GB ✅
        da_expenses=3_000,        # 3/50 = 6% ✅
        interest_expenses=2_000,  # 2/30 = 6.7% ✅
        operating_cash_flow=30_000,
        capex=4_000,              # 4/25 = 16% ✅
    )
    balance = BalanceSheet(
        total_assets=150_000,
        current_assets=40_000,
        current_liabilities=20_000,
        equity=80_000,            # ROE = 25/80 = 31.25% ✅
        gross_debt=30_000,        # 30/25 = 1.2 years ✅
        retained_earnings=50_000, # positive ✅
        treasury_shares=-5_000,   # negative = buyback ✅
    )
    return income, balance


def _weak_industrial() -> tuple[IncomeStatement, BalanceSheet]:
    """A commodity business with poor metrics."""
    income = IncomeStatement(
        revenue=100_000,
        gross_profit=10_000,      # 10% ❌
        net_income=2_000,         # 2% ❌
        operating_income=4_000,
        selling_expenses=20_000,
        ga_expenses=8_000,        # 8/10 = 80% ❌
        da_expenses=5_000,        # 50% of gross ❌
        interest_expenses=3_000,  # 75% of EBIT ❌
        operating_cash_flow=1_000,
        capex=2_000,              # 100% of LL ❌
    )
    balance = BalanceSheet(
        total_assets=200_000,
        current_assets=30_000,
        current_liabilities=25_000,
        equity=20_000,            # ROE 10% ❌
        gross_debt=50_000,        # 25 years ❌
        retained_earnings=-5_000, # negative ❌
        treasury_shares=None,
    )
    return income, balance


def _strong_bank() -> BankMetrics:
    """A well-run bank with excellent metrics."""
    return BankMetrics(
        mfb=40_000,
        credit_cost=8_000,        # 20% ✅
        admin_expenses=12_000,
        service_revenue=10_000,
        roe=0.22,                 # 22% ✅
        roa=0.018,                # 1.8% ✅
        efficiency_ratio=0.24,   # 24% ✅
        npl_ratio=0.015,          # 1.5% ✅
        basel_ratio=0.16,         # 16% ✅
        has_buyback=True,         # ✅
    )


def _weak_bank() -> BankMetrics:
    return BankMetrics(
        mfb=40_000,
        credit_cost=30_000,       # 75% ❌
        admin_expenses=35_000,
        service_revenue=10_000,
        roe=0.05,                 # 5% ❌
        roa=0.004,                # 0.4% ❌
        efficiency_ratio=0.70,   # 70% ❌
        npl_ratio=0.06,           # 6% ❌
        basel_ratio=0.11,         # 11% ❌ (just above regulatory minimum)
        has_buyback=False,        # ❌
    )


# ---------------------------------------------------------------------------
# Industrial tests
# ---------------------------------------------------------------------------

class TestIndustrialScoring(unittest.TestCase):

    def test_strong_company_scores_high(self):
        income, balance = _strong_industrial()
        result = score_industrial(income, balance)
        self.assertGreater(result.score_100, 70)

    def test_weak_company_scores_low(self):
        income, balance = _weak_industrial()
        result = score_industrial(income, balance)
        self.assertLess(result.score_100, 40)

    def test_gross_margin_above_40_is_green(self):
        income, balance = _strong_industrial()
        result = score_industrial(income, balance)
        mb_metric = next(m for m in result.metrics if "Margem Bruta" in m.name)
        self.assertEqual(mb_metric.status, MetricStatus.GREEN)
        self.assertEqual(mb_metric.points, mb_metric.max_points)

    def test_gross_margin_below_20_is_red(self):
        income, balance = _weak_industrial()
        result = score_industrial(income, balance)
        mb_metric = next(m for m in result.metrics if "Margem Bruta" in m.name)
        self.assertEqual(mb_metric.status, MetricStatus.RED)
        self.assertEqual(mb_metric.points, 0)

    def test_missing_values_score_zero_not_crash(self):
        income = IncomeStatement(
            revenue=None, gross_profit=None, net_income=50_000,
            operating_income=None, selling_expenses=None, ga_expenses=None,
            da_expenses=None, interest_expenses=None,
            operating_cash_flow=None, capex=None,
        )
        balance = BalanceSheet(
            total_assets=None, current_assets=None, current_liabilities=None,
            equity=100_000, gross_debt=None, retained_earnings=None, treasury_shares=None,
        )
        result = score_industrial(income, balance)
        self.assertIsInstance(result.score_100, int)
        self.assertGreaterEqual(result.score_100, 0)

    def test_retained_earnings_positive_is_green(self):
        income, balance = _strong_industrial()
        result = score_industrial(income, balance)
        re_metric = next(m for m in result.metrics if "Lucros Acumulados" in m.name)
        self.assertEqual(re_metric.status, MetricStatus.GREEN)

    def test_treasury_shares_negative_is_green(self):
        income, balance = _strong_industrial()
        result = score_industrial(income, balance)
        treasury = next(m for m in result.metrics if "Tesouraria" in m.name)
        self.assertEqual(treasury.status, MetricStatus.GREEN)

    def test_all_metrics_have_required_fields(self):
        income, balance = _strong_industrial()
        result = score_industrial(income, balance)
        for metric in result.metrics:
            self.assertIsNotNone(metric.name)
            self.assertIsNotNone(metric.benchmark)
            self.assertIsNotNone(metric.explanation)
            self.assertIsNotNone(metric.formula)
            self.assertGreater(metric.max_points, 0)

    def test_score_is_sum_of_metric_points(self):
        income, balance = _strong_industrial()
        result = score_industrial(income, balance)
        total = sum(m.points for m in result.metrics)
        max_pts = sum(m.max_points for m in result.metrics)
        self.assertEqual(result.total_points, total)
        self.assertEqual(result.max_points, max_pts)


# ---------------------------------------------------------------------------
# Bank tests
# ---------------------------------------------------------------------------

class TestBankScoring(unittest.TestCase):

    def _dummy_balance(self) -> BalanceSheet:
        return BalanceSheet(
            total_assets=1_000_000, current_assets=None, current_liabilities=None,
            equity=100_000, gross_debt=None, retained_earnings=None, treasury_shares=None,
        )

    def _dummy_income(self) -> IncomeStatement:
        return IncomeStatement(
            revenue=None, gross_profit=None, net_income=20_000,
            operating_income=None, selling_expenses=None, ga_expenses=None,
            da_expenses=None, interest_expenses=None,
            operating_cash_flow=None, capex=None,
        )

    def test_strong_bank_scores_high(self):
        result = score_bank(self._dummy_income(), self._dummy_balance(), _strong_bank())
        self.assertGreater(result.score_100, 80)

    def test_weak_bank_scores_low(self):
        result = score_bank(self._dummy_income(), self._dummy_balance(), _weak_bank())
        self.assertLess(result.score_100, 30)

    def test_roe_above_20_is_green(self):
        bank = _strong_bank()
        result = score_bank(self._dummy_income(), self._dummy_balance(), bank)
        roe_m = next(m for m in result.metrics if "ROE" in m.name)
        self.assertEqual(roe_m.status, MetricStatus.GREEN)

    def test_npl_above_4_is_red(self):
        bank = _weak_bank()
        result = score_bank(self._dummy_income(), self._dummy_balance(), bank)
        npl_m = next(m for m in result.metrics if "Inadimpl" in m.name)
        self.assertEqual(npl_m.status, MetricStatus.RED)

    def test_missing_npl_is_unavailable(self):
        bank = BankMetrics(
            mfb=40_000, credit_cost=8_000, admin_expenses=12_000,
            service_revenue=10_000, roe=0.22, roa=0.018,
            efficiency_ratio=0.24, npl_ratio=None, basel_ratio=0.16,
            has_buyback=True,
        )
        result = score_bank(self._dummy_income(), self._dummy_balance(), bank)
        npl_m = next(m for m in result.metrics if "Inadimpl" in m.name)
        self.assertEqual(npl_m.status, MetricStatus.UNAVAILABLE)
        self.assertEqual(npl_m.points, 0)
        self.assertEqual(npl_m.formatted_value, "N/D")

    def test_bank_has_exactly_7_metrics(self):
        result = score_bank(self._dummy_income(), self._dummy_balance(), _strong_bank())
        self.assertEqual(len(result.metrics), 7)

    def test_btg_1t25_annualised_roe_is_green(self):
        """
        BTG 1T25: LL=3.261.874 × 4 = 13.047.496; PL=62.836.577
        ROE = 20.8% → should be green.
        """
        ll_annual = 3_261_874 * 4
        pl = 62_836_577
        roe = ll_annual / pl  # ≈ 0.2077

        bank = BankMetrics(
            mfb=7_245_125 * 4, credit_cost=2_118_667 * 4,
            admin_expenses=1_809_846 * 4, service_revenue=2_681_533 * 4,
            roe=roe, roa=ll_annual / 611_754_584,
            efficiency_ratio=None, npl_ratio=None, basel_ratio=0.154,
            has_buyback=True,
        )
        income = IncomeStatement(
            revenue=None, gross_profit=None, net_income=ll_annual,
            operating_income=None, selling_expenses=None, ga_expenses=None,
            da_expenses=None, interest_expenses=None,
            operating_cash_flow=None, capex=None,
        )
        balance = BalanceSheet(
            total_assets=611_754_584, current_assets=None, current_liabilities=None,
            equity=pl, gross_debt=None, retained_earnings=None, treasury_shares=None,
        )
        result = score_bank(income, balance, bank)
        roe_m = next(m for m in result.metrics if "ROE" in m.name)
        self.assertEqual(roe_m.status, MetricStatus.GREEN)
        self.assertAlmostEqual(roe_m.value, roe, places=4)

    def test_bb_2025_roe_is_red(self):
        """
        BB 2025: LL=20.685; PL=192.105
        ROE = 10.8% → should be red (< 15%).
        """
        bank = BankMetrics(
            mfb=103_128, credit_cost=61_947, admin_expenses=38_872,
            service_revenue=34_813, roe=20_685 / 192_105,
            roa=20_685 / 2_451_621, efficiency_ratio=0.277,
            npl_ratio=0.0517, basel_ratio=0.1513, has_buyback=True,
        )
        income = IncomeStatement(
            revenue=None, gross_profit=None, net_income=20_685,
            operating_income=None, selling_expenses=None, ga_expenses=None,
            da_expenses=None, interest_expenses=None,
            operating_cash_flow=None, capex=None,
        )
        balance = BalanceSheet(
            total_assets=2_451_621, current_assets=None, current_liabilities=None,
            equity=192_105, gross_debt=None, retained_earnings=None, treasury_shares=None,
        )
        result = score_bank(income, balance, bank)
        roe_m = next(m for m in result.metrics if "ROE" in m.name)
        self.assertEqual(roe_m.status, MetricStatus.RED)


if __name__ == "__main__":
    unittest.main()
