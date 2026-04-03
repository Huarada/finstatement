"""
Caso de uso: análise completa de PDF financeiro.

Pipeline:
  1. Extração de tabelas e metadados
  2. Detecção de setor (banco / industrial)
  3. Busca das linhas financeiras por padrões de regex
  4. Normalização de escala (R$ mil vs R$ milhões)
  5. Anualização inteligente (apenas quando dados são trimestrais puros)
  6. Validação de plausibilidade via Pydantic
  7. Cálculo do Buffett Score

Correções v2.2:
  - FCO e CapEx não encontrados → os padrões de regex não cobriam a
    nomenclatura Petrobras. Adicionadas variantes com "líquidos" e
    "e intangíveis".
  - Lucro líquido Petrobras → "Acionistas Petrobras" como fallback do
    total do período.
  - Validação Pydantic garante coerência entre receita e lucro líquido
    antes de prosseguir ao scoring.
"""
from __future__ import annotations

import re
from typing import Optional

from app.core.exceptions import NoTablesFoundError
from app.domain.entities import (
    AnalysisResult,
    BalanceSheet,
    BankMetrics,
    DocumentMeta,
    FinancialTable,
    IncomeStatement,
    SectorType,
)
from app.domain.parsers.column_resolver import best_column_index, _score_header as _col_score
from app.domain.parsers.row_finder import find_row, extract_value
from app.domain.schemas import FinancialDataSchema
from app.domain.scoring.buffett import score_bank, score_industrial
from app.infrastructure.pdf.extractor import extract_tables_from_pdf


# ─────────────────────────────────────────────────────────────────────────────
# Catálogo de padrões de linhas
# ─────────────────────────────────────────────────────────────────────────────

def _p(*patterns: str) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


# Receita / MFB
_PAT_REVENUE = _p(
    r"receita\s*(operacional\s*)?l[íi]quida",
    r"receita\s*de\s*vendas\b",
    r"receita\s*l[íi]quida\s*de\s*vendas",
    r"^receitas?\s*l[íi]quidas?$",
    r"receita\s*total",
    r"receitas?\s*totais?\b",
    r"resultado\s*l[íi]quido\s*com\s*instrumentos\s*financeiros",
    r"resultado\s*bruto\s*da\s*intermedia",
    r"vendas\s*l[íi]quidas?",
)

# Lucro Bruto / MFB
_PAT_GROSS = _p(
    r"^lucro\s*bruto$",
    r"lucro\s*bruto\b",
    r"margem\s*financeira\s*bruta",
    r"resultado\s*l[íi]quido\s*com\s*instrumentos\s*financeiros",
    r"resultado\s*bruto\s*da\s*intermedia",
    r"margem\s*financeira\b",
)

# Lucro Líquido
_PAT_NET_INCOME = _p(
    r"lucro\s*l[íi]quido\s*ajustado",
    r"lucro\s*\(prej[uú]izo\)\s*l[íi]quido",
    r"lucro.*l[íi]quido.*per[íi]odo",
    r"resultado\s*l[íi]quido\s*do\s*(exerc[íi]cio|per[íi]odo)",
    r"^lucro\s*l[íi]quido$",
    r"lucro\s*l[íi]quido\b",
    r"resultado\s*l[íi]quido\b",
    # [FIX v2.2] Petrobras: "Acionistas Petrobras" é a linha de atribuição
    # do lucro e é o fallback quando a linha "do período" não é capturada.
    r"acionistas\s+petrobras",
    r"acionistas\s+da\s+controladora",
)

# Resultado Operacional / EBIT
_PAT_OPER = _p(
    r"resultado\s*operacional\s*antes",
    r"^resultado\s*operacional$",
    r"resultado\s*operacional\b",
    r"lucro\s*operacional\s*antes\s*da\s*tributa[cç][aã]o",
    r"^lucro\s*operacional$",
    r"lucro\s*operacional\b",
    r"^ebit\b",
    r"lucro\s*antes\s*do\s*ir",
    r"resultado\s*antes\s*do\s*(ir|imposto)",
    r"lucro\s*antes\s*do\s*resultado\s*financeiro",
)

