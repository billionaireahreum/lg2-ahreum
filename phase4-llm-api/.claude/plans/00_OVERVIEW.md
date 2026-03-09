# Phase 4 - LLM 감성 문구 + FastAPI

**담당자**: 이가원
**브랜치**: `phase4-llm-api`
**선행 조건**: Phase 3 완료 (추천 결과 vod_recommendation 테이블)

---

## 목표
추천 결과에 LG Exaone 4.0으로 감성 문구 생성 + FastAPI 엔드포인트 제공

## 주요 기능
- `GET /recommend/{user_id}` → TOP-N 추천 VOD + 감성 문구
- `GET /similar/{vod_id}` → 유사 VOD (pgvector cosine)
- LG Exaone 4.0 API 연동 (감성 문구 생성)

## 기술 스택
- FastAPI + uvicorn
- LG Exaone 4.0 API
- pgvector cosine similarity 쿼리

## TDD 테스트 위치
`phase4-llm-api/tests/`
- API 엔드포인트 테스트: pytest + httpx (TestClient)

## 환경변수 추가 필요
```
LG_EXAONE_KEY=<LG Exaone API 키>
```

## DB 정책
- 읽기 전용 (추천 결과 조회만)
- DB 스키마 변경 필요 시 황대원에게 전달
