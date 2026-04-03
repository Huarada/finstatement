/**
 * Buffett Score visualisation module.
 *
 * Renders:
 *   - Radial gauge (SVG, CSS-animated arc)
 *   - Metric heat-map table with expandable explanation rows
 *
 * Pure DOM manipulation — receives a plain data object, returns HTML.
 * No global state.
 */

import { statusClass, statusLabel, scoreColour } from "../utils/formatters.js";

const SCORE_LABELS = {
  green: "Vantagem Competitiva Durável",
  yellow: "Vantagem Moderada",
  orange: "Sem Moat Claro",
  red: "Evitar — Fundamentos Fracos",
};

/**
 * Render the full Buffett Score panel into a container element.
 *
 * @param {HTMLElement} container
 * @param {object} buffett - buffett object from API response
 */
export function renderBuffettScore(container, buffett) {
  const colour = scoreColour(buffett.score_100);
  const cssVar = `var(--${colour === "orange" ? "orange" : colour})`;

  container.innerHTML = `
    <div class="buffett-panel stagger">
      <div class="buffett-gauge-wrap">
        ${_buildGauge(buffett.score_100, colour)}
        <div class="buffett-score-label">
          <span class="buffett-score-num" style="color:${cssVar}">${buffett.score_100}</span>
          <span class="buffett-score-denom">/100</span>
        </div>
        <div class="buffett-label-text">${buffett.label}</div>
        <div class="buffett-sector-badge">
          ${buffett.sector === "bank" ? "🏦 Banco" : "🏭 Industrial"} · 
          ${buffett.total_points}/${buffett.max_points} pts
        </div>
      </div>

      <div class="buffett-metrics-wrap">
        <div class="section-label">Métricas Buffett</div>
        <table class="data-table buffett-table">
          <thead>
            <tr>
              <th>Métrica</th>
              <th>Valor</th>
              <th>Status</th>
              <th style="text-align:right">Pts</th>
            </tr>
          </thead>
          <tbody>
            ${buffett.metrics.map(_buildMetricRow).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;

  // Attach expand/collapse listeners
  container.querySelectorAll(".metric-row-trigger").forEach((row) => {
    row.addEventListener("click", () => {
      const detail = row.nextElementSibling;
      if (!detail?.classList.contains("metric-detail-row")) return;
      const isOpen = detail.style.display !== "none";
      detail.style.display = isOpen ? "none" : "table-row";
      row.querySelector(".expand-icon").textContent = isOpen ? "+" : "−";
    });
  });

  // Animate gauge arc after paint
  requestAnimationFrame(() => {
    const arc = container.querySelector(".gauge-arc");
    if (arc) {
      arc.style.strokeDashoffset = arc.dataset.targetOffset;
    }
  });
}

/**
 * Build the SVG radial gauge.
 * @param {number} score - 0..100
 * @param {string} colour - "green" | "yellow" | "orange" | "red"
 */
function _buildGauge(score, colour) {
  const R = 70;
  const CX = 90, CY = 90;
  const circumference = 2 * Math.PI * R;
  // Arc covers 270° (from 135° to 405°, bottom-left to bottom-right)
  const arcLen = circumference * 0.75;
  const filled = arcLen * (score / 100);
  const offset = arcLen - filled;

  const colourMap = {
    green: "#00d4aa", yellow: "#f5c842", orange: "#ff8c42", red: "#ff4d6a",
  };
  const stroke = colourMap[colour] || "#00d4aa";

  return `
    <svg class="gauge-svg" viewBox="0 0 180 180" width="180" height="180">
      <!-- Track -->
      <circle
        cx="${CX}" cy="${CY}" r="${R}"
        fill="none"
        stroke="#1e2330"
        stroke-width="10"
        stroke-linecap="round"
        stroke-dasharray="${arcLen} ${circumference}"
        stroke-dashoffset="0"
        transform="rotate(135 ${CX} ${CY})"
      />
      <!-- Fill arc -->
      <circle
        class="gauge-arc"
        cx="${CX}" cy="${CY}" r="${R}"
        fill="none"
        stroke="${stroke}"
        stroke-width="10"
        stroke-linecap="round"
        stroke-dasharray="${arcLen} ${circumference}"
        stroke-dashoffset="${arcLen}"
        data-target-offset="${offset}"
        transform="rotate(135 ${CX} ${CY})"
        style="transition: stroke-dashoffset 1.2s cubic-bezier(.4,0,.2,1); filter: drop-shadow(0 0 8px ${stroke}66)"
      />
    </svg>
  `;
}

/**
 * Build a single metric row (trigger + collapsible detail).
 */
function _buildMetricRow(m) {
  const badgeClass = {
    green: "badge-green", yellow: "badge-yellow",
    red: "badge-red", unavailable: "badge-gray",
  }[m.status] || "badge-gray";

  const ptsColour = m.points === m.max_points
    ? "var(--green)"
    : m.points > 0
    ? "var(--gold)"
    : "var(--text-3)";

  return `
    <tr class="metric-row-trigger" style="cursor:pointer">
      <td>
        <span class="expand-icon" style="font-family:var(--font-mono);color:var(--text-3);margin-right:6px">+</span>
        ${m.name}
      </td>
      <td class="num">${m.formatted_value}</td>
      <td><span class="badge ${badgeClass}">${_statusIcon(m.status)} ${_shortStatus(m.status)}</span></td>
      <td class="num" style="color:${ptsColour};font-weight:500">${m.points}/${m.max_points}</td>
    </tr>
    <tr class="metric-detail-row" style="display:none">
      <td colspan="4" style="background:var(--bg-3);padding:var(--s-4)">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--s-4);font-size:.85rem">
          <div>
            <div style="font-family:var(--font-mono);font-size:.65rem;color:var(--text-3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">Benchmark</div>
            <div style="color:var(--text-2)">${m.benchmark}</div>
          </div>
          <div>
            <div style="font-family:var(--font-mono);font-size:.65rem;color:var(--text-3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">Fórmula</div>
            <div style="color:var(--text-2);font-family:var(--font-mono);font-size:.8rem">${m.formula}</div>
          </div>
        </div>
        <div style="margin-top:var(--s-3);color:var(--text-2);font-size:.875rem;font-style:italic;border-top:1px solid var(--border);padding-top:var(--s-3)">${m.explanation}</div>
      </td>
    </tr>
  `;
}

function _statusIcon(status) {
  return { green: "✅", yellow: "⚠️", red: "❌", unavailable: "—" }[status] || "—";
}

function _shortStatus(status) {
  return { green: "Verde", yellow: "Amarelo", red: "Vermelho", unavailable: "N/D" }[status] || "N/D";
}
