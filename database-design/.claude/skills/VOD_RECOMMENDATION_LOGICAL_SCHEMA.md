# VOD 추천 웹서비스 논리적 스키마 설계 문서

**프로젝트명**: 고성능 VOD 추천 엔진 (10,000 QPS 기준)  
**버전**: 1.0  
**작성일**: 2026-03-05  
**대상 시스템**: 하이브리드 검색 기반 추천 시스템 (Milvus + PostgreSQL 멀티 티어 캐싱)

---

## 1. 요구사항 분석

### 1.1 핵심 요구사항
- **추천 아키텍처**: 벡터 임베딩 기반 하이브리드 검색 (메타데이터 + 의미적 유사도)
- **성능 목표**: 10,000 QPS 처리, 밀리초 단위 레이턴시
- **데이터 출처**: RAG를 통한 메타데이터 보강 + 사용자 행동 데이터
- **추천 로직**: 2단계 (1차 검색 → Re-Ranking)

### 1.2 엔티티 영역 분류
1. **VOD 영역**: 콘텐츠 메타데이터 및 파생 특성
2. **유저 영역**: 인구통계학적 데이터 및 행동 패턴
3. **시청 이력 영역**: 사용자-콘텐츠 상호작용 기록
4. **벡터/임베딩 영역**: 고차원 표현 및 추천 결과

---

## 2. 엔티티-관계 모델 (개념적 설계)

### 2.1 VOD (Video On Demand) 엔티티

#### 목적
콘텐츠 고유의 메타데이터를 저장하며, 벡터 임베딩의 기초 정보 제공

#### 주요 속성 분류

| 범주 | 용도 | 속성 |
|------|------|------|
| **식별자** | 고유성 보증 | full_asset_id |
| **기본 메타데이터** | 검색/필터링 | asset_nm, CT_CL, genre, provider, genre_detail |
| **구조적 정보** | 시리즈 관리 | series_nm, episode_number (NEW) |
| **기술 사양** | 콘텐츠 처리 | disp_rtm, resolution (NEW), format (NEW) |
| **제작진 정보** | 검색/RAG 소스 | director, cast_lead, cast_guest |
| **설명 및 요약** | 임베딩 입력 | smry, keywords (NEW) |
| **분류 정보** | 필터/추천 | rating, age_certification (NEW) |
| **시간 정보** | 시계열 분석 | release_date, created_at (NEW), updated_at (NEW) |
| **비즈니스 정보** | 수익화 | asset_prod (결제 유형) |
| **미디어 자산** | 임베딩/UI 렌더링 | thumbnail, poster_url (NEW), video_preview_url (NEW) |

---

### 2.2 USER 엔티티

#### 목적
사용자의 인구통계학적 특성과 행동 패턴을 저장하며, 추천 개인화의 기초 제공

#### 주요 속성 분류

| 범주 | 용도 | 속성 | 데이터 타입 | 갱신 빈도 |
|------|------|------|----------|---------|
| **식별자** | 고유성 | sha2_hash | VARCHAR(64) | 정적 |
| **인구통계** | 세그멘테이션 | age_grp10, gender (NEW) | ENUM | 연 1회 |
| **행동 패턴** | 프로파일링 | inhome_rate, ch_hh_avg_month1 | INTEGER/FLOAT | 월 1회 |
| **구독 현황** | 비즈니스 인텔 | svod_scrb_cnt_grp, paid_chnl_cnt_grp | INTEGER | 일 1회 |
| **특화 컨텐츠** | 선호도 세그먼트 | kids_use_pv_month1, genre_preference_flags (NEW) | INTEGER/BITFIELD | 월 1회 |
| **외부 서비스** | 시장 분석 | nfx_use_yn | BOOLEAN | 월 1회 |
| **메타데이터** | 관리 | created_at, last_active_at (NEW) | TIMESTAMP | 매 세션 |

---

### 2.3 WATCH_HISTORY 엔티티

#### 목적
사용자-콘텐츠 상호작용을 기록하며, 추천 모델의 핵심 신호 제공

#### 주요 속성 분류

| 범주 | 용도 | 속성 | 계산 방식 |
|------|------|------|---------|
| **식별자** | 추적 | watch_history_id (NEW) | PRIMARY KEY |
| **관계** | 조인 | user_id_fk, vod_id_fk (NEW) | FOREIGN KEY |
| **시간 정보** | 시계열 | strt_dt, end_dt (NEW), watched_at (NEW) | TIMESTAMP |
| **재생 통계** | 파생 지표 | use_tms (초), completion_rate | use_tms / disp_rtm * 100 |
| **만족도 지표** | 추천 신호 | satisfaction (베이지안 스코어) | (v*R + m*C)/(v+m): v=시청건수, R=시청비율, C=전체평균, m=5.0 |
| **세션 정보** | 분석 | device_type (NEW), playback_quality (NEW) | ENUM |
| **상태 관리** | 비즈니스 로직 | status (완료/중단/재개), is_rewatch (NEW) | ENUM/BOOLEAN |

