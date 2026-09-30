import os
import httpx
import json
import re
import html
from typing import List
from sqlalchemy.orm import Session
from app.config import GMS_KEY
from app.config import HUGGINGFACE_TOKEN, LOCAL_EXTERNAL_STUBS

# --- LCEL 임포트 ---
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from fastapi import HTTPException
if LOCAL_EXTERNAL_STUBS:
    from app.local_providers import LocalVectorStore as Chroma
else:
    from langchain_chroma import Chroma
    from langchain_openai import OpenAIEmbeddings, ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_classic.chains import create_history_aware_retriever, create_retrieval_chain
    from langchain_classic.chains.combine_documents import create_stuff_documents_chain
    from langchain_classic.retrievers import ContextualCompressionRetriever
    from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
    from langchain_community.cross_encoders import HuggingFaceCrossEncoder


# --- 전역 변수 초기화 ---
GMS_BASE_URL = "https://gms.ssafy.io/gmsapi/api.openai.com/v1"
CHROMA_PERSIST_DIRECTORY = os.getenv("CHROMA_PERSIST_DIRECTORY", "./chroma_db")

# 1. 모델 및 벡터 스토어 클라이언트 초기화
if LOCAL_EXTERNAL_STUBS:
    from app.local_providers import LocalEmbeddings
    embedding_model = LocalEmbeddings()
    llm = None
    reranker_model = None
else:
    try:
        embedding_model = OpenAIEmbeddings(
            model="text-embedding-3-large", api_key=GMS_KEY, base_url=GMS_BASE_URL
        )
        print("✅ 임베딩 모델 초기화 성공")

        llm = ChatOpenAI(
            temperature=0.7, model_name="gpt-5-mini", api_key=GMS_KEY, base_url=GMS_BASE_URL
        )
        print("✅ LLM 모델 초기화 성공")

        # --- Reranker 모델 초기화 (다중 fallback 전략) ---
        reranker_model = None

        # 시도 1: 한국어 최적화 모델 (토큰 필요)
        if HUGGINGFACE_TOKEN:
            try:
                reranker_model = HuggingFaceCrossEncoder(
                    model_name="Dongjin-kr/ko-reranker",
                    model_kwargs={
                        'device': 'cpu',
                        'trust_remote_code': True,
                        'token': HUGGINGFACE_TOKEN
                    }
                )
                print("✅ Reranker 모델 초기화 성공 (Dongjin-kr/ko-reranker)")
            except Exception as e:
                print(f"⚠️ 한국어 Reranker 초기화 실패: {e}")

        # 시도 2: 공개 다국어 모델 (토큰 불필요)
        if reranker_model is None:
            try:
                reranker_model = HuggingFaceCrossEncoder(
                    model_name="BAAI/bge-reranker-base",
                    model_kwargs={'device': 'cpu'}
                )
                print("✅ Reranker 모델 초기화 성공 (BAAI/bge-reranker-base)")
            except Exception as e:
                print(f"⚠️ BAAI Reranker 초기화 실패: {e}")

        # 시도 3: 가장 안정적인 영어 모델 (최종 fallback)
        if reranker_model is None:
            try:
                reranker_model = HuggingFaceCrossEncoder(
                    model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
                    model_kwargs={'device': 'cpu'}
                )
                print("✅ Reranker 모델 초기화 성공 (ms-marco-MiniLM-L-6-v2)")
            except Exception as e:
                print(f"❌ 모든 Reranker 초기화 실패: {e}")
                reranker_model = None

    except Exception as e:
        print(f"❌ 모델 초기화 실패: {e}")
        embedding_model = None
        llm = None
        reranker_model = None



# --- ID-컬렉션명 변환 헬퍼 함수 ---
def _get_collection_name(document_id: str) -> str:
    # Canonical IDs make the mapping injective; never sanitize or truncate aliases.
    from app.security.authorization import document_ref
    document_ref(document_id)
    return f"material_{document_id}"



# --- 워크플로우 1: 임베딩 생성 (Service Logic) ---

async def download_json_from_cloudfront(url: str) -> dict:
    if LOCAL_EXTERNAL_STUBS:
        from app.local_providers import load_fixture_json
        return load_fixture_json(url)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, follow_redirects=True)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"CloudFront/S3 JSON 다운로드 실패 (URL: {url}): HTTP {response.status_code}",
                )
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="JSON 다운로드 시간 초과")
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500, detail="다운로드된 파일이 유효한 JSON이 아닙니다."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"JSON 다운로드 중 오류: {str(e)}")


def _clean_html_content(html_text: str) -> str:
    if not html_text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", html_text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = " ".join(text.split())
    return text