# Despesas G&A
_PAT_GA = _p(
    r"total\s*despesas?\s*gerais\s*e\s*adm",
    r"despesas?\s*gerais\s*e\s*adm",
    r"^despesas?\s*administrativas$",
    r"despesas?\s*administrativas\b",
    r"despesas?\s*de\s*pessoal",
    r"despesas?\s*com\s*(vendas|comerciais?)\s*e\s*adm",
    r"despesas?\s*operacionais\b",
)

# Depreciação & Amortização
_PAT_DA = _p(
    r"deprecia[cç][aã]o[,\s].*amortiza[cç][aã]o",
    r"deprecia[cç][aã]o\s*e\s*amortiza[cç][aã]o",
    r"deprecia[cç][aã]o.*exaust[aã]o",
    r"^deprecia[cç][aã]o$",
    r"amortiza[cç][aã]o\s*de\s*intang[íi]vel",
    r"deprecia[cç][aã]o,\s*deple[cç][aã]o\s*e\s*amortiza[cç][aã]o",
)

# Despesas Financeiras
_PAT_INTEREST = _p(
    r"despesas?\s*financeiras\b",
    r"resultado\s*financeiro\s*l[íi]quido",
    r"resultado\s*financeiro\b",
    r"receitas?\s*\(despesas?\)\s*financeiras?",
    r"despesas?\s*de\s*juros",
    r"encargos?\s*financeiros",
    r"juros\s*(e\s*)?encargos",
)

# Fluxo de Caixa Operacional
_PAT_FCO = _p(
    # [FIX v2.2] Petrobras: "líquidos" ausente no padrão anterior
    r"recursos?\s*l[íi]quidos?\s*gerados?\s*(pelas?\s*)?atividades?\s*operac",
    r"recursos?\s*l[íi]quidos?\s*utilizados?\s*(nas?\s*)?atividades?\s*operac",
    r"recursos?\s*gerados?\s*(pelas?\s*)?atividades?\s*operac",
    # [FIX v2.3] Petrobras 4T25: "operacionais" fica na linha seguinte (label truncado
    # por quebra de linha no PDF). Padrão mais permissivo que captura o label parcial
    # mas específico o suficiente para não confundir com atividades de investimento/financiamento.
    r"recursos?\s*l[íi]quidos?\s*gerados?\s*pelas?\s*atividades?\s*(?:operac)?$",
    # BTG / demais
    r"caixa\s*(utilizado|proveniente)\s*[/\/]\s*(proveniente|utilizado)\s*das?\s*atividades?\s*operac",
    r"caixa\s*l[íi]quido\s*gerado\s*nas?\s*atividades?\s*operac",
    r"caixa\s*l[íi]quido\s*(das?\s*)?atividades?\s*operac",
    r"^atividades?\s*operacionais$",
    r"fluxo\s*de\s*caixa\s*das?\s*atividades?\s*operac",
)

# CapEx
_PAT_CAPEX = _p(
    # [FIX v2.2] Petrobras: "e intangíveis" ausente no padrão anterior
    r"aquisi[cç]\w*\s*de\s*ativos?\s*imobilizados?\s*(e\s*intang[íi]veis?)?",
    r"adi[cç][oõ]es?\s*de\s*imobilizado",
    r"aquisi[cç]\w*\s*[/\/]\s*aliena[cç]\w*\s*de\s*imobilizado",
    r"investimentos?\s*em\s*imobilizado",
    r"\bcapex\b",
    r"compras?\s*de\s*(ativo|imobilizado|propriedade)",
)

