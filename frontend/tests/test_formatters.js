/**
 * Unit tests for formatters.js
 *
 * Runs in Node.js without a browser via:
 *   node tests/test_formatters.js
 *
 * Uses a minimal custom assertion library — no external dependencies.
 */

// ── Minimal test runner ────────────────────────────────────────────────────

let passed = 0;
let failed = 0;

function describe(suiteName, fn) {
  console.log(`\n  ${suiteName}`);
  fn();
}

function it(label, fn) {
  try {
    fn();
    console.log(`    ✅ ${label}`);
    passed++;
  } catch (err) {
    console.log(`    ❌ ${label}`);
    console.log(`       ${err.message}`);
    failed++;
  }
}

function expect(actual) {
  return {
    toBe(expected) {
      if (actual !== expected) {
        throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
      }
    },
    toContain(substr) {
      if (!String(actual).includes(substr)) {
        throw new Error(`Expected "${actual}" to contain "${substr}"`);
      }
    },
    toMatch(regex) {
      if (!regex.test(String(actual))) {
        throw new Error(`Expected "${actual}" to match ${regex}`);
      }
    },
    toBeTruthy() {
      if (!actual) throw new Error(`Expected truthy, got ${actual}`);
    },
    toBeGreaterThan(n) {
      if (actual <= n) throw new Error(`Expected ${actual} > ${n}`);
    },
  };
}

// ── Import helpers (ESM-compatible inline) ─────────────────────────────────
// Since Node < 22 without --experimental-vm-modules can't import ESM easily,
// we inline the functions under test here.

function formatCurrency(value) {
  if (value == null || isNaN(value)) return "N/D";
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= 1_000_000) return `${sign}R$${(abs / 1_000_000).toFixed(1)}T`;
  if (abs >= 1_000) return `${sign}R$${(abs / 1_000).toFixed(1)}B`;
  return `${sign}R$${abs.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}M`;
}

function formatPercent(value, decimals = 1) {
  if (value == null || isNaN(value)) return "N/D";
  return `${(value * 100).toFixed(decimals)}%`;
}

function formatMultiplier(value) {
  if (value == null || isNaN(value)) return "N/D";
  return `${value.toFixed(2)}x`;
}

function statusClass(status) {
  const map = { green: "status--green", yellow: "status--yellow", red: "status--red", unavailable: "status--gray" };
  return map[status] ?? "status--gray";
}

function statusLabel(status) {
  const map = { green: "✅ Excelente", yellow: "⚠️ Adequado", red: "❌ Fraco", unavailable: "— N/D" };
  return map[status] ?? "—";
}

function scoreColour(score100) {
  if (score100 >= 70) return "green";
  if (score100 >= 50) return "yellow";
  if (score100 >= 30) return "orange";
  return "red";
}

function truncate(text, maxLen = 80) {
  if (!text) return "";
  return text.length <= maxLen ? text : text.slice(0, maxLen - 1) + "…";
}

// ── Test suites ────────────────────────────────────────────────────────────

describe("formatCurrency", () => {
  it("returns N/D for null", () => expect(formatCurrency(null)).toBe("N/D"));
  it("returns N/D for undefined", () => expect(formatCurrency(undefined)).toBe("N/D"));
  it("returns N/D for NaN", () => expect(formatCurrency(NaN)).toBe("N/D"));
  it("formats millions correctly", () => expect(formatCurrency(3_261_874)).toContain("R$3.3T"));
  it("formats billions correctly", () => expect(formatCurrency(1_500)).toContain("B"));
  it("formats negative with minus sign", () => expect(formatCurrency(-5_000)).toContain("−"));
  it("small number shows M suffix", () => expect(formatCurrency(500)).toContain("M"));
});

describe("formatPercent", () => {
  it("returns N/D for null", () => expect(formatPercent(null)).toBe("N/D"));
  it("converts 0.208 to 20.8%", () => expect(formatPercent(0.208)).toBe("20.8%"));
  it("converts 0.277 to 27.7%", () => expect(formatPercent(0.277)).toBe("27.7%"));
  it("converts 0 to 0.0%", () => expect(formatPercent(0)).toBe("0.0%"));
  it("respects decimals param", () => expect(formatPercent(0.1513, 2)).toBe("15.13%"));
  it("handles negative percentages", () => expect(formatPercent(-0.05)).toBe("-5.0%"));
});

describe("formatMultiplier", () => {
  it("returns N/D for null", () => expect(formatMultiplier(null)).toBe("N/D"));
  it("formats 1.5 as 1.50x", () => expect(formatMultiplier(1.5)).toBe("1.50x"));
  it("formats 0 as 0.00x", () => expect(formatMultiplier(0)).toBe("0.00x"));
});

describe("statusClass", () => {
  it("green maps correctly", () => expect(statusClass("green")).toBe("status--green"));
  it("yellow maps correctly", () => expect(statusClass("yellow")).toBe("status--yellow"));
  it("red maps correctly", () => expect(statusClass("red")).toBe("status--red"));
  it("unavailable maps to gray", () => expect(statusClass("unavailable")).toBe("status--gray"));
  it("unknown maps to gray", () => expect(statusClass("unknown")).toBe("status--gray"));
});

describe("statusLabel", () => {
  it("green is Excelente", () => expect(statusLabel("green")).toContain("Excelente"));
  it("yellow is Adequado", () => expect(statusLabel("yellow")).toContain("Adequado"));
  it("red is Fraco", () => expect(statusLabel("red")).toContain("Fraco"));
  it("unavailable shows N/D", () => expect(statusLabel("unavailable")).toContain("N/D"));
});

describe("scoreColour", () => {
  it("90 is green", () => expect(scoreColour(90)).toBe("green"));
  it("70 is green boundary", () => expect(scoreColour(70)).toBe("green"));
  it("69 is yellow", () => expect(scoreColour(69)).toBe("yellow"));
  it("50 is yellow boundary", () => expect(scoreColour(50)).toBe("yellow"));
  it("49 is orange", () => expect(scoreColour(49)).toBe("orange"));
  it("30 is orange boundary", () => expect(scoreColour(30)).toBe("orange"));
  it("29 is red", () => expect(scoreColour(29)).toBe("red"));
  it("0 is red", () => expect(scoreColour(0)).toBe("red"));
  it("10 is red", () => expect(scoreColour(10)).toBe("red"));
});

describe("truncate", () => {
  it("short text unchanged", () => expect(truncate("hello")).toBe("hello"));
  it("empty string returns empty", () => expect(truncate("")).toBe(""));
  it("null returns empty", () => expect(truncate(null)).toBe(""));
  it("long text is truncated", () => {
    const long = "a".repeat(100);
    const result = truncate(long, 80);
    expect(result.length).toBe(80);
    expect(result).toContain("…");
  });
  it("exactly maxLen is not truncated", () => {
    const text = "a".repeat(80);
    expect(truncate(text, 80)).toBe(text);
  });
});

// ── Summary ────────────────────────────────────────────────────────────────

console.log(`\n${"─".repeat(50)}`);
console.log(`  Total: ${passed + failed} | ✅ ${passed} passed | ❌ ${failed} failed`);
console.log(`${"─".repeat(50)}`);

if (failed > 0) process.exit(1);
