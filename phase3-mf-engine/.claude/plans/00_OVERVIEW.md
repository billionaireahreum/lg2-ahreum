# Phase 3 - Matrix Factorization 추천 엔진

**담당자**: 최기문
**브랜치**: `phase3-mf-engine`
**선행 조건**: Phase 2 완료 (vod_embedding 166,159개 생성 완료)

---

## 목표
시청 이력 기반 Matrix Factorization + 벡터 유사도 결합 하이브리드 추천

## 입력
- `watch_history`: 3,992,530건 (user × vod × 시청비율)
- `vod_embedding`: 166,159개 (384d 벡터)
- 만족도 공식: `(v * R + m * C) / (v + m)` (베이지안 스코어, 60초 이하=0)

## 출력
- `vod_recommendation` 테이블 업데이트 (황대원에게 전달)
- 유저별 TOP-N 추천 VOD 목록

## 기술 스택
- Matrix Factorization: Surprise 라이브러리 (SVD)
- 벡터 유사도: pgvector cosine similarity
- DB: 읽기 전용 계정 사용

## TDD 테스트 위치
`phase3-mf-engine/tests/`

## DB 정책
- 읽기: 직접 쿼리 가능
- 쓰기: 결과 CSV 생성 → 황대원에게 전달
