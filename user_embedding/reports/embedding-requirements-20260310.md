# pgvector 임베딩 생성 및 저장 속도 최적화 요구사항 정의서

**작성일**: 2026-03-10
**작성자**: 박아름
**브랜치**: `embedding-design`
**관련 Sprint**: Sprint 2 - Task 2 (RAG_Data_Pipeline 설계)

---

## 1. 개요

VOD 추천 시스템의 핵심 기반인 **콘텐츠 임베딩**을 pgvector에 저장하기 위한
생성 및 저장 속도 최적화 방안을 정의한다.

---

## 2. 현황 분석 (Before)

### 기존 방식 (`02_generate_embeddings.py`)

| 항목 | 수치 |
|------|------|
| 처리 대상 | 166,159 row 각각 독립 임베딩 |
| 임베딩 연산 횟수 | **166,159회** |
| 인코딩 방식 | `model.encode([text])` — 1건씩 호출 |
| 입력 텍스트 필드 | asset_nm, ct_cl, genre, genre_detail, director, cast_lead, smry |
| 누락 필드 | cast_guest (조연), release_date (개봉연도) |
| 체크포인트 | `vod_embedding`에 없는 row만 처리 |

### 문제점

1. **중복 연산**: 동일 콘텐츠(겨울왕국)가 23개 row → 23번 동일 임베딩 연산
2. **인코딩 비효율**: 1건씩 호출로 CPU 배치 처리 미활용
3. **메타데이터 불완전**: cast_guest, release_date 누락 → 임베딩 품질 저하
4. **세션 단절 취약**: 인메모리 캐싱으로 재시작 시 중복 처리 발생 가능

---

## 3. 개선 방안 (After)

### 신규 방식 (`generate_embeddings.py` v2)

| 항목 | 수치 |
|------|------|
| 처리 대상 | 시리즈 단위 그룹핑 후 대표 row 1건 |
| 임베딩 연산 횟수 | **23,541회** (86% 절감) |
| 인코딩 방식 | `model.encode(all_texts, batch_size=128)` — 전체 배치 |
| 입력 텍스트 필드 | + cast_guest, release_date 추가 (9개 필드) |
| 대표 row 선택 | 메타데이터 완성도(채워진 필드 수) 기준 |
| 저장 방식 | ON CONFLICT DO UPDATE (멱등성 보장) |

### 개선 핵심 로직

```
[전체 VOD 로드] → [시리즈 그룹핑] → [대표 row 선택] → [배치 인코딩] → [벡터 복사 저장]
  166,159 row       23,541 그룹       completeness score    batch_size=128    전 row 동일 벡터
```

---

## 4. 성능 측정 결과

### 실행 환경

| 항목 | 사양 |
|------|------|
| CPU | (Anaconda base, CPU-only) |
| 메모리 | — |
| 임베딩 모델 | paraphrase-multilingual-MiniLM-L12-v2 (384d) |
| 데이터 규모 | 166,159 row / 23,541 시리즈 |
| 실행일시 | 2026-03-10 22:08 ~ 22:19 |

### 실측 속도

| 단계 | 소요 시간 | 처리량 |
|------|----------|--------|
| 모델 로드 | 약 6초 | — |
| VOD 메타데이터 로딩 | 약 2초 | 166,159건 |
| 시리즈 그룹핑 | 약 1초 | 23,541 그룹 |
| 배치 인코딩 | **8분 46초** | 23,541건 / 배치당 2.86초 |
| DB 저장 | **약 2분** | 166,159건 |
| **총 소요시간** | **약 11분** | 166,159개 완료 |

### 배치 인코딩 상세

```
총 배치 수     : 184배치 (23,541 / 128)
배치당 소요    : 평균 2.86초
전체 인코딩    : 8분 46초
초당 처리 시리즈: 약 44.8건/초
```

### 기존 방식 대비 개선율 (추정)

| 지표 | 기존 방식 (추정) | 신규 방식 (실측) | 개선율 |
|------|----------------|----------------|--------|
| 임베딩 연산 횟수 | 166,159회 | 23,541회 | **86% 절감** |
| 예상 인코딩 시간 | ~62분 | 8분 46초 | **약 7배 단축** |
| 전체 소요시간 | ~65분 이상 | 11분 | **약 6배 단축** |
| 임베딩 커버리지 | 100% | 100% | 동일 |

