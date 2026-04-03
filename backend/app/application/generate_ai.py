"""
GenerateAiInsights use case.

v3.1 — Forced data-anchoring for *Desc fields:
  - _build_score_desc_hints() generates explicit, per-field data citations
    from the pre-computed financial numbers, injected directly before the
    JSON schema so the model cannot ignore them.
  - Schema placeholders rewritten to show the expected citation format.
  - _SCORE_DERIVATION_RULES strengthened with PROIBIÇÃO explicit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from app.application.ai_providers import (
    AiProvider,
    ProviderError,
    detect_provider_from_key,
    get_provider,
)
from app.core.config import settings
from app.core.exceptions import AiProviderError
from app.domain.entities import AnalysisResult, SectorType


# ─────────────────────────────────────────────────────────────────────────────
# Domain dataclasses — mirror the frontend JSON schema exactly
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Highlight:
    text: str
    confidence: int
    reason: str


@dataclass
class PorterForce:
    name: str
    label: str
    score: int
    comment: str


@dataclass
class Contradiction:
    found: bool
    text: str


@dataclass
class AiAnalysis:
    highlights: list[Highlight] = field(default_factory=list)
    challenges: list[Highlight] = field(default_factory=list)
    swot: dict[str, list[str]] = field(default_factory=dict)
    porter: dict[str, PorterForce] = field(default_factory=dict)
    market_position: str = ""
    admin_insights: str = ""
    ir_reliability: str = ""


@dataclass
class AiConclusion:
    verdict: str = "AGUARDAR"
    verdict_class: str = "neutral"
    summary: str = ""
    risk_score: int = 5
    risk_label: str = ""
    risk_desc: str = ""
    growth_score: int = 5
    growth_label: str = ""
    growth_desc: str = ""
    reliability_score: int = 5
    reliability_label: str = ""
    reliability_desc: str = ""
    confidence_level: str = "MÉDIA"
    contradictions: list[Contradiction] = field(default_factory=list)
    catalysts: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    final_paragraph: str = ""


@dataclass
class AiInsights:
    provider: str
    analysis: AiAnalysis
    conclusion: AiConclusion


# ─────────────────────────────────────────────────────────────────────────────
# Context builders
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_currency(v: Optional[float]) -> str:
    return f"R${v:,.0f}M" if v is not None else "N/D"


def _build_table_context(result: AnalysisResult) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for table in result.tables[:12]:
        base_id = table.id.split("_")[0]
        if base_id in seen:
            continue
        seen.add(base_id)
        lines.append(f"\n[{table.title}]")
        if table.columns:
            lines.append("  " + " | ".join(str(c) for c in table.columns[:6]))
        for row in table.rows[:30]:
            vals = " | ".join(str(v) for v in row.values[:5])
            lines.append(f"  {row.label}: {vals}")
    return "\n".join(lines) if lines else "(nenhuma tabela extraída)"


def _build_financial_summary(result: AnalysisResult) -> str:
    inc = result.income
    bal = result.balance
    return "\n".join([
        f"Receita Líquida:     {_fmt_currency(inc.revenue)}",
        f"Lucro Bruto/MFB:     {_fmt_currency(inc.gross_profit)}",
        f"Lucro Líquido:       {_fmt_currency(inc.net_income)}",
        f"Result. Operacional: {_fmt_currency(inc.operating_income)}",
        f"Despesas G&A:        {_fmt_currency(inc.ga_expenses)}",
        f"D&A:                 {_fmt_currency(inc.da_expenses)}",
        f"FCO:                 {_fmt_currency(inc.operating_cash_flow)}",
        f"CapEx:               {_fmt_currency(inc.capex)}",
        f"Ativo Total:         {_fmt_currency(bal.total_assets)}",
        f"Patrimônio Líquido:  {_fmt_currency(bal.equity)}",
        f"Dívida Bruta:        {_fmt_currency(bal.gross_debt)}",
    ])


def _build_buffett_context(result: AnalysisResult) -> str:
    buf = result.buffett
    icon_map = {"green": "✅", "yellow": "⚠️", "red": "❌"}
    metric_lines = "\n".join(
        f"  {icon_map.get(m.status.value, '—')} {m.name}: "
        f"{m.formatted_value} ({m.points}/{m.max_points} pts)"
        for m in buf.metrics
    ) or "  (sem métricas calculadas)"
    return f"BUFFETT SCORE: {buf.score_100}/100 — {buf.label}\n{metric_lines}"


def _compute_derived_ratios(result: AnalysisResult) -> str:
    inc = result.income
    bal = result.balance
    buf = result.buffett

    green_count = sum(1 for m in buf.metrics if m.status.value == "green")
    red_count   = sum(1 for m in buf.metrics if m.status.value == "red")
    extracted   = sum(1 for m in buf.metrics if m.status.value != "unavailable")

    lines: list[str] = []
    if inc.revenue and inc.net_income:
        lines.append(f"- Margem líquida: {inc.net_income / inc.revenue * 100:.1f}%")
    if inc.revenue and inc.gross_profit:
        lines.append(f"- Margem bruta: {inc.gross_profit / inc.revenue * 100:.1f}%")
    if bal.gross_debt is not None and bal.equity and bal.equity != 0:
        lines.append(f"- Alavancagem (Dívida/PL): {bal.gross_debt / bal.equity:.2f}x")
    if inc.operating_cash_flow is not None and inc.capex is not None:
        fcf = inc.operating_cash_flow - abs(inc.capex)
        lines.append(f"- FCF estimado: {_fmt_currency(fcf)}")
    if inc.net_income and bal.equity and bal.equity != 0:
        lines.append(f"- ROE: {inc.net_income / abs(bal.equity) * 100:.1f}%")
    if inc.net_income and bal.total_assets and bal.total_assets > 0:
        lines.append(f"- ROA: {inc.net_income / bal.total_assets * 100:.2f}%")
    lines.extend([
        f"- Métricas Buffett extraídas: {extracted}/{len(buf.metrics)}",
        f"- Métricas verdes: {green_count} | vermelhas: {red_count}",
        f"- Buffett Score: {buf.score_100}/100",
    ])
    return "\n".join(lines)


def _resolve_verdict_guidance(result: AnalysisResult) -> str:
    buf = result.buffett
    extracted = sum(1 for m in buf.metrics if m.status.value != "unavailable")
    if buf.score_100 >= 75:
        return "FORTE MOAT DURÁVEL — veredito pode ser COMPRAR se qualitativos confirmam."
    if buf.score_100 >= 55:
        return "VANTAGEM MODERADA — veredito COMPRAR ou AGUARDAR conforme momentum."
    if buf.score_100 >= 35:
        return "SEM MOAT CLARO — prefira AGUARDAR ou VENDER salvo catalisador concreto."
    if buf.score_100 > 0:
        return "CAPITAL-INTENSIVO SEM MOAT — AGUARDAR ou VENDER."
    if extracted == 0:
        return "SCORE ZERO SEM DRE — veredito AGUARDAR obrigatório, confidenceLevel=BAIXA."
    return "SCORE ZERO COM DRE — métricas em nível crítico. AGUARDAR ou VENDER."


# ─────────────────────────────────────────────────────────────────────────────
# [NEW v3.1] Score desc hints — explicit data anchors per field
# ─────────────────────────────────────────────────────────────────────────────

def _build_score_desc_hints(result: AnalysisResult) -> str:
    """
    Generate per-field data citations that the model MUST copy verbatim into
    riskDesc, growthDesc and reliabilityDesc.

    Each hint lists the exact numbers available for that field so the model
    cannot fall back to generic language.  Placed immediately before the JSON
    schema so it takes priority over earlier instructions.
    """
    inc = result.income
    bal = result.balance
    buf = result.buffett

    extracted   = sum(1 for m in buf.metrics if m.status.value != "unavailable")
    green_count = sum(1 for m in buf.metrics if m.status.value == "green")
    red_count   = sum(1 for m in buf.metrics if m.status.value == "red")

    # ── riskDesc ──────────────────────────────────────────────────────────
    risk_parts: list[str] = []
    if bal.gross_debt is not None and bal.equity and bal.equity != 0:
        lev = bal.gross_debt / bal.equity
        risk_parts.append(f"Dívida/PL = {lev:.2f}x")
    else:
        risk_parts.append("Dívida bruta = N/D (incerteza = risco)")

    if inc.revenue and inc.net_income:
        ml = inc.net_income / inc.revenue * 100
        risk_parts.append(f"Margem líquida = {ml:.1f}%")

    if inc.operating_cash_flow is not None and inc.capex is not None:
        fcf = inc.operating_cash_flow - abs(inc.capex)
        risk_parts.append(f"FCF = {_fmt_currency(fcf)}")

    if red_count:
        risk_parts.append(f"{red_count} métrica(s) Buffett vermelha(s)")

    # ── growthDesc ────────────────────────────────────────────────────────
    growth_parts: list[str] = []
    if inc.revenue and inc.gross_profit:
        mb = inc.gross_profit / inc.revenue * 100
        growth_parts.append(f"Margem bruta = {mb:.1f}%")

    if inc.operating_cash_flow is not None and inc.capex is not None:
        fcf = inc.operating_cash_flow - abs(inc.capex)
        growth_parts.append(f"FCF = {_fmt_currency(fcf)}")

    if inc.capex is not None:
        growth_parts.append(f"CapEx = {_fmt_currency(inc.capex)}")

    if not growth_parts:
        growth_parts.append("dados de crescimento insuficientes (N/D)")

    # ── reliabilityDesc ───────────────────────────────────────────────────
    rel_parts: list[str] = [
        f"{extracted}/{len(buf.metrics)} métricas extraídas",
        f"{green_count} verdes / {red_count} vermelhas",
        f"Score {buf.score_100}/100",
    ]
    if inc.revenue and bal.total_assets:
        rel_parts.append(
            f"Receita = {_fmt_currency(inc.revenue)} | "
            f"Ativo = {_fmt_currency(bal.total_assets)}"
        )

    return (
        "ATENÇÃO — PREENCHIMENTO OBRIGATÓRIO DOS CAMPOS *Desc:\n"
        "Os campos riskDesc, growthDesc e reliabilityDesc NÃO PODEM conter texto genérico.\n"
        "Cada campo deve ser UMA frase curta (máx. 20 palavras) citando os dados abaixo:\n\n"
        f"  riskDesc  → cite: {' | '.join(risk_parts)}\n"
        f"  growthDesc → cite: {' | '.join(growth_parts)}\n"
        f"  reliabilityDesc → cite: {' | '.join(rel_parts)}\n\n"
        "Formato esperado (exemplos de estrutura, NÃO copiar literalmente):\n"
        '  riskDesc: "Dívida/PL de X.XXx e margem líquida de Y.Y% sustentam risco [label]."\n'
        '  growthDesc: "Margem bruta de XX.X% e FCF de R$XXXm indicam [perspectiva]."\n'
        '  reliabilityDesc: "X/12 métricas extraídas com Score YY/100 conferem confiabilidade [label]."\n'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Prompt assembly
# ─────────────────────────────────────────────────────────────────────────────

_SCORE_DERIVATION_RULES = """
REGRAS OBRIGATÓRIAS PARA SCORES (1–10):

