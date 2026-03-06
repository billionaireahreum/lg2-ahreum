# Plan 05 - 확장 설계 계획 (Phase 2 이후)

**목표**: 벡터 임베딩 기반 추천 시스템으로 확장
**우선순위**: 선택 (Phase 2 이후)
**선행 조건**: Phase 1 (핵심 3개 테이블) 완료 및 검증

---

## 1. 확장 목표

Phase 1의 핵심 3개 테이블을 기반으로:
1. **VOD_EMBEDDING / USER_EMBEDDING**: 벡터 임베딩 메타데이터 테이블 (PostgreSQL)
2. **Milvus 연동**: 실제 벡터 저장 및 유사도 검색
3. **VOD_RECOMMENDATION**: 추천 결과 캐시 테이블

---

## 2. VOD_EMBEDDING 테이블

벡터는 Milvus에 저장, PostgreSQL에는 메타데이터만 저장.

```sql
CREATE TABLE vod_embedding (
    vod_embedding_id    BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- 참조
    vod_id_fk           VARCHAR(64)     NOT NULL UNIQUE
                        REFERENCES vod(full_asset_id) ON DELETE CASCADE,

    -- Milvus 연동
    milvus_collection   VARCHAR(128),   -- Milvus 컬렉션명
    milvus_vector_id    BIGINT,         -- Milvus 내부 ID

    -- 임베딩 정보
    embedding_type      VARCHAR(32)     NOT NULL,
                        -- 'CONTENT'(1536d), 'METADATA'(384d), 'VISUAL'(512d), 'HYBRID'(2432d)
    embedding_dimension INTEGER         NOT NULL,
    model_version       VARCHAR(64),    -- 'openai-text-embedding-3-large-v1'

    -- 벡터 통계 (빠른 필터링용)
    vector_magnitude    NUMERIC(10,6),  -- L2 norm

    -- 시간
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE vod_embedding IS 'VOD 벡터 임베딩 메타데이터 (실제 벡터는 Milvus에 저장)';
COMMENT ON COLUMN vod_embedding.embedding_type IS 'CONTENT=1536d, METADATA=384d, VISUAL=512d, HYBRID=2432d';

-- 인덱스
CREATE INDEX idx_vod_emb_type ON vod_embedding(embedding_type);
CREATE INDEX idx_vod_emb_updated ON vod_embedding(updated_at DESC);
```

### 벡터 생성 파이프라인
```
VOD 테이블 (smry + asset_nm + genre_detail)
    ↓
RAG 보강 (director, rating, release_date)
    ↓
멀티모달 임베딩 생성
    ├── 텍스트 임베딩 (384d): smry + asset_nm + genre_detail
    ├── 콘텐츠 임베딩 (1536d): OpenAI/Claude multimodal
    └── 시각 임베딩 (512d): thumbnail 이미지
    ↓
벡터 정규화 (L2 normalization)
    ↓
Milvus 저장 (cosine similarity 메트릭)
    +
vod_embedding 메타데이터 저장
```

---

## 3. USER_EMBEDDING 테이블

```sql
CREATE TABLE user_embedding (
    user_embedding_id   BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- 참조
    user_id_fk          VARCHAR(64)     NOT NULL
                        REFERENCES users(sha2_hash) ON DELETE CASCADE,

    -- Milvus 연동
    milvus_collection   VARCHAR(128),
    milvus_vector_id    BIGINT,

    -- 임베딩 정보
    embedding_type      VARCHAR(32)     NOT NULL,
                        -- 'BEHAVIOR'(256d), 'PREFERENCE'(128d), 'DEMOGRAPHIC'(64d), 'HYBRID'(448d)
    embedding_dimension INTEGER         NOT NULL,
    model_version       VARCHAR(64),

    -- 생성 기반
    base_record_count   INTEGER,        -- 사용에 사용된 watch_history 행 수

    -- 시간
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_user_embedding UNIQUE (user_id_fk, embedding_type)
);

COMMENT ON TABLE user_embedding IS '사용자 벡터 임베딩 메타데이터 (실제 벡터는 Milvus에 저장)';

-- 인덱스
CREATE INDEX idx_user_emb_type ON user_embedding(embedding_type);
CREATE INDEX idx_user_emb_updated ON user_embedding(updated_at DESC);
```

