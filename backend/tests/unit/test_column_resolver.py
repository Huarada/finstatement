"""
Unit tests for column index resolution.

Covers all Brazilian financial report header formats.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from app.domain.parsers.column_resolver import best_column_index, _score_header


class TestScoreHeader(unittest.TestCase):

    def test_annual_label_scores_highest(self):
        score = _score_header("Exercício/2025")
        self.assertGreater(score, 9.0)

    def test_year_only_scores_high(self):
        score = _score_header("2025")
        self.assertGreaterEqual(score, 9.0)

    def test_more_recent_year_scores_higher(self):
        self.assertGreater(_score_header("2025"), _score_header("2024"))

    def test_full_ifrs_date_scores_well(self):
        score = _score_header("31/03/2025")
        self.assertGreater(score, 7.0)

    def test_more_recent_date_scores_higher(self):
        self.assertGreater(_score_header("31/03/2025"), _score_header("31/12/2024"))

    def test_mmm_yy_score(self):
        score = _score_header("Dez/25")
        self.assertGreater(score, 6.0)

    def test_mmm_yy_recency(self):
        self.assertGreater(_score_header("Dez/25"), _score_header("Set/25"))
        self.assertGreater(_score_header("Set/25"), _score_header("Dez/24"))

    def test_quarterly_scores_lowest(self):
        self.assertLess(_score_header("4T25"), _score_header("Dez/25"))
        self.assertLess(_score_header("4T25"), _score_header("2025"))

    def test_delta_column_excluded(self):
        self.assertLess(_score_header("Δ% A/A"), 0)
        self.assertLess(_score_header("Var. %"), 0)
        self.assertLess(_score_header("delta"), 0)


class TestBestColumnIndex(unittest.TestCase):

    def test_btg_ifrs_dre_selects_first_data_col(self):
        """DRE with IFRS dates: 31/03/2025 should win over 31/03/2024."""
        cols = ("Nota", "31/03/2025", "31/03/2024")
        self.assertEqual(best_column_index(cols), 1)

    def test_year_only_selects_most_recent(self):
        cols = ("Conta", "2023", "2024", "2025")
        self.assertEqual(best_column_index(cols), 3)

    def test_mixed_cols_prefers_annual_over_quarterly(self):
        """'2025' annual label should beat '4T25' quarterly."""
        cols = ("Conta", "4T24", "3T25", "4T25", "2024", "2025")
        self.assertEqual(best_column_index(cols), 5)

    def test_mmm_yy_selects_dez25(self):
        cols = ("Conta", "Dez/24", "Set/25", "Dez/25")
        self.assertEqual(best_column_index(cols), 3)

    def test_delta_columns_skipped(self):
        """Delta columns should never be selected."""
        cols = ("Conta", "2024", "Δ% A/A", "2025")
        self.assertEqual(best_column_index(cols), 3)

    def test_single_data_column_fallback(self):
        cols = ("Conta", "2025")
        self.assertEqual(best_column_index(cols), 1)

    def test_caching_consistency(self):
        """Same input must always return same result (lru_cache)."""
        cols = ("Conta", "2024", "2025")
        self.assertEqual(best_column_index(cols), best_column_index(cols))


if __name__ == "__main__":
    unittest.main()
