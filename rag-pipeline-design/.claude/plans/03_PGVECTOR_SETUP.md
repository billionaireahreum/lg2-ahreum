# Plan 03 - pgvector 설정 및 HNSW 인덱스

**목표**: PostgreSQL에 pgvector 확장 설치, vod_embedding에 벡터 컬럼 추가, HNSW 인덱스 생성
**스크립트**: `schema/pgvector_setup.sql`

---

## 1. pgvector 설치

### macOS
```bash
brew install pgvector
```

### Ubuntu/Debian
```bash
sudo apt install postgresql-16-pgvector
```

### Windows (pgAdmin 또는 psql)
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## 2. vod_embedding 벡터 컬럼 추가

```sql
-- 기존 vod_embedding 테이블에 벡터 컬럼 추가
ALTER TABLE vod_embedding
ADD COLUMN IF NOT EXISTS content_vector vector(384);
```

현재 차원: **384** (paraphrase-multilingual-MiniLM-L12-v2)
향후 CONTENT(1536d) 추가 시: `content_vector_large vector(1536)` 별도 컬럼

---

## 3. HNSW 인덱스 생성

```sql
-- HNSW 인덱스 (cosine similarity 기준)
CREATE INDEX IF NOT EXISTS idx_vod_emb_vector_hnsw
    ON vod_embedding
    USING hnsw (content_vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### HNSW 파라미터 선택 이유

| 파라미터 | 값 | 의미 |
|---------|-----|------|
| m | 16 | 각 노드의 최대 연결 수. 클수록 정확하지만 메모리 ↑ |
| ef_construction | 64 | 인덱스 빌드 시 탐색 범위. 클수록 정확하지만 빌드 느림 |

**166k VOD 기준**: m=16, ef_construction=64 → 빌드 ~5분, 검색 < 20ms

---

## 4. 검색 성능 튜닝

```sql
-- 검색 시 ef_search 설정 (정확도 vs 속도 트레이드오프)
SET hnsw.ef_search = 100;  -- 기본값 40, 높일수록 정확하지만 느림

-- 권장: Top-100 추천에서 ef_search = 100
-- 실시간 응답: ef_search = 40~60
-- 배치 처리: ef_search = 200
```

---

## 5. 유사도 검색 함수

```sql
CREATE OR REPLACE FUNCTION search_similar_vods(
    query_vector    vector(384),
    top_k           INTEGER DEFAULT 100,
    emb_type        VARCHAR DEFAULT 'METADATA'
)
RETURNS TABLE (
    vod_id_fk       VARCHAR,
    asset_nm        VARCHAR,
    genre           VARCHAR,
    similarity      NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ve.vod_id_fk,
        v.asset_nm,
        v.genre,
        (1 - (ve.content_vector <=> query_vector))::NUMERIC AS similarity
    FROM vod_embedding ve
    JOIN vod v ON ve.vod_id_fk = v.full_asset_id
    WHERE ve.embedding_type = emb_type
      AND ve.content_vector IS NOT NULL
      AND v.is_active = TRUE
    ORDER BY ve.content_vector <=> query_vector
    LIMIT top_k;
END;
$$ LANGUAGE plpgsql;
```

### 사용 예시
```sql
-- Python에서 쿼리 벡터를 문자열로 변환해서 전달
SELECT * FROM search_similar_vods(
    '[0.123, -0.456, ...]'::vector(384),
    100,
    'METADATA'
);
```

---

## 6. 인덱스 상태 확인

```sql
-- 인덱스 크기 확인
SELECT
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) AS index_size
FROM pg_indexes
WHERE tablename = 'vod_embedding';

-- 벡터 컬럼 NULL 현황
SELECT
    COUNT(*) AS total,
    COUNT(content_vector) AS with_vector,
    COUNT(*) - COUNT(content_vector) AS without_vector
FROM vod_embedding;
```

---

## 7. 성능 벤치마크 목표

| 쿼리 | 목표 | 조건 |
|------|------|------|
| Top-100 유사 VOD 검색 | < 50ms | HNSW, ef_search=100 |
| 전체 스캔 (인덱스 없음) | ~5초 | 비교용 |
| 배치 임베딩 삽입 (256건) | < 1초 | |