#### 만족도(Satisfaction) 계산 로직 - 베이지안 스코어 기반

베이지안 평점 알고리즘을 기반으로 한 신뢰도 기반 만족도 계산

**공식**:
```
satisfaction = (v * R + m * C) / (v + m)

변수:
- v: 영상별 시청 건수 (시청 이력이 많을수록 신뢰도 높음)
- R: 시청 비율 (completion_rate) = use_tms / disp_rtm (0 ~ 1)
- C: 전체 영상의 평균 시청 비율 (global average)
- m: 신뢰도 조절 파라미터 (기본값: 5.0)

범위: 0.0 ~ 1.0
```

**로직 설명**:

1. **v (시청 건수)**: 영상당 시청 회수
   - v가 클수록 (많이 시청된 영상) 실제 시청 비율 R의 신뢰도 증가
   - 적은 시청 횟수의 영상은 전체 평균 C로 보정되어 과대평가 방지
   - 예: 히트작(v=1000)과 신작(v=5)의 만족도가 동일한 R값이라도 차별화

2. **R (시청 비율)**: 개별 영상의 완주율
   - use_tms_float / disp_rtm_sec
   - 0 (미시청) ~ 1 (완주) 범위

3. **C (전체 평균)**: 데이터셋 전체의 평균 시청 비율
   - 전역 기준점 제공
   - 어떤 영상이 "좋은" 완주율인지 컨텍스트 제공

4. **m (신뢰도 조절 파라미터)**
   - m이 작을수록 (예: 0.1): 개별 영상의 R을 더 중요하게 반영
   - m이 클수록 (예: 10.0): 전체 평균 C의 비중이 증가 (보수적 평가)
   - 권장 범위: 0.1 ~ 10.0 (데이터 특성에 따라 조정)
   - 기본값 5.0: 시청 건수 5회를 신뢰도 기준점으로 설정

**계산 예시**:
```
C = 0.5 (전체 평균 시청 비율), m = 5.0

영상 A: v=100, R=0.8
→ satisfaction = (100*0.8 + 5*0.5) / (100+5) = 82.5/105 = 0.786
  → 해석: 많이 시청된 영상(v=100), 높은 완주율(0.8)이므로 높은 신뢰도

영상 B: v=1, R=0.9
→ satisfaction = (1*0.9 + 5*0.5) / (1+5) = 3.4/6 = 0.567
  → 해석: 한 번만 시청(v=1)된 영상이므로 평균(C=0.5)에 가깝게 보정됨

영상 C: v=10, R=0.3
→ satisfaction = (10*0.3 + 5*0.5) / (10+5) = 5.5/15 = 0.367
  → 해석: 여러 번 시청되었지만 낮은 완주율이므로 낮은 만족도

결론: 시청 건수(신뢰도)를 고려하여 영상의 실제 품질을 반영
```

**데이터 품질 필터**:
```python
# 시청 시간 60초 이하 또는 정보미상(NaN) → 0점 처리
satisfaction = 0 if (use_tms_float <= 60 or use_tms_float.isna())
```

---

### 2.4 VOD_EMBEDDING 엔티티

#### 목적
콘텐츠의 고차원 벡터 표현을 저장하며, 빠른 유사도 검색 가능

#### 주요 속성 분류

| 속성 | 차원 | 생성 방식 | 갱신 빈도 | 저장소 |
|------|------|---------|---------|------|
| **콘텐츠 벡터** | 1536 | OpenAI/Claude multimodal embedding | 월 1회 | Milvus |
| **메타데이터 벡터** | 384 | 텍스트 임베딩 (제목+줄거리+장르) | 월 1회 | Milvus |
| **시각적 벡터** | 512 | 썸네일/포스터 이미지 임베딩 | 월 1회 | Milvus |
| **복합 벡터** | 2432 | 모든 벡터의 concatenation | 월 1회 | Milvus |
| **메타데이터** | - | vod_id_fk, embedding_model_version | - | PostgreSQL |

#### 벡터 생성 파이프라인
```
1. 원본 데이터 수집: smry + cast_lead + genre_detail
2. RAG 보강: director, rating, release_date 추가 정보
3. 멀티모달 인코딩: 텍스트 + 이미지
4. 벡터 정규화: L2 normalization
5. Milvus 저장: 메트릭 = cosine similarity
```

---

### 2.5 USER_EMBEDDING 엔티티

#### 목적
사용자의 행동 패턴과 선호도를 고차원 표현으로 변환

#### 주요 속성 분류

| 속성 | 차원 | 생성 방식 | 갱신 빈도 |
|------|------|---------|---------|
| **행동 임베딩** | 256 | 시청 이력 + 완주율 통계 | 주 1회 |
| **장르 선호도 벡터** | 128 | 각 장르별 완주율 분포 | 주 1회 |
| **인구통계 벡터** | 64 | 연령대 + 성별 + 행동율 인코딩 | 월 1회 |
| **복합 벡터** | 448 | 모든 벡터의 concatenation | 주 1회 |

