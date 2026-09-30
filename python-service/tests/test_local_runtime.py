import os
import subprocess
import sys
import unittest
from unittest.mock import patch
os.environ.update(APP_ENV="test", LOCAL_EXTERNAL_STUBS="true")
from fastapi.testclient import TestClient
from main import app
from app.services.local_provider import download_fixture_pdf


class LocalDocumentTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_marks_provider_double(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["external_provider"], "local_stub")

    def test_real_pdf_text_pipeline(self):
        response = self.client.post("/api/pdf/extract-structure", json={"pdfUrl": "https://local-fixture.invalid/sample.pdf", "options": {"extractTables": False}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["metadata"]["hasTextLayer"])
        self.assertEqual(response.json()["metadata"]["pageCount"], 1)
        self.assertIn("Water", response.text)

    def test_gemini_boundary_marked_as_stub(self):
        response = self.client.post("/api/pdf/parse-pdf-gemini", json={"pdfUrl": "https://local-fixture.invalid/sample.pdf"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["metadata"]["model"], "local_stub")

    def test_external_url_rejected_before_network(self):
        from fastapi import HTTPException
        with patch("httpx.AsyncClient", side_effect=AssertionError("Network attempt")):
            with self.assertRaises(HTTPException):
                download_fixture_pdf("https://example.com/private.pdf")

    def test_deployment_rejects_local_double(self):
        result = subprocess.run([sys.executable, "-c", "import app.utils.config"], env={**os.environ, "APP_ENV": "production"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertNotEqual(result.returncode, 0)

    def test_no_large_models_loaded(self):
        self.assertFalse(any(name in sys.modules for name in ("torch", "transformers", "layoutparser", "google.generativeai")))


if __name__ == "__main__":
    unittest.main()
