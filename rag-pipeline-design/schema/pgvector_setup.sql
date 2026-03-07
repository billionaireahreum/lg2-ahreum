-- ============================================================
-- pgvector 설정 스크립트
-- 실행: psql -d vod_recommendation -f schema/pgvector_setup.sql
-- 선행: create_tables.sql + create_extension_tables.sql 실행 완료
-- ============================================================


-- 1. pgvector 확장 설치 (DB 관리자 권한 필요)
CREATE EXTENSION IF NOT EXISTS vector;


-- 2. vod_embedding에 벡터 컬럼 추가 (384d - paraphrase-multilingual-MiniLM-L12-v2)
ALTER TABLE vod_embedding
ADD COLUMN IF NOT EXISTS content_vector vector(384);

COMMENT ON COLUMN vod_embedding.content_vector IS
    'METADATA 임베딩 벡터 384d (paraphrase-multilingual-MiniLM-L12-v2, L2 정규화)';


-- 3. HNSW 인덱스 생성 (cosine similarity)
--    m=16: 각 노드 최대 연결 수
--    ef_construction=64: 빌드 시 탐색 범위
--    166k VOD 기준 빌드 ~5분, 검색 < 20ms
CREATE INDEX IF NOT EXISTS idx_vod_emb_vector_hnsw
    ON vod_embedding
    USING hnsw (content_vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);


-- 4. 유사도 검색 함수
--    사용: SELECT * FROM search_similar_vods('[0.1, -0.2, ...]'::vector(384), 100);
CREATE OR REPLACE FUNCTION search_similar_vods(
    query_vector    vector(384),
    top_k           INTEGER  DEFAULT 100,
    emb_type        VARCHAR  DEFAULT 'METADATA'
)
RETURNS TABLE (
    vod_id_fk   VARCHAR,
    asset_nm    VARCHAR,
    genre       VARCHAR,
    similarity  NUMERIC
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

COMMENT ON FUNCTION search_similar_vods IS
    'query_vector와 코사인 유사도 기준 Top-K VOD 반환. HNSW 인덱스 사용.';


-- 5. 검증 쿼리
-- 실행 후 아래로 현황 확인:

-- 인덱스 크기
-- SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass))
-- FROM pg_indexes WHERE tablename = 'vod_embedding';

-- 벡터 컬럼 현황
-- SELECT
--     COUNT(*) AS total,
--     COUNT(content_vector) AS with_vector,
--     COUNT(*) - COUNT(content_vector) AS without_vector
-- FROM vod_embedding;
