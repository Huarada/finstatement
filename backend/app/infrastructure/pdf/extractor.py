"""
PDF extraction infrastructure.

Pipeline:
  L1: pdfplumber → words com coordenadas X/Y
  L2: agrupamento em linhas → limites de colunas → matriz de texto
  L3: classificação semântica via assinaturas de palavras-chave
  L4: split de mega-tabelas (destaques_banco) → FinancialTable[]

Correções v2.3:
  - [BUG 1] DFC sendo classificado como Balanço: Fix via _is_clearly_dfc().

  - [BUG 2] Colunas desaparecendo em tabelas largas: _COL_ASSIGN_TOL=80pt.

  - [BUG 3] _detect_headers selecionando linha errada: exige ≥2 células.

  - [BUG 4] Resultado Operacional = N/D: pdfplumber separa label ("Lucro antes
    do resultado financeiro,") e valores (145.870) em linhas com gap Y=6pt.
    _ROW_TOL aumentado de 5 para 7 captura esse gap sem mesclar linhas reais.

  - [BUG 5] Patrimônio Líquido = N/D: Balanço da Petrobras está em 2 páginas
    (p.23=Ativo+Passivo circ., p.24=Passivo não circ.+PL). A página 24 só
    tinha 1 hit Balanço (Patrimônio Líquido), abaixo do minHits=3. Adicionados
    keywords "capital subscrito", "reservas de lucros" e "total do passivo"
    para que a página 24 seja classificada como Balanço.

  - [ORIGINAL v2.1] Detecção de coluna via header de período, empresa por marca,
    _parse_cell para "204,6" sem ponto de milhar.
"""
from __future__ import annotations

import io
import re
from typing import Optional

import pdfplumber

from app.core.exceptions import PdfParsingError
from app.domain.entities import DocumentMeta, FinancialTable, PeriodType, TableRow
from app.domain.scoring.annualizer import annualization_factor, detect_period_type


# ─────────────────────────────────────────────────────────────────────────────
# Constantes de extração
# ─────────────────────────────────────────────────────────────────────────────

_MIN_BLOCK_ROWS    = 3
_ROW_TOL           = 7    # [FIX v2.3] era 5 — Petrobras DRE tem gap Y=6pt entre label
                           # e valores em linhas longas (ex: "Lucro antes do resultado
                           # financeiro, participações e tributos sobre o lucro")
_COL_CLUSTER_GAP   = 28    # máx. distância para agrupar pontos em um cluster de coluna
_COL_ASSIGN_TOL    = 80    # [FIX v2.2] era 55 — muito pequeno para tabelas de 5 colunas
_MIN_COL_HIT_RATIO = 0.20
_META_PAGES        = 5


# ─────────────────────────────────────────────────────────────────────────────
# Extração de metadados
# ─────────────────────────────────────────────────────────────────────────────

_COMPANY_PAT = re.compile(
    r"([A-ZÁÉÍÓÚÀÂÊÔÃÕÇÜ][A-Za-záéíóúàâêôãõçü\s&]+(?:S\.A\.|S/A|SA)\b)",
    re.UNICODE,
)

_COMPANY_BRAND_PATS: list[tuple[re.Pattern, Optional[str]]] = [
    (re.compile(r"\b(Magazine\s*Luiza|MagazineLuiza)\b", re.IGNORECASE), "Magazine Luiza"),
    (re.compile(r"\bMagalu\b"),                                             "Magalu"),
    (re.compile(r"\bPetrobras\b",        re.IGNORECASE),                   "Petrobras"),
    (re.compile(r"\bSuzano\b",           re.IGNORECASE),                   "Suzano"),
    (re.compile(r"\bEmbraer\b",          re.IGNORECASE),                   "Embraer"),
    (re.compile(r"\bAmbev\b",            re.IGNORECASE),                   "Ambev"),
    (re.compile(r"\bGerdau\b",           re.IGNORECASE),                   "Gerdau"),
    (re.compile(r"\bItaú\s*Unibanco\b",  re.IGNORECASE),                   "Itaú Unibanco"),
    (re.compile(r"\bBradesco\b",         re.IGNORECASE),                   "Bradesco"),
    (re.compile(r"\bSantander\b",        re.IGNORECASE),                   "Santander"),
    (re.compile(r"\bNubank\b",           re.IGNORECASE),                   "Nubank"),
    (re.compile(r"\bXP\s+Inc\b",         re.IGNORECASE),                   "XP Inc"),
    (re.compile(r"\bBTG\s+Pactual\b",    re.IGNORECASE),                   "BTG Pactual"),
    (re.compile(r"\bWEG\b"),                                                "WEG"),
    (re.compile(r"\bTotvs\b",            re.IGNORECASE),                   "Totvs"),
    (re.compile(r"\bLocaweb\b",          re.IGNORECASE),                   "Locaweb"),
    (re.compile(r"\bRaia\s*Drogasil\b",  re.IGNORECASE),                   "Raia Drogasil"),
    (re.compile(r"\bClearSale\b",        re.IGNORECASE),                   "ClearSale"),
    (re.compile(r"\b([A-Z]{4}[0-9]{1,2})\b"),                              None),
]

