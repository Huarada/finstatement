/**
 * Results renderer module.
 * Knows how to turn an AnalysisResult (API response) into DOM.
 */

import { renderBuffettScore } from "./buffett.js";
import { formatCurrency, formatPercent } from "../utils/formatters.js";

export function renderResults(data) {
  const root = document.getElementById("results");
  root.innerHTML = "";
  root.classList.add("visible", "fade-in");
  root.appendChild(_buildMetaBar(data));
  root.appendChild(_buildScoreSection(data));
  root.appendChild(_buildFinancialsSection(data));
  if (data.ai_insights) root.appendChild(_buildAiSection(data.ai_insights));
  root.appendChild(_buildTablesSection(data));
  root.appendChild(_buildResetRow());
  _injectComponentStyles();
}

function _buildMetaBar(data) {
  const { meta, sector } = data;
  const el = _div("meta-bar card stagger");
  el.style.marginBottom = "var(--s-6)";
  el.innerHTML = `
    <div class="meta-bar-inner">
      <div>
        <div class="stat-label">Empresa</div>
        <div style="font-family:var(--font-display);font-weight:700;font-size:1.1rem">${meta.company || "—"}</div>
      </div>
      <div>
        <div class="stat-label">Período</div>
        <div style="font-family:var(--font-mono)">${meta.period || "—"}</div>
        ${meta.annualization_factor > 1
          ? `<div style="font-family:var(--font-mono);font-size:.7rem;color:var(--gold)">×${meta.annualization_factor} anualizado (${meta.period_type})</div>`
          : ""}
      </div>
      <div>
        <div class="stat-label">Documento</div>
        <div style="font-family:var(--font-mono);font-size:.85rem;color:var(--text-2)">${meta.doc_type}</div>
      </div>
      <div>
        <div class="stat-label">Setor</div>
        <div>${sector === "bank" ? "🏦 Financeiro/Bancário" : "🏭 Industrial"}</div>
      </div>
      <div>
        <div class="stat-label">Moeda</div>
        <div style="font-family:var(--font-mono);font-size:.85rem">${meta.currency}</div>
      </div>
    </div>`;
  return el;
}

function _buildScoreSection(data) {
  const wrap = _div("");
  wrap.style.marginBottom = "var(--s-6)";
  const labelEl = _div("section-label");
  labelEl.textContent = "Buffett Score";
  wrap.appendChild(labelEl);
  const panel = _div("card");
  renderBuffettScore(panel, data.buffett);
  wrap.appendChild(panel);
  return wrap;
}

function _buildFinancialsSection(data) {
  const { income, balance, bank_metrics } = data;
  const isBank = !!bank_metrics;
  const wrap = _div("");
  wrap.style.marginBottom = "var(--s-6)";

  const incomeItems = isBank ? [
    { label: "MFB (anual)", val: bank_metrics.mfb, pct: false },
    { label: "Custo Crédito", val: bank_metrics.credit_cost, pct: false },
    { label: "Receita Serviços", val: bank_metrics.service_revenue, pct: false },
    { label: "Despesas Adm.", val: bank_metrics.admin_expenses, pct: false },
    { label: "Lucro Líquido", val: income.net_income, pct: false },
    { label: "ROE", val: bank_metrics.roe, pct: true },
    { label: "ROA", val: bank_metrics.roa, pct: true },
    { label: "Eficiência", val: bank_metrics.efficiency_ratio, pct: true },
    { label: "NPL +90d", val: bank_metrics.npl_ratio, pct: true },
    { label: "Basileia", val: bank_metrics.basel_ratio, pct: true },
  ] : [
    { label: "Receita Líquida", val: income.revenue, pct: false },
    { label: "Lucro Bruto", val: income.gross_profit, pct: false },
    { label: "Lucro Líquido", val: income.net_income, pct: false },
    { label: "EBIT", val: income.operating_income, pct: false },
    { label: "D&A", val: income.da_expenses, pct: false },
    { label: "FCO", val: income.operating_cash_flow, pct: false },
    { label: "CapEx", val: income.capex, pct: false },
  ];

  const balItems = [
    { label: "Ativo Total", val: balance.total_assets, pct: false },
    { label: "Patrimônio Líq.", val: balance.equity, pct: false },
    { label: "Dívida Bruta", val: balance.gross_debt, pct: false },
    { label: "Lucros Acum.", val: balance.retained_earnings, pct: false },
    { label: "Ações Tesour.", val: balance.treasury_shares, pct: false },
  ];

  const incLabel = _div("section-label");
  incLabel.textContent = isBank ? "Métricas Bancárias" : "Demonstração do Resultado";
  wrap.appendChild(incLabel);
  wrap.appendChild(_div("stat-grid stagger", incomeItems.map(_statBox).join("")));

  const balLabel = _div("section-label");
  balLabel.textContent = "Balanço Patrimonial";
  balLabel.style.marginTop = "var(--s-6)";
  wrap.appendChild(balLabel);
  wrap.appendChild(_div("stat-grid stagger", balItems.map(_statBox).join("")));
  return wrap;
}

