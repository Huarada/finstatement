from __future__ import annotations

class FinStatementError(Exception):
    pass

class PdfParsingError(FinStatementError):
    def __init__(self, reason: str, page=None):
        self.reason = reason; self.page = page
        super().__init__(f"PDF parsing failed (page={page}): {reason}")

class NoTablesFoundError(FinStatementError):
    def __init__(self, total_pages: int):
        self.total_pages = total_pages
        super().__init__(f"No financial tables detected in a {total_pages}-page document.")

class InsufficientDataError(FinStatementError):
    def __init__(self, missing_fields):
        self.missing_fields = missing_fields
        super().__init__(f"Insufficient data. Missing: {', '.join(missing_fields)}")

class AiProviderError(FinStatementError):
    def __init__(self, provider: str, reason: str):
        self.provider = provider; self.reason = reason
        super().__init__(f"AI provider '{provider}' error: {reason}")