_PERIOD_PAT   = re.compile(
    r"\b([1-4][Tt][Qq]?\.?\s*(?:de\s*)?(?:19|20)?\d{2})\b|\b((19|20)\d{2})\b",
    re.IGNORECASE,
)
_CURRENCY_PAT = re.compile(r"R\$\s*(?:mil(?:hões?)?|bilhões?)?", re.IGNORECASE)

_DOCTYPE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sum[aá]rio\s*(do\s*)?resultado",       re.I), "Sumário do Resultado"),
    (re.compile(r"release\s*de\s*resultado",             re.I), "Release de Resultados"),
    (re.compile(r"divulga[cç][aã]o\s*de\s*resultado",    re.I), "Divulgação de Resultados"),
    (re.compile(r"apresenta[cç][aã]o.*resultado",        re.I), "Apresentação de Resultados"),
    (re.compile(r"relat[oó]rio\s*anual",                 re.I), "Relatório Anual"),
    (
        re.compile(r"demonstra\w+\s+financeiras?\s+intermedi[aá]rias?", re.I),
        "Demonstrações Intermediárias (IFRS)",
    ),
]


def _extract_meta(pages_text: list[str]) -> DocumentMeta:
    sample  = " ".join(pages_text[:_META_PAGES])
    company = ""

    for pat, canonical in _COMPANY_BRAND_PATS:
        m = pat.search(sample)
        if m:
            company = canonical if canonical is not None else (
                m.group(1) if m.lastindex else m.group(0)
            ).strip()
            break

    if not company:
        m = _COMPANY_PAT.search(sample)
        if m:
            company = m.group(1).strip()[:70]

    period = ""
    m = _PERIOD_PAT.search(sample)
    if m:
        period = m.group(1) or m.group(2) or ""

    m        = _CURRENCY_PAT.search(sample)
    currency = m.group(0).strip() if m else "R$ Milhões"

    doc_type = "DFP/ITR"
    for pat, label in _DOCTYPE_PATTERNS:
        if pat.search(sample):
            doc_type = label
            break

    period_type = detect_period_type(sample)
    ann_factor  = annualization_factor(period_type)

    return DocumentMeta(
        company=company, period=period, currency=currency,
        doc_type=doc_type, period_type=period_type,
        annualization_factor=ann_factor,
    )


# ─────────────────────────────────────────────────────────────────────────────
# L2: helpers de layout
# ─────────────────────────────────────────────────────────────────────────────

def _group_by_rows(items: list[dict], tol: int = _ROW_TOL) -> list[list[dict]]:
    if not items:
        return []
    sorted_items = sorted(items, key=lambda i: i["y"])
    rows: list[list[dict]] = [[sorted_items[0]]]
    for item in sorted_items[1:]:
        if abs(item["y"] - rows[-1][0]["y"]) <= tol:
            rows[-1].append(item)
        else:
            rows.append([item])
    for row in rows:
        row.sort(key=lambda i: i["x"])
    return rows


_PERIOD_TOKEN_PAT = re.compile(
    r"^[1-4][TtQq]\d{2,4}$"     # 4T25, 3T25, 1Q24
    r"|^[QqTt][1-4][\-\s]?\d{2,4}$"  # Q1-24
    r"|^20\d{2}$"                 # 2025, 2024
    r"|^12[Mm]\d{2,4}$"           # 12M25, 12M2025
    r"|^[Dd]ez\.?\/?\s*\d{2,4}$" # Dez/25, Dez/2025
    r"|^\d{4}[Aa]$",              # 2025A
    re.IGNORECASE,
)


