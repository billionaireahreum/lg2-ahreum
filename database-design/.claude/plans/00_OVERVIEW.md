# VOD 추천 시스템 - Database 개발 마스터 플랜

**프로젝트**: VOD 추천 웹서비스 - PostgreSQL 데이터베이스
**브랜치**: database-design
**작성일**: 2026-03-06
**상태**: 진행 중

---

## 1. 프로젝트 개요

### 목표
CSV 형태의 원본 VOD 시청 데이터를 PostgreSQL 데이터베이스로 마이그레이션하고, 향후 벡터 임베딩 기반 추천 시스템으로 확장 가능한 정규화된 스키마를 설계·구현한다.

### 실제 데이터 규모 (설계요구사항.md 기준)
| 항목 | 수치 |
|------|------|
| 총 시청 이력 | 3,992,530건 |
| 고유 사용자 | 242,702명 |
| 고유 VOD | 166,159개 |
| 평균 시청 횟수/사용자 | 16.45회 |
| 평균 시청 횟수/VOD | 24.03회 |
| 데이터 기간 | 2025-01-01 ~ 2025-01-31 |

### 핵심 결과물
| 파일 | 경로 | 우선순위 |
|------|------|---------|
| DDL 스크립트 | `schema/create_tables.sql` | 필수 |
| 인덱스 스크립트 | `schema/create_indexes.sql` | 필수 |
| 설계 문서 | `schema/DESIGN.md` | 필수 |
| 마이그레이션 코드 | `migration/migrate.py` | 선택 |
| 성능 테스트 쿼리 | `schema/performance_test.sql` | 선택 |

---

## 2. 테이블 구조 요약

### Phase 1 - 핵심 3개 테이블 (현재 목표)
```
USER (242,702행)
  └── WATCH_HISTORY (3,992,530행) ──> VOD (166,159행)
```

### Phase 2 - 임베딩 확장 (향후)
```
VOD ──> VOD_EMBEDDING (Milvus 메타데이터)
USER ──> USER_EMBEDDING (Milvus 메타데이터)
USER + VOD ──> VOD_RECOMMENDATION (추천 캐시)
```

---

## 3. 개발 단계별 계획

### Phase 1: 스키마 설계 및 DDL (현재)
- **계획 문서**: `plans/01_DDL_PLAN.md`
- **산출물**: `schema/create_tables.sql`, `schema/create_indexes.sql`
- **핵심 작업**:
  - PostgreSQL 전용 DDL 작성 (MySQL 문법 변환)
  - 3NF 정규화 검증
  - 인덱스 전략 수립
  - RAG 추적 컬럼 포함

### Phase 2: 데이터 마이그레이션
- **계획 문서**: `plans/02_MIGRATION_PLAN.md`
- **산출물**: `migration/migrate.py`
- **핵심 작업**:
  - CSV → PostgreSQL 로드
  - 데이터 정합성 검증
  - 결측치 처리 (NULL 허용)

### Phase 3: 성능 최적화
- **계획 문서**: `plans/03_PERFORMANCE_PLAN.md`
- **산출물**: `schema/performance_test.sql`
- **핵심 작업**:
  - 복합 인덱스 튜닝
  - EXPLAIN ANALYZE 분석
  - 파티셔닝 전략

### Phase 4: 검증 및 테스트
- **계획 문서**: `plans/04_TESTING_PLAN.md`
- **핵심 작업**:
  - 데이터 정합성 검증 쿼리
  - 성능 목표 달성 확인
  - 정규화 검증

### Phase 5: 확장 설계
- **계획 문서**: `plans/05_EXTENSION_PLAN.md`
- **핵심 작업**:
  - VOD_EMBEDDING / USER_EMBEDDING 스키마
  - VOD_RECOMMENDATION 캐시 테이블
  - pgvector 연동 전략

---

## 4. 기술 스택

| 항목 | 선택 | 이유 |
|------|------|------|
| 데이터베이스 | PostgreSQL 15+ | 트랜잭션, pgvector 지원 |
| 마이그레이션 | Python + psycopg2 / SQLAlchemy | 유연한 데이터 검증 |
| 벡터 저장소 | Milvus (향후) | 고차원 벡터 검색 최적화 |
| 캐시 | Redis (향후) | L1 추천 캐시 |

---

## 5. 중요 설계 결정사항

