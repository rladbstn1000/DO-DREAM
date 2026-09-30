"""Input/file boundaries, using controlled DNS/transport only."""
import asyncio
import tempfile
import unittest
from unittest.mock import patch
import runtime_fixture
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.main import app
from app.document_processor import router as documents
from app.security.authorization import require_object_url


class DocumentBoundaryTests(unittest.TestCase):
    def test_external_file_download_fails_before_transport(self):
        with patch.object(documents, "LOCAL_EXTERNAL_STUBS", False), patch("httpx.AsyncClient", side_effect=AssertionError("Network attempt")) as transport:
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(documents.download_from_cloudfront("https://storage.invalid/file.pdf", "/unused"))
            self.assertEqual(caught.exception.status_code, 503)
            transport.assert_not_called()

    def test_unbound_url_spellings_are_denied_without_network(self):
        urls = ["https://local-fixture.invalid:bad/sample.pdf", "https://[::1]/sample.pdf",
                "https://2130706433/sample.pdf", "https://[::ffff:127.0.0.1]/sample.pdf",
                "https://local-fixture.invalid:444/sample.pdf", "https://other.invalid/sample.pdf",
                "https://local-fixture.invalid@other.invalid/sample.pdf", "file:///tmp/sample.pdf",
                "https://local-fixture.invalid/sample.pdf?redirect=https://other.invalid"]
        with patch("socket.getaddrinfo", side_effect=AssertionError("DNS attempt")) as dns, patch("httpx.AsyncClient", side_effect=AssertionError("Network attempt")) as transport:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(HTTPException) as caught:
                    require_object_url(url, "sample.pdf")
                self.assertEqual(caught.exception.status_code, 400)
            dns.assert_not_called()
            transport.assert_not_called()

    def test_authorized_synthetic_object_remains_network_free(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as handle, patch("socket.getaddrinfo", side_effect=AssertionError("DNS attempt")):
            url = require_object_url("https://local-fixture.invalid/sample.pdf", "sample.pdf")
            asyncio.run(documents.download_from_cloudfront(url, handle.name))
            self.assertTrue(handle.read().startswith(b"%PDF-"))

    def test_prompt_and_concept_count_contract_is_bounded(self):
        with self.assertRaises(ValidationError):
            documents.CloudFrontPDFRequest(uploaded_file_id=1, cloudfront_url="https://local-fixture.invalid/sample.pdf", output_format="x" * 10001)
        with self.assertRaises(ValidationError):
            documents.ConceptCheckRequest(uploaded_file_id=1, concept_checks=[{}] * 101)

    def test_body_limit_precedes_json_and_auth_dependencies(self):
        response = TestClient(app).post("/rag/chat", content=b"x" * (2 * 1024 * 1024 + 1),
                                        headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413)

    def test_legacy_document_config_uses_same_explicit_settings(self):
        with patch("dotenv.load_dotenv", side_effect=AssertionError("dotenv discovery")):
            import importlib
            from app.document_processor import config
            importlib.reload(config)
            self.assertEqual(config.SECRET_KEY_BYTES, __import__('app.config', fromlist=['SECRET_KEY_BYTES']).SECRET_KEY_BYTES)


if __name__ == "__main__":
    unittest.main()