def _boundaries_from_period_header(rows: list[list[dict]]) -> list[float]:
    """
    Estratégia primária de detecção de colunas: encontra a linha de cabeçalho
    que contém tokens de período (4T25, 2025, etc.) e usa as posições X desses
    tokens como centros exatos das colunas.

    Abordagem mais robusta que clustering por X porque elimina o problema de
    drift de média móvel quando os gaps entre colunas são < _COL_CLUSTER_GAP.

    Retorna [] se nenhuma linha com ≥ 2 tokens de período for encontrada.
    """
    for row in rows[:8]:
        period_items = [
            i for i in row if _PERIOD_TOKEN_PAT.match(i["text"].strip())
        ]
        if len(period_items) < 2:
            continue

        # Limite da área de rótulo: X máximo dos tokens que NÃO são período
        non_period = [
            i for i in row if not _PERIOD_TOKEN_PAT.match(i["text"].strip())
        ]
        label_x = max((i["x"] for i in non_period), default=0.0)

        # Centros das colunas de dados: X de cada token de período
        # Mescla tokens muito próximos (artefatos duplicados, < 15pt)
        period_xs = sorted(round(i["x"]) for i in period_items)
        merged: list[float] = [float(period_xs[0])]
        for px in period_xs[1:]:
            if px - merged[-1] < 15:
                merged[-1] = (merged[-1] + px) / 2.0
            else:
                merged.append(float(px))

        return [label_x] + merged

    return []


def _find_column_boundaries(rows: list[list[dict]]) -> list[float]:
    """
    Detecta limites de colunas.

    Estratégia 1 (prioritária): header com tokens de período (4T25, 2025…).
    Usa as posições X dos tokens como centros exatos — elimina o problema de
    drift de média móvel que ocorria com o Petrobras 4T25 (todos os gaps < 28pt,
    causando colapso de 6 colunas em 2).

    Estratégia 2 (fallback): clusterização por coordenadas X.
    Para tabelas com gap label/data > 80pt, separa as regiões antes de clusterizar
    para preservar colunas nas extremidades.
    """
    period_bounds = _boundaries_from_period_header(rows)
    if period_bounds:
        return period_bounds

    # ── Fallback: clusterização por coordenadas X ─────────────────────────
    xs: list[float] = []
    for row in rows:
        for item in row:
            xs.append(round(item["x"]))
    xs_unique = sorted(set(xs))
    if not xs_unique:
        return []

    if len(xs_unique) > 2:
        gaps = [(xs_unique[i+1] - xs_unique[i], i) for i in range(len(xs_unique)-1)]
        max_gap, max_gap_idx = max(gaps, key=lambda g: g[0])

        if max_gap > 80:
            label_xs = xs_unique[:max_gap_idx + 1]
            data_xs  = xs_unique[max_gap_idx + 1:]
            clusters: list[float] = [min(label_xs)]
            if data_xs:
                dc = [data_xs[0]]
                for x in data_xs[1:]:
                    if x - dc[-1] < _COL_CLUSTER_GAP:
                        dc[-1] = (dc[-1] + x) / 2
                    else:
                        clusters.append(dc[-1])
                        dc = [x]
                clusters.append(dc[-1])
            return clusters

    clusters_std: list[float] = [xs_unique[0]]
    for x in xs_unique[1:]:
        if x - clusters_std[-1] < _COL_CLUSTER_GAP:
            clusters_std[-1] = (clusters_std[-1] + x) / 2
        else:
            clusters_std.append(x)
    return clusters_std


def _count_cols_hit(row: list[dict], bounds: list[float]) -> int:
    hits: set[int] = set()
    for item in row:
        best_dist, best_i = float("inf"), -1
        for i, b in enumerate(bounds):
            d = abs(b - item["x"])
            if d < best_dist:
                best_dist, best_i = d, i
        if best_dist < 35:
            hits.add(best_i)
    return len(hits)


def _rows_to_matrix(rows: list[list[dict]], bounds: list[float]) -> list[list[str]]:
    if not bounds:
        return []

    label_cutoff = (bounds[0] + bounds[1]) / 2 if len(bounds) > 1 else bounds[0] + 200
    matrix: list[list[str]] = []

    for row in rows:
        cells        = [""] * len(bounds)
        label_parts: list[str] = []

        for item in row:
            if item["x"] <= label_cutoff:
                label_parts.append(item["text"])
            else:
                best_dist, best_i = float("inf"), len(bounds) - 1
                for i, b in enumerate(bounds[1:], start=1):
                    d = abs(b - item["x"])
                    if d < best_dist:
                        best_dist, best_i = d, i
                # [FIX v2.2] _COL_ASSIGN_TOL aumentado de 55 para 80
                if best_dist < _COL_ASSIGN_TOL:
                    cells[best_i] = (cells[best_i] + " " + item["text"]).strip()

        cells[0] = " ".join(label_parts)
        matrix.append(cells)
    return matrix


def _clean_matrix(matrix: list[list[str]]) -> list[list[str]]:
    if not matrix:
        return []
    cc       = len(matrix[0])
    keep_cols = [c for c in range(cc) if any((r[c] if c < len(r) else "").strip() for r in matrix)]
    result   = []
    for row in matrix:
        cleaned = [(row[c] if c < len(row) else "") for c in keep_cols]
        if any(c.strip() for c in cleaned):
            result.append(cleaned)
    return result


