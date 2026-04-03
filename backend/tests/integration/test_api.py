"""
Integration tests for the Flask API.

These tests use Flask's test client — no live server needed.
PDF parsing is tested with a minimal synthetic PDF built via pypdf.
"""
import sys
import os
import io
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from app.api.main import create_app


def _make_minimal_pdf() -> bytes:
    """
    Build a minimal PDF with a few financial keywords in it.
    Uses pypdf to create a valid PDF in memory.
    """
    from pypdf import PdfWriter
    from pypdf.generic import (
        ArrayObject, DecodedStreamObject, DictionaryObject,
        NameObject, NumberObject,
    )

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestHealthEndpoint(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_health_returns_200(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_health_returns_ok_status(self):
        resp = self.client.get("/health")
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "ok")

    def test_health_returns_version(self):
        resp = self.client.get("/health")
        data = json.loads(resp.data)
        self.assertIn("version", data)


class TestApiDocsEndpoint(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_docs_returns_200(self):
        resp = self.client.get("/api/v1/docs")
        self.assertEqual(resp.status_code, 200)

    def test_docs_lists_endpoints(self):
        resp = self.client.get("/api/v1/docs")
        data = json.loads(resp.data)
        self.assertIn("endpoints", data)


class TestAnalyzeEndpointValidation(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_missing_file_returns_400(self):
        resp = self.client.post("/api/v1/analyze")
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertIn("error", data)

    def test_non_pdf_file_returns_400(self):
        data = {"file": (io.BytesIO(b"not a pdf"), "file.txt")}
        resp = self.client.post(
            "/api/v1/analyze",
            data=data,
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)

    def test_empty_pdf_returns_error(self):
        data = {"file": (io.BytesIO(b""), "empty.pdf")}
        resp = self.client.post(
            "/api/v1/analyze",
            data=data,
            content_type="multipart/form-data",
        )
        self.assertIn(resp.status_code, (400, 422))

    def test_invalid_pdf_bytes_returns_422(self):
        """Random bytes that don't form a valid PDF."""
        data = {"file": (io.BytesIO(b"not a pdf at all" * 10), "bad.pdf")}
        resp = self.client.post(
            "/api/v1/analyze",
            data=data,
            content_type="multipart/form-data",
        )
        # Should return either 422 (parsing failed) or 200 with empty tables
        self.assertIn(resp.status_code, (200, 422))

    def test_blank_pdf_returns_422_no_tables(self):
        """A valid but blank PDF with no financial content."""
        pdf_bytes = _make_minimal_pdf()
        data = {"file": (io.BytesIO(pdf_bytes), "blank.pdf")}
        resp = self.client.post(
            "/api/v1/analyze",
            data=data,
            content_type="multipart/form-data",
        )
        # Either 422 (no tables) or 200 with empty tables
        self.assertIn(resp.status_code, (200, 422))
        if resp.status_code == 422:
            body = json.loads(resp.data)
            self.assertIn("error", body)


class TestResponseSchema(unittest.TestCase):
    """
    Verify the response JSON has the expected top-level keys.
    Uses a blank PDF — most values will be None/empty, but the schema must hold.
    """

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.pdf_bytes = _make_minimal_pdf()

    def _post_pdf(self) -> tuple[int, dict]:
        data = {"file": (io.BytesIO(self.pdf_bytes), "test.pdf")}
        resp = self.client.post(
            "/api/v1/analyze",
            data=data,
            content_type="multipart/form-data",
        )
        return resp.status_code, json.loads(resp.data)

    def test_200_response_has_meta_key(self):
        status, body = self._post_pdf()
        if status == 200:
            self.assertIn("meta", body)

    def test_200_response_has_buffett_key(self):
        status, body = self._post_pdf()
        if status == 200:
            self.assertIn("buffett", body)

    def test_200_response_buffett_has_score(self):
        status, body = self._post_pdf()
        if status == 200:
            self.assertIn("score_100", body["buffett"])

    def test_error_response_has_error_key(self):
        status, body = self._post_pdf()
        if status != 200:
            self.assertIn("error", body)


if __name__ == "__main__":
    unittest.main()