riskScore — DERIVE dos dados acima:
  • Alavancagem (Dívida/PL): >2x → score 7-10; 1-2x → 4-6; <1x → 1-3
  • Margem líquida negativa → adicione +2 ao risco
  • FCF negativo → adicione +2 ao risco
  • Cada métrica Buffett vermelha → +0.5
  • Sem dados de dívida → score ≥ 6 (incerteza = risco)

growthScore — DERIVE dos dados acima:
  • Margem bruta >40% → base 6-8; 20-40% → base 4-6; <20% → base 2-4
  • FCF positivo e crescente → +1 a +2
  • CAPEX alto com FCF positivo (reinvestimento) → +1
  • Dados insuficientes → score ≤ 4 com growthLabel="Incerto"

reliabilityScore — DERIVE dos dados acima:
  • Quantidade de tabelas extraídas com dados completos
  • Métricas Buffett extraídas vs. total possível
  • Consistência entre DRE e Balanço (lucro vs PL, receita vs ativos)
  • Dados faltantes ou inconsistentes → score ≤ 4

PROIBIÇÕES ABSOLUTAS:
  • riskScore, growthScore e reliabilityScore NÃO PODEM ser iguais entre si.
  • NÃO use os valores 5, 6, 7 simultaneamente nos três campos.
  • riskDesc, growthDesc e reliabilityDesc NÃO PODEM conter "ausência de dados",
    "falta de informações" ou qualquer texto genérico — DEVEM citar números reais."""

_ANALYSIS_QUALITY_RULES = """
REGRAS DE QUALIDADE E RIGOR INSTITUCIONAL — cada afirmação deve ser ancorada nos dados frios:

SWOT:
  • Cada item DEVE conter um número do relatório (ex: margem, alavancagem, giro). Seja cirúrgico.
  • "Marca forte" ou "líder de mercado" SÓ se houver evidência de 'pricing power' ou market share.
  • Weaknesses: foque em queima de caixa (cash burn), alavancagem perigosa ou compressão de margens.
  • Opportunities/Threats: ignore obviedades macroeconômicas. Foque em dinâmicas setoriais diretas.

PORTER (5 Forças):
  • rivalry: nomeie concorrentes reais do setor. Avalie consolidação e guerra de preços.
  • newEntrants: avalie barreiras reais (moats de custo, switching costs, CAPEX, regulação).
  • suppliers: identifique gargalos na cadeia de suprimentos e poder de repasse de preço.
  • buyers: analise concentração de receita e elasticidade-preço.
  • substitutes: cite ameaças reais (tecnológicas ou de mudança de modelo de negócio).
  • Cada comment com 2-3 frases de raciocínio crítico, CÉTICO e NÃO genérico.

HIGHLIGHTS / CHALLENGES:
  • Citar valores numéricos do relatório (ex: "compressão de margem bruta para 42,3%").
  • reason: indicar tabela/linha de origem.
  • confidence: 9-10 apenas para dados contábeis reportados (DRE/Balanço); 5-6 para guidances.