# Balanço
_PAT_ASSETS     = _p(
    r"total\s*do\s*ativo\b", r"^ativo\s*total$",
    r"^total\s*de\s*ativos?$", r"total\s*ativo\b",
    r"^ativo$", r"soma\s*do\s*ativo",
)
_PAT_CURR_ASSETS = _p(
    r"total\s*do\s*ativo\s*circulante",
    r"^ativo\s*circulante$", r"ativo\s*circulante\b",
)
_PAT_CURR_LIAB   = _p(
    r"total\s*do\s*passivo\s*circulante",
    r"^passivo\s*circulante$", r"passivo\s*circulante\b",
)
_PAT_EQUITY      = _p(
    r"^patrim[oô]nio\s*l[íi]quido$",
    r"patrim[oô]nio\s*l[íi]quido\s*total",
    r"patrim[oô]nio\s*l[íi]quido\b",
    r"total\s*do\s*patrim[oô]nio",
    r"total\s*patrim[oô]nio", r"equity\b",
    # [FIX v2.3] Petrobras p.24: PL total no Balanço de 2 páginas
    r"atribu[íi]do\s*aos?\s*acionistas\s*da\s*controladora$",
)
_PAT_DEBT        = _p(
    r"d[íi]vida\s*bruta\s*total\b", r"^d[íi]vida\s*bruta$",
    r"d[íi]vida\s*bruta\b",
    r"empr[eé]stimos?,?\s*financiam\w*\s*e\s*deb[eê]ntures",
    r"empr[eé]stimos?\s*e\s*financiam\w*\b",
    r"capta[cç][oõ]es?\s*no\s*mercado",
)
_PAT_RETAINED    = _p(
    r"^reservas?\s*de\s*lucros?$",   # [FIX v2.3] match mais preciso (p.24)
    r"reservas?\s*de\s*lucros?",
    r"^lucros?\s*acumulados?$",
    r"lucros?\s*acumulados?\b", r"resultado\s*acumulado",
    r"prejuízos?\s*acumulados?",
)
_PAT_TREASURY    = _p(
    r"a[cç][oõ]es?\s*em\s*tesouraria", r"treasury",
    # [FIX v2.3] Petrobras p.24 combina ações em tesouraria com reserva de capital
    r"reserva\s*de\s*capital.*a[cç][oõ]es\s*em\s*tesouraria",
)

# Métricas bancárias
_PAT_MFB         = _p(
    r"margem\s*financeira\s*bruta",
    r"resultado\s*l[íi]quido\s*com\s*instrumentos\s*financeiros",
    r"resultado\s*bruto\s*da\s*intermedia",
)
_PAT_CREDIT_COST = _p(
    r"custo\s*do\s*cr[eé]dito",
    r"perdas?\s*esperadas?\s*decorrentes?\s*de\s*risco",
    r"perda\s*esperada", r"pcld",
)
_PAT_ADM_EXP  = _p(r"despesas?\s*administrativas")
_PAT_SVC_REV  = _p(
    r"receitas?\s*de\s*presta[cç][aã]o\s*de\s*servi[cç]os?",
    r"receitas?\s*de\s*servi[cç]os?",
)
_PAT_RSPL = _p(r"rspl|retorno.*patrim[oô]nio", r"roe\b")
_PAT_ROA  = _p(r"retorno\s*(sobre|s\/)\s*ativos?|roa\b")
_PAT_EFIC = _p(r"[íi]ndice\s*de\s*efici[eê]ncia", r"efficiency\s*ratio")
_PAT_NPL  = _p(r"inad\+?90|inadimpl[eê]ncia.*90|atraso.*90")
_PAT_BASEL = _p(r"[íi]ndice\s*de\s*basileia", r"basileia\s*total")