def _detect_narrative_right_column(items: list[dict], page_width: float) -> bool:
    """
    Detecta layout de duas colunas onde a coluna direita é prosa narrativa.

    Token é "prosa" apenas se tiver > 4 chars e < 30% de caracteres
    numéricos/pontuação. Tokens curtos como "pp", "-", "1,1%" são
    artefatos de tabela, não prosa.
    """
    if len(items) < 10:
        return False
    mid_x        = page_width * 0.50
    right_items  = [i for i in items if i["x"] > mid_x]
    if len(right_items) < 6:
        return False

    _digit_or_punct = re.compile(r"[\d\.,\-\+\%\(\)\[\]/]")
    prose_count     = 0
    for item in right_items:
        text = item["text"]
        if len(text) <= 4:
            continue
        digit_chars = len(_digit_or_punct.findall(text))
        if digit_chars / len(text) < 0.30:
            prose_count += 1

    return prose_count / len(right_items) > 0.50


def _split_into_segments(rows: list[list[dict]], bounds: list[float]) -> list[list[list[dict]]]:
    segs: list[list[list[dict]]] = []
    cur:  list[list[dict]]       = []
    for row in rows:
        if not any(i["text"].strip() for i in row) and len(cur) > 2:
            segs.append(cur)
            cur = []
        elif any(i["text"].strip() for i in row):
            cur.append(row)
    if len(cur) > 2:
        segs.append(cur)
    return segs if segs else [rows]


# ─────────────────────────────────────────────────────────────────────────────
# L2: detecção de regiões tabulares
# ─────────────────────────────────────────────────────────────────────────────

def _detect_table_regions(pages: list[dict]) -> list[dict]:
    all_tables: list[dict] = []
    for page in pages:
        items = page["items"]
        if len(items) < 6:
            continue

        is_dual   = _detect_narrative_right_column(items, page["width"])
        effective = [i for i in items if i["x"] <= page["width"] * 0.52] if is_dual else items

        rows = _group_by_rows(effective)
        if len(rows) < 3:
            continue

        bounds = _find_column_boundaries(rows)
        if len(bounds) < 2:
            continue

        tabular_rows = [r for r in rows if _count_cols_hit(r, bounds) >= 2]
        if len(tabular_rows) < 3:
            continue
        if len(tabular_rows) / len(rows) < _MIN_COL_HIT_RATIO:
            continue

        for seg in _split_into_segments(rows, bounds):
            if len(seg) < 3:
                continue
            matrix  = _rows_to_matrix(seg, bounds)
            cleaned = _clean_matrix(matrix)
            if len(cleaned) >= 3 and len(cleaned[0]) >= 2:
                all_tables.append({"page": page["page_num"], "matrix": cleaned})

    return all_tables


# ─────────────────────────────────────────────────────────────────────────────
# L3: assinaturas e classificação
# ─────────────────────────────────────────────────────────────────────────────