> 기존 방식 추정 근거: 배치 없이 1건씩 encode 시 건당 약 0.022초 × 166,159 = 약 3,655초(61분)

---

## 5. 임베딩 입력 텍스트 구성

```
{제목} {유형} {장르} {세부장르} 감독: {director} 주연: {cast_lead} 조연: {cast_guest} {줄거리} {개봉연도}
```

| 필드 | 포함 여부 | 비고 |
|------|----------|------|
| asset_nm | ✅ | 핵심 식별자 |
| ct_cl | ✅ | TV/영화 등 상위 맥락 |
| genre | ✅ | 유사도 형성 핵심 |
| genre_detail | ✅ | 세부 장르 |
| director | ✅ | 감독 레이블 포함 |
| cast_lead | ✅ | 주연 레이블 포함 |
| cast_guest | ✅ | 조연 레이블 포함 (신규 추가) |
| smry | ✅ | 가장 큰 semantic signal |
| release_date | ✅ | 연도만 추출 (신규 추가) |
| rating | ❌ | 필터링 전용, 임베딩 미포함 |

---

## 6. pgvector 저장 구조

### vod_embedding 테이블

```sql
CREATE TABLE vod_embedding (
    vod_id_fk         VARCHAR   REFERENCES vod(full_asset_id),
    embedding_type    VARCHAR,  -- 'METADATA'
    embedding_dimension INT,    -- 384
    model_version     VARCHAR,  -- 'paraphrase-multilingual-MiniLM-L12-v2'
    vector_magnitude  FLOAT,    -- 1.0 (L2 정규화)
    content_vector    VECTOR(384),
    updated_at        TIMESTAMP,
    PRIMARY KEY (vod_id_fk, embedding_type)
);
```

### 인덱스 (HNSW)

```sql
CREATE INDEX ON vod_embedding
USING hnsw (content_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

- cosine 유사도 검색 최적화
- `normalize_embeddings=True` → dot product = cosine similarity

---

## 7. 요구사항 정의

### 기능 요구사항

| ID | 요구사항 | 우선순위 | 상태 |
|----|---------|---------|------|
| FR-01 | 전체 활성 VOD 166,159개 임베딩 생성 | 필수 | ✅ 완료 |
| FR-02 | 시리즈 단위 그룹핑 (normalized_title + ct_cl) | 필수 | ✅ 완료 |
| FR-03 | cast_guest, release_date 임베딩 텍스트 포함 | 필수 | ✅ 완료 |
| FR-04 | pgvector vod_embedding 테이블 저장 | 필수 | ✅ 완료 |
| FR-05 | 재실행 시 기존 임베딩 덮어쓰기 (멱등성) | 필수 | ✅ 완료 |
| FR-06 | User Embedding 생성 (시청이력 기반 가중 평균) | 필수 | 🔜 예정 |
| FR-07 | 코사인 유사도 기반 콘텐츠 추천 검색 | 필수 | 🔜 예정 |

### 비기능 요구사항

| ID | 요구사항 | 목표값 | 실측값 |
|----|---------|--------|--------|
| NFR-01 | 전체 임베딩 생성 시간 | 20분 이내 | **11분** ✅ |
| NFR-02 | 임베딩 커버리지 | 100% | **100%** ✅ |
| NFR-03 | 벡터 차원 | 384d | **384d** ✅ |
| NFR-04 | 유사도 검색 응답 시간 | 100ms 이내 | 미측정 |

---

## 8. 다음 단계

| 순서 | 작업 | 담당 | 예상 일정 |
|------|------|------|----------|
| 1 | User Embedding 생성 로직 TDD 개발 | 박아름 | 2026-03-11~ |
| 2 | 유사도 검색 API 구현 | 이가원 | Phase 4 |
| 3 | DB 서버 이관 + RBAC 설정 | 황대원 | 예정 |
| 4 | 추천 결과 품질 평가 | 전체 | Phase 4+ |