function _statBox({ label, val, pct }) {
  const fmt = pct ? formatPercent(val) : formatCurrency(val);
  const cls = val == null ? "" : val < 0 ? "negative" : "positive";
  return `<div class="stat-box"><div class="stat-label">${label}</div><div class="stat-value ${cls}">${fmt}</div></div>`;
}

function _buildAiSection(ai) {
  const wrap = _div("");
  wrap.style.marginBottom = "var(--s-6)";
  const labelEl = _div("section-label");
  labelEl.textContent = "Análise por IA";
  wrap.appendChild(labelEl);

  const verdictColour = ai.verdict === "COMPRAR" ? "var(--green)" : ai.verdict === "EVITAR" ? "var(--red)" : "var(--gold)";

  wrap.innerHTML += `
    <div class="card stagger" style="margin-bottom:var(--s-4)">
      <div style="display:flex;align-items:center;gap:var(--s-4);flex-wrap:wrap">
        <div style="font-family:var(--font-display);font-size:2rem;font-weight:800;color:${verdictColour}">${ai.verdict}</div>
        <div>
          <div style="font-size:.95rem;color:var(--text-2)">${ai.verdict_summary}</div>
          <div style="font-family:var(--font-mono);font-size:.7rem;color:var(--text-3);margin-top:4px">Confiança: ${ai.confidence_level}</div>
        </div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--s-4);margin-bottom:var(--s-4)">
      <div class="card">
        <div class="section-label">Destaques</div>
        ${ai.highlights.map((h) => `<div style="margin-bottom:var(--s-3);padding-bottom:var(--s-3);border-bottom:1px solid var(--border)"><div style="font-size:.9rem">${h.statement}</div><div style="font-family:var(--font-mono);font-size:.65rem;color:var(--text-3);margin-top:4px">Confiança ${h.confidence}/10 · ${h.source}</div></div>`).join("")}
      </div>
      <div class="card">
        <div class="section-label">Desafios</div>
        ${ai.challenges.map((h) => `<div style="margin-bottom:var(--s-3);padding-bottom:var(--s-3);border-bottom:1px solid var(--border)"><div style="font-size:.9rem">${h.statement}</div><div style="font-family:var(--font-mono);font-size:.65rem;color:var(--text-3);margin-top:4px">Confiança ${h.confidence}/10</div></div>`).join("")}
      </div>
    </div>
    <div class="card" style="margin-bottom:var(--s-4)">
      <div class="section-label">SWOT</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--s-4)">
        ${[{k:"strengths",l:"Forças",c:"var(--green)"},{k:"weaknesses",l:"Fraquezas",c:"var(--red)"},{k:"opportunities",l:"Oportunidades",c:"var(--accent)"},{k:"threats",l:"Ameaças",c:"var(--orange)"}].map(({k,l,c})=>`<div><div style="font-family:var(--font-mono);font-size:.65rem;color:${c};text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">${l}</div><div style="font-size:.9rem;color:var(--text-2)">${ai.swot[k]||"—"}</div></div>`).join("")}
      </div>
    </div>
    <div class="card" style="margin-bottom:var(--s-4)">
      <div class="section-label">Forças de Porter</div>
      <div style="display:flex;flex-wrap:wrap;gap:var(--s-3)">
        ${(ai.porter||[]).map((f)=>{const c=f.level==="Alta"?"badge-red":f.level==="Moderada"?"badge-yellow":"badge-green";return `<div style="flex:1;min-width:150px;background:var(--bg-3);border:1px solid var(--border);border-radius:var(--r-md);padding:var(--s-3)"><div style="font-family:var(--font-mono);font-size:.7rem;color:var(--text-3);margin-bottom:4px">${f.name}</div><span class="badge ${c}">${f.level}</span><div style="font-size:.8rem;color:var(--text-2);margin-top:var(--s-2)">${f.rationale}</div></div>`;}).join("")}
      </div>
    </div>
    <div class="card">
      <div class="section-label">Conclusão Final</div>
      <div style="font-family:var(--font-body);font-size:1rem;color:var(--text-2);font-style:italic;line-height:1.7">${ai.final_conclusion}</div>
    </div>`;
  return wrap;
}