_TABLE_SIGS = [
    {
        "id": "destaques_banco", "priority": 11, "minHits": 4,
        "title": "Destaques do Resultado — Banco",
        "kws": [
            re.compile(r"lucro\s*l[íi]quido\s*ajustado",                re.I),
            re.compile(r"margem\s*financeira\s*(bruta|l[íi]quida)",      re.I),
            re.compile(r"custo\s*do\s*cr[eé]dito",                       re.I),
            re.compile(r"total\s*de\s*ativos?",                          re.I),
            re.compile(r"patrim[oô]nio\s*l[íi]quido",                   re.I),
            re.compile(r"carteira\s*de\s*cr[eé]dito",                   re.I),
            re.compile(r"rspl|retorno.*patrim[oô]nio",                   re.I),
            re.compile(r"inadimpl[eê]ncia|inad\s*\+?\s*90",             re.I),
            re.compile(r"[íi]ndice\s*de\s*basileia",                    re.I),
            re.compile(r"receitas?\s*de\s*presta[cç][aã]o",             re.I),
            re.compile(r"despesas?\s*administrativas",                   re.I),
        ],
    },
    {
        "id": "dre", "priority": 10, "minHits": 2,
        "title": "DRE — Demonstração do Resultado",
        "kws": [
            re.compile(r"receita\s*(l[íi]quida|bruta|oper)",            re.I),
            re.compile(r"lucro\s*(bruto|l[íi]quido|oper)",              re.I),
            re.compile(r"resultado\s*(bruto|oper|financ)",               re.I),
            re.compile(r"ebitda|lajida",                                 re.I),
            re.compile(r"custo.*mercad|cpv|cmv",                         re.I),
            re.compile(r"despesa.*venda|despesa.*adm",                   re.I),
            re.compile(r"dedu[cç][aã]o|dedu[cç][oõ]es",                re.I),
            re.compile(r"receita\s*de\s*intermedia[cç][aã]o",           re.I),
            re.compile(r"resultado\s*bruto\s*da\s*intermedia",          re.I),
            re.compile(r"margem\s*financeira",                           re.I),
            re.compile(r"provisao\s*para\s*devedores",                  re.I),
        ],
    },
    # ── DFC com prioridade 12 — ACIMA do Balanço (9) e DRE (10) ──────────
    # Motivo: a seção de variação do capital de giro do DFC lista nomes de
    # contas de balanço ("Contas a receber", "Estoques", etc.), fazendo o
    # classificador genérico preferir Balanço. A função _is_clearly_dfc()
    # aplica um override ainda antes do scoring.
    {
        "id": "dfc", "priority": 12, "minHits": 2,
        "title": "Demonstração de Fluxo de Caixa",
        "kws": [
            re.compile(r"fluxo\s*de\s*caixa|caixa\s*l[íi]quido",       re.I),
            re.compile(r"atividades?\s*(oper|investim|financ)",          re.I),
            re.compile(r"saldo\s*(inicial|final)\s*de\s*caixa",         re.I),
            re.compile(r"aumento.*redu.*caixa",                         re.I),
            re.compile(r"varia.*capital\s*de\s*giro",                   re.I),
            re.compile(r"caixa\s*gerado\s*pelas?\s*opera[cç][oõ]es",   re.I),
            re.compile(r"caixa\s*utilizado\s*nas?\s*atividades",        re.I),
            re.compile(r"varia[cç][aã]o\s*l[íi]quida\s*de\s*caixa",   re.I),
            # [FIX v2.2] padrões específicos Petrobras/DFC
            re.compile(r"recursos?\s*l[íi]quidos?\s*(gerados?|utilizados?)"
                       r"\s*(pelas?|nas?)\s*atividades?",               re.I),
            re.compile(r"caixa\s*e\s*equivalentes\s*de\s*caixa\s*no\s*(in[íi]cio|fim)",
                                                                         re.I),
        ],
    },
    {
        "id": "ebitda", "priority": 8, "minHits": 3,
        "title": "Reconciliação EBITDA / LAJIDA",
        "kws": [
            re.compile(r"ebitda|lajida",                                 re.I),
            re.compile(r"deprecia",                                      re.I),
            re.compile(r"amortiza",                                      re.I),
            re.compile(r"resultado\s*financ",                           re.I),
            re.compile(r"imposto.*renda|ir.*csll",                      re.I),
            re.compile(r"outras\s*despesas",                            re.I),
        ],
    },
    {
        "id": "balanco", "priority": 9, "minHits": 3,
        "title": "Balanço Patrimonial",
        "kws": [
            re.compile(r"ativo\s*(total|circulante|n[aã]o\s*circ|imobiliz)", re.I),
            re.compile(r"passivo\s*(total|circulante|n[aã]o\s*circ)",        re.I),
            re.compile(r"patrim[oô]nio\s*l[íi]quido",                       re.I),
            re.compile(r"caixa\s*(e\s*)?(equiv|banco)",                      re.I),
            re.compile(r"estoques?",                                          re.I),
            re.compile(r"contas?\s*a\s*(receber|pagar)",                     re.I),
            re.compile(r"imobilizado",                                        re.I),
            re.compile(r"intang[íi]vel",                                     re.I),
            re.compile(r"capta[cç][oõ]es?\s*no\s*mercado",                 re.I),
            re.compile(r"opera[cç][oõ]es?\s*de\s*cr[eé]dito",             re.I),
            re.compile(r"carteira\s*de\s*cr[eé]dito",                       re.I),
            re.compile(r"dep[oó]sitos?\s*(totais|de\s*clientes)",           re.I),
            # [FIX v2.3] Petrobras p.24: Balanço span 2 páginas — PL na p.24
            # só tinha 1 hit. Estes keywords existem na p.24 e elevam para ≥3.
            re.compile(r"capital\s*subscrito",                               re.I),
            re.compile(r"reservas?\s*de\s*lucros?",                         re.I),
            re.compile(r"total\s*do\s*passivo",                             re.I),
        ],
    },
    {
        "id": "divida", "priority": 6, "minHits": 2,
        "title": "Endividamento e Dívida Líquida",
        "kws": [
            re.compile(r"d[íi]vida\s*(l[íi]quida|bruta|total)",        re.I),
            re.compile(r"empr[eé]stimos?\s*e\s*financiam",             re.I),
            re.compile(r"d[eé]bentures?",                               re.I),
            re.compile(r"alavancagem|leverage",                         re.I),
        ],
    },
    {
        "id": "sgda", "priority": 6, "minHits": 2,
        "title": "Despesas com Vendas (SG&A)",
        "kws": [
            re.compile(r"despesas?\s*com\s*vendas",                    re.I),
            re.compile(r"royalties|marketing",                         re.I),
            re.compile(r"despesas?\s*com\s*pessoal",                   re.I),
            re.compile(r"ocupa[cç][aã]o.*utilities",                   re.I),
        ],
    },
    {
        "id": "kpis", "priority": 5, "minHits": 2,
        "title": "Indicadores Financeiros e Operacionais",
        "kws": [
            re.compile(r"indicadores?|highlights?|destaques?\s*financ", re.I),
            re.compile(r"margem\s*(bruta|ebitda|l[íi]quida)",          re.I),
            re.compile(r"roe|roa|roic",                                 re.I),
            re.compile(r"d[íi]vida\s*l[íi]quida.*ebitda",             re.I),
            re.compile(r"rspl|retorno.*patrim[oô]nio\s*l[íi]quido",   re.I),
            re.compile(r"retorno\s*(sobre|s\/)ativos?",                re.I),
            re.compile(r"[íi]ndice\s*de\s*efici[eê]ncia",             re.I),
            re.compile(r"inadimpl[eê]ncia.*90",                        re.I),
        ],
    },
]