# --- 메인 데이터 추출 함수 (chapters 스키마) ---
def extract_data_from_json(json_data: dict) -> List[Document]:
    """
    JSON 데이터('chapters' 스키마)에서 Document 객체 리스트를 추출합니다.
    """
    documents = []
    chapters = json_data.get("chapters", [])

    if not chapters:
        return []

    print(f"📖 'chapters' 스키마 감지: 총 {len(chapters)}개 챕터 처리 시작")

    for chapter in chapters:
        chapter_id = chapter.get("id")
        title = chapter.get("title")
        content_html = chapter.get("content", "")
        chapter_type = chapter.get("type")

        base_metadata = {
            "chapter_id": str(chapter_id),
            "title": title or "제목 없음",
            "type": chapter_type,
        }

        if "새 챕터의 내용을 입력하세요" in content_html:
            continue

        if chapter_type == "content":
            plain_text = _clean_html_content(content_html)
            if plain_text.strip():
                documents.append(
                    Document(page_content=plain_text, metadata=base_metadata)
                )

        elif chapter_type == "quiz":
            qa_list = chapter.get("qa", [])
            for idx, qa_pair in enumerate(qa_list):
                q = qa_pair.get("question", "")
                a = qa_pair.get("answer", "")
                if not q or not a:
                    continue
                qa_content = f"질문: {q}\n정답: {a}"
                qa_metadata = base_metadata.copy()
                qa_metadata["qa_index"] = idx
                documents.append(
                    Document(page_content=qa_content, metadata=qa_metadata)
                )

    print(f"✅ JSON 파싱 완료. 총 {len(documents)}개의 Document 생성.")
    return documents


# --- 초기 데이터 추출 함수 (하이브리드 지원) ---
def extract_initial_data_from_json(json_data: dict) -> List[Document]:
    """
    텍스트 추출 직후 JSON에서 Document 객체 리스트를 추출합니다.
    'chapters' 스키마와 'parsedData' 스키마(Flat 및 Nested)를 모두 지원합니다.
    """
    
    # 1. 'chapters' 키 확인 (우선 순위: 신규 스키마)
    if "chapters" in json_data:
        print("ℹ️ [초기 임베딩] 'chapters' 스키마가 감지되었습니다.")
        return extract_data_from_json(json_data)

    # 2. 'parsedData' 처리 (구형 스키마)
    data_list = []
    
    # Case A: parsedData 래퍼가 있는 경우
    if "parsedData" in json_data:
        print("ℹ️ [초기 임베딩] 'parsedData' Wrapper 감지")
        data_list = json_data["parsedData"].get("data", [])
    # Case B: parsedData 없이 바로 data가 있는 경우 (S3 저장 방식)
    elif "data" in json_data:
        print("ℹ️ [초기 임베딩] Flat 'data' 구조 감지")
        data_list = json_data.get("data", [])
    
    if not data_list:
        keys = list(json_data.keys())
        raise ValueError(f"JSON에서 유효한 데이터('chapters', 'parsedData', 'data')를 찾을 수 없습니다. (Keys: {keys})")
    
    print(f"ℹ️ 데이터 리스트 확인됨 ({len(data_list)}개 인덱스)")
    
    documents = []
    
    for data_item in data_list:
        index = data_item.get("index", "unknown")
        index_title = data_item.get("index_title", "제목 없음")
        titles = data_item.get("titles", [])
        
        for title_item in titles:
            title = title_item.get("title", "")
            if "개념" in title and ("check" in title.lower() or "Check" in title):
                continue
            
            s_titles = title_item.get("s_titles", [])
            for s_title_item in s_titles:
                s_title = s_title_item.get("s_title", "")
                contents = s_title_item.get("contents")
                
                base_metadata = {
                    "index": index,
                    "index_title": index_title,
                    "title": title,
                    "s_title": s_title,
                    "type": "content"
                }
                
                if contents and contents.strip():
                    full_text = f"{title}\n{s_title}\n{contents}"
                    documents.append(Document(page_content=full_text, metadata=base_metadata))
                
                ss_titles = s_title_item.get("ss_titles", [])
                for ss_title_item in ss_titles:
                    ss_title = ss_title_item.get("ss_title", "")
                    ss_contents = ss_title_item.get("contents")
                    
                    if ss_contents and ss_contents.strip():
                        ss_metadata = base_metadata.copy()
                        ss_metadata["ss_title"] = ss_title
                        full_text = f"{title}\n{s_title}\n{ss_title}\n{ss_contents}"
                        documents.append(Document(page_content=full_text, metadata=ss_metadata))
    
    print(f"✅ 초기 파싱 완료. 총 {len(documents)}개의 Document 생성.")
    return documents


def create_and_store_embeddings(document_id: str, documents: List[Document]):
    """Legacy direct mutations are disabled; creation requires the durable job ledger."""
    raise RuntimeError('Direct legacy index writes are disabled')


def create_initial_embeddings(pdf_id: str, documents: List[Document]):
    raise RuntimeError('Direct legacy index writes are disabled')


class VersionedRagChain:
    def __init__(self,pointer):
        self.pointer = dict(pointer)

    async def ainvoke(self,request):
        from app.indexing.chroma import retrieve
        docs = retrieve(self.pointer,request['input'],limit=5)
        if LOCAL_EXTERNAL_STUBS:
            from app.local_providers import MARKER
            return {'answer':MARKER+' '+docs[0].page_content[:300]}
        if llm is None:
            raise ValueError('Answer provider unavailable')
        prompt = ChatPromptTemplate.from_messages([
            ('system','자료의 본문만 참고하여 한두 문장으로 답하세요. 자료에 없으면 모른다고 답하세요.\n{context}'),
            MessagesPlaceholder(variable_name='chat_history'),('user','{input}')])
        response = await (prompt | llm).ainvoke({'context':'\n'.join(doc.page_content for doc in docs),
            'input':request['input'],'chat_history':request.get('chat_history',[])})
        return {'answer':response.content}


def get_rag_chain(pointer):
    if not isinstance(pointer,dict) or 'candidate' not in pointer:
        raise ValueError('An authorized active index pointer is required')
    return VersionedRagChain(pointer)
