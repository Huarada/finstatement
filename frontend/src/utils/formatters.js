/**
 * Pure formatting utilities.
 *
 * All functions are pure (no side effects) and exported individually
 * so they can be imported and tested in isolation.
 */

/**
 * Format a number as BRL currency shorthand.
 * @param {number|null|undefined} value
 * @param {string} currency - e.g. "R$ Milhões"
 * @returns {string}
 */
export function formatCurrency(value, currency = "R$ Milhões") {
  if (value == null || isNaN(value)) return "N/D";
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= 1_000_000) return `${sign}R$${(abs / 1_000_000).toFixed(1)}T`;
  if (abs >= 1_000) return `${sign}R$${(abs / 1_000).toFixed(1)}B`;
  return `${sign}R$${abs.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}M`;
}

/**
 * Format a ratio as a percentage string.
 * @param {number|null|undefined} value - decimal ratio (0.15 = 15%)
 * @param {number} decimals
 * @returns {string}
 */
export function formatPercent(value, decimals = 1) {
  if (value == null || isNaN(value)) return "N/D";
  return `${(value * 100).toFixed(decimals)}%`;
}

/**
 * Format a multiplier.
 * @param {number|null|undefined} value
 * @returns {string}
 */
export function formatMultiplier(value) {
  if (value == null || isNaN(value)) return "N/D";
  return `${value.toFixed(2)}x`;
}

/**
 * Map a MetricStatus string to a CSS class.
 * @param {"green"|"yellow"|"red"|"unavailable"} status
 * @returns {string}
 */
export function statusClass(status) {
  const map = {
    green: "status--green",
    yellow: "status--yellow",
    red: "status--red",
    unavailable: "status--gray",
  };
  return map[status] ?? "status--gray";
}

/**
 * Map a MetricStatus to a human-readable label in Portuguese.
 * @param {"green"|"yellow"|"red"|"unavailable"} status
 * @returns {string}
 */
export function statusLabel(status) {
  const map = {
    green: "✅ Excelente",
    yellow: "⚠️ Adequado",
    red: "❌ Fraco",
    unavailable: "— N/D",
  };
  return map[status] ?? "—";
}

/**
 * Map a score 0–100 to a colour token.
 * @param {number} score100
 * @returns {"green"|"yellow"|"orange"|"red"}
 */
export function scoreColour(score100) {
  if (score100 >= 70) return "green";
  if (score100 >= 50) return "yellow";
  if (score100 >= 30) return "orange";
  return "red";
}

/**
 * Truncate a string to `maxLen` characters, appending "…" if needed.
 * @param {string} text
 * @param {number} maxLen
 * @returns {string}
 */
export function truncate(text, maxLen = 80) {
  if (!text) return "";
  return text.length <= maxLen ? text : text.slice(0, maxLen - 1) + "…";
}