### 5.1 만족도(Satisfaction) 공식
베이지안 스코어 기반 신뢰도 가중 평점 (0.0 ~ 1.0)
```
satisfaction = (v * R + m * C) / (v + m)
  v: VOD별 시청 건수
  R: 시청 비율 (use_tms / disp_rtm_sec)
  C: 전체 평균 시청 비율 (~0.47)
  m: 신뢰도 조절 파라미터 (기본값 5.0)
```
- 60초 이하 시청 → satisfaction = 0.0
- 데이터에 이미 계산된 값이 저장되어 있음 → CSV에서 직접 로드

### 5.2 결측치 처리
| 컬럼 | NULL 수 | 처리 방법 |
|------|---------|---------|
| director | 313건 (0.01%) | NULL 허용 + RAG 추후 처리 |
| smry | 28건 (0.00%) | NULL 허용 + RAG 추후 처리 |

RAG 추적용 컬럼 추가 (선택):
- `rag_processed BOOLEAN DEFAULT FALSE`
- `rag_source VARCHAR(64)`
- `rag_processed_at TIMESTAMP`

### 5.3 PostgreSQL 전용 문법 (MySQL 문법 사용 금지)
| MySQL | PostgreSQL |
|-------|-----------|
| `AUTO_INCREMENT` | `BIGINT GENERATED ALWAYS AS IDENTITY` |
| `ENGINE=InnoDB` | (없음) |
| `FULLTEXT INDEX` | `GIN` 인덱스 + `tsvector` |
| `ON UPDATE CURRENT_TIMESTAMP` | 트리거 사용 |
| `DATE_SUB(NOW(), INTERVAL 30 DAY)` | `NOW() - INTERVAL '30 days'` |
| `COMMENT '...'` | `COMMENT ON COLUMN ... IS '...'` |

---

## 6. 성능 목표

| 쿼리 패턴 | 목표 응답시간 | 인덱스 |
|---------|------------|-------|
| 사용자별 시청이력 조회 | < 100ms | idx_wh_user_id |
| VOD별 시청 통계 | < 100ms | idx_wh_vod_id |
| 날짜 범위 조회 | < 500ms | idx_wh_strt_dt |
| 만족도 상위 VOD | < 200ms | idx_wh_satisfaction |

---

## 7. 파일 디렉토리 구조 (목표)

```
database-design/
├── .claude/
│   ├── claude.md
│   └── skills/
│       ├── VOD_RECOMMENDATION_LOGICAL_SCHEMA.md
│       └── SATISFACTION_FORMULA_UPDATE.md
├── plans/                          # 이 폴더 (개발 계획)
│   ├── 00_OVERVIEW.md              # 마스터 플랜 (이 파일)
│   ├── 01_DDL_PLAN.md              # DDL 작성 계획
│   ├── 02_MIGRATION_PLAN.md        # 마이그레이션 계획
│   ├── 03_PERFORMANCE_PLAN.md      # 성능 최적화 계획
│   ├── 04_TESTING_PLAN.md          # 검증/테스트 계획
│   └── 05_EXTENSION_PLAN.md        # 확장 설계 계획
├── schema/
│   ├── create_tables.sql           # [생성 예정] 테이블 DDL
│   ├── create_indexes.sql          # [생성 예정] 인덱스 DDL
│   ├── create_constraints.sql      # [생성 예정] 제약조건
│   └── DESIGN.md                   # [생성 예정] 설계 설명 문서
├── migration/
│   └── migrate.py                  # [생성 예정] 마이그레이션 스크립트
├── data/
│   ├── prepared_data/              # CSV 원본
│   └── rag_analysis/               # RAG 결측치 분석
└── README.md
```

---

## 8. 참고 문서

| 문서 | 경로 | 내용 |
|------|------|------|
| 설계 요구사항 | `C:/Users/army5/Downloads/설계요구사항.md` | 실제 데이터 통계 및 요구사항 |
| 논리적 스키마 | `.claude/skills/VOD_RECOMMENDATION_LOGICAL_SCHEMA.md` | 전체 엔티티 설계 (섹션 3 참고) |
| 만족도 공식 | `.claude/skills/SATISFACTION_FORMULA_UPDATE.md` | 베이지안 스코어 계산 |
| 작업 지침 | `.claude/claude.md` | Claude Code 작업 가이드 |
