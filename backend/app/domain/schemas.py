"""
Pydantic validation schemas.

Responsabilidade única: validar e coagir dados nas fronteiras do sistema.
  • Entrada: dados financeiros extraídos do PDF (antes do scoring)
  • Entrada: resposta JSON dos provedores de IA

Design de acoplamento:
  - Este módulo NÃO importa entidades de domínio (entities.py).
  - Os modelos aqui são DTOs de validação; a conversão para entidades de
    domínio é feita no código que chama o schema (application layer).
  - Toda regra de negócio (scoring, análise) permanece em domain/.

Uso:
    from app.domain.schemas import AiResponseSchema, FinancialDataSchema

    schema = AiResponseSchema.model_validate(raw_dict)
    data   = FinancialDataSchema.model_validate(extracted_dict)
"""
from __future__ import annotations

import math
from typing import Annotated, Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Tipos auxiliares
# ─────────────────────────────────────────────────────────────────────────────

_OptFloat = Optional[float]
_Score    = Annotated[int, Field(ge=1, le=10, default=5)]


def _reject_non_finite(v: Any) -> Any:
    """Rejeita NaN / Inf antes de chegar ao validator de campo."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


# ─────────────────────────────────────────────────────────────────────────────
# Dados financeiros extraídos
# ─────────────────────────────────────────────────────────────────────────────

class IncomeStatementSchema(BaseModel):
    """
    Demonstração do Resultado validada.

    Regras de plausibilidade:
      • Lucro líquido > 5× receita → erro de magnitude → descartado
      • Lucro bruto > 1,1× receita → erro de unidade → descartado
    """

    revenue:              _OptFloat = None
    gross_profit:         _OptFloat = None
    net_income:           _OptFloat = None
    operating_income:     _OptFloat = None
    selling_expenses:     _OptFloat = None
    ga_expenses:          _OptFloat = None
    da_expenses:          _OptFloat = None
    interest_expenses:    _OptFloat = None
    operating_cash_flow:  _OptFloat = None
    capex:                _OptFloat = None

    @field_validator("*", mode="before")
    @classmethod
    def _coerce_non_finite(cls, v: Any) -> Any:
        return _reject_non_finite(v)

    @model_validator(mode="after")
    def _cross_field_plausibility(self) -> "IncomeStatementSchema":
        if self.revenue and self.net_income:
            if abs(self.net_income) > abs(self.revenue) * 5:
                self.net_income = None

        if self.revenue and self.gross_profit:
            if abs(self.gross_profit) > abs(self.revenue) * 1.1:
                self.gross_profit = None

        return self


class BalanceSheetSchema(BaseModel):
    """
    Balanço Patrimonial validado.

    Regras de plausibilidade:
      • |PL| > 2× ativo total → erro de unidade → PL descartado
      • Ativo circulante > ativo total → descartado
    """

    total_assets:        _OptFloat = None
    current_assets:      _OptFloat = None
    current_liabilities: _OptFloat = None
    equity:              _OptFloat = None
    gross_debt:          _OptFloat = None
    retained_earnings:   _OptFloat = None
    treasury_shares:     _OptFloat = None

    @field_validator("*", mode="before")
    @classmethod
    def _coerce_non_finite(cls, v: Any) -> Any:
        return _reject_non_finite(v)

    @model_validator(mode="after")
    def _cross_field_plausibility(self) -> "BalanceSheetSchema":
        if self.total_assets and self.equity:
            if abs(self.equity) > abs(self.total_assets) * 2:
                self.equity = None

        if self.total_assets and self.current_assets:
            if abs(self.current_assets) > abs(self.total_assets) * 1.05:
                self.current_assets = None

        return self


class FinancialDataSchema(BaseModel):
    """DTO de topo para validação de todos os dados extraídos do PDF."""

    income:  IncomeStatementSchema = Field(default_factory=IncomeStatementSchema)
    balance: BalanceSheetSchema    = Field(default_factory=BalanceSheetSchema)

    @classmethod
    def from_raw(
        cls,
        income_kwargs:  dict[str, _OptFloat],
        balance_kwargs: dict[str, _OptFloat],
    ) -> "FinancialDataSchema":
        """Factory conveniente: cria e valida a partir de dicts brutos."""
        return cls(
            income=IncomeStatementSchema(**income_kwargs),
            balance=BalanceSheetSchema(**balance_kwargs),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Resposta da IA
# ─────────────────────────────────────────────────────────────────────────────

class AiHighlightSchema(BaseModel):
    text:       str  = ""
    confidence: _Score = 5
    reason:     str  = ""

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v: Any) -> int:
        try:
            return max(1, min(10, int(v)))
        except (TypeError, ValueError):
            return 5


class AiPorterForceSchema(BaseModel):
    score:   _Score = 5
    label:   str    = ""
    comment: str    = ""

    @field_validator("score", mode="before")
    @classmethod
    def _coerce_score(cls, v: Any) -> int:
        try:
            return max(1, min(10, int(v)))
        except (TypeError, ValueError):
            return 5


class AiSwotSchema(BaseModel):
    strengths:     list[str] = Field(default_factory=list)
    weaknesses:    list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    threats:       list[str] = Field(default_factory=list)

    @field_validator("strengths", "weaknesses", "opportunities", "threats", mode="before")
    @classmethod
    def _ensure_list(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v if x]
        if v:
            return [str(v)]
        return []


class AiAnalysisSchema(BaseModel):
    highlights:      list[AiHighlightSchema]          = Field(default_factory=list)
    challenges:      list[AiHighlightSchema]          = Field(default_factory=list)
    swot:            AiSwotSchema                      = Field(default_factory=AiSwotSchema)
    porter:          dict[str, AiPorterForceSchema]    = Field(default_factory=dict)
    marketPosition:  str                               = ""
    adminInsights:   str                               = ""
    irReliability:   str                               = ""

    @field_validator("highlights", "challenges", mode="before")
    @classmethod
    def _ensure_highlight_list(cls, v: Any) -> list[Any]:
        return v if isinstance(v, list) else []

    @field_validator("porter", mode="before")
    @classmethod
    def _normalise_porter(cls, v: Any) -> dict[str, Any]:
        if isinstance(v, list):
            return {f.get("name", f"force_{i}"): f for i, f in enumerate(v) if isinstance(f, dict)}
        return v if isinstance(v, dict) else {}


class AiContradictionSchema(BaseModel):
    found: bool = False
    text:  str  = ""

    @field_validator("found", mode="before")
    @classmethod
    def _coerce_found(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in {"true", "1", "yes", "sim"}
        return bool(v)


_VALID_VERDICTS      = {"COMPRAR", "AGUARDAR", "VENDER"}
_VALID_VERDICT_CLASS = {"positive", "neutral", "negative"}
_VALID_CONFIDENCE    = {"ALTA", "MÉDIA", "BAIXA"}


class AiConclusionSchema(BaseModel):
    verdict:           str                          = "AGUARDAR"
    verdictClass:      str                          = "neutral"
    summary:           str                          = ""
    riskScore:         _Score                       = 5
    riskLabel:         str                          = ""
    riskDesc:          str                          = ""
    growthScore:       _Score                       = 5
    growthLabel:       str                          = ""
    growthDesc:        str                          = ""
    reliabilityScore:  _Score                       = 5
    reliabilityLabel:  str                          = ""
    reliabilityDesc:   str                          = ""
    confidenceLevel:   str                          = "MÉDIA"
    contradictions:    list[AiContradictionSchema]  = Field(default_factory=list)
    catalysts:         list[str]                    = Field(default_factory=list)
    risks:             list[str]                    = Field(default_factory=list)
    finalParagraph:    str                          = ""

    @field_validator("verdict", mode="before")
    @classmethod
    def _validate_verdict(cls, v: Any) -> str:
        s = str(v).upper().strip()
        return s if s in _VALID_VERDICTS else "AGUARDAR"

    @field_validator("verdictClass", mode="before")
    @classmethod
    def _validate_verdict_class(cls, v: Any) -> str:
        s = str(v).lower().strip()
        return s if s in _VALID_VERDICT_CLASS else "neutral"

    @field_validator("confidenceLevel", mode="before")
    @classmethod
    def _validate_confidence(cls, v: Any) -> str:
        s = str(v).upper().strip()
        return s if s in _VALID_CONFIDENCE else "MÉDIA"

    @field_validator("riskScore", "growthScore", "reliabilityScore", mode="before")
    @classmethod
    def _coerce_score(cls, v: Any) -> int:
        try:
            return max(1, min(10, int(v)))
        except (TypeError, ValueError):
            return 5

    @field_validator("catalysts", "risks", mode="before")
    @classmethod
    def _ensure_list(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v if x]
        return [str(v)] if v else []

    @field_validator("contradictions", mode="before")
    @classmethod
    def _ensure_contradiction_list(cls, v: Any) -> list[Any]:
        return v if isinstance(v, list) else []


class AiResponseSchema(BaseModel):
    """
    Schema raiz para toda resposta de provedor de IA.

    Uso:
        raw_dict = json.loads(ai_text)
        schema   = AiResponseSchema.model_validate(raw_dict)
        # schema.analysis, schema.conclusion já validados e coagidos.
    """

    analysis:   AiAnalysisSchema   = Field(default_factory=AiAnalysisSchema)
    conclusion: AiConclusionSchema  = Field(default_factory=AiConclusionSchema)

    model_config = {"extra": "ignore"}   # campos extras da IA são silenciosamente ignorados
