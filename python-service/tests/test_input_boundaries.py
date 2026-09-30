"""Synthetic input/transport failures only; no provider, DNS or external traffic."""
import asyncio
import io
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.update(APP_ENV="test", LOCAL_EXTERNAL_STUBS="true")
from fastapi import HTTPException
from fastapi.testclient import TestClient
from main import app
from app.routers import pdf_structure
from app.input_limits import RequestBodyLimit


class InputBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_denied_url_retains_client_error(self):
        for path in ("extract-structure", "extract-headings", "parse-pdf-gemini"):
            response = self.client.post("/api/pdf/" + path, json={"pdfUrl": "https://other.invalid/private.pdf"})
            self.assertEqual(response.status_code, 400, response.text)

    def test_upstream_exception_is_not_a_response_or_log_payload(self):
        secret = "SYNTHETIC_PRIVATE_URL?Signature=do-not-log"
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        logger = logging.getLogger("app.routers.pdf_structure")
        logger.addHandler(handler)
        try:
            with patch.object(pdf_structure, "download_pdf", side_effect=RuntimeError(secret)):
                response = self.client.post("/api/pdf/extract-structure", json={"pdfUrl": "https://local-fixture.invalid/sample.pdf"})
            self.assertEqual(response.status_code, 500)
            self.assertNotIn(secret, response.text)
            self.assertNotIn(secret, output.getvalue())
        finally:
            logger.removeHandler(handler)

    def test_download_is_disabled_outside_local_boundary(self):
        with patch.object(pdf_structure.settings, "LOCAL_EXTERNAL_STUBS", False), patch("httpx.AsyncClient", side_effect=AssertionError("Network attempt")) as transport:
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(pdf_structure.download_pdf("https://storage.invalid/sample.pdf"))
            self.assertEqual(caught.exception.status_code, 503)
            transport.assert_not_called()

    def test_upload_filename_and_mime_are_rejected_before_parser(self):
        with patch.object(pdf_structure, "GeminiPDFParser") as parser:
            for filename, mime in (("../private.pdf", "application/pdf"), ("sample.pdf", "text/plain"), ("dir\\sample.pdf", "application/pdf")):
                response = self.client.post("/api/pdf/parse-pdf-gemini-upload", files={"file": (filename, b"%PDF-1.4\nsynthetic", mime)})
                self.assertEqual(response.status_code, 400, response.text)
            parser.assert_not_called()

    def test_upload_magic_is_rejected_before_parser(self):
        with patch.object(pdf_structure, "GeminiPDFParser") as parser:
            response = self.client.post("/api/pdf/parse-pdf-gemini-upload", files={"file": ("sample.pdf", b"not a PDF", "application/pdf")})
            self.assertEqual(response.status_code, 400, response.text)
            parser.assert_not_called()

    def test_general_runtime_does_not_auto_activate_provider(self):
        # This is a deliberately invalid synthetic marker, not a real credential.
        env = {**os.environ, "APP_ENV": "production", "LOCAL_EXTERNAL_STUBS": "false", "GEMINI_API_KEY": "SYNTHETIC-NOT-A-KEY"}
        result = subprocess.run([sys.executable, "-c", "import app.utils.config"], env=env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_url_spellings_never_reach_dns_or_transport(self):
        urls = ["http://127.0.0.1/sample.pdf", "https://2130706433/sample.pdf",
                "https://[::1]/sample.pdf", "https://[::ffff:127.0.0.1]/sample.pdf",
                "https://local-fixture.invalid:444/sample.pdf",
                "https://local-fixture.invalid@other.invalid/sample.pdf",
                "https://local-fixture.invalid/sample.pdf?redirect=https://other.invalid",
                "file:///tmp/sample.pdf", "https://local-fixture.invalid/%73ample.pdf"]
        with patch("socket.getaddrinfo", side_effect=AssertionError("DNS attempt")) as dns, patch("httpx.AsyncClient", side_effect=AssertionError("Network attempt")) as transport:
            for url in urls:
                response = self.client.post("/api/pdf/extract-structure", json={"pdfUrl": url})
                self.assertEqual(response.status_code, 400)
            dns.assert_not_called()
            transport.assert_not_called()

    def test_oversize_upload_is_rejected_before_parser(self):
        with patch.object(pdf_structure.settings, "MAX_PDF_SIZE_MB", 1), patch.object(pdf_structure, "GeminiPDFParser") as parser:
            response = self.client.post("/api/pdf/parse-pdf-gemini-upload", files={"file": ("sample.pdf", b"%PDF-" + b"x" * 1048576, "application/pdf")})
            self.assertEqual(response.status_code, 413, response.text)
            parser.assert_not_called()

    def test_urlencoded_is_rejected_before_form_parser(self):
        response = self.client.post("/api/pdf/parse-pdf-gemini-upload", content=b"file=" + b"x" * 100,
                                    headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(response.status_code, 415)

    def test_missing_table_extractor_is_not_a_successful_empty_result(self):
        with patch.object(pdf_structure, "TABLE_EXTRACTOR_AVAILABLE", False):
            response = self.client.post("/api/pdf/extract-structure", json={
                "pdfUrl": "https://local-fixture.invalid/sample.pdf", "options": {"extractTables": True}})
            self.assertEqual(response.status_code, 501, response.text)

    def test_ocr_does_not_activate_when_optional_package_appears(self):
        with patch.object(pdf_structure, "LAYOUT_DETECTOR_AVAILABLE", True):
            response = self.client.post("/api/pdf/extract-structure", json={
                "pdfUrl": "https://local-fixture.invalid/sample.pdf", "options": {"useOcr": True}})
            self.assertEqual(response.status_code, 501, response.text)

    def test_valid_pdf_upload_still_uses_real_text_parser(self):
        from app.services.local_provider import download_fixture_pdf
        path = download_fixture_pdf("https://local-fixture.invalid/sample.pdf")
        try:
            response = self.client.post("/api/pdf/parse-pdf-gemini-upload", files={"file": ("sample.pdf", path.read_bytes(), "application/pdf")})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("Water", response.text)
        finally:
            path.unlink()

    def test_pdf_page_limit_and_failed_page_are_not_partial_success(self):
        import fitz
        from app.services.pdf_analyzer import PDFAnalyzer
        from app.services.local_provider import parse_pdf
        with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
            with fitz.open() as doc:
                doc.new_page().insert_text((72, 72), "Synthetic first page")
                doc.new_page().insert_text((72, 72), "Synthetic second page")
                doc.save(handle.name)
            analyzer = PDFAnalyzer()
            with patch.object(pdf_structure.settings, "MAX_PDF_PAGES", 1):
                with self.assertRaises(ValueError):
                    analyzer.open(handle.name)
                self.assertIsNone(analyzer.doc)
                with self.assertRaises(ValueError):
                    parse_pdf(handle.name)
            analyzer.open(handle.name)
            try:
                with patch.object(analyzer, "analyze_page", side_effect=RuntimeError("synthetic page failure")):
                    with self.assertRaisesRegex(ValueError, "partial output"):
                        analyzer.analyze_document()
            finally:
                analyzer.close()


class BodyLimitTests(unittest.IsolatedAsyncioTestCase):
    async def run_body(self, messages, headers=(), *, timeout_seconds=.05):
        calls, sent = [], []

        async def inner(scope, receive, send):
            calls.append((await receive()).get('body'))

        async def receive():
            if messages:
                return messages.pop(0)
            await asyncio.sleep(1)

        async def send(message):
            sent.append(message)

        await RequestBodyLimit(inner, max_bytes=8, json_max_bytes=8, timeout_seconds=timeout_seconds)(
            {'type': 'http', 'method': 'POST', 'path': '/', 'headers': headers}, receive, send)
        return calls, [message['status'] for message in sent if message['type'] == 'http.response.start']

    async def test_streamed_limit_without_content_length(self):
        calls, statuses = await self.run_body([{'type': 'http.request', 'body': b'12345', 'more_body': True},
                                               {'type': 'http.request', 'body': b'6789', 'more_body': False}])
        self.assertEqual((calls, statuses), ([], [413]))

    async def test_declared_limit_and_invalid_lengths(self):
        for headers, expected in [([(b'content-length', b'9')], 413),
                                   ([(b'content-length', b'-1')], 400),
                                   ([(b'content-length', b'0'), (b'content-length', b'0')], 400)]:
            calls, statuses = await self.run_body([], headers)
            self.assertEqual((calls, statuses), ([], [expected]))

    async def test_exact_streamed_limit_reaches_application(self):
        calls, statuses = await self.run_body([{'type': 'http.request', 'body': b'1234', 'more_body': True},
                                               {'type': 'http.request', 'body': b'5678'}])
        self.assertEqual((calls, statuses), ([b'12345678'], []))

    async def test_slow_body_is_bounded(self):
        self.assertEqual(await self.run_body([]), ([], [408]))

    async def test_disconnect_and_length_mismatch(self):
        self.assertEqual(await self.run_body([{'type': 'http.disconnect'}]), ([], [400]))
        self.assertEqual(await self.run_body([{'type': 'http.request', 'body': b'1'}],
                                            [(b'content-length', b'2')]), ([], [400]))


if __name__ == "__main__":
    unittest.main()
