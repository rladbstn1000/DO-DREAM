from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.common.db_session import get_db
from app.security.auth import get_current_user
from app.security.models import User
from app.security.authorization import require_file, require_object_url
from pydantic import BaseModel, HttpUrl, ConfigDict, Field, StrictInt
import tempfile
import os
from typing import List, Dict, Any

from app.document_processor.pdf_parser import PDFParser
from app.config import LOCAL_EXTERNAL_STUBS

router = APIRouter(
    prefix="/document",
    tags=["Document Processor"]
)

# 요청 바디 모델 정의
class CloudFrontPDFRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uploaded_file_id: StrictInt = Field(gt=0, le=9223372036854775807)
    cloudfront_url: HttpUrl  # CloudFront URL
    output_format: str = Field(max_length=10000, default="""
{
    "indexes": ["01 사회 문화 현상의 이해", "02 사회 문화현상의 연구 방법", ...],
    "data": [
        {
            "index": "01",
            "index_title": "챕터 제목",
            "titles": [
                {
                    "title": "섹션 제목",
                    "s_titles": [
                        {
                            "s_title": "소제목",
                            "contents": "내용",
                            "ss_titles": [
                                {
                                    "ss_title": "하위 소제목",
                                    "contents": "내용"
                                }
                            ]
                        }
                    ]
                }
            ],
            "concept_checks": [
                {
                    "title": "개념 Check",
                    "questions": [
                        {
                            "question": "1. 질문1\\n2. 질문2",
                            "answer": "1. 답변1\\n2. 답변2"
                        }
                    ]
                }
            ]
        }
    ]
}
""")

# 개념 Check 가공 요청 모델
class ConceptCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uploaded_file_id: StrictInt = Field(gt=0, le=9223372036854775807)
    concept_checks: List[Dict[str, Any]] = Field(min_length=1, max_length=100)

async def download_from_cloudfront(url: str, local_path: str) -> None:
    """
    CloudFront URL에서 파일을 다운로드하여 로컬에 저장
    
    Args:
        url: CloudFront 파일 URL
        local_path: 저장할 로컬 경로
    
    Raises:
        HTTPException: 다운로드 실패 시
    """
    if LOCAL_EXTERNAL_STUBS:
        from app.local_providers import write_fixture_pdf
        write_fixture_pdf(url, local_path)
        return
    # External file fetching is not part of either currently supported mode.
    # Do not retain a dormant redirect-following arbitrary-URL downloader.
    raise HTTPException(503, "External PDF downloads are disabled")

@router.post("/parse-pdf-from-cloudfront")
async def parse_pdf_from_cloudfront(request: CloudFrontPDFRequest,
    current_user: User = Depends(get_current_user), common_db: Session = Depends(get_db)):
    """
    CloudFront URL로부터 PDF를 다운로드하여 Gemini로 파싱
    
    요청 예시:
    {
        "cloudfront_url": "https://d111111abcdef8.cloudfront.net/pdfs/sample.pdf",
        "output_format": "..." (선택사항)
    }
    
    응답 예시:
    {
        "cloudfront_url": "https://...",
        "filename": "sample.pdf",
        "parsed_data": { ... }
    }
    """
    file = require_file(common_db, current_user, request.uploaded_file_id)
    require_object_url(request.cloudfront_url, file.s3_key)
    temp_path = None
    try:
        # URL 검증 - PDF 파일인지 확인
        url_str = str(request.cloudfront_url)
        # 쿼리 파라미터를 제거한 경로에서 .pdf 확인 (CloudFront signed URL 지원)
        url_path = url_str.split('?')[0]
        if not url_path.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail="PDF 파일 URL만 지원됩니다. URL 경로는 .pdf로 끝나야 합니다."
            )
        
        # 임시 파일 생성
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_path = temp_file.name
        
        # CloudFront에서 파일 다운로드
        await download_from_cloudfront(url_str, temp_path)
        
        # 다운로드된 파일 크기 확인
        file_size = os.path.getsize(temp_path)
        if file_size == 0:
            raise HTTPException(status_code=500, detail="다운로드된 파일이 비어있습니다.")
        
        print(f"PDF 파일 크기: {file_size / 1024:.2f} KB")
        
        # Gemini로 파싱
        parser = PDFParser()
        parsed_data = parser.parse_pdf(temp_path, request.output_format)
        
        # 파일명 추출 (URL 끝에서)
        filename = url_str.split('/')[-1].split('?')[0]  # 쿼리 파라미터 제거
        
        return {
            "cloudfront_url": url_str,
            "filename": filename,
            "parsed_data": parsed_data
        }
        
    except HTTPException:
        # HTTPException은 그대로 재발생
        raise
    except Exception as e:
        print("Document processing failed")
        raise HTTPException(status_code=500, detail="Document processing unavailable")
    finally:
        # 임시 파일 정리
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                print(f"✅ 임시 파일 삭제: {temp_path}")
            except Exception as e:
                print("Temporary PDF cleanup failed")

@router.post("/process-concept-check")
async def process_concept_check(request: ConceptCheckRequest,
    current_user: User = Depends(get_current_user), common_db: Session = Depends(get_db)):
    """
    개념 Check 항목을 Gemini로 가공하여 정제된 형태로 반환

    요청 예시:
    {
        "concept_checks": [
            {
                "s_title": "개념 Check",
                "contents": "1. 다양한 학문 간의 교류를 통해 사회·문화 현상을 총 체적으로 연구하는 경향을 (  ) 연구 경향이라고 한다.\n2. 기능론과(  )은 거시적 관점, (  )은 미시적 관점이다.",
                "answer": "1. 간학문적\n2. 갈등론, 상징적 상호 작용론"
            }
        ]
    }

    응답 예시:
    {
        "processed_concept_checks": [
            {
                "title": "개념 Check",
                "questions": [
                    {
                        "question": "다양한 학문 간의 교류를 통해 사회·문화 현상을 총 체적으로 연구하는 경향을 무엇이라고 하는가?",
                        "answer": "간학문적 연구 경향"
                    }
                ]
            }
        ]
    }
    """
    require_file(common_db, current_user, request.uploaded_file_id)
    try:
        print(f"개념 Check 가공 시작: {len(request.concept_checks)}개 항목")

        if not request.concept_checks:
            raise HTTPException(status_code=400, detail="concept_checks가 비어있습니다.")

        # Gemini로 가공
        parser = PDFParser()
        processed_data = parser.process_concept_checks(request.concept_checks)

        print(f"✅ 개념 Check 가공 완료")

        return processed_data

    except HTTPException:
        raise
    except Exception as e:
        print("Concept processing failed")
        raise HTTPException(status_code=500, detail="Concept processing unavailable")
