"""Network-free synthetic storage and Gemini boundary for local/test only."""
from pathlib import Path
import tempfile
import fitz
from fastapi import HTTPException
from app.utils.config import settings

if not settings.LOCAL_EXTERNAL_STUBS:
    raise RuntimeError("Local provider requires explicit local/test configuration")


def download_fixture_pdf(url):
    if url != "https://local-fixture.invalid/sample.pdf":
        raise HTTPException(status_code=400, detail="Local storage supports only synthetic sample.pdf; network denied")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as handle:
        path = Path(handle.name)
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 80), "DO-DREAM synthetic local sample", fontsize=16)
        page.insert_text((72, 110), "Water consists of hydrogen and oxygen.", fontsize=12)
        doc.save(path)
    return path


def parse_pdf(path):
    with fitz.open(path) as doc:
        text = "\n".join(page.get_text() for page in doc)
    if not text.strip():
        raise ValueError("Local parser requires a PDF text layer; OCR/model inference is not run")
    return {"external_provider": "local_stub", "indexes": ["01 LOCAL STUB"], "data": [{"index": "01", "index_title": "LOCAL STUB: real AI not run", "titles": [{"title": "Synthetic local extraction", "s_titles": [{"s_title": "PDF text", "contents": text, "ss_titles": []}]}], "concept_checks": []}]}
