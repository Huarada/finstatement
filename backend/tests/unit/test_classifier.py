"""
Unit tests for the financial table classifier.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from app.domain.parsers.classifier import classify_block, score_block, TABLE_SIGNATURES


def _sig(id_: str):
    return next(s for s in TABLE_SIGNATURES if s.id == id_)


class TestScoreBlock(unittest.TestCase):

    def test_dre_keywords_score_correctly(self):
        lines = ["Receita Líquida", "Lucro Bruto", "Resultado Operacional"]
        sig = _sig("dre")
        hits = score_block(lines, sig)
        self.assertGreaterEqual(hits, 2)

    def test_banco_keywords_score_correctly(self):
        lines = [
            "Lucro Líquido Ajustado",
            "Margem Financeira Bruta",
            "Custo do Crédito",
            "Total de Ativos",
            "Patrimônio Líquido",
        ]
        sig = _sig("destaques_banco")
        hits = score_block(lines, sig)
        self.assertGreaterEqual(hits, 4)

    def test_empty_block_scores_zero(self):
        for sig in TABLE_SIGNATURES:
            self.assertEqual(score_block([], sig), 0)


class TestClassifyBlock(unittest.TestCase):

    def test_dre_block_classified_correctly(self):
        lines = [
            "Receita Líquida de Vendas",
            "Custo dos Produtos Vendidos",
            "Lucro Bruto",
            "Despesas com Vendas",
            "Resultado Operacional",
        ]
        sig = classify_block(lines)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.id, "dre")

    def test_balanco_block_classified_correctly(self):
        lines = [
            "Ativo Total",
            "Ativo Circulante",
            "Passivo Circulante",
            "Patrimônio Líquido",
            "Imobilizado",
            "Intangível",
        ]
        sig = classify_block(lines)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.id, "balanco")

    def test_dfc_block_classified_correctly(self):
        lines = [
            "Fluxo de Caixa das Atividades Operacionais",
            "Atividades de Investimento",
            "Saldo Final de Caixa",
        ]
        sig = classify_block(lines)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.id, "dfc")

    def test_btg_dfc_pattern_classified_correctly(self):
        """BTG uses 'Caixa (utilizado) / proveniente das atividades operacionais'."""
        lines = [
            "Caixa (utilizado) / proveniente das atividades operacionais",
            "Atividades de investimento",
            "Caixa proveniente das atividades de financiamento",
        ]
        sig = classify_block(lines)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.id, "dfc")

    def test_kpi_block_classified_correctly(self):
        lines = [
            "Indicadores Financeiros e Operacionais",
            "Retorno sobre Patrimônio Líquido (RSPL)",
            "Retorno sobre Ativos (ROA)",
            "Índice de Eficiência",
        ]
        sig = classify_block(lines)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.id, "kpis")

    def test_destaques_banco_wins_over_dre(self):
        """
        When a block has both DRE and Balanço keywords (BB mega-table),
        destaques_banco should be selected (priority 11 > 10).
        """
        lines = [
            "Lucro Líquido Ajustado",
            "Margem Financeira Bruta",
            "Custo do Crédito",
            "Total de Ativos",
            "Patrimônio Líquido",
            "Carteira de Crédito",
            "Receitas de Prestação de Serviços",
        ]
        sig = classify_block(lines)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.id, "destaques_banco")

    def test_irrelevant_block_returns_none(self):
        lines = [
            "As notas explicativas são parte integrante das demonstrações",
            "São Paulo, 23 de maio de 2025",
            "PricewaterhouseCoopers",
        ]
        sig = classify_block(lines)
        self.assertIsNone(sig)

    def test_single_keyword_below_min_hits_returns_none(self):
        lines = ["Lucro Bruto"]  # DRE needs min_hits=2
        sig = classify_block(lines)
        # Should not match dre (needs 2 hits)
        if sig is not None:
            self.assertNotEqual(sig.id, "dre")


if __name__ == "__main__":
    unittest.main()
