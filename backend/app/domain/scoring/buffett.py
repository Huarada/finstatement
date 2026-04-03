from __future__ import annotations
import math
from typing import Optional
from app.domain.entities import BalanceSheet, BankMetrics, BuffettMetric, BuffettScore, IncomeStatement, MetricStatus, SectorType

_SCORE_LABELS = [(90,"Vantagem Competitiva Durável (Moat Forte)"),(70,"Vantagem Competitiva Moderada"),(50,"Negócio Razoável / Sem Moat Claro"),(30,"Negócio Commodity / Alta Competição"),(0,"Evitar — Fundamentos Fracos")]

def _label_for_score(s):
    for t, l in _SCORE_LABELS:
        if s >= t: return l
    return _SCORE_LABELS[-1][1]

def _build_metric(name, value, format_fn, benchmark, explanation, formula, score_fn, max_points):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return BuffettMetric(name=name, value=None, formatted_value="N/D", benchmark=benchmark,
            explanation=explanation, formula=formula, status=MetricStatus.UNAVAILABLE, points=0, max_points=max_points)
    status = score_fn(value)
    pts = max_points if status == MetricStatus.GREEN else (round(max_points * 0.5) if status == MetricStatus.YELLOW else 0)
    return BuffettMetric(name=name, value=value, formatted_value=format_fn(value), benchmark=benchmark,
        explanation=explanation, formula=formula, status=status, points=pts, max_points=max_points)

def _pct(v): return f"{v*100:.1f}%"
def _mult(v): return f"{v:.2f}x"
def _yrs(v): return f"{v:.1f} anos"

