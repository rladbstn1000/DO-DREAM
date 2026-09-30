"""
Explicit environment-only configuration for the isolated PDF processor.
"""

from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """애플리케이션 설정"""

    APP_ENV: str = "production"
    LOCAL_EXTERNAL_STUBS: bool = False

    # 기본 설정
    APP_NAME: str = "PDF Structure Extraction Service"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False

    # 서버 설정
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS 설정 (Java Spring Boot 주소)
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

    # CLOVA OCR API 설정
    CLOVA_OCR_API_URL: str = ""
    CLOVA_OCR_SECRET_KEY: str = ""

    # Gemini API 설정
    GEMINI_API_KEY: str = ""

    # PDF 처리 설정
    MAX_PDF_SIZE_MB: int = 10
    MAX_PDF_PAGES: int = 100
    MAX_EXTRACTED_TEXT_CHARS: int = 2_000_000
    PDF_DPI: int = 350  # 이미지 렌더링 DPI (레이아웃 감지용)
    OCR_DPI: int = 300  # OCR용 DPI

    # 폰트 감지 임계값
    HEADING_FONT_RATIO_L1: float = 1.8  # Level 1 (대단원)
    HEADING_FONT_RATIO_L2: float = 1.4  # Level 2 (중단원)
    HEADING_FONT_RATIO_L3: float = 1.2  # Level 3 (소단원)

    # LayoutParser 모델 설정
    LAYOUT_MODEL_TYPE: str = "lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config"
    LAYOUT_CONFIDENCE_THRESHOLD: float = 0.7

    # 임시 파일 저장 경로
    TEMP_DIR: str = "/tmp/pdf-processing"

    class Config:
        env_file = None
        env_file_encoding = "utf-8"
        case_sensitive = True


# 싱글톤 인스턴스 생성
settings = Settings()
if settings.LOCAL_EXTERNAL_STUBS and settings.APP_ENV not in {"local", "test"}:
    raise RuntimeError("LOCAL_EXTERNAL_STUBS is permitted only in local/test")
if settings.APP_ENV == "local" and not settings.LOCAL_EXTERNAL_STUBS:
    raise RuntimeError("Local runtime requires LOCAL_EXTERNAL_STUBS=true")
if not settings.LOCAL_EXTERNAL_STUBS:
    raise RuntimeError("External PDF/OCR operation is disabled; use explicit isolated local/test mode")
if not (1 <= settings.MAX_PDF_SIZE_MB <= 10 and 1 <= settings.MAX_PDF_PAGES <= 100
        and 1 <= settings.MAX_EXTRACTED_TEXT_CHARS <= 2_000_000):
    raise RuntimeError("PDF processing limits exceed the supported local boundary")

# 임시 디렉토리 생성
os.makedirs(settings.TEMP_DIR, exist_ok=True)
