-- ============================================================
-- VOD 추천 시스템 - Phase 2 확장 테이블 DDL
-- 대상 DB : vod_recommendation
-- 작성일  : 2026-03-06
-- 참고    : database-design/.claude/plans/05_EXTENSION_PLAN.md
--
-- 실행 전제: create_tables.sql 실행 완료 (users, vod, watch_history 존재)
-- 포함 테이블:
--   1. vod_embedding      - VOD 벡터 임베딩 메타데이터
--   2. user_embedding     - 사용자 벡터 임베딩 메타데이터
--   3. vod_recommendation - 추천 결과 캐시
--
-- 참고: 실제 벡터는 Milvus(또는 pgvector)에 저장
--       이 테이블들은 메타데이터 및 캐시 역할
-- ============================================================


-- ============================================================
-- 1. VOD_EMBEDDING 테이블
--    VOD 벡터 임베딩 메타데이터 저장
--    실제 벡터 → Milvus / pgvector
--    이 테이블 → 벡터 버전, 모델 정보, Milvus ID 등 메타데이터
-- ============================================================

CREATE TABLE vod_embedding (

    vod_embedding_id    BIGINT          GENERATED ALWAYS AS IDENTITY,

    -- 참조
    vod_id_fk           VARCHAR(64)     NOT NULL,

    -- Milvus 연동 정보
    milvus_collection   VARCHAR(128),                       -- Milvus 컬렉션명
    milvus_vector_id    BIGINT,                             -- Milvus 내부 ID

    -- 임베딩 정보
    -- CONTENT=1536d, METADATA=384d, VISUAL=512d, HYBRID=2432d
    embedding_type      VARCHAR(32)     NOT NULL,
    embedding_dimension INTEGER         NOT NULL,
    model_version       VARCHAR(64),                        -- 'openai-text-embedding-3-large-v1'

    -- 벡터 통계 (빠른 필터링용)
    vector_magnitude    NUMERIC(10,6),                      -- L2 norm

    -- 시간
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_vod_embedding PRIMARY KEY (vod_embedding_id),
    CONSTRAINT uq_vod_embedding UNIQUE (vod_id_fk, embedding_type),
    CONSTRAINT fk_vod_emb FOREIGN KEY (vod_id_fk)
        REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    CONSTRAINT chk_vod_emb_type CHECK (
        embedding_type IN ('CONTENT', 'METADATA', 'VISUAL', 'HYBRID')
    )
);

COMMENT ON TABLE  vod_embedding                 IS 'VOD 벡터 임베딩 메타데이터 (실제 벡터는 Milvus/pgvector에 저장)';
COMMENT ON COLUMN vod_embedding.embedding_type  IS 'CONTENT=1536d / METADATA=384d / VISUAL=512d / HYBRID=2432d';
COMMENT ON COLUMN vod_embedding.milvus_vector_id IS 'Milvus 내부 벡터 ID (조회 시 사용)';
COMMENT ON COLUMN vod_embedding.vector_magnitude IS 'L2 norm - 빠른 거리 계산용 사전 계산값';

CREATE INDEX idx_vod_emb_type    ON vod_embedding(embedding_type);
CREATE INDEX idx_vod_emb_updated ON vod_embedding(updated_at DESC);

CREATE TRIGGER trg_vod_embedding_updated_at
    BEFORE UPDATE ON vod_embedding
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- 2. USER_EMBEDDING 테이블
--    사용자 행동 벡터 임베딩 메타데이터 저장
--    BEHAVIOR=256d, PREFERENCE=128d, DEMOGRAPHIC=64d, HYBRID=448d
-- ============================================================

CREATE TABLE user_embedding (

    user_embedding_id   BIGINT          GENERATED ALWAYS AS IDENTITY,

    -- 참조
    user_id_fk          VARCHAR(64)     NOT NULL,

    -- Milvus 연동 정보
    milvus_collection   VARCHAR(128),
    milvus_vector_id    BIGINT,

    -- 임베딩 정보
    -- BEHAVIOR=256d, PREFERENCE=128d, DEMOGRAPHIC=64d, HYBRID=448d
    embedding_type      VARCHAR(32)     NOT NULL,
    embedding_dimension INTEGER         NOT NULL,
    model_version       VARCHAR(64),

    -- 생성 기반 정보
    base_record_count   INTEGER,                            -- 생성에 사용된 watch_history 행 수

    -- 시간
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_user_embedding PRIMARY KEY (user_embedding_id),
    CONSTRAINT uq_user_embedding UNIQUE (user_id_fk, embedding_type),
    CONSTRAINT fk_user_emb FOREIGN KEY (user_id_fk)
        REFERENCES users(sha2_hash) ON DELETE CASCADE,
    CONSTRAINT chk_user_emb_type CHECK (
        embedding_type IN ('BEHAVIOR', 'PREFERENCE', 'DEMOGRAPHIC', 'HYBRID')
    )
);

