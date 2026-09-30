"""
PDF 구조화 추출 Python FastAPI 서비스

Java Spring Boot와 통신하여 PDF의 구조를 분석하고
TipTap 에디터용 JSON을 생성하는 마이크로서비스
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import logging
from contextlib import asynccontextmanager

# 환경 설정
from app.utils.config import settings
from app.input_limits import RequestBodyLimit

# 라우터 임포트
from app.routers import pdf_structure

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    애플리케이션 시작/종료 시 실행되는 로직
    """
    # 시작 시
    logger.info("🚀 PDF 구조화 서비스 시작 중...")
    logger.info(f"환경: {settings.ENVIRONMENT}")

    # TODO: LayoutParser 모델 사전 로드 (선택사항)
    # await load_layout_model()

    yield

    # 종료 시
    logger.info("⏹️  PDF 구조화 서비스 종료")


# FastAPI 앱 생성
app = FastAPI(
    title="PDF Structure Extraction Service",
    description="PDF 문서를 분석하여 목차/표/그림을 추출하고 TipTap JSON으로 변환",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV in {"local", "test"} else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.APP_ENV in {"local", "test"} else None,
)
app.add_middleware(RequestBodyLimit, max_bytes=settings.MAX_PDF_SIZE_MB * 1024 * 1024 + 65536)

# CORS 설정 (Java Spring Boot와 통신)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def mark_local_providers(request, call_next):
    response = await call_next(request)
    if settings.LOCAL_EXTERNAL_STUBS:
        response.headers["X-DO-DREAM-External-Provider"] = "local_stub"
    return response


# ========== 기본 엔드포인트 ==========

@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "service": "PDF Structure Extraction Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "extract": "/api/pdf/extract-structure (POST)"
        }
    }


@app.get("/health")
async def health_check():
    """
    Health check 엔드포인트
    Java 서비스에서 Python 서비스 상태 확인용
    """
    try:
        # TODO: 필요시 LayoutParser 모델 로드 상태 확인
        return {
            "status": "healthy",
            "service": "pdf-structure-service",
            "environment": settings.APP_ENV,
            "external_provider": "local_stub" if settings.LOCAL_EXTERNAL_STUBS else "configured"
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail="Service unhealthy")


@app.get("/api/test")
async def test_endpoint():
    """테스트용 엔드포인트"""
    if settings.APP_ENV not in {"local", "test"}:
        raise HTTPException(404, "Not found")
    return {
        "message": "PDF 구조화 서비스가 정상 작동 중입니다!",
        "test": "OK"
    }


# ========== 라우터 등록 ==========
app.include_router(pdf_structure.router, tags=["PDF Structure"])


# ========== 에러 핸들러 ==========

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """HTTP 예외 핸들러"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """일반 예외 핸들러"""
    logger.error("Unhandled PDF processing failure")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error"
        }
    )


# ========== 메인 실행 ==========

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