# ── Âncoras inconfundíveis de DFC ─────────────────────────────────────────────
# Estas frases aparecem SOMENTE em DFCs. Usadas para override de classificação
# antes do scoring (evita DFC → Balanço por causa da seção de capital de giro).
_DFC_ANCHOR_PAT = re.compile(
    r"fluxo\s*de\s*caixa\s*das?\s*atividades?\s*(operac|investim|financ)"
    r"|recursos?\s*l[íi]quidos?\s*(gerados?|utilizados?)\s*(pelas?|nas?)\s*atividades?"
    r"|caixa\s*l[íi]quido\s*(gerado|utilizado)\s*(nas?|pelas?)\s*atividades?"
    r"|caixa\s*e\s*equivalentes.*(?:in[íi]cio|fim)\s*do\s*per[íi]odo",
    re.IGNORECASE,
)

_NORM_RE = re.compile(r"[\u0300-\u036f]")


def _norm_text(t: str) -> str:
    import unicodedata
    return _NORM_RE.sub("", unicodedata.normalize("NFD", t.lower()))


def _is_clearly_dfc(raw_corpus: str) -> bool:
    """
    Verifica se o corpus bruto contém marcadores que SOMENTE aparecem em DFCs.

    Usa o corpus NÃO normalizado para manter acentos e maiúsculas que
    ajudam os padrões a serem mais específicos.
    """
    return bool(_DFC_ANCHOR_PAT.search(raw_corpus))


_YEAR_PAT     = re.compile(
    r"\b(19|20)\d{2}\b|\d[tT]\d{2}|12[mM]\d{2}"
    r"|\b(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\b",
    re.I,
)
_VAR_PAT      = re.compile(r"var\s*%?|%|delta",   re.I)
_ARTIFACT_PAT = re.compile(r"^Col\d+$")


def _is_artifact_row(row: list[str]) -> bool:
    data_cells = [c for c in row[1:] if c.strip()]
    return bool(data_cells) and all(_ARTIFACT_PAT.match(c.strip()) for c in data_cells)


def _detect_headers(matrix: list[list[str]]) -> tuple[int, list[str]]:
    """
    Retorna (índice da linha de header, nomes das colunas).

    [FIX v2.1] Exige ≥ 2 células não-vazias nas colunas de dados.
    Impede que linhas como "4T25" (com apenas col[0] preenchida) sejam
    reconhecidas como header, selecionando a linha correta mais abaixo.
    """
    for i, row in enumerate(matrix[:8]):
        rs = " ".join(row)
        non_empty_data = [c for c in row[1:] if c.strip()]
        if len(non_empty_data) < 2:
            continue
        if (_YEAR_PAT.search(rs) or _VAR_PAT.search(rs)) and not _is_artifact_row(row):
            cols = [
                (c.strip() or (f"Conta" if j == 0 else f"Col{j+1}"))
                for j, c in enumerate(row)
            ]
            return i, cols

    for i, row in enumerate(matrix[:5]):
        if sum(1 for c in row if c.strip()) >= 2:
            cols = [
                (c.strip() or (f"Conta" if j == 0 else f"Col{j+1}"))
                for j, c in enumerate(row)
            ]
            return i, cols

    row0 = matrix[0] if matrix else []
    cols = [
        (c.strip() or (f"Conta" if j == 0 else f"Col{j+1}"))
        for j, c in enumerate(row0)
    ]
    return 0, cols


