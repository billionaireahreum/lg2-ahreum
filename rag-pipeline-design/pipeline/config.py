"""
RAG 파이프라인 설정
환경변수로 오버라이드 가능
"""
import os


# DB 연결
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))
DB_NAME     = os.getenv("DB_NAME", "vod_recommendation")
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# Claude API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = "claude-haiku-4-5-20251001"   # 빠름 + 저렴

# 임베딩 모델 (로컬, 무료, 한국어 지원)
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM   = 384
EMBEDDING_TYPE  = "METADATA"
BATCH_SIZE      = 256   # 임베딩 배치 크기 (메모리에 따라 조정)