### 사용자 벡터 생성 파이프라인

```
WATCH_HISTORY (최근 90일)
    ↓
통계 계산
    ├── 장르별 completion_rate 집계
    ├── 시청 빈도 분포
    └── 시간대별 선호도
    ↓
벡터 생성
    ├── behavior_embedding (256d): 완주율 + 시청빈도
    ├── genre_preference_embedding (128d): 장르별 친화도
    ├── demographic_embedding (64d): 연령대 + 행동율
    └── concat → hybrid (448d)
    ↓
Milvus 저장 + user_embedding 메타데이터 저장
```

---

## 4. VOD_RECOMMENDATION 테이블

```sql
CREATE TABLE vod_recommendation (
    recommendation_id   BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- 참조
    user_id_fk          VARCHAR(64)     NOT NULL
                        REFERENCES users(sha2_hash) ON DELETE CASCADE,
    vod_id_fk           VARCHAR(64)     NOT NULL
                        REFERENCES vod(full_asset_id) ON DELETE CASCADE,

    -- 순위
    rank_initial        SMALLINT        NOT NULL,   -- 1차 벡터 검색 순위 (1~1000)
    rank_final          SMALLINT        NOT NULL,   -- Re-Ranking 후 순위 (1~100)

    -- 점수
    similarity_score    NUMERIC(6,4)    NOT NULL,   -- 벡터 유사도 (0.0~1.0)
    rerank_score        NUMERIC(6,4)    NOT NULL,   -- Re-Ranking 최종 점수

    -- Re-Ranking 상세 (JSON)
    rerank_factors      JSONB,
    -- 예시: {"freshness": 0.8, "popularity": 0.6, "user_match": 0.9, "diversity": -0.1}

    -- 설명
    reason              VARCHAR(255),               -- "유사 장르 추천", "인기 상승 작품"

    -- 캐시 관리
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    expired_at          TIMESTAMP,                  -- TTL (기본 7일)

    -- 피드백 (재학습용)
    is_clicked          BOOLEAN         NOT NULL DEFAULT FALSE,
    is_watched          BOOLEAN         NOT NULL DEFAULT FALSE,
    click_at            TIMESTAMP,

    CONSTRAINT uq_recommendation UNIQUE (user_id_fk, vod_id_fk, created_at)
);

COMMENT ON TABLE vod_recommendation IS '추천 결과 캐시 테이블 (TTL: 7일, 매일 배치 갱신)';
COMMENT ON COLUMN vod_recommendation.rerank_factors IS 'Re-Ranking 세부 요소 JSON';

-- 인덱스
CREATE INDEX idx_rec_user_rank ON vod_recommendation(user_id_fk, rank_final)
    WHERE expired_at > NOW();                       -- 유효한 추천만 인덱싱

CREATE INDEX idx_rec_expired ON vod_recommendation(expired_at)
    WHERE is_clicked = FALSE;                       -- 만료된 비클릭 추천 청소용

CREATE INDEX idx_rec_rerank ON vod_recommendation(rerank_score DESC);
```

---

## 5. 추천 파이프라인 설계

### 5.1 전체 흐름

```
사용자 요청 (user_id)
    ↓
[Step 1] Redis L1 캐시 확인 (TTL 1시간)
    ├── 히트: 즉시 반환
    └── 미스 → [Step 2]
    ↓
[Step 2] PostgreSQL VOD_RECOMMENDATION 확인 (TTL 7일)
    ├── 히트: Redis에 캐시 후 반환
    └── 미스 → [Step 3]
    ↓
[Step 3] 콜드스타트 처리
    ├── watch_history 0건: 인구통계 기반 벡터 생성
    └── watch_history 있음: USER_EMBEDDING 조회
    ↓
[Step 4] Milvus 벡터 검색 (Top-1000)
    ├── user_embedding vs vod_embedding
    └── cosine similarity
    ↓
[Step 5] Re-Ranking
    ├── freshness_boost: 신규 VOD 가산점
    ├── popularity: watch_history 빈도
    ├── diversity_penalty: 동일 장르 과다 감점
    └── business_rule: 유료/무료 정책
    ↓
[Step 6] Top-100 결정
    ↓
[Step 7] VOD_RECOMMENDATION 저장 (TTL 7일)
    ↓
[Step 8] Redis 캐시 저장 (TTL 1시간)
    ↓
응답
```