_TOTAL_PAT = re.compile(
    r"^total\b|\btotal\s|^lucro\s*liquido$|^receita\s*(operacional\s*)?liquida$"
    r"|^ativo\s*total$|^passivo.*total|^ebitda\s*ajustado$|^resultado\s*liquido"
    r"|^caixa.*final$|^aumento.*caixa",
    re.I,
)
_SECTION_PAT = re.compile(
    r"^ativo\s*circulante$|^ativo\s*nao\s*circ|^passivo\s*circulante$"
    r"|^passivo\s*nao\s*circ|^atividades?\s*(oper|investim|financ)"
    r"|^indicadores?\s*(de\s*)?(capital|multiplos|mercado)|^carteira\s*de\s*credito$",
    re.I,
)


def _classify_row_type(label: str) -> str:
    if re.match(r"^\s*\|{1,2}\s*", label):
        return "section"
    n = _norm_text(label)
    if _TOTAL_PAT.search(n):
        return "total"
    if _SECTION_PAT.search(n):
        return "section"
    return "normal"


def _count_leading_spaces(s: str) -> int:
    n = len(s) - len(s.lstrip())
    if n >= 6:
        return 2
    if n >= 2:
        return 1
    return 0


def _build_rows(matrix: list[list[str]], header_row_idx: int) -> list[dict]:
    rows = []
    for i, cells in enumerate(matrix):
        if i == header_row_idx:
            continue
        if not cells or not any(c.strip() for c in cells):
            continue
        label = (cells[0] or "").strip()
        if not label:
            continue
        rows.append({
            "label":  label,
            "values": [c.strip() for c in cells],
            "type":   _classify_row_type(label),
            "indent": _count_leading_spaces(cells[0] or ""),
        })
    return rows


# ── Split de mega-tabela banco ────────────────────────────────────────────────

_SECTION_HDR_PAT = re.compile(r"^\s*\|{1,2}\s*(.+)")
_SECTION_MAP = [
    (re.compile(r"resultado\s*gerencial",                         re.I), "dre"),
    (re.compile(r"balan[cç]o\s*patrimonial",                     re.I), "balanco"),
    (re.compile(r"carteira\s*de\s*cr[eé]dito",                   re.I), "carteira_credito"),
    (re.compile(r"indicadores?\s*(de\s*)?(capital|multiplos|mercado)", re.I), "kpis"),
]
_SECTION_TITLE = {
    "dre":             "DRE — Demonstração do Resultado",
    "balanco":         "Balanço Patrimonial",
    "carteira_credito": "Carteira de Crédito",
    "kpis":            "Indicadores Financeiros e Operacionais",
}