marketPosition: exija evidência de vantagens competitivas sustentáveis com base nos números.
adminInsights: critique o 'capital allocation', política de dividendos, recompras e ROIC/ROE.
irReliability: penalize severamente se a empresa esconde FCO ou foca demais em non-GAAP."""


def _build_prompt(result: AnalysisResult) -> str:
    sector_label = (
        "Financeiro/Bancário"
        if result.sector == SectorType.BANK
        else "Industrial/Não-Financeiro"
    )
    company = result.meta.company or "empresa não identificada"

    # [v3.1] desc hints injected immediately before the JSON schema
    desc_hints = _build_score_desc_hints(result)

    return f"""INSTRUÇÃO CRÍTICA: Responda APENAS com JSON puro e válido.
Sem markdown, sem blocos de código, sem texto antes ou depois do JSON.
A primeira linha DEVE ser {{ e a última }}.

Você é um Analista de Equity Research Sênior e Gestor de Portfólio (Buy-side) de um renomado hedge fund global, focado em 'Value Investing'.
Sua análise do Release de Resultados de {company} deve ser implacável, cética e focada em fundamentos, geração de caixa livre (FCF), alocação de capital e qualidade do negócio.
Não se deixe engabelar por "EBITDA ajustado" ou pelas narrativas otimistas da diretoria.
Cada afirmação DEVE ser estritamente ancorada nos dados frios extraídos abaixo.

═══ IDENTIFICAÇÃO ═══
EMPRESA: {company}
PERÍODO: {result.meta.period or "—"}
MOEDA: {result.meta.currency}
SETOR: {sector_label}
DOCUMENTO: {result.meta.doc_type}

═══ DADOS FINANCEIROS ═══
{_build_financial_summary(result)}

═══ TABELAS EXTRAÍDAS DO RI ═══
{_build_table_context(result)}

═══ BUFFETT SCORE ═══
{_build_buffett_context(result)}

═══ INDICADORES PRÉ-CALCULADOS (use para derivar seus scores) ═══
{_compute_derived_ratios(result)}

═══ DIRETRIZ DE VEREDITO ═══
{_resolve_verdict_guidance(result)}

{_SCORE_DERIVATION_RULES}

{_ANALYSIS_QUALITY_RULES}

═══ INSTRUÇÃO FINAL ANTES DO SCHEMA — LEIA COM ATENÇÃO ═══
{desc_hints}

