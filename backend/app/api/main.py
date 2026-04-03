"""Flask API — v1 routes."""
from __future__ import annotations
import mimetypes, traceback
from pathlib import Path
from typing import Any
from flask import Flask, Response, jsonify, request
from app.application.analyze_pdf import analyze_pdf
from app.application.generate_ai import AiInsights, generate_ai_insights
from app.core.config import settings
from app.core.exceptions import AiProviderError, FinStatementError, NoTablesFoundError, PdfParsingError
from app.domain.entities import AnalysisResult

_BACKEND_DIR  = Path(__file__).resolve().parent.parent.parent
_FRONTEND_DIR = _BACKEND_DIR.parent / "frontend"

def _serve_file(rel_path: str) -> Response:
    target = (_FRONTEND_DIR / rel_path).resolve()
    try: target.relative_to(_FRONTEND_DIR)
    except ValueError: return Response("Forbidden", status=403)
    if not target.is_file(): target = _FRONTEND_DIR / "index.html"
    mime, _ = mimetypes.guess_type(str(target))
    return Response(target.read_bytes(), mimetype=mime or "text/html")

def _metric_to_dict(m: Any) -> dict:
    return {"name":m.name,"value":m.value,"formatted_value":m.formatted_value,
            "benchmark":m.benchmark,"explanation":m.explanation,"formula":m.formula,
            "status":m.status.value,"points":m.points,"max_points":m.max_points}

def _result_to_dict(result: AnalysisResult) -> dict:
    inc=result.income; bal=result.balance; buf=result.buffett; bk=result.bank_metrics
    return {
        "meta":{"company":result.meta.company,"period":result.meta.period,
                "currency":result.meta.currency,"doc_type":result.meta.doc_type,
                "period_type":result.meta.period_type.value,
                "annualization_factor":result.meta.annualization_factor},
        "sector":result.sector.value,
        "income":{"revenue":inc.revenue,"gross_profit":inc.gross_profit,"net_income":inc.net_income,
                  "operating_income":inc.operating_income,"ga_expenses":inc.ga_expenses,
                  "da_expenses":inc.da_expenses,"interest_expenses":inc.interest_expenses,
                  "operating_cash_flow":inc.operating_cash_flow,"capex":inc.capex},
        "balance":{"total_assets":bal.total_assets,"current_assets":bal.current_assets,
                   "current_liabilities":bal.current_liabilities,"equity":bal.equity,
                   "gross_debt":bal.gross_debt,"retained_earnings":bal.retained_earnings,
                   "treasury_shares":bal.treasury_shares},
        "bank_metrics":{
            "mfb":bk.mfb,"credit_cost":bk.credit_cost,"admin_expenses":bk.admin_expenses,
            "service_revenue":bk.service_revenue,"roe":bk.roe,"roa":bk.roa,
            "efficiency_ratio":bk.efficiency_ratio,"npl_ratio":bk.npl_ratio,
            "basel_ratio":bk.basel_ratio,"has_buyback":bk.has_buyback
        } if bk else None,
        "buffett":{"score_100":buf.score_100,"label":buf.label,"total_points":buf.total_points,
                   "max_points":buf.max_points,"sector":buf.sector.value,
                   "metrics":[_metric_to_dict(m) for m in buf.metrics]},
        "tables_summary":[{"id":t.id,"title":t.title,"rows":len(t.rows),"page":t.page,
                           "confidence":round(t.confidence,2),"from_destaques":t.from_destaques}
                          for t in result.tables],
        "tables_detail":[{"id":t.id,"title":t.title,"page":t.page,
                          "confidence":round(t.confidence,2),"from_destaques":t.from_destaques,
                          "columns":list(t.columns),
                          "rows":[{"label":r.label,"values":list(r.values)} for r in t.rows[:200]]}
                         for t in result.tables],
        "debug":result.debug_info,
    }