def _split_destaques_table(classified: dict, raw_page: int, columns: list[str]) -> list[dict]:
    sections: dict[str, list[dict]] = {}
    current = "dre"
    for row in classified.get("rows", []):
        m = _SECTION_HDR_PAT.match(row["label"])
        if m:
            hdr = m.group(1).strip()
            for pat, sid in _SECTION_MAP:
                if pat.search(hdr):
                    current = sid
                    break
            continue
        sections.setdefault(current, []).append(row)

    results = []
    for sid, rows in sections.items():
        if len(rows) < 2:
            continue
        results.append({
            "id":             sid,
            "title":          _SECTION_TITLE.get(sid, sid),
            "subtitle":       f"Extraído de Destaques do Resultado · Pág. {raw_page} · {len(rows)} linhas",
            "columns":        columns,
            "rows":           rows,
            "_confidence":    0.85,
            "_priority":      10 if sid == "dre" else 9 if sid == "balanco" else 5,
            "_from_destaques": True,
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# L3: classificador principal
# ─────────────────────────────────────────────────────────────────────────────

def _classify_tables(raw_tables: list[dict]) -> list[dict]:
    """
    Classifica cada tabela bruta em um tipo semântico.

    Ordem de precedência:
      1. Override DFC — âncoras inconfundíveis forçam DFC imediatamente
      2. Scoring normal — hits × priority; vence o maior score com minHits
    """
    results:  list[dict]     = []
    used_ids: dict[str, int] = {}

    # Encontra a assinatura DFC para uso no override
    _dfc_sig = next(s for s in _TABLE_SIGS if s["id"] == "dfc")

    for raw in raw_tables:
        matrix     = raw["matrix"]
        raw_corpus = " ".join(row[0] for row in matrix if row and row[0].strip())
        corpus     = _norm_text(raw_corpus)

        # ── [FIX v2.2] Override DFC — evita DFC → Balanço ────────────────
        if _is_clearly_dfc(raw_corpus):
            best_sig, best_hits, best_score = _dfc_sig, 3, 999
        else:
            best_score, best_sig, best_hits = 0, None, 0
            for sig in _TABLE_SIGS:
                hits  = sum(1 for kw in sig["kws"] if kw.search(corpus))
                score = hits * sig["priority"] if hits >= sig["minHits"] else 0
                if score > best_score:
                    best_score, best_sig, best_hits = score, sig, hits

        if best_sig is None or best_score < 4:
            continue

        confidence = min(best_hits / len(best_sig["kws"]) + 0.1, 1.0)
        sid        = best_sig["id"]
        used_ids[sid] = used_ids.get(sid, 0) + 1
        is_dup        = used_ids[sid] > 1
        final_id      = f"{sid}_{used_ids[sid]}" if is_dup else sid

        header_idx, cols = _detect_headers(matrix)
        rows = _build_rows(matrix, header_idx)
        if len(rows) < 2:
            continue

        classified: dict = {
            "id":              final_id,
            "title":           best_sig["title"] + (" (cont.)" if is_dup else ""),
            "subtitle":        f"Página {raw['page']} · {len(rows)} linhas",
            "columns":         cols,
            "rows":            rows,
            "page":            raw["page"],
            "_confidence":     confidence,
            "_priority":       best_sig["priority"],
            "_from_destaques": False,
        }

        if sid == "destaques_banco":
            results.append(classified)
            for sub in _split_destaques_table(classified, raw["page"], cols):
                existing = next(
                    (r for r in results if r["id"] == sub["id"] and not r.get("_from_destaques")),
                    None,
                )
                if not existing:
                    results.append(sub)
            continue

        results.append(classified)

    results.sort(key=lambda t: t.get("_priority", 0), reverse=True)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Conversão para entidades de domínio
# ─────────────────────────────────────────────────────────────────────────────

def _to_financial_table(t: dict, page: int) -> FinancialTable:
    cols = tuple(str(c) for c in (t.get("columns") or []))
    rows = tuple(
        TableRow(
            label=str(r.get("label", "")),
            values=tuple(str(v) for v in r.get("values", [])[1:]),
        )
        for r in (t.get("rows") or [])
        if r.get("label")
    )
    return FinancialTable(
        id=t.get("id", "unknown"),
        title=t.get("title", ""),
        columns=cols,
        rows=rows,
        page=t.get("page", page),
        confidence=float(t.get("_confidence", 0.7)),
        from_destaques=bool(t.get("_from_destaques", False)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# L1: extração de texto via pdfplumber
# ─────────────────────────────────────────────────────────────────────────────

def _extract_pages(pdf) -> list[dict]:
    pages = []
    for page_num, page in enumerate(pdf.pages, start=1):
        try:
            width  = float(page.width)
            height = float(page.height)
            words  = page.extract_words(x_tolerance=5, y_tolerance=3) or []
            items  = []
            for w in words:
                text = (w.get("text") or "").strip()
                if not text:
                    continue
                x = float(w.get("x0", 0))
                y = float(w.get("top", 0))
                if x < -5:
                    continue
                items.append({"text": text, "x": x, "y": y})
            pages.append({
                "page_num": page_num,
                "items":    items,
                "width":    width,
                "height":   height,
            })
        except Exception:
            continue
    return pages


# ─────────────────────────────────────────────────────────────────────────────
# Interface pública
# ─────────────────────────────────────────────────────────────────────────────

def extract_tables_from_pdf(pdf_bytes: bytes) -> tuple[DocumentMeta, list[FinancialTable]]:
    """
    Pipeline L1→L4 completo.

    Returns:
        (DocumentMeta, list[FinancialTable])
    Raises:
        PdfParsingError
    """
    try:
        pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise PdfParsingError(reason=str(exc)) from exc

    try:
        pages      = _extract_pages(pdf)
        pages_text = [" ".join(i["text"] for i in p["items"]) for p in pages]
        meta       = _extract_meta(pages_text)
        raw_tables = _detect_table_regions(pages)
        classified = _classify_tables(raw_tables)
    finally:
        pdf.close()

    financial_tables: list[FinancialTable] = []
    seen: set[tuple[str, int]] = set()
    for t in classified:
        ft  = _to_financial_table(t, t.get("page", 0))
        key = (ft.id, ft.page)
        if key not in seen:
            seen.add(key)
            financial_tables.append(ft)

    return meta, financial_tables
