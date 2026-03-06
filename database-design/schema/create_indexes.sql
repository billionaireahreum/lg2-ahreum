-- ============================================================
-- VOD 추천 시스템 - 인덱스 DDL
-- 대상 DB : vod_recommendation
-- 작성일  : 2026-03-06
-- 참고    : database-design/.claude/plans/03_PERFORMANCE_PLAN.md
--
-- 실행 전제: create_tables.sql 실행 완료
-- 실행 시점: 마이그레이션(데이터 적재) 완료 후 실행 권장
--            (대용량 INSERT 중 인덱스 유지 오버헤드 방지)
-- ============================================================


-- ============================================================
-- 1. WATCH_HISTORY 인덱스 (성능에 가장 중요)
-- ============================================================

-- [HIGH] 사용자별 시청이력 조회 - 가장 빈번한 패턴
-- 쿼리: WHERE user_id_fk = ?
CREATE INDEX idx_wh_user_id
    ON watch_history(user_id_fk);

-- [HIGH] VOD별 시청 통계 조회
-- 쿼리: WHERE vod_id_fk = ?
CREATE INDEX idx_wh_vod_id
    ON watch_history(vod_id_fk);

-- [HIGH] 날짜 범위 조회
-- 쿼리: WHERE strt_dt BETWEEN ? AND ?
CREATE INDEX idx_wh_strt_dt
    ON watch_history(strt_dt DESC);

-- [MEDIUM] 사용자별 시간순 조회 - 커버링 인덱스 효과
-- 쿼리: WHERE user_id_fk = ? ORDER BY strt_dt DESC
CREATE INDEX idx_wh_user_strt
    ON watch_history(user_id_fk, strt_dt DESC);

-- [MEDIUM] 만족도 상위 VOD 조회 (0점 제외 부분 인덱스)
-- 쿼리: ORDER BY satisfaction DESC / WHERE satisfaction > 0.6
CREATE INDEX idx_wh_satisfaction
    ON watch_history(satisfaction DESC)
    WHERE satisfaction > 0;

-- [MEDIUM] VOD별 만족도 집계
-- 쿼리: WHERE vod_id_fk = ? + AVG(satisfaction)
CREATE INDEX idx_wh_vod_sat
    ON watch_history(vod_id_fk, satisfaction);


-- ============================================================
-- 2. VOD 인덱스
-- ============================================================

-- [HIGH] 콘텐츠 유형 필터링
-- 쿼리: WHERE ct_cl = '영화'
CREATE INDEX idx_vod_ct_cl
    ON vod(ct_cl);

-- [MEDIUM] 장르 필터링
-- 쿼리: WHERE genre = '드라마'
CREATE INDEX idx_vod_genre
    ON vod(genre);

-- [LOW] RAG 배치 처리 대상 조회 (부분 인덱스)
-- 쿼리: WHERE rag_processed = FALSE (배치 작업용)
CREATE INDEX idx_vod_rag_pending
    ON vod(created_at)
    WHERE rag_processed = FALSE;

-- [MEDIUM] 전문 검색 (GIN 인덱스)
-- 쿼리: WHERE to_tsvector(...) @@ to_tsquery(?)
-- 참고: 한국어 형태소 분석은 'simple' config 사용
--       pg_bigm 확장 설치 시 더 정확한 한국어 검색 가능
CREATE INDEX idx_vod_fts
    ON vod
    USING GIN (
        to_tsvector('simple',
            COALESCE(asset_nm, '') || ' ' ||
            COALESCE(smry, '')    || ' ' ||
            COALESCE(genre, '')
        )
    );


-- ============================================================
-- 3. USERS 인덱스
-- ============================================================

-- [MEDIUM] 연령대 세그멘테이션 / 콜드스타트 추천
-- 쿼리: WHERE age_grp10 = '30대'
CREATE INDEX idx_users_age
    ON users(age_grp10);

-- [LOW] NFX 사용자 필터 (부분 인덱스 - 전체의 ~13%)
-- 쿼리: WHERE nfx_use_yn = TRUE
CREATE INDEX idx_users_nfx
    ON users(sha2_hash)
    WHERE nfx_use_yn = TRUE;


-- ============================================================
-- 4. 인덱스 생성 확인
-- ============================================================

-- 아래 쿼리로 생성된 인덱스 목록 확인:
--
-- SELECT indexname, tablename, indexdef
-- FROM pg_indexes
-- WHERE tablename IN ('users', 'vod', 'watch_history')
--   AND schemaname = 'public'
-- ORDER BY tablename, indexname;