def score_industrial(income: IncomeStatement, balance: BalanceSheet) -> BuffettScore:
    metrics = []
    ll=income.net_income; lb=income.gross_profit; rec=income.revenue; depr=income.da_expenses
    sga=income.ga_expenses; juros=income.interest_expenses; oper=income.operating_income
    fco=income.operating_cash_flow; capex=income.capex; pl=balance.equity
    at=balance.total_assets; div=balance.gross_debt

    mb=(lb/rec) if lb and rec and rec>0 else None
    metrics.append(_build_metric("Margem Bruta",mb,_pct,"≥ 40% = excelente · 20–40% = razoável · < 20% = commodity",
        "Cap.7: Margens brutas consistentemente acima de 40% indicam vantagem competitiva durável.",
        "Lucro Bruto ÷ Receita Líquida",lambda v: MetricStatus.GREEN if v>=0.40 else (MetricStatus.YELLOW if v>=0.20 else MetricStatus.RED),25))

    # [FIX v2.3] Usar abs(sga)/lb — despesas G&A podem ser negativas (convenção contábil)
    sga_ratio=(abs(sga)/lb) if sga is not None and lb and lb>0 else None
    metrics.append(_build_metric("SG&A como % do Lucro Bruto",sga_ratio,_pct,"< 30% = excelente · 30–80% = razoável · > 80% = preocupante",
        "Cap.12: Empresas com DCA consistentemente gastam menos em vendas e administração.",
        "Despesas G&A ÷ Lucro Bruto",lambda v: MetricStatus.GREEN if v<0.30 else (MetricStatus.YELLOW if v<0.80 else MetricStatus.RED),10))

    # [FIX v2.3] Usar abs(depr)/lb
    da_ratio=(abs(depr)/lb) if depr is not None and lb and lb>0 else None
    metrics.append(_build_metric("D&A como % do Lucro Bruto",da_ratio,_pct,"< 10% = excelente · 10–25% = razoável · > 25% = capital intensivo",
        "Cap.14: Baixa depreciação relativa indica negócio leve em ativos — sinal de moat.",
        "Depreciação e Amortização ÷ Lucro Bruto",lambda v: MetricStatus.GREEN if v<0.10 else (MetricStatus.YELLOW if v<0.25 else MetricStatus.RED),10))

    # [FIX v2.3] Usar abs(juros)/abs(oper) — ambos podem ser negativos por convenção
    jur_ratio=(abs(juros)/abs(oper)) if juros is not None and oper and oper!=0 else None
    metrics.append(_build_metric("Despesas Financeiras / Resultado Operacional",jur_ratio,_pct,"< 15% = excelente · 15–50% = razoável · > 50% = alto endividamento",
        "Cap.20: Empresas com DCA produzem muito mais do que gastam em juros.",
        "|Juros| ÷ |Resultado Operacional|",lambda v: MetricStatus.GREEN if v<0.15 else (MetricStatus.YELLOW if v<0.50 else MetricStatus.RED),10))

    ml=(ll/rec) if ll and rec and rec>0 else None
    metrics.append(_build_metric("Margem Líquida",ml,_pct,"≥ 20% = excelente · 10–20% = bom · < 10% = fraco",
        "Cap.22: Margens líquidas persistentemente acima de 20% são raras e indicam vantagem competitiva.",
        "Lucro Líquido ÷ Receita Líquida",lambda v: MetricStatus.GREEN if v>=0.20 else (MetricStatus.YELLOW if v>=0.10 else MetricStatus.RED),15))

    roe=(ll/abs(pl)) if ll and pl and pl!=0 else None
    metrics.append(_build_metric("Retorno sobre Patrimônio Líquido (ROE)",roe,_pct,"≥ 20% = excelente · ≥ 15% = bom · < 10% = fraco",
        "Cap.29: ROE consistentemente alto indica que a empresa reinveste lucros com alta taxa de retorno.",
        "Lucro Líquido ÷ Patrimônio Líquido",lambda v: MetricStatus.GREEN if v>=0.20 else (MetricStatus.YELLOW if v>=0.15 else MetricStatus.RED),20))

    roa=(ll/at) if ll and at and at>0 else None
    metrics.append(_build_metric("Retorno sobre Ativos (ROA)",roa,_pct,"≥ 12% = excelente · ≥ 6% = bom · < 4% = fraco",
        "Cap.34: ROA alto com baixa alavancagem é o perfil ideal.",
        "Lucro Líquido ÷ Total de Ativos",lambda v: MetricStatus.GREEN if v>=0.12 else (MetricStatus.YELLOW if v>=0.06 else MetricStatus.RED),10))

    debt_yrs=(abs(div)/abs(ll)) if div is not None and ll and ll!=0 else None
    metrics.append(_build_metric("Dívida Bruta / Lucro Líquido (anos para quitar)",debt_yrs,_yrs,"< 3 anos = excelente · 3–5 anos = razoável · > 5 anos = alto",
        "Cap.35: Buffett prefere empresas que poderiam quitar toda a dívida em menos de 3 anos.",
        "Dívida Bruta ÷ Lucro Líquido",lambda v: MetricStatus.GREEN if v<3 else (MetricStatus.YELLOW if v<5 else MetricStatus.RED),10))

    # [FIX v2.3] abs(capex)/abs(ll) — CapEx é negativo por convenção contábil;
    # antes: capex/ll = -108.714/110.605 = -0.98 → GREEN (< 0.25) ERRADO
    # agora: |capex|/ll = 108.714/110.605 = 0.98 → RED (> 0.50) CORRETO
    cpx_ratio=(abs(capex)/abs(ll)) if capex is not None and ll and ll!=0 else None
    metrics.append(_build_metric("CapEx como % do Lucro Líquido",cpx_ratio,_pct,"< 25% = excelente · 25–50% = razoável · > 50% = capital intensivo",
        "Cap.43: Empresas com DCA reinvestem pouco em ativos físicos.",
        "|CapEx| ÷ |Lucro Líquido|",lambda v: MetricStatus.GREEN if v<0.25 else (MetricStatus.YELLOW if v<0.50 else MetricStatus.RED),10))

    # [FIX v2.3] abs(fco)/abs(ll) — FCO positivo, LL pode variar de sinal
    fco_ratio=(abs(fco)/abs(ll)) if fco is not None and ll and ll!=0 else None
    metrics.append(_build_metric("FCO / Lucro Líquido",fco_ratio,_pct,"≥ 100% = excelente · 75–100% = bom · < 75% = atenção",
        "Cap.44: Lucro que se converte em caixa real.",
        "Fluxo de Caixa Operacional ÷ Lucro Líquido",lambda v: MetricStatus.GREEN if v>=1.0 else (MetricStatus.YELLOW if v>=0.75 else MetricStatus.RED),10))

    re_val=balance.retained_earnings
    metrics.append(_build_metric("Lucros Acumulados (Reservas de Lucro)",re_val,lambda v:f"R${v:,.0f}M",
        "Positivo e crescente = excelente · Negativo = empresa distribui mais do que ganha",
        "Cap.39: Lucros acumulados positivos e crescentes indicam que a empresa reinveste consistentemente.",
        "Saldo de Reservas de Lucros no Balanço",lambda v: MetricStatus.GREEN if v>0 else MetricStatus.RED,5))

    treasury=balance.treasury_shares
    metrics.append(_build_metric("Recompra de Ações (Ações em Tesouraria)",treasury,lambda v:f"R${abs(v):,.0f}M",
        "Presente e crescente = positivo · Ausente = neutro",
        "Cap.46: Recompras consistentes indicam que a gestão acredita que suas ações estão abaixo do valor intrínseco.",
        "Saldo negativo de Ações em Tesouraria no Balanço",lambda v: MetricStatus.GREEN if v<0 else MetricStatus.YELLOW,5))

    total_pts=sum(m.points for m in metrics); max_pts=sum(m.max_points for m in metrics)
    score_100=round(total_pts/max_pts*100) if max_pts else 0
    return BuffettScore(total_points=total_pts,max_points=max_pts,score_100=score_100,label=_label_for_score(score_100),sector=SectorType.INDUSTRIAL,metrics=metrics)