function _buildTablesSection(data) {
  const wrap = _div("");
  wrap.style.marginBottom = "var(--s-6)";
  const labelEl = _div("section-label");
  labelEl.textContent = `Tabelas Detectadas (${data.tables_summary.length})`;
  wrap.appendChild(labelEl);
  wrap.innerHTML += `<div class="card"><table class="data-table"><thead><tr><th>Tipo</th><th>Título</th><th>Linhas</th><th>Página</th><th>Confiança</th></tr></thead><tbody>${data.tables_summary.map((t)=>`<tr><td><span class="badge badge-gray" style="font-family:var(--font-mono)">${t.id}</span></td><td style="color:var(--text-2);font-size:.85rem">${t.title}</td><td class="num">${t.rows}</td><td class="num">${t.page}</td><td class="num">${Math.round(t.confidence*100)}%</td></tr>`).join("")}</tbody></table></div>`;
  return wrap;
}

function _buildResetRow() {
  const wrap = _div("");
  wrap.innerHTML = `<div style="text-align:center;padding:var(--s-5) 0"><button class="btn btn-ghost" id="btn-reset">← Analisar outro PDF</button></div>`;
  wrap.querySelector("#btn-reset").addEventListener("click", () => {
    const results = document.getElementById("results");
    results.classList.remove("visible");
    results.innerHTML = "";
    document.getElementById("upload-panel").scrollIntoView({ behavior: "smooth" });
  });
  return wrap;
}

function _div(className, html) {
  const el = document.createElement("div");
  if (className) el.className = className;
  if (html !== undefined) el.innerHTML = html;
  return el;
}

function _injectComponentStyles() {
  if (document.getElementById("results-styles")) return;
  const style = document.createElement("style");
  style.id = "results-styles";
  style.textContent = `
    .meta-bar-inner{display:flex;flex-wrap:wrap;gap:var(--s-5);align-items:start}
    .meta-bar-inner>div{min-width:120px}
    .buffett-panel{display:grid;grid-template-columns:220px 1fr;gap:var(--s-6);align-items:start}
    .buffett-gauge-wrap{text-align:center}
    .buffett-score-label{margin-top:-48px;position:relative;z-index:1}
    .buffett-score-num{font-family:var(--font-mono);font-size:2.8rem;font-weight:500;line-height:1}
    .buffett-score-denom{font-family:var(--font-mono);font-size:1rem;color:var(--text-3)}
    .buffett-label-text{font-family:var(--font-display);font-size:.85rem;font-weight:700;margin-top:var(--s-2);color:var(--text-2);line-height:1.3}
    .buffett-sector-badge{font-family:var(--font-mono);font-size:.7rem;color:var(--text-3);margin-top:var(--s-2)}
    .gauge-svg{overflow:visible}
    @media(max-width:700px){.buffett-panel{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);
}