#### 생성 로직
```
user_embedding = concat(
    behavior_embedding(completion_rates, watch_frequency),
    genre_preference_embedding(genre_affinity_scores),
    demographic_embedding(age_grp10, gender, inhome_rate),
    temporal_embedding(seasonality, time_of_day_preference)
)
```

---

### 2.6 VOD_RECOMMENDATION 엔티티 (NEW)

#### 목적
1차 벡터 검색 결과를 저장하고 Re-Ranking에 사용

#### 주요 속성 분류

| 속성 | 용도 | 설명 |
|------|------|------|
| **recommendation_id** | 추적 | PRIMARY KEY |
| **user_id_fk** | 참조 | 추천 대상 사용자 |
| **vod_id_fk** | 참조 | 추천 대상 VOD |
| **rank_initial** | 1차 순위 | Milvus 검색 결과 순위 (1~1000) |
| **rank_final** | 최종 순위 | Re-Ranking 후 최종 순위 |
| **similarity_score** | 유사도 | 벡터 유사도 점수 (0.0~1.0) |
| **rerank_score** | 종합 점수 | 콜드스타트 필터 + 비즈니스 로직 + 유사도 |
| **rerank_factors** | 상세 정보 | JSON {freshness: 0.8, popularity: 0.6, ...} |
| **reason** | 설명 | "유사 장르 추천", "인기 작품" 등 |
| **created_at** | 타임스탐프 | 추천 생성 시각 |
| **expired_at** | TTL | 캐시 만료 시간 |
| **is_clicked** | 피드백 | 사용자 클릭 여부 (재학습용) |

---

## 3. 논리적 스키마 설계 (DDL)

### 3.1 VOD 테이블

