"""
Unit tests for period detection and annualization.

All tests are pure — no I/O, no external dependencies.
"""
import sys
import os
import unittest

# Allow running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from app.domain.scoring.annualizer import annualization_factor, detect_period_type
from app.domain.entities import PeriodType


class TestDetectPeriodType(unittest.TestCase):

    def test_quarterly_from_quarter_code(self):
        self.assertEqual(detect_period_type("Resultados 1T25"), PeriodType.QUARTERLY)
        self.assertEqual(detect_period_type("4T2024 relatório"), PeriodType.QUARTERLY)

    def test_quarterly_from_trimestre_word(self):
        self.assertEqual(
            detect_period_type("primeiro trimestre de 2025"),
            PeriodType.QUARTERLY,
        )
        self.assertEqual(
            detect_period_type("quarto trimestre"),
            PeriodType.QUARTERLY,
        )

    def test_quarterly_from_ifrs_interim(self):
        text = (
            "Demonstrações Financeiras Intermediárias Consolidadas "
            "Condensadas em IFRS Banco BTG Pactual Março 2025"
        )
        self.assertEqual(detect_period_type(text), PeriodType.QUARTERLY)

    def test_quarterly_from_tres_meses(self):
        self.assertEqual(
            detect_period_type("período de três meses findo em 31 de março"),
            PeriodType.QUARTERLY,
        )

    def test_semiannual_from_semester_code(self):
        self.assertEqual(detect_period_type("1S2025"), PeriodType.SEMIANNUAL)
        self.assertEqual(detect_period_type("2S24"), PeriodType.SEMIANNUAL)

    def test_semiannual_from_semestre_word(self):
        self.assertEqual(detect_period_type("primeiro semestre"), PeriodType.SEMIANNUAL)
        self.assertEqual(detect_period_type("seis meses findo"), PeriodType.SEMIANNUAL)

    def test_annual_default(self):
        self.assertEqual(detect_period_type("Demonstrações Financeiras 2025"), PeriodType.ANNUAL)
        self.assertEqual(detect_period_type("Exercício findo em 31 de dezembro de 2024"), PeriodType.ANNUAL)

    def test_annual_empty_string(self):
        self.assertEqual(detect_period_type(""), PeriodType.ANNUAL)


class TestAnnualizationFactor(unittest.TestCase):

    def test_annual_factor_is_one(self):
        self.assertEqual(annualization_factor(PeriodType.ANNUAL), 1)

    def test_semiannual_factor_is_two(self):
        self.assertEqual(annualization_factor(PeriodType.SEMIANNUAL), 2)

    def test_quarterly_factor_is_four(self):
        self.assertEqual(annualization_factor(PeriodType.QUARTERLY), 4)

    def test_btg_quarterly_annualization(self):
        """BTG 1T25 net income 3.261.874 → annualised 13.047.496."""
        quarterly_ll = 3_261_874
        factor = annualization_factor(PeriodType.QUARTERLY)
        self.assertEqual(quarterly_ll * factor, 13_047_496)


if __name__ == "__main__":
    unittest.main()
