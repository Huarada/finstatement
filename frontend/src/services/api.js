/**
 * API service — single point of contact for all backend calls.
 *
 * Design:
 *  - All fetch logic is here; UI modules never call fetch() directly.
 *  - Returns typed result objects; throws ApiError on failure.
 *  - Easy to mock in tests: replace the default export.
 */

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

const BASE_URL = window.FINSTATEMENT_API_URL || "http://localhost:8000";

/**
 * @param {string} path
 * @param {RequestInit} options
 * @returns {Promise<any>}
 */
async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  let resp;
  try {
    resp = await fetch(url, options);
  } catch (networkErr) {
    throw new ApiError("Network error — is the server running?", 0, null);
  }

  let body;
  try {
    body = await resp.json();
  } catch {
    body = null;
  }

  if (!resp.ok) {
    const msg = body?.error || `HTTP ${resp.status}`;
    throw new ApiError(msg, resp.status, body);
  }

  return body;
}

/**
 * Analyse a PDF file (local scoring only, no AI).
 *
 * @param {File} file
 * @returns {Promise<AnalysisResult>}
 */
export async function analyzeFile(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/api/v1/analyze", { method: "POST", body: form });
}

/**
 * Analyse a PDF file and generate AI narrative insights.
 *
 * @param {File} file
 * @param {string} apiKey - Anthropic API key
 * @returns {Promise<AnalysisResult & { ai_insights: AiInsights }>}
 */
export async function analyzeFileWithInsights(file, apiKey) {
  const form = new FormData();
  form.append("file", file);
  if (apiKey) form.append("api_key", apiKey);
  return request("/api/v1/analyze/insights", { method: "POST", body: form });
}

/**
 * Health check.
 * @returns {Promise<{status: string, version: string}>}
 */
export async function healthCheck() {
  return request("/health");
}