```sql
CREATE TABLE vod (
    -- 식별자
    full_asset_id VARCHAR(64) PRIMARY KEY,
    
    -- 기본 메타데이터
    asset_nm VARCHAR(255) NOT NULL,
    ct_cl VARCHAR(32) NOT NULL,  -- 대분류 (드라마/영화/예능 등)
    genre VARCHAR(64),
    provider VARCHAR(128),
    genre_detail VARCHAR(255),
    
    -- 구조적 정보
    series_nm VARCHAR(255),
    episode_number INTEGER,
    is_series BOOLEAN DEFAULT FALSE,
    
    -- 기술 사양
    disp_rtm INTEGER NOT NULL,  -- 영상 길이 (초)
    resolution VARCHAR(16),  -- 1080p, 4K 등
    format VARCHAR(32),  -- mp4, mkv 등
    
    -- 제작진
    director VARCHAR(255),
    cast_lead TEXT,  -- JSON 배열: [{"name": "...", "role": "..."}, ...]
    cast_guest TEXT,
    
    -- 설명 및 요약
    smry TEXT,  -- 줄거리
    keywords TEXT,  -- JSON 배열
    
    -- 분류 정보
    rating VARCHAR(16),  -- 전체이용가, 12세 이상 등
    age_certification INTEGER,  -- 0, 12, 15, 18
    
    -- 시간 정보
    release_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 비즈니스 정보
    asset_prod VARCHAR(16),  -- 'FREE', 'PAID'
    is_active BOOLEAN DEFAULT TRUE,
    
    -- 미디어 자산
    thumbnail VARCHAR(512),  -- S3 URL
    poster_url VARCHAR(512),
    video_preview_url VARCHAR(512),
    
    -- 인덱싱
    INDEX idx_ct_cl (ct_cl),
    INDEX idx_genre (genre),
    INDEX idx_release_date (release_date),
    INDEX idx_asset_prod (asset_prod),
    FULLTEXT INDEX idx_smry (smry),
    FULLTEXT INDEX idx_asset_nm (asset_nm)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 3.2 USER 테이블

```sql
CREATE TABLE user (
    -- 식별자
    sha2_hash VARCHAR(64) PRIMARY KEY,
    
    -- 인구통계
    age_grp10 VARCHAR(16),  -- '10s', '20s', '30s', ...
    gender VARCHAR(8),  -- 'M', 'F', 'U' (Unknown)
    
    -- 행동 패턴
    inhome_rate INTEGER,  -- 0~100: 집돌이 지수 백분율
    ch_hh_avg_month1 FLOAT,  -- 월 평균 TV 시청 시간
    
    -- 구독 현황
    svod_scrb_cnt_grp INTEGER,  -- 구독 VOD 시청 횟수 그룹
    paid_chnl_cnt_grp INTEGER,  -- 유료 채널 결제 횟수 그룹
    
    -- 특화 콘텐츠
    kids_use_pv_month1 INTEGER,  -- 키즈 콘텐츠 월 시청 횟수
    genre_preference_flags VARCHAR(256),  -- BITFIELD: 각 장르별 관심도
    
    -- 외부 서비스
    nfx_use_yn BOOLEAN,  -- Netflix 사용 여부
    
    -- 메타데이터
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    
    -- 인덱싱
    INDEX idx_age_grp10 (age_grp10),
    INDEX idx_gender (gender),
    INDEX idx_last_active_at (last_active_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 3.3 WATCH_HISTORY 테이블

```sql
CREATE TABLE watch_history (
    -- 식별자
    watch_history_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 관계
    user_id_fk VARCHAR(64) NOT NULL,
    vod_id_fk VARCHAR(64) NOT NULL,
    
    -- 시간 정보
    strt_dt TIMESTAMP NOT NULL,
    end_dt TIMESTAMP,
    watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 재생 통계
    use_tms INTEGER NOT NULL,  -- 시청 시간 (초)
    completion_rate FLOAT GENERATED ALWAYS AS (
        (CAST(use_tms AS FLOAT) / 
         COALESCE((SELECT disp_rtm FROM vod WHERE full_asset_id = vod_id_fk), 1)) * 100
    ) STORED,  -- 완주율 (%)
    
    -- 만족도 지표 (베이지안 스코어)
    satisfaction FLOAT,
    
    -- 세션 정보
    device_type VARCHAR(32),  -- 'PC', 'MOBILE', 'TV'
    playback_quality VARCHAR(16),  -- '480p', '720p', '1080p', '4K'
    
    -- 상태 관리
    status VARCHAR(16),  -- 'COMPLETED', 'ABANDONED', 'PAUSED'
    is_rewatch BOOLEAN DEFAULT FALSE,
    
    -- 인덱싱
    FOREIGN KEY (user_id_fk) REFERENCES user(sha2_hash) ON DELETE CASCADE,
    FOREIGN KEY (vod_id_fk) REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id_fk),
    INDEX idx_vod_id (vod_id_fk),
    INDEX idx_strt_dt (strt_dt),
    INDEX idx_completion_rate (completion_rate),
    INDEX idx_satisfaction (satisfaction),
    UNIQUE KEY unique_watch_session (user_id_fk, vod_id_fk, strt_dt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### WATCH_HISTORY 만족도 계산 트리거
```sql
CREATE TRIGGER trg_calculate_satisfaction
BEFORE INSERT ON watch_history
FOR EACH ROW
BEGIN
    DECLARE v_count INT;
    DECLARE global_avg_completion FLOAT;
    DECLARE bayesian_m FLOAT;
    DECLARE watch_ratio FLOAT;
    
    -- 파라미터 설정
    SET bayesian_m = 5.0;  -- 신뢰도 조절 파라미터
    
    -- 1. 영상별 시청 건수(v) 조회
    SELECT COUNT(*) INTO v_count
    FROM watch_history
    WHERE vod_id_fk = NEW.vod_id_fk
      AND watch_history_id != COALESCE(NEW.watch_history_id, -1);
    
    -- v가 0이면 현재 레코드가 첫 번째 시청이므로 1로 설정
    IF v_count IS NULL THEN
        SET v_count = 1;
    ELSE
        SET v_count = v_count + 1;  -- 현재 삽입 포함
    END IF;
    
    -- 2. 전체 시청 비율 평균(C) 계산
    SELECT AVG(CAST(use_tms AS FLOAT) / 
               COALESCE((SELECT disp_rtm FROM vod WHERE full_asset_id = wh.vod_id_fk), 1))
    INTO global_avg_completion
    FROM watch_history wh
    WHERE use_tms > 0;
    
    -- 평균값이 NULL이면 기본값 설정
    IF global_avg_completion IS NULL THEN
        SET global_avg_completion = 0.5;
    END IF;
    
    -- 3. 현재 레코드의 시청 비율(R) 계산
    SET watch_ratio = CAST(NEW.use_tms AS FLOAT) / 
                      COALESCE((SELECT disp_rtm FROM vod WHERE full_asset_id = NEW.vod_id_fk), 1);
    SET watch_ratio = LEAST(watch_ratio, 1.0);  -- 0~1 범위로 클립
    
    -- 4. 베이지안 스코어 계산
    -- satisfaction = (v * R + m * C) / (v + m)
    SET NEW.satisfaction = (v_count * watch_ratio + bayesian_m * global_avg_completion) / 
                           (v_count + bayesian_m);
    
    -- 5. 데이터 품질 필터: 시청 시간 60초 이하 또는 NULL → 0점
    IF NEW.use_tms <= 60 OR NEW.use_tms IS NULL THEN
        SET NEW.satisfaction = 0.0;
    END IF;
END;
```

---

### 3.4 VOD_EMBEDDING 테이블

```sql
CREATE TABLE vod_embedding (
    -- 식별자
    vod_embedding_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 참조
    vod_id_fk VARCHAR(64) NOT NULL UNIQUE,
    
    -- 벡터 저장소 메타데이터
    milvus_collection_id VARCHAR(128),  -- Milvus 컬렉션명
    vector_id BIGINT,  -- Milvus 내부 ID
    
    -- 임베딩 정보
    embedding_type VARCHAR(32),  -- 'CONTENT', 'METADATA', 'VISUAL', 'HYBRID'
    embedding_dimension INTEGER,  -- 1536, 384, 512, 2432 등
    embedding_model_version VARCHAR(64),  -- 'openai-embedding-3-large-v1' 등
    
    -- 벡터 통계 (검색 최적화용)
    vector_magnitude FLOAT,  -- L2 norm for quick distance calc
    max_component_value FLOAT,  -- 벡터 성분의 최댓값
    
    -- 시간 정보
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 인덱싱
    FOREIGN KEY (vod_id_fk) REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    INDEX idx_milvus_id (milvus_collection_id),
    INDEX idx_embedding_type (embedding_type),
    INDEX idx_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**주요 설계 결정**:
- 실제 벡터는 Milvus에 저장, PostgreSQL에는 메타데이터만 저장
- 벡터 버전 관리를 통해 모델 업데이트 시 점진적 마이그레이션 가능

---

### 3.5 USER_EMBEDDING 테이블

```sql
CREATE TABLE user_embedding (
    -- 식별자
    user_embedding_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 참조
    user_id_fk VARCHAR(64) NOT NULL,
    
    -- 벡터 저장소 메타데이터
    milvus_collection_id VARCHAR(128),  -- Milvus 컬렉션명
    vector_id BIGINT,  -- Milvus 내부 ID
    
    -- 임베딩 정보
    embedding_type VARCHAR(32),  -- 'BEHAVIOR', 'PREFERENCE', 'DEMOGRAPHIC', 'HYBRID'
    embedding_dimension INTEGER,
    embedding_model_version VARCHAR(64),
    
    -- 생성 기반
    base_record_count INTEGER,  -- 생성에 사용된 watch_history 개수
    
    -- 시간 정보
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 인덱싱
    FOREIGN KEY (user_id_fk) REFERENCES user(sha2_hash) ON DELETE CASCADE,
    INDEX idx_milvus_id (milvus_collection_id),
    INDEX idx_embedding_type (embedding_type),
    INDEX idx_updated_at (updated_at),
    UNIQUE KEY unique_user_embedding (user_id_fk, embedding_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 3.6 VOD_RECOMMENDATION 테이블

```sql
CREATE TABLE vod_recommendation (
    -- 식별자
    recommendation_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- 참조
    user_id_fk VARCHAR(64) NOT NULL,
    vod_id_fk VARCHAR(64) NOT NULL,
    
    -- 순위 정보
    rank_initial INTEGER NOT NULL,  -- 1차 벡터 검색 순위
    rank_final INTEGER NOT NULL,  -- Re-Ranking 후 순위
    
    -- 점수
    similarity_score FLOAT NOT NULL,  -- 벡터 유사도 (0.0~1.0)
    rerank_score FLOAT NOT NULL,  -- 최종 점수
    
    -- Re-Ranking 상세 정보 (JSON)
    rerank_factors JSON,  -- {
                          --   "freshness": 0.8,
                          --   "popularity": 0.6,
                          --   "user_preference_match": 0.9,
                          --   "diversity_penalty": -0.1,
                          --   "cold_start_boost": 0.2
                          -- }
    
    -- 설명
    reason VARCHAR(255),  -- "유사 장르 추천", "인기 상승 작품", ...
    
    -- 캐시 관리
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expired_at TIMESTAMP,  -- TTL 만료 시간 (1주일)
    
    -- 피드백
    is_clicked BOOLEAN DEFAULT FALSE,
    is_watched BOOLEAN DEFAULT FALSE,
    click_timestamp TIMESTAMP NULL,
    
    -- 인덱싱
    FOREIGN KEY (user_id_fk) REFERENCES user(sha2_hash) ON DELETE CASCADE,
    FOREIGN KEY (vod_id_fk) REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id_fk),
    INDEX idx_vod_id (vod_id_fk),
    INDEX idx_rank_final (rank_final),
    INDEX idx_rerank_score (rerank_score),
    INDEX idx_created_at (created_at),
    INDEX idx_expired_at (expired_at),
    UNIQUE KEY unique_recommendation (user_id_fk, vod_id_fk, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**TTL 관리 및 청소**:
```sql
-- 만료된 추천 일괄 삭제 (매일 새벽)
DELETE FROM vod_recommendation 
WHERE expired_at < NOW() AND is_clicked = FALSE;

-- 혹은 소프트 삭제 + 아카이브로 전환
UPDATE vod_recommendation 
SET is_active = FALSE 
WHERE expired_at < NOW() AND is_clicked = FALSE;
```

---

## 4. 데이터 흐름 및 처리 파이프라인

### 4.1 VOD 메타데이터 파이프라인

```
원본 데이터 (기존 VOD 마트)
    ↓
[데이터 검증 & 정규화]
    ├─ NULL 값 처리
    ├─ 중복 제거
    └─ 포맷 표준화
    ↓
VOD 테이블 INSERT/UPDATE
    ↓
[RAG 보강]  ← Claude API
    ├─ cast_lead 추출
    ├─ cast_guest 보강
    ├─ rating 자동 분류
    └─ release_date 검증
    ↓
VOD 테이블 UPDATE (RAG 컬럼)
    ↓
[멀티모달 임베딩 생성]
    ├─ 텍스트: smry + asset_nm + genre_detail
    ├─ 이미지: thumbnail → OpenAI vision embedding
    └─ 메타: director + cast_lead 병렬 처리
    ↓
Milvus 저장 (벡터)
VOD_EMBEDDING 테이블 저장 (메타)
```

### 4.2 사용자 벡터 생성 파이프라인

```
WATCH_HISTORY 조회 (최근 90일)
    ↓
[통계 계산]
    ├─ 장르별 완주율 집계
    ├─ 시청 빈도 분포
    └─ 시간대별 선호도
    ↓
[벡터 생성]
    ├─ behavior_embedding: 완주율 + 시청 빈도
    ├─ genre_preference_embedding: 장르별 친화도
    ├─ demographic_embedding: 나이 + 성별 + 행동율
    └─ temporal_embedding: 요일별 + 시간대별 선호
    ↓
벡터 정규화 (L2 Norm)
    ↓
Milvus 저장 (벡터)
USER_EMBEDDING 테이블 저장 (메타)
```

### 4.3 추천 생성 파이프라인

```
사용자 요청 (user_id)
    ↓
[1단계: 콜드스타트 처리]
    ├─ 신규 사용자? → 인구통계 기반 벡터 생성
    ├─ 활동 부족? → 장르 기본값 적용
    └─ 기존 사용자? → USER_EMBEDDING 조회
    ↓
[2단계: 벡터 검색 (Milvus)]
    ├─ user_embedding과 vod_embedding 코사인 유사도
    ├─ Top-1000 결과 반환
    └─ similarity_score 계산
    ↓
[3단계: Re-Ranking]
    ├─ 콜드스타트 필터: 신규 VOD 가산점
    ├─ 인기도: watch_history 빈도 기반
    ├─ 다양성: 이미 추천된 장르 감점
    ├─ 비즈니스 로직: 유료/무료 정책
    └─ 개인화: 사용자 선호도 재조정
    ↓
최종 순위 결정 (Top-100)
    ↓
VOD_RECOMMENDATION 캐시 저장 (TTL: 7일)
    ↓
응답 (100개 추천 리스트)
```

---

## 5. 성능 최적화 전략

### 5.1 인덱싱 전략

| 테이블 | 인덱스 | 목적 | 우선순위 |
|--------|--------|------|---------|
| **VOD** | ct_cl, genre, asset_prod | 필터링 | HIGH |
| **VOD** | FULLTEXT(smry, asset_nm) | 텍스트 검색 | MEDIUM |
| **WATCH_HISTORY** | (user_id, vod_id, strt_dt) | 조인 및 시계열 조회 | HIGH |
| **WATCH_HISTORY** | completion_rate, satisfaction | 분석 쿼리 | MEDIUM |
| **USER** | (age_grp10, gender) | 세그멘테이션 | MEDIUM |
| **VOD_RECOMMENDATION** | (user_id, rank_final, created_at) | 캐시 조회 및 갱신 | HIGH |

### 5.2 파티셔닝 전략

```sql
-- WATCH_HISTORY 시간 기반 파티셔닝
ALTER TABLE watch_history PARTITION BY RANGE (YEAR(strt_dt)) (
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN MAXVALUE
);

-- VOD_RECOMMENDATION 사용자 기반 파티셔닝 (HASH)
ALTER TABLE vod_recommendation PARTITION BY HASH (CRC32(user_id_fk)) PARTITIONS 128;
```

### 5.3 캐싱 전략

| 캐시 레이어 | 대상 | TTL | 갱신 방식 |
|----------|------|-----|---------|
| **Redis L1** | 상위 1,000명 활성 사용자 추천 | 1시간 | 실시간 |
| **PostgreSQL** | VOD_RECOMMENDATION 캐시 | 7일 | 일 1회 배치 |
| **Milvus L2** | 벡터 인덱스 (HNSW) | 무제한 | 주 1회 리인덱싱 |

---

## 6. 콜드스타트 문제 해결

### 6.1 신규 VOD 처리

```sql
-- 신규 VOD에 대한 부스트 스코어 계산
SELECT vod_id_fk,
       CASE 
           WHEN DATEDIFF(CURDATE(), release_date) < 30 THEN 0.5  -- 신규 보너스
           WHEN DATEDIFF(CURDATE(), release_date) < 7 THEN 0.8   -- 초신규 보너스
           ELSE 0.0
       END AS freshness_boost
FROM vod
WHERE is_active = TRUE;
```

### 6.2 신규 사용자 처리

```
신규 사용자 (watch_history 0건)
    ↓
인구통계 기반 벡터 생성
    ├─ age_grp10 → 동일 연령대 선호도 통계
    ├─ gender → 성별별 시청 패턴
    └─ inhome_rate → 거실형/개인형 콘텐츠 분류
    ↓
해당 세그먼트의 평균 벡터 사용
    ↓
일반적 인기도 + 다양성 필터 적용
```

---

## 7. 데이터 품질 및 모니터링

### 7.1 데이터 검증 규칙

| 엔티티 | 검증 항목 | 기준 | 알림 수준 |
|--------|---------|------|---------|
| **VOD** | asset_nm 중복 | 동일 시리즈 내 1회만 | WARNING |
| **VOD** | smry 길이 | 10~1000자 | ERROR |
| **WATCH_HISTORY** | use_tms 이상 | use_tms > disp_rtm | ERROR |
| **WATCH_HISTORY** | strt_dt 순서 | strt_dt ≤ end_dt | ERROR |
| **USER** | age_grp10 형식 | '10s', '20s', ... | ERROR |

### 7.2 모니터링 메트릭

```sql
-- 일일 통계 (모니터링 대시보드)
SELECT 
    DATE(watched_at) AS watch_date,
    COUNT(DISTINCT user_id_fk) AS daily_active_users,
    COUNT(*) AS total_watch_sessions,
    AVG(completion_rate) AS avg_completion_rate,
    AVG(satisfaction) AS avg_satisfaction
FROM watch_history
WHERE watched_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY watch_date
ORDER BY watch_date DESC;
```

---

## 8. 확장성 및 마이그레이션 계획

### 8.1 단계별 구현 계획

| 단계 | 목표 | 기간 | 산출물 |
|------|------|------|--------|
| **Phase 1** | 기본 스키마 구현 | 2주 | VOD, USER, WATCH_HISTORY 테이블 |
| **Phase 2** | 벡터 파이프라인 | 3주 | VOD_EMBEDDING, USER_EMBEDDING 생성 |
| **Phase 3** | 추천 로직 | 2주 | VOD_RECOMMENDATION 캐시 + Re-Ranking |
| **Phase 4** | 성능 최적화 | 2주 | 인덱싱, 파티셔닝, 캐싱 |
| **Phase 5** | 프로덕션 배포 | 1주 | 모니터링 + CI/CD |

### 8.2 버전 관리

```
v1.0: 기본 논리 스키마
v1.1: RAG 컬럼 추가 (cast_lead, cast_guest, rating)
v1.2: 벡터 임베딩 다중화 (CONTENT, METADATA, VISUAL, HYBRID)
v2.0: 콜드스타트 최적화 및 Re-Ranking v2
```

---

## 9. 주요 설계 결정사항

### 9.1 벡터 저장소 분리 (Milvus vs PostgreSQL)

**결정**: Milvus에 벡터, PostgreSQL에 메타데이터

| 기준 | Milvus | PostgreSQL |
|------|--------|-----------|
| **장점** | 빠른 검색(O(log n)), 스케일 용이 | 트랜잭션, 관계 관리 |
| **단점** | 트랜잭션 약함 | 고차원 벡터 검색 느림 |

**결과**: 멀티 데이터스토어로 최고 성능 달성

### 9.2 만족도 계산 방식

**선택**: 베이지안 스코어 기반 신뢰도 가중 평점 (0.0~1.0)

```
satisfaction = (v * R + m * C) / (v + m)

v: 영상별 시청 건수
R: 시청 비율 (use_tms / disp_rtm)
C: 전체 영상의 평균 시청 비율
m: 신뢰도 조절 파라미터 (기본값: 5.0)
```

**이유**:
- **신뢰도 기반 평가**: 많이 시청된 영상의 만족도를 더 신뢰 (v의 가중치)
- **전역 기준점**: 각 영상의 만족도를 전체 데이터셋 맥락에서 평가 (C 활용)
- **과소 평가 보정**: 시청 횟수가 적은 영상의 우발적 높은 점수를 전체 평균으로 보정
- **확장성**: m 파라미터 조정으로 신뢰도 기준 유연하게 변경 가능 (A/B 테스트 용이)

**예시**:
```
C = 0.5, m = 5.0 인 경우

인기 영상 A (v=100, R=0.8): satisfaction = 0.786
신작 B (v=1, R=0.9): satisfaction = 0.567
저품질 C (v=10, R=0.3): satisfaction = 0.367

→ 시청 건수(신뢰도)를 고려하여 실제 품질 반영
```

### 9.3 추천 캐싱 전략

**선택**: VOD_RECOMMENDATION 테이블 기반 7일 TTL 캐시

**이유**:
- 사용자당 Top-100 추천 = ~800B (저비용)
- 일 1회 배치 갱신으로 최신성 확보
- Redis와의 2단계 캐싱 (L1: 1시간, L2: 7일)

---

## 10. ERD (Entity-Relationship Diagram)

```
┌──────────────┐
│     VOD      │
├──────────────┤
│ full_asset_id│──┐
│ asset_nm     │  │
│ ct_cl        │  │
│ genre        │  │
│ disp_rtm     │  │
│ ...          │  │
└──────────────┘  │
                  │
                  ├────────────┬───────────────┬──────────────┐
                  │            │               │              │
                  │            │               │              │
          ┌───────▼─────┐ ┌───▼───────┐ ┌───▼─────────┐ ┌──▼──────┐
          │ WATCH_HISTORY│ │VOD_EMBEDDING│ │VOD_RECOMMEND│ │DEVICE*  │
          ├───────────────┤ ├───────────────┤ ├──────────────┤ └─────────┘
          │user_id_fk(FK)├─┤vod_id_fk(FK)  │ │user_id_fk(FK)├─┐
          │vod_id_fk(FK) │ │milvus_*      │ │vod_id_fk(FK)│ │
          │use_tms        │ │embedding_*   │ │rank_initial  │ │
          │completion_rate│ │created_at    │ │rerank_score  │ │
          │satisfaction   │ │              │ │reason        │ │
          └───────┬───────┘ └───────────────┘ └──────────────┘ │
                  │                                             │
          ┌───────▼───────┐                                     │
          │     USER      │                                     │
          ├───────────────┤                          ┌──────────▼──┐
          │sha2_hash(PK)  │                          │USER_EMBEDDING│
          │age_grp10      │                          ├─────────────┤
          │gender         │                          │user_id_fk(FK)
          │inhome_rate    │                          │vector_id    │
          │...            │◄─────────────────────────┤embedding_*  │
          └───────────────┘ 1:N                      └─────────────┘
```

---

## 11. 쿼리 예시

### 11.1 사용자 추천 조회

```sql
-- 상위 50개 추천 VOD 조회
SELECT 
    r.rank_final,
    v.asset_nm,
    v.ct_cl,
    v.genre,
    r.similarity_score,
    r.rerank_score,
    r.reason
FROM vod_recommendation r
JOIN vod v ON r.vod_id_fk = v.full_asset_id
WHERE r.user_id_fk = ?
  AND r.expired_at > NOW()
  AND r.is_clicked = FALSE
ORDER BY r.rank_final
LIMIT 50;
```

### 11.2 사용자 시청 패턴 분석

```sql
-- 사용자별 완주율 및 만족도
SELECT 
    u.sha2_hash,
    u.age_grp10,
    COUNT(*) AS watch_count,
    AVG(wh.completion_rate) AS avg_completion,
    AVG(wh.satisfaction) AS avg_satisfaction,
    STRING_AGG(DISTINCT v.genre, ',') AS preferred_genres
FROM user u
LEFT JOIN watch_history wh ON u.sha2_hash = wh.user_id_fk
LEFT JOIN vod v ON wh.vod_id_fk = v.full_asset_id
WHERE wh.watched_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY u.sha2_hash, u.age_grp10;
```

### 11.3 콜드스타트 세그먼트 추천

```sql
-- 신규 사용자와 유사한 세그먼트의 인기 VOD 추천
SELECT 
    v.full_asset_id,
    v.asset_nm,
    COUNT(wh.watch_history_id) AS view_count,
    AVG(wh.satisfaction) AS avg_sat,
    0.5 AS freshness_boost
FROM vod v
JOIN watch_history wh ON v.full_asset_id = wh.vod_id_fk
JOIN user u ON wh.user_id_fk = u.sha2_hash
WHERE u.age_grp10 = ?
  AND u.gender = ?
  AND wh.satisfaction > 0.6
  AND v.is_active = TRUE
GROUP BY v.full_asset_id
HAVING view_count >= 10
ORDER BY avg_sat DESC, view_count DESC
LIMIT 100;
```

---

## 12. 참고사항 및 향후 확장

### 12.1 향후 추가 기능

- **콘텐츠 협업 필터링**: WATCH_HISTORY 기반 유저-유저 유사도
- **시계열 분석**: 계절성/요일별 추천 동적 조정
- **A/B 테스팅**: 추천 알고리즘 변형 비교
- **피드백 루프**: 클릭/시청 데이터 기반 모델 재학습
- **실시간 인기도**: Redis Sorted Set 기반 HOT 아이템

### 12.2 보안 고려사항

- **PII 보호**: sha2_hash는 양방향 복호화 불가능
- **접근 제어**: WATCH_HISTORY는 해당 사용자만 조회 가능
- **데이터 암호화**: 전송 중 TLS, 저장 시 필드 암호화
- **감사 로그**: 추천 변경 이력 기록

---

**문서 작성 완료**  
버전: 1.0  
마지막 수정: 2026-03-05