def _insights_to_dict(ins: AiInsights) -> dict:
    a=ins.analysis; c=ins.conclusion
    return {
        "provider":ins.provider,
        "analysis":{"highlights":[{"text":h.text,"confidence":h.confidence,"reason":h.reason} for h in a.highlights],
                    "challenges":[{"text":h.text,"confidence":h.confidence,"reason":h.reason} for h in a.challenges],
                    "swot":a.swot,
                    "porter":{n:{"score":f.score,"label":f.label,"comment":f.comment} for n,f in a.porter.items()},
                    "marketPosition":a.market_position,"adminInsights":a.admin_insights,"irReliability":a.ir_reliability},
        "conclusion":{"verdict":c.verdict,"verdictClass":c.verdict_class,"summary":c.summary,
                      "riskScore":c.risk_score,"riskLabel":c.risk_label,"riskDesc":c.risk_desc,
                      "growthScore":c.growth_score,"growthLabel":c.growth_label,"growthDesc":c.growth_desc,
                      "reliabilityScore":c.reliability_score,"reliabilityLabel":c.reliability_label,
                      "reliabilityDesc":c.reliability_desc,"confidenceLevel":c.confidence_level,
                      "contradictions":[{"found":x.found,"text":x.text} for x in c.contradictions],
                      "catalysts":c.catalysts,"risks":c.risks,"finalParagraph":c.final_paragraph},
    }

def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = settings.max_pdf_size_mb * 1024 * 1024
    app.config["TESTING"] = settings.debug

    @app.after_request
    def _add_cors(r: Response) -> Response:
        r.headers["Access-Control-Allow-Origin"] = "*"
        r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        r.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return r

    @app.route("/", defaults={"path": ""}, methods=["OPTIONS"])
    @app.route("/<path:path>", methods=["OPTIONS"])
    def _options(_path=""): return Response(status=204)

    @app.get("/")
    def index(): return _serve_file("index.html")

    @app.get("/src/<path:subpath>")
    def frontend_src(subpath): return _serve_file(f"src/{subpath}")

    @app.get("/health")
    def health(): return jsonify({"status":"ok","version":"2.1.0"})

    @app.post("/api/v1/analyze")
    def analyze():
        if "file" not in request.files: return jsonify({"error":"Missing 'file' field."}), 400
        uploaded = request.files["file"]
        if not uploaded.filename or not uploaded.filename.lower().endswith(".pdf"):
            return jsonify({"error":"Only PDF files are accepted."}), 400
        pdf_bytes = uploaded.read()
        if not pdf_bytes: return jsonify({"error":"Uploaded file is empty."}), 400
        result = analyze_pdf(pdf_bytes)
        return jsonify(_result_to_dict(result)), 200

    @app.post("/api/v1/analyze/insights")
    def analyze_with_insights():
        if "file" not in request.files: return jsonify({"error":"Missing 'file' field."}), 400
        uploaded = request.files["file"]
        if not uploaded.filename or not uploaded.filename.lower().endswith(".pdf"):
            return jsonify({"error":"Only PDF files are accepted."}), 400
        pdf_bytes = uploaded.read()
        api_key = request.form.get("api_key") or settings.anthropic_api_key
        provider_name = request.form.get("provider") or None
        result = analyze_pdf(pdf_bytes)
        response_data = _result_to_dict(result)
        if api_key:
            try:
                insights = generate_ai_insights(result, api_key=api_key, provider_name=provider_name)
                response_data["ai_insights"] = _insights_to_dict(insights)
            except AiProviderError as exc:
                response_data["ai_insights"] = None
                response_data["ai_error"] = str(exc)
        else:
            response_data["ai_insights"] = None
        return jsonify(response_data), 200

    @app.get("/api/v1/docs")
    def api_docs():
        return jsonify({"version":"2.1.0","endpoints":{
            "GET /health":"Liveness probe",
            "POST /api/v1/analyze":"Analyse PDF (no AI)",
            "POST /api/v1/analyze/insights":"Analyse PDF + AI narrative"}})

    @app.errorhandler(PdfParsingError)
    def h_pdf(e): return jsonify({"error":str(e),"type":"pdf_parsing_error"}), 422
    @app.errorhandler(NoTablesFoundError)
    def h_notables(e): return jsonify({"error":str(e),"type":"no_tables_found"}), 422
    @app.errorhandler(AiProviderError)
    def h_ai(e): return jsonify({"error":str(e),"type":"ai_provider_error","provider":e.provider}), 502
    @app.errorhandler(FinStatementError)
    def h_domain(e): return jsonify({"error":str(e),"type":"domain_error"}), 422
    @app.errorhandler(413)
    def h_large(_): return jsonify({"error":f"PDF exceeds {settings.max_pdf_size_mb}MB.","type":"file_too_large"}), 413
    @app.errorhandler(500)
    def h_500(_):
        if settings.debug: return jsonify({"error":traceback.format_exc(),"type":"internal_error"}), 500
        return jsonify({"error":"Internal server error.","type":"internal_error"}), 500

    return app