_BANK_NAME_PAT = re.compile(
    r"\b(banco|itaú|bradesco|santander|btg|caixa\s*econ|nubank|xp\s*inc"
    r"|c6\s*bank|sicoob|sicredi|inter\s*bank|bbi|bmg|safra)\b",
    re.IGNORECASE,
)
_BANK_DRE_PAT = re.compile(
    r"\b(margem\s*financeira|resultado\s*bruto\s*da\s*intermedia"
    r"|[íi]ndice\s*de\s*basileia|carteira\s*de\s*cr[eé]dito"
    r"|resultado\s*l[íi]quido\s*com\s*instrumentos\s*financeiros)\b",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _table_by_id(tables: list[FinancialTable], *ids: str) -> list[FinancialTable]:
    result = []
    for t in tables:
        for base_id in ids:
            if t.id == base_id or t.id.startswith(base_id + "_"):
                result.append(t)
                break
    return result


def _column_quality(t: FinancialTable) -> float:
    """
    Score de qualidade de colunas de uma tabela.

    Tabelas com cabeçalhos de período reconhecidos (4T25, 2025…) têm score > 1.0.
    Tabelas com colunas-fallback ("Variação", genéricas) têm score ≈ 5.0 (ruído).
    Tabelas com período real têm score ≥ 9.0 (anuais) ou 1.0 (trimestrais).

    Objetivo: priorizar tabelas financeiras reais sobre tabelas de segmento
    ou KPIs com colunas de variação detectados como DRE.
    """
    if not t.columns or len(t.columns) < 2:
        return -1.0
    try:
        idx   = best_column_index(t.columns)
        score = _col_score(str(t.columns[idx]))
        # Score 5.0 = fallback genérico (sem padrão de período reconhecido)
        # Score 1.0 = trimestral reconhecido (4T25, 1Q24…) → tabela financeira real
        # Se nenhuma coluna tem padrão reconhecido, retorna penalidade
        if score <= 0:
            return -10.0   # coluna excluída ou vazia
        if abs(score - 5.0) < 0.1:
            return 0.0     # fallback genérico → penalidade leve
        return score       # período reconhecido → score alto
    except Exception:
        return -1.0


def _get_val(
    patterns: list[re.Pattern],
    *tables: Optional[FinancialTable],
    multiplier: float = 1.0,
) -> Optional[float]:
    match = find_row(patterns, *tables)
    if match is None or match.value is None:
        return None
    return match.value * multiplier


def _get_pct(patterns: list[re.Pattern], *tables: Optional[FinancialTable]) -> Optional[float]:
    for table in tables:
        if table is None:
            continue
        for pat in patterns:
            row = next((r for r in table.rows if pat.search(r.label)), None)
            if row is None:
                continue
            for raw in reversed(row.values):
                clean = str(raw or "").replace("%", "").replace(",", ".").strip()
                try:
                    n = float(clean)
                    if 0 < abs(n) <= 200:
                        return n / 100
                except ValueError:
                    continue
    return None


def _detect_sector(meta: DocumentMeta, tables: list[FinancialTable]) -> SectorType:
    all_text    = " ".join(
        t.title + " " + " ".join(r.label for r in t.rows[:20])
        for t in tables
    )
    company_text = (meta.company + " " + all_text[:500]).lower()
    if _BANK_NAME_PAT.search(company_text):
        return SectorType.BANK
    if _BANK_DRE_PAT.search(all_text):
        return SectorType.BANK
    return SectorType.INDUSTRIAL


def _has_buyback(tables: list[FinancialTable]) -> bool:
    for table in tables:
        for row in table.rows:
            if re.search(r"tesouraria|recompra|buyback|treasury", row.label, re.I):
                if any(v.strip() not in ("", "-", "—", "0") for v in row.values):
                    return True
    return False


def _detect_scale_factor(
    income: IncomeStatement,
    balance_raw: dict[str, Optional[float]],
) -> float:
    rev = income.revenue
    if rev is None or rev <= 0:
        return 1.0
    bal_vals = [abs(v) for v in balance_raw.values() if v is not None and abs(v) > 0]
    if not bal_vals:
        return 1.0
    ratio = max(bal_vals) / abs(rev)
    if ratio > 500:
        return 1.0 / 1_000.0
    if ratio > 500_000:
        return 1.0 / 1_000_000.0
    return 1.0


def _effective_annualization_factor(tables: list[FinancialTable], meta_factor: int) -> float:
    """
    Retorna 1.0 quando a melhor coluna das tabelas de DRE já é anual,
    evitando anualização dupla.

    Threshold ≥ 9.0 captura:
    - Explicitamente anuais: 12M25, Exercício → score ≥ 10.0
    - Ano isolado: "2025", "2024" → score ≈ 9.25
      (colunas acumuladas em releases de resultados trimestrais, ex: Petrobras 4T25)

    [FIX v2.3] era 10.0 — não detectava colunas "2025"/"2024" como anuais,
    causando anualização × 4 incorreta em releases com coluna anual explícita.
    """
    INCOME_IDS = {"dre", "ebitda", "kpis", "destaques_banco"}
    for t in tables:
        base = t.id.split("_")[0]
        if base not in INCOME_IDS:
            continue
        if not t.columns or len(t.columns) < 2:
            continue
        try:
            idx   = best_column_index(t.columns)
            score = _col_score(str(t.columns[idx]))
            if score >= 9.0:
                return 1.0
        except Exception:
            continue
    return float(meta_factor)


# ─────────────────────────────────────────────────────────────────────────────
# Caso de uso público
# ─────────────────────────────────────────────────────────────────────────────

def analyze_pdf(pdf_bytes: bytes) -> AnalysisResult:
    """
    Pipeline completo de análise de PDF financeiro.

    Raises:
        PdfParsingError: PDF ilegível.
        NoTablesFoundError: Nenhuma tabela financeira detectada.
    """
    meta, tables = extract_tables_from_pdf(pdf_bytes)

    if not tables:
        from pypdf import PdfReader
        import io as _io
        try:
            n = len(PdfReader(_io.BytesIO(pdf_bytes)).pages)
        except Exception:
            n = 0
        raise NoTablesFoundError(total_pages=n)

    # ── Deduplicação: máx. 3 tabelas DRE ─────────────────────────────────
    # Ordena por qualidade de coluna (tabelas com período reconhecido primeiro),
    # depois por página. Garante que tabelas com colunas genéricas/fallback
    # (ex: "Variação", segmentos) não suprimam o DRE real.
    _MAX_DRE_TABLES = 3
    dre_all = sorted(
        _table_by_id(tables, "dre"),
        key=lambda t: (-_column_quality(t), t.page),  # quality desc, page asc
    )
    if len(dre_all) > _MAX_DRE_TABLES:
        dre_drop = {id(t) for t in dre_all[_MAX_DRE_TABLES:]}
        tables   = [t for t in tables if id(t) not in dre_drop]

    # ── Segregação por tipo ───────────────────────────────────────────────
    dre_tables    = _table_by_id(tables, "dre")
    bal_tables    = _table_by_id(tables, "balanco")
    dfc_tables    = _table_by_id(tables, "dfc")
    ebitda_tables = _table_by_id(tables, "ebitda")
    kpi_tables    = _table_by_id(tables, "kpis")
    dest_dre      = [t for t in dre_tables  if t.from_destaques]
    dest_bal      = [t for t in bal_tables  if t.from_destaques]
    dest_kpi      = [t for t in kpi_tables  if t.from_destaques]
    dest_all      = [t for t in tables if t.from_destaques]
    all_dre       = dre_tables
    all_bal       = bal_tables + dfc_tables   # DFC como fallback para FCO/CapEx

    # ── Fator de anualização ──────────────────────────────────────────────
    af     = _effective_annualization_factor(tables, meta.annualization_factor)
    sector = _detect_sector(meta, tables)

    # ── Demonstração do Resultado ─────────────────────────────────────────
    income_raw = IncomeStatement(
        revenue=_get_val(
            _PAT_REVENUE, *dest_dre, *dest_all, *dre_tables, *ebitda_tables, *kpi_tables,
            multiplier=af,
        ),
        gross_profit=_get_val(
            _PAT_GROSS, *dest_dre, *dest_all, *dre_tables, *ebitda_tables,
            multiplier=af,
        ),
        net_income=_get_val(
            _PAT_NET_INCOME, *dest_dre, *dest_all, *dre_tables, *ebitda_tables, *kpi_tables,
            multiplier=af,
        ),
        operating_income=_get_val(
            _PAT_OPER, *dre_tables, *ebitda_tables, *all_dre,
            multiplier=af,
        ),
        selling_expenses=None,
        ga_expenses=_get_val(
            _PAT_GA, *dest_dre, *dest_all, *dre_tables,
            multiplier=af,
        ),
        da_expenses=_get_val(
            _PAT_DA, *dre_tables, *ebitda_tables, *all_dre, *all_bal,
            multiplier=af,
        ),
        interest_expenses=_get_val(
            _PAT_INTEREST, *dre_tables, *ebitda_tables, *all_dre,
            multiplier=af,
        ),
        # [FIX v2.2] dfc_tables agora corretamente classificado →
        # FCO e CapEx encontrados. all_bal mantido como fallback.
        operating_cash_flow=_get_val(_PAT_FCO, *dfc_tables, *all_bal),
        capex=_get_val(_PAT_CAPEX, *dfc_tables, *all_bal, *all_dre),
    )

    # ── Balanço Patrimonial ───────────────────────────────────────────────
    _bal_raw: dict[str, Optional[float]] = {
        "total_assets":        _get_val(_PAT_ASSETS,      *dest_bal, *dest_all, *bal_tables),
        "current_assets":      _get_val(_PAT_CURR_ASSETS,  *dest_bal, *bal_tables),
        "current_liabilities": _get_val(_PAT_CURR_LIAB,    *dest_bal, *bal_tables),
        "equity":              _get_val(_PAT_EQUITY,       *dest_bal, *dest_all, *bal_tables),
        "gross_debt":          _get_val(_PAT_DEBT,         *bal_tables, *dest_bal),
        "retained_earnings":   _get_val(_PAT_RETAINED,     *dest_bal, *bal_tables),
        "treasury_shares":     _get_val(_PAT_TREASURY,     *dest_bal, *bal_tables),
    }

    scale    = _detect_scale_factor(income_raw, _bal_raw)
    if scale != 1.0:
        _bal_raw = {k: (v * scale if v is not None else None) for k, v in _bal_raw.items()}

    # ── Validação Pydantic ────────────────────────────────────────────────
    # Descarta valores que contradizem relações contábeis básicas
    # (e.g. lucro líquido > 5× receita → erro de unidade de escala).
    validated = FinancialDataSchema.from_raw(
        income_kwargs={
            "revenue":             income_raw.revenue,
            "gross_profit":        income_raw.gross_profit,
            "net_income":          income_raw.net_income,
            "operating_income":    income_raw.operating_income,
            "selling_expenses":    income_raw.selling_expenses,
            "ga_expenses":         income_raw.ga_expenses,
            "da_expenses":         income_raw.da_expenses,
            "interest_expenses":   income_raw.interest_expenses,
            "operating_cash_flow": income_raw.operating_cash_flow,
            "capex":               income_raw.capex,
        },
        balance_kwargs=_bal_raw,
    )

    income  = IncomeStatement(
        revenue=validated.income.revenue,
        gross_profit=validated.income.gross_profit,
        net_income=validated.income.net_income,
        operating_income=validated.income.operating_income,
        selling_expenses=validated.income.selling_expenses,
        ga_expenses=validated.income.ga_expenses,
        da_expenses=validated.income.da_expenses,
        interest_expenses=validated.income.interest_expenses,
        operating_cash_flow=validated.income.operating_cash_flow,
        capex=validated.income.capex,
    )
    balance = BalanceSheet(
        total_assets=validated.balance.total_assets,
        current_assets=validated.balance.current_assets,
        current_liabilities=validated.balance.current_liabilities,
        equity=validated.balance.equity,
        gross_debt=validated.balance.gross_debt,
        retained_earnings=validated.balance.retained_earnings,
        treasury_shares=validated.balance.treasury_shares,
    )

    # ── Métricas bancárias ────────────────────────────────────────────────
    bank_metrics: Optional[BankMetrics] = None
    if sector == SectorType.BANK:
        mfb_raw = _get_val(_PAT_MFB, *dest_dre, *dest_all, *dre_tables, *kpi_tables)
        mfb     = mfb_raw * af if mfb_raw else None
        cc_raw  = _get_val(_PAT_CREDIT_COST, *dest_dre, *dest_all, *dre_tables)
        cc      = abs(cc_raw) * af if cc_raw else None
        adm_raw = _get_val(_PAT_ADM_EXP, *dest_dre, *dest_all, *dre_tables)
        adm     = abs(adm_raw) * af if adm_raw else None
        svc_raw = _get_val(_PAT_SVC_REV, *dest_dre, *dest_all, *dre_tables)
        svc     = abs(svc_raw) * af if svc_raw else None

        roe_direct = _get_pct(_PAT_RSPL, *kpi_tables, *dest_kpi, *dest_all)
        roa_direct = _get_pct(_PAT_ROA,  *kpi_tables, *dest_kpi, *dest_all)
        ll  = income.net_income
        pl  = balance.equity
        at  = balance.total_assets
        roe = roe_direct or (ll / abs(pl)  if ll and pl and pl != 0 else None)
        roa = roa_direct or (ll / at       if ll and at and at > 0 else None)
        efic = _get_pct(_PAT_EFIC, *kpi_tables, *dest_kpi, *dest_all) or (
            adm / (mfb + (svc or 0))
            if adm and mfb and (mfb + (svc or 0)) > 0
            else None
        )
        bank_metrics = BankMetrics(
            mfb=mfb, credit_cost=cc, admin_expenses=adm, service_revenue=svc,
            roe=roe, roa=roa, efficiency_ratio=efic,
            npl_ratio=_get_pct(_PAT_NPL,  *kpi_tables, *dest_kpi, *dest_all, *dre_tables),
            basel_ratio=_get_pct(_PAT_BASEL, *kpi_tables, *dest_kpi, *dest_all),
            has_buyback=_has_buyback(tables),
        )

    # ── Buffett Score ──────────────────────────────────────────────────────
    buffett = (
        score_bank(income, balance, bank_metrics)
        if sector == SectorType.BANK and bank_metrics
        else score_industrial(income, balance)
    )

    return AnalysisResult(
        meta=meta, tables=tables, income=income, balance=balance,
        bank_metrics=bank_metrics, buffett=buffett, sector=sector,
        debug_info={
            "total_pages":            "n/a",
            "tables_found":           len(tables),
            "scale_factor":           scale,
            "effective_af":           af,
            "meta_af":                meta.annualization_factor,
            "dfc_tables_found":       len(dfc_tables),
            "tables_by_id":           {
                t.id: {
                    "title":          t.title,
                    "rows":           len(t.rows),
                    "page":           t.page,
                    "best_col":       str(t.columns[best_column_index(t.columns)])
                                      if len(t.columns) > 1 else "?",
                    "best_col_score": round(
                        _col_score(str(t.columns[best_column_index(t.columns)])), 2
                    ) if len(t.columns) > 1 else 0,
                }
                for t in tables
            },
            "period_type":            meta.period_type.value,
            "annualization_factor":   meta.annualization_factor,
            "sector":                 sector.value,
        },
    )