def score_bank(income: IncomeStatement, balance: BalanceSheet, bank: BankMetrics) -> BuffettScore:
    metrics=[]
    roe=bank.roe; roa=bank.roa; efic=bank.efficiency_ratio; cc=bank.credit_cost
    mfb=bank.mfb; basel=bank.basel_ratio; npl=bank.npl_ratio; has_buyback=bank.has_buyback

    metrics.append(_build_metric("Retorno sobre Patrimônio Líquido / RSPL (ROE)",roe,_pct,"≥ 20% = excelente · ≥ 15% = bom · < 10% = fraco",
        "Cap.48: ROE bancário acima de 15% indica banco bem gerido com vantagem competitiva.",
        "Lucro Líquido Ajustado ÷ Patrimônio Líquido",lambda v: MetricStatus.GREEN if v>=0.20 else (MetricStatus.YELLOW if v>=0.15 else MetricStatus.RED),25))

    metrics.append(_build_metric("Retorno sobre Ativos (ROA)",roa,_pct,"≥ 1,5% = excelente · ≥ 1,0% = bom · < 0,5% = fraco",
        "Cap.34: Para bancos alavancados ~10×, ROA de 1% equivale a ROE de ~10%.",
        "Lucro Líquido ÷ Total de Ativos",lambda v: MetricStatus.GREEN if v>=0.015 else (MetricStatus.YELLOW if v>=0.010 else MetricStatus.RED),20))

    eff=efic or ((abs(bank.admin_expenses)/((mfb or 0)+(bank.service_revenue or 0))) if bank.admin_expenses and mfb and (mfb+(bank.service_revenue or 0))>0 else None)
    metrics.append(_build_metric("Índice de Eficiência Operacional",eff,_pct,"< 40% = excelente · 40–60% = bom · > 70% = ineficiente",
        "Equivalente bancário do SG&A (Cap.12). Mede que % das receitas é consumida por despesas administrativas.",
        "Despesas Administrativas ÷ (MFB + Receitas de Serviços)",lambda v: MetricStatus.GREEN if v<=0.40 else (MetricStatus.YELLOW if v<=0.60 else MetricStatus.RED),15))

    # [FIX v2.3] abs(cc)/mfb
    cc_ratio=(abs(cc)/mfb) if cc is not None and mfb and mfb>0 else None
    metrics.append(_build_metric("Custo do Crédito como % da Margem Financeira Bruta",cc_ratio,_pct,"< 30% = excelente · 30–60% = moderado · > 60% = carteira deteriorada",
        "Equivalente bancário da Margem Bruta (Cap.10). MFB = Lucro Bruto do banco.",
        "Custo do Crédito (PCLD) ÷ Margem Financeira Bruta",lambda v: MetricStatus.GREEN if v<=0.30 else (MetricStatus.YELLOW if v<=0.60 else MetricStatus.RED),15))

    metrics.append(_build_metric("Índice de Basileia (Capital Total)",basel,_pct,"≥ 15% = muito conservador · ≥ 13% = bom · 10,5–13% = adequado · < 10,5% = atenção",
        "Cap.42 e 49: Buffett prefere bancos conservadores. Basileia é o termômetro oficial de solidez.",
        "Patrimônio de Referência ÷ Ativos Ponderados pelo Risco",lambda v: MetricStatus.GREEN if v>=0.15 else (MetricStatus.YELLOW if v>=0.13 else MetricStatus.RED),15))

    metrics.append(_build_metric("Inadimplência +90 dias (NPL ratio)",npl,_pct,"< 2% = excelente · 2–4% = moderado · > 4% = carteira deteriorada",
        "Cap.37: Qualidade da carteira de crédito. NPL alto indica critérios de concessão frouxos.",
        "Créditos em atraso +90d ÷ Carteira Total",lambda v: MetricStatus.GREEN if v<=0.02 else (MetricStatus.YELLOW if v<=0.04 else MetricStatus.RED),10))

    buyback_val=1.0 if has_buyback else None
    metrics.append(_build_metric("Recompra de Ações / JCP (Retorno de Capital ao Acionista)",buyback_val,
        lambda v:"✅ Ativo" if v else "❌ Ausente","Banco retorna capital = gera acima do mínimo regulatório exigido",
        "Cap.46: Recompras e JCP substanciais só ocorrem quando o banco gera capital acima do mínimo regulatório.",
        "Presença de programa de recompra e/ou JCP relevantes",lambda v: MetricStatus.GREEN if v>0 else MetricStatus.RED,5))

    total_pts=sum(m.points for m in metrics); max_pts=sum(m.max_points for m in metrics)
    score_100=round(total_pts/max_pts*100) if max_pts else 0
    return BuffettScore(total_points=total_pts,max_points=max_pts,score_100=score_100,label=_label_for_score(score_100),sector=SectorType.BANK,metrics=metrics)
