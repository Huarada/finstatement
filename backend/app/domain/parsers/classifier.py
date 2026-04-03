"""
Financial table classifier.

Uses keyword co-occurrence scoring to assign a semantic type
(DRE, Balanço, DFC, KPIs, …) to each candidate text block.

Design: pure functions operating on raw string lists.
No I/O, no global state — fully unit-testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TableSignature:
    """Describes what keywords identify a particular table type."""
    id: str
    title: str
    keywords: tuple[re.Pattern, ...]
    min_hits: int
    priority: int


def _p(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


# ---------------------------------------------------------------------------
# Table signatures ordered by priority (higher = matched first when tied)
# ---------------------------------------------------------------------------

TABLE_SIGNATURES: tuple[TableSignature, ...] = (
    TableSignature(
        id="destaques_banco",
        title="Destaques do Resultado — Banco",
        keywords=(
            _p(r"lucro\s*l[íi]quido\s*ajustado"),
            _p(r"margem\s*financeira\s*(bruta|l[íi]quida)"),
            _p(r"custo\s*do\s*cr[eé]dito"),
            _p(r"total\s*de\s*ativos?"),
            _p(r"patrim[oô]nio\s*l[íi]quido"),
            _p(r"carteira\s*de\s*cr[eé]dito"),
            _p(r"rspl|retorno.*patrim[oô]nio"),
            _p(r"inadimpl[eê]ncia|inad\s*\+?\s*90"),
            _p(r"[íi]ndice\s*de\s*basileia"),
            _p(r"receitas?\s*de\s*presta[cç][aã]o"),
            _p(r"despesas?\s*administrativas"),
        ),
        min_hits=4,
        priority=11,
    ),
    TableSignature(
        id="dre",
        title="DRE — Demonstração do Resultado",
        keywords=(
            _p(r"receita\s*(l[íi]quida|bruta|oper)"),
            _p(r"lucro\s*(bruto|l[íi]quido|oper)"),
            _p(r"resultado\s*(bruto|oper|financ)"),
            _p(r"ebitda|lajida"),
            _p(r"custo.*mercad|cpv|cmv"),
            _p(r"despesa.*venda|despesa.*adm"),
            _p(r"resultado\s*l[íi]quido\s*com\s*instrumentos\s*financeiros"),
            _p(r"margem\s*financeira"),
            _p(r"resultado\s*bruto\s*da\s*intermedia"),
        ),
        min_hits=2,
        priority=10,
    ),
    TableSignature(
        id="balanco",
        title="Balanço Patrimonial",
        keywords=(
            _p(r"ativo\s*(total|circulante|n[aã]o\s*circ|imobiliz)"),
            _p(r"passivo\s*(total|circulante|n[aã]o\s*circ)"),
            _p(r"patrim[oô]nio\s*l[íi]quido"),
            _p(r"caixa\s*(e\s*)?(equiv|banco)"),
            _p(r"estoques?"),
            _p(r"imobilizado"),
            _p(r"intang[íi]vel"),
            _p(r"opera[cç][oõ]es?\s*de\s*cr[eé]dito"),
            _p(r"dep[oó]sitos?\s*(totais|de\s*clientes)"),
        ),
        min_hits=3,
        priority=9,
    ),
    TableSignature(
        id="dfc",
        title="Demonstração de Fluxo de Caixa",
        keywords=(
            _p(r"fluxo\s*de\s*caixa|caixa\s*l[íi]quido"),
            _p(r"atividades?\s*(oper|investim|financ)"),
            _p(r"saldo\s*(inicial|final)\s*de\s*caixa"),
            _p(r"varia.*capital\s*de\s*giro"),
            _p(r"caixa\s*gerado\s*pelas?\s*opera[cç][oõ]es"),   # BB
            _p(r"caixa\s*(utilizado|proveniente).*atividades"),  # BTG IFRS
            _p(r"varia[cç][aã]o\s*l[íi]quida\s*de\s*caixa"),
        ),
        min_hits=2,
        priority=9,
    ),
    TableSignature(
        id="ebitda",
        title="Reconciliação EBITDA / LAJIDA",
        keywords=(
            _p(r"ebitda|lajida"),
            _p(r"deprecia"),
            _p(r"amortiza"),
            _p(r"resultado\s*financ"),
            _p(r"imposto.*renda|ir.*csll"),
        ),
        min_hits=3,
        priority=8,
    ),
    TableSignature(
        id="kpis",
        title="Indicadores Financeiros e Operacionais",
        keywords=(
            _p(r"indicadores?|highlights?|destaques?\s*financ"),
            _p(r"margem\s*(bruta|ebitda|l[íi]quida)"),
            _p(r"roe|roa|roic"),
            _p(r"d[íi]vida\s*l[íi]quida.*ebitda"),
            _p(r"rspl|retorno.*patrim[oô]nio\s*l[íi]quido"),
            _p(r"retorno\s*(sobre|s\/)\s*ativos?"),
            _p(r"[íi]ndice\s*de\s*efici[eê]ncia"),
            _p(r"inadimpl[eê]ncia.*90"),
        ),
        min_hits=2,
        priority=5,
    ),
    TableSignature(
        id="divida",
        title="Endividamento e Dívida Líquida",
        keywords=(
            _p(r"d[íi]vida\s*(l[íi]quida|bruta|total)"),
            _p(r"empr[eé]stimos?\s*e\s*financiam"),
            _p(r"d[eé]bentures?"),
            _p(r"alavancagem|leverage"),
        ),
        min_hits=2,
        priority=6,
    ),
)


def score_block(lines: list[str], signature: TableSignature) -> int:
    """
    Count how many of the signature's keyword patterns appear in `lines`.

    Args:
        lines: Raw text lines from a candidate table block.
        signature: The signature to score against.

    Returns:
        Number of distinct keyword hits.
    """
    joined = " ".join(lines).lower()
    return sum(1 for pat in signature.keywords if pat.search(joined))


def classify_block(lines: list[str]) -> TableSignature | None:
    """
    Return the best-matching TableSignature for a text block, or None.

    Strategy: collect all signatures whose min_hits threshold is met,
    then return the one with the highest (hits, priority) tuple.

    Args:
        lines: Raw text lines from a candidate table block.

    Returns:
        Winning TableSignature, or None if no signature qualifies.
    """
    candidates = []
    for sig in TABLE_SIGNATURES:
        hits = score_block(lines, sig)
        if hits >= sig.min_hits:
            candidates.append((hits, sig.priority, sig))

    if not candidates:
        return None

    # Sort descending by hits then priority
    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return candidates[0][2]