═══ SCHEMA JSON — preencha com análise REAL, NÃO copie placeholders ═══
{{"analysis":{{"highlights":[{{"text":"<destaque específico COM número do RI>","confidence":"<5-10 baseado na evidência>","reason":"<tabela e linha fonte>"}},{{"text":"<segundo destaque>","confidence":"<valor>","reason":"<fonte>"}},{{"text":"<terceiro destaque>","confidence":"<valor>","reason":"<fonte>"}},{{"text":"<quarto destaque>","confidence":"<valor>","reason":"<fonte>"}}],"challenges":[{{"text":"<desafio COM magnitude numérica>","confidence":"<valor>","reason":"<evidência>"}},{{"text":"<segundo desafio>","confidence":"<valor>","reason":"<evidência>"}},{{"text":"<risco sistêmico>","confidence":"<valor>","reason":"<contexto macro>"}}],"swot":{{"strengths":["<força COM dado numérico>","<segunda força>","<terceira>","<quarta>"],"weaknesses":["<fraqueza COM métrica>","<segunda>","<terceira>"],"opportunities":["<oportunidade setorial específica>","<segunda>","<terceira>"],"threats":["<ameaça concreta ao negócio>","<segunda>","<terceira>"]}},"porter":{{"rivalry":{{"score":"<DERIVE: 1-10>","label":"<Baixa/Moderada/Alta/Muito Alta>","comment":"<2-3 frases com concorrentes reais e dinâmica competitiva>"}},"newEntrants":{{"score":"<DERIVE>","label":"<valor>","comment":"<barreiras regulatórias e de capital específicas>"}},"suppliers":{{"score":"<DERIVE>","label":"<valor>","comment":"<insumos críticos e poder de barganha>"}},"buyers":{{"score":"<DERIVE>","label":"<valor>","comment":"<concentração de clientes e elasticidade>"}},"substitutes":{{"score":"<DERIVE>","label":"<valor>","comment":"<substitutos reais no mercado brasileiro>"}}}},"marketPosition":"<3 frases sobre posição competitiva COM market share ou ranking setorial>","adminInsights":"<2 frases sobre governança, alocação de capital, política de dividendos>","irReliability":"<avaliação da qualidade e completude da divulgação com exemplos>"}},"conclusion":{{"verdict":"<COMPRAR|AGUARDAR|VENDER — siga diretriz acima>","verdictClass":"<positive|neutral|negative>","summary":"<3 frases com NÚMEROS justificando o veredito, mencione Buffett Score>","riskScore":"<CALCULE conforme regras>","riskLabel":"<Baixo|Moderado|Alto|Muito Alto>","riskDesc":"<UMA frase curta citando obrigatoriamente os dados de risco listados acima>","growthScore":"<CALCULE conforme regras>","growthLabel":"<Baixo|Moderado|Alto|Forte>","growthDesc":"<UMA frase curta citando obrigatoriamente os dados de crescimento listados acima>","reliabilityScore":"<CALCULE conforme regras>","reliabilityLabel":"<Baixa|Moderada|Alta>","reliabilityDesc":"<UMA frase curta citando obrigatoriamente completude e consistência dos dados acima>","confidenceLevel":"<BAIXA se <5 métricas|MÉDIA se 5-9|ALTA se ≥10>","contradictions":[{{"found":"<true se inconsistência entre DRE e Balanço>","text":"<descreva ou confirme coerência>"}},{{"found":"<bool>","text":"<segundo ponto>"}}],"catalysts":["<catalisador específico com horizonte temporal>","<segundo>","<terceiro>"],"risks":["<risco específico com gatilho e magnitude>","<segundo>","<terceiro>"],"finalParagraph":"<4 frases: recomendação + horizonte + 2 condições que mudariam a tese>"}}}}"""


# ─────────────────────────────────────────────────────────────────────────────
# Response parsing
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json_object(raw_text: str) -> str:
    clean = raw_text.strip()
    if clean.startswith("```"):
        clean = clean.split("```", 2)[-1].lstrip("json").strip()
        clean = clean.rsplit("```", 1)[0].strip()
    start = clean.find("{")
    end   = clean.rfind("}")
    if start != -1 and end != -1:
        clean = clean[start:end + 1]
    return clean


def _safe_int(value, default: int = 5) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_str_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value]
    if value:
        return [str(value)]
    return []


def _parse_highlights(raw: list) -> list[Highlight]:
    return [
        Highlight(
            text=str(h.get("text", h.get("statement", ""))),
            confidence=_safe_int(h.get("confidence"), 7),
            reason=str(h.get("reason", h.get("source", ""))),
        )
        for h in (raw or [])
        if isinstance(h, dict)
    ]


def _parse_porter(raw) -> dict[str, PorterForce]:
    if isinstance(raw, list):
        raw = {f.get("name", ""): f for f in raw if isinstance(f, dict)}
    result: dict[str, PorterForce] = {}
    for name in ("rivalry", "newEntrants", "suppliers", "buyers", "substitutes"):
        entry = (raw or {}).get(name, {})
        if isinstance(entry, dict):
            result[name] = PorterForce(
                name=name,
                label=str(entry.get("label", "Moderada")),
                score=_safe_int(entry.get("score"), 5),
                comment=str(entry.get("comment", entry.get("rationale", ""))),
            )
    return result


def _parse_analysis(data: dict) -> AiAnalysis:
    ar   = data.get("analysis", data)
    swot = ar.get("swot", {})
    return AiAnalysis(
        highlights=_parse_highlights(ar.get("highlights", [])),
        challenges=_parse_highlights(ar.get("challenges", [])),
        swot={
            "strengths":     _safe_str_list(swot.get("strengths", [])),
            "weaknesses":    _safe_str_list(swot.get("weaknesses", [])),
            "opportunities": _safe_str_list(swot.get("opportunities", [])),
            "threats":       _safe_str_list(swot.get("threats", [])),
        },
        porter=_parse_porter(ar.get("porter", {})),
        market_position=str(ar.get("marketPosition", ar.get("market_position", ""))),
        admin_insights=str(ar.get("adminInsights", ar.get("admin_insights", ""))),
        ir_reliability=str(ar.get("irReliability", ar.get("ir_reliability", ""))),
    )


def _parse_conclusion(data: dict) -> AiConclusion:
    cr = data.get("conclusion", data)
    return AiConclusion(
        verdict=str(cr.get("verdict", "AGUARDAR")),
        verdict_class=str(cr.get("verdictClass", cr.get("verdict_class", "neutral"))),
        summary=str(cr.get("summary", "")),
        risk_score=_safe_int(cr.get("riskScore",      cr.get("risk_score")), 5),
        risk_label=str(cr.get("riskLabel",            cr.get("risk_label", ""))),
        risk_desc=str(cr.get("riskDesc",              cr.get("risk_desc", ""))),
        growth_score=_safe_int(cr.get("growthScore",  cr.get("growth_score")), 5),
        growth_label=str(cr.get("growthLabel",        cr.get("growth_label", ""))),
        growth_desc=str(cr.get("growthDesc",          cr.get("growth_desc", ""))),
        reliability_score=_safe_int(cr.get("reliabilityScore", cr.get("reliability_score")), 5),
        reliability_label=str(cr.get("reliabilityLabel", cr.get("reliability_label", ""))),
        reliability_desc=str(cr.get("reliabilityDesc", cr.get("reliability_desc", ""))),
        confidence_level=str(cr.get("confidenceLevel", cr.get("confidence_level", "MÉDIA"))),
        contradictions=[
            Contradiction(found=bool(c.get("found", False)), text=str(c.get("text", "")))
            for c in (cr.get("contradictions", []) or [])
            if isinstance(c, dict)
        ],
        catalysts=_safe_str_list(cr.get("catalysts", [])),
        risks=_safe_str_list(cr.get("risks", [])),
        final_paragraph=str(cr.get("finalParagraph", cr.get("final_paragraph", ""))),
    )


def _parse_response(raw_text: str, provider_name: str) -> AiInsights:
    clean = _extract_json_object(raw_text)
    try:
        data = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise AiProviderError(
            provider_name,
            f"JSON inválido: {exc}. Início: {raw_text[:200]}",
        ) from exc
    return AiInsights(
        provider=provider_name,
        analysis=_parse_analysis(data),
        conclusion=_parse_conclusion(data),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def generate_ai_insights(
    result: AnalysisResult,
    api_key: Optional[str] = None,
    provider_name: Optional[str] = None,
) -> AiInsights:
    key = api_key or settings.anthropic_api_key
    if not key:
        raise AiProviderError("unknown", "API key não configurada")

    resolved = provider_name or detect_provider_from_key(key)

    try:
        provider: AiProvider = get_provider(resolved, key)
    except ValueError as exc:
        raise AiProviderError(resolved, str(exc)) from exc

    prompt = _build_prompt(result)

    try:
        raw = provider.complete(prompt, max_tokens=settings.ai_max_tokens)
    except ProviderError as exc:
        raise AiProviderError(exc.provider, exc.reason) from exc

    return _parse_response(raw, resolved)