### 5.2 콜드스타트 처리

```sql
-- 신규 사용자 (watch_history 없음): 동일 세그먼트 인기 VOD
SELECT
    v.full_asset_id,
    v.asset_nm,
    COUNT(wh.watch_history_id) AS view_count,
    AVG(wh.satisfaction) AS avg_sat
FROM vod v
JOIN watch_history wh ON v.full_asset_id = wh.vod_id_fk
JOIN users u ON wh.user_id_fk = u.sha2_hash
WHERE u.age_grp10 = $1           -- 같은 연령대
  AND wh.satisfaction > 0.6
  AND v.is_active = TRUE
GROUP BY v.full_asset_id, v.asset_nm
HAVING COUNT(*) >= 10
ORDER BY avg_sat DESC, view_count DESC
LIMIT 100;
```

---

## 6. pgvector 옵션 (Milvus 대안)

소규모 운영 시 PostgreSQL 내에서 벡터 검색 가능:

```sql
-- pgvector 설치
CREATE EXTENSION vector;

-- VOD 벡터 저장 (1536차원)
ALTER TABLE vod_embedding
ADD COLUMN content_vector vector(1536);

-- HNSW 인덱스 생성
CREATE INDEX idx_vod_vector_hnsw
    ON vod_embedding
    USING hnsw (content_vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 유사도 검색
SELECT vod_id_fk, 1 - (content_vector <=> $1::vector) AS similarity
FROM vod_embedding
ORDER BY content_vector <=> $1::vector
LIMIT 100;
```

| 기준 | pgvector | Milvus |
|------|---------|--------|
| 설치 복잡도 | 낮음 (확장) | 높음 (별도 서버) |
| 검색 성능 | HNSW (충분) | HNSW (더 빠름) |
| 확장성 | PostgreSQL 제한 | 독립 스케일 |
| 운영 비용 | 낮음 | 높음 |
| 권장 규모 | VOD < 500,000개 | VOD > 500,000개 |

**현재 VOD 166,159개 → pgvector로 시작, 필요 시 Milvus로 마이그레이션**

---

## 7. 단계별 구현 순서

| Phase | 목표 | 선행 조건 |
|-------|------|---------|
| **1** | USER, VOD, WATCH_HISTORY DDL + 마이그레이션 | - |
| **2a** | VOD_EMBEDDING 테이블 + 텍스트 임베딩 생성 | Phase 1 완료 |
| **2b** | USER_EMBEDDING 테이블 + 행동 벡터 생성 | Phase 1 완료 |
| **3** | VOD_RECOMMENDATION + Re-Ranking 로직 | Phase 2 완료 |
| **4** | Redis 캐시 연동 | Phase 3 완료 |
| **5** | 피드백 루프 (클릭 → 모델 재학습) | Phase 4 완료 |

---

## 8. 주요 설계 결정사항 (확장 관련)

### 8.1 벡터 저장소 선택
- **Phase 2 초기**: pgvector (설치 간단, 현재 규모 충분)
- **스케일 아웃 시**: Milvus 마이그레이션 (독립적 수평 확장)

### 8.2 추천 캐시 TTL
- Redis (L1): 1시간 (실시간 활성 사용자)
- PostgreSQL VOD_RECOMMENDATION (L2): 7일 (배치 사용자)
- 만료 정책: 매일 새벽 `DELETE WHERE expired_at < NOW() AND is_clicked = FALSE`

### 8.3 임베딩 갱신 주기
| 임베딩 | 갱신 주기 | 이유 |
|--------|---------|------|
| VOD 메타데이터 벡터 | 월 1회 | 콘텐츠 거의 변경 없음 |
| VOD 인기도 반영 벡터 | 주 1회 | 시청 트렌드 반영 |
| USER 행동 벡터 | 주 1회 | 시청 패턴 변화 반영 |
| USER 인구통계 벡터 | 월 1회 | 거의 변경 없음 |