COMMENT ON TABLE  user_embedding                  IS '사용자 벡터 임베딩 메타데이터 (실제 벡터는 Milvus/pgvector에 저장)';
COMMENT ON COLUMN user_embedding.embedding_type   IS 'BEHAVIOR=256d / PREFERENCE=128d / DEMOGRAPHIC=64d / HYBRID=448d';
COMMENT ON COLUMN user_embedding.base_record_count IS '임베딩 생성에 사용된 watch_history 건수 (신뢰도 지표)';

CREATE INDEX idx_user_emb_type    ON user_embedding(embedding_type);
CREATE INDEX idx_user_emb_updated ON user_embedding(updated_at DESC);

CREATE TRIGGER trg_user_embedding_updated_at
    BEFORE UPDATE ON user_embedding
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- 3. VOD_RECOMMENDATION 테이블
--    추천 결과 캐시 테이블 (TTL: 7일)
--    갱신 주기: 일 1회 배치
--    캐싱 전략: Redis L1(1시간) → 이 테이블 L2(7일)
-- ============================================================

CREATE TABLE vod_recommendation (

    recommendation_id   BIGINT          GENERATED ALWAYS AS IDENTITY,

    -- 참조
    user_id_fk          VARCHAR(64)     NOT NULL,
    vod_id_fk           VARCHAR(64)     NOT NULL,

    -- 순위 정보
    rank_initial        SMALLINT        NOT NULL,           -- 1차 벡터 검색 순위 (1~1000)
    rank_final          SMALLINT        NOT NULL,           -- Re-Ranking 후 최종 순위 (1~100)

    -- 점수
    similarity_score    NUMERIC(6,4)    NOT NULL,           -- 벡터 유사도 (0.0~1.0)
    rerank_score        NUMERIC(6,4)    NOT NULL,           -- Re-Ranking 최종 점수

    -- Re-Ranking 상세 요소 (JSON)
    -- 예: {"freshness":0.8, "popularity":0.6, "user_match":0.9, "diversity":-0.1}
    rerank_factors      JSONB,

    -- 추천 이유
    reason              VARCHAR(255),                       -- "유사 장르 추천", "인기 상승 작품"

    -- 캐시 관리
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    expired_at          TIMESTAMP,                          -- TTL 만료 시각 (기본 7일)

    -- 사용자 피드백 (재학습용)
    is_clicked          BOOLEAN         NOT NULL DEFAULT FALSE,
    is_watched          BOOLEAN         NOT NULL DEFAULT FALSE,
    click_at            TIMESTAMP,

    CONSTRAINT pk_vod_recommendation PRIMARY KEY (recommendation_id),
    CONSTRAINT uq_recommendation UNIQUE (user_id_fk, vod_id_fk, created_at),
    CONSTRAINT fk_rec_user FOREIGN KEY (user_id_fk)
        REFERENCES users(sha2_hash) ON DELETE CASCADE,
    CONSTRAINT fk_rec_vod  FOREIGN KEY (vod_id_fk)
        REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    CONSTRAINT chk_rank CHECK (rank_final BETWEEN 1 AND 100),
    CONSTRAINT chk_score CHECK (
        similarity_score BETWEEN 0.0 AND 1.0 AND
        rerank_score     BETWEEN 0.0 AND 1.0
    )
);

COMMENT ON TABLE  vod_recommendation              IS '추천 결과 캐시 테이블 - TTL 7일, 일 1회 배치 갱신';
COMMENT ON COLUMN vod_recommendation.rank_initial IS '1차 Milvus 벡터 검색 순위 (1~1000)';
COMMENT ON COLUMN vod_recommendation.rank_final   IS 'Re-Ranking 후 최종 순위 (1~100)';
COMMENT ON COLUMN vod_recommendation.rerank_factors IS 'Re-Ranking 세부 요소 JSON: freshness/popularity/user_match/diversity';
COMMENT ON COLUMN vod_recommendation.expired_at   IS '캐시 만료 시각 (생성 후 7일), 만료+미클릭 → 배치 삭제';
COMMENT ON COLUMN vod_recommendation.is_clicked   IS '사용자 클릭 여부 (피드백 신호, 재학습용)';

-- 유효한 추천 조회용 (가장 빈번한 패턴)
CREATE INDEX idx_rec_user_rank
    ON vod_recommendation(user_id_fk, rank_final)
    WHERE expired_at > NOW();

-- 만료된 캐시 청소용
CREATE INDEX idx_rec_expired
    ON vod_recommendation(expired_at)
    WHERE is_clicked = FALSE;

-- Re-Ranking 점수 기반 조회
CREATE INDEX idx_rec_rerank_score
    ON vod_recommendation(rerank_score DESC);

-- 피드백 분석용
CREATE INDEX idx_rec_clicked
    ON vod_recommendation(user_id_fk, click_at)
    WHERE is_clicked = TRUE;


-- ============================================================
-- TTL 만료 캐시 삭제 함수 (매일 배치로 실행)
-- 사용: SELECT cleanup_expired_recommendations();
-- ============================================================

CREATE OR REPLACE FUNCTION cleanup_expired_recommendations()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM vod_recommendation
    WHERE expired_at < NOW()
      AND is_clicked = FALSE;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'Deleted % expired recommendations', deleted_count;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_recommendations IS
    'TTL 만료 + 미클릭 추천 삭제. 매일 새벽 배치로 실행.';
