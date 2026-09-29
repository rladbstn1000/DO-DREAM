from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.common.db_session import get_db
from app.security.auth import get_current_user
from app.security.models import User
from app.security.authorization import require_file, require_object_url
from pydantic import BaseModel, HttpUrl, ConfigDict, Field, StrictInt
import tempfile
import os
import httpx
from urllib.parse import urlparse
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
    output_format: str = """
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
"""

# 개념 Check 가공 요청 모델
class ConceptCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uploaded_file_id: StrictInt = Field(gt=0, le=9223372036854775807)
    concept_checks: List[Dict[str, Any]]  # s_title == "개념 Check"인 항목 리스트

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
    try:
        print("Authorized object download started")
        
        # httpx 비동기 클라이언트 생성
        async with httpx.AsyncClient(timeout=60.0) as client:  # 60초 타임아웃
            response = await client.get(url, follow_redirects=True)
            
            # HTTP 상태 코드 확인
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="CloudFront에 해당 파일이 존재하지 않습니다.")
            elif response.status_code == 403:
                raise HTTPException(status_code=403, detail="CloudFront 파일 접근 권한이 없습니다. (URL이 만료되었거나 권한이 없습니다)")
            elif response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Object download failed"
                )
            
            # Content-Type 검증 (선택사항이지만 안전함)
            content_type = response.headers.get('content-type', '')
            if 'application/pdf' not in content_type and not url.endswith('.pdf'):
                print(f"⚠️ 경고: Content-Type이 PDF가 아닙니다: {content_type}")
                # 경고만 하고 진행 (확장자로 판단)
            
            # 파일 크기 확인 (100MB 제한)
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > 100 * 1024 * 1024:
                raise HTTPException(
                    status_code=413,
                    detail="파일 크기가 너무 큽니다. (최대 100MB)"
                )
            
            # 파일로 저장
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            print(f"다운로드 완료: {local_path} ({len(response.content)} bytes)")
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="CloudFront 다운로드 시간 초과 (60초)")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail="Object provider unavailable")
    except HTTPException:
        # HTTPException은 그대로 재발생
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Object download failed")

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
                print(f"⚠️ 임시 파일 삭제 실패: {e}")

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