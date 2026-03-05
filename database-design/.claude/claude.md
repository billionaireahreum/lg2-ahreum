# Database Design Project - Claude Code 작업 지침

**프로젝트명**: VOD 추천 시스템 - PostgreSQL 데이터베이스 설계  
**목표**: 4백만 행 VOD 시청 데이터를 기반으로 확장성 있는 PostgreSQL 데이터베이스 설계  
**소유자**: Data Engineering Team  
**상태**: 진행 중

---

## 📋 프로젝트 개요

### 목표
- PostgreSQL 기반 정규화된 데이터베이스 설계
- 3개 메인 테이블: USER, VOD, WATCH_HISTORY
- 10,000+ QPS 처리 가능한 성능 최적화
- 향후 벡터 임베딩 및 추천 기능 확장 가능

### 입력 데이터
- 시청이력: 약 4,000,000건
- 고유 사용자: 약 1,200,000명
- 고유 VOD: 약 45,000개
- 기간: 2025년 1월

---

## 🏗️ 설계 원칙

### 1. 정규화
- **요구사항**: 최소 3NF (제3정규형)
- **목표**: 데이터 무결성 보장 + 이상 제거
- **검증**: 각 테이블의 정규화 단계 명시

### 2. 성능
- **우선 조회 패턴**:
  1. 사용자별 시청이력 조회 (WHERE user_id = ?)
  2. VOD별 시청 통계 조회 (WHERE vod_id = ?)
  3. 날짜범위 시청 데이터 조회 (WHERE strt_dt BETWEEN ? AND ?)
  4. 만족도 상위 VOD 조회 (ORDER BY satisfaction DESC)

- **목표 성능**:
  - 사용자별 조회: < 100ms
  - VOD별 조회: < 100ms
  - 날짜 범위 조회: < 500ms

### 3. 확장성
- **향후 기능 고려**:
  - 벡터 임베딩 저장 (pgvector)
  - 추천 결과 저장 (VOD_RECOMMENDATION 테이블)
  - 사용자 선호도 테이블
  - 시계열 분석 (월별/주별 파티셔닝)

### 4. 유지보수성
- **명확한 제약조건**: NOT NULL, UNIQUE, FOREIGN KEY 명시
- **인덱싱 전략**: 각 인덱스의 목적 문서화
- **주석**: DDL에 테이블/컬럼 설명 포함

---

## 📊 데이터 구조 정의

### User 테이블
```
식별자: sha2_hash (VARCHAR 64)
속성: 인구통계(AGE_GRP10, 성별), 행동패턴(INHOME_RATE), 구독정보(SVOD/PAID), 특화콘텐츠(KIDS_USE)
예상 행: 1,200,000
예상 크기: 80-100MB
```

### VOD 테이블
```
식별자: full_asset_id (VARCHAR 64)
속성: 메타데이터(asset_nm, CT_CL, genre), 기술(disp_rtm), 제작진(director, cast), 요약(smry)
결측치: director, cast_lead, cast_guest, rating, release_date (RAG로 처리 예정)
예상 행: 45,000
예상 크기: 5-10MB
```

### Watch_History 테이블
```
식별자: watch_history_id (BIGINT, AUTO_INCREMENT)
외래키: user_id_fk, vod_id_fk
속성: 시간(strt_dt, end_dt), 통계(use_tms, completion_rate, satisfaction)
예상 행: 4,000,000
예상 크기: 150-200MB
분할 전략: 월별 파티셔닝 (2025-01, 2025-02, ...)
```

---

## 🔑 주요 설계 결정사항

### 1. 테이블 분리 (정규화)
- **이유**: 데이터 중복 제거, 저장공간 절감
- **영향**:
  - USER: 사용자 데이터 중복 제거 (760MB → 80MB)
  - VOD: 영상 정보 중복 제거 (761MB → 5MB)
  - WATCH_HISTORY: 순수 관계 데이터만 유지

### 2. 기본키 전략
- **USER**: sha2_hash (해시된 사용자 ID)
- **VOD**: full_asset_id (영상 식별자)
- **WATCH_HISTORY**: watch_history_id (자동생성)

### 3. 인덱싱 전략
- **필수 인덱스**:
  - WATCH_HISTORY(user_id_fk) - 사용자별 조회
  - WATCH_HISTORY(vod_id_fk) - VOD별 조회
  - WATCH_HISTORY(strt_dt) - 날짜범위 조회
  - WATCH_HISTORY(satisfaction) - 순위 조회

- **복합 인덱스**:
  - WATCH_HISTORY(user_id_fk, strt_dt) - 사용자별 시간순 조회

### 4. 파티셔닝 (향후)
```sql
-- WATCH_HISTORY 월별 파티셔닝
PARTITION BY RANGE (YEAR_MONTH(strt_dt)) (
  PARTITION p202501 VALUES LESS THAN (202502),
  PARTITION p202502 VALUES LESS THAN (202503),
  ...
)
```

### 5. 결측치 처리
- **현재 상태**: NULL 그대로 저장
- **향후 처리**: RAG 파이프라인에서 채움
- **추적 컬럼** (선택):
  - rag_processed (BOOLEAN)
  - rag_source (VARCHAR)
  - rag_processed_at (TIMESTAMP)

---

## 📝 결과물 요구사항

### 필수
1. **DDL 스크립트** (create_tables.sql)
   - CREATE TABLE 3개 (USER, VOD, WATCH_HISTORY)
   - CREATE INDEX (성능 최적화)
   - 제약조건 (NOT NULL, UNIQUE, FOREIGN KEY)
   - 테이블/컬럼 주석

2. **설계 문서** (DESIGN.md)
   - 각 테이블 설계 이유
   - 인덱스 선택 근거
   - 성능 예측
   - 확장 계획

### 선택
3. **마이그레이션 코드** (migrate.py)
   - Python SQLAlchemy 또는 SQL
   - prepared_data/*.csv → PostgreSQL
   - 데이터 검증 로직

4. **성능 테스트** (performance_test.sql)
   - 각 주요 조회 패턴 쿼리
   - EXPLAIN ANALYZE 결과

---

## 🔍 검증 기준

### 데이터 정합성
- [ ] 외래키 제약조건 위반 없음
- [ ] 사용자 수: ~1,200,000명
- [ ] VOD 수: ~45,000개
- [ ] 시청이력: ~4,000,000건

### 성능
- [ ] 사용자별 조회: < 100ms
- [ ] VOD별 조회: < 100ms
- [ ] 날짜 범위 조회: < 500ms

### 정규화
- [ ] 제1정규형: 모든 속성이 원자값
- [ ] 제2정규형: 부분 종속 제거
- [ ] 제3정규형: 이행 종속 제거

---

## 📂 파일 구조

```
database-design/
├── .claude/
│   └── claude.md                  # 이 파일
├── data/
│   ├── prepared_data/             # prepare_for_claude_code.py 결과
│   │   ├── 02_data_summary.json
│   │   ├── user_sample_100rows.csv
│   │   ├── vod_sample_100rows.csv
│   │   ├── watch_history_sample_100rows.csv
│   │   ├── user_table.csv         # 마이그레이션용
│   │   ├── vod_table.csv
│   │   └── watch_history_table.csv
│   └── rag_analysis/              # generate_rag_metadata.py 결과
│       └── 05_claude_prompt.md    # 결측치 정보
├── schema/
│   ├── create_tables.sql          # ← Claude가 생성할 파일
│   ├── create_indexes.sql
│   ├── create_constraints.sql
│   └── DESIGN.md                  # ← Claude가 생성할 파일
├── migration/
│   └── migrate.py                 # ← Claude가 생성할 파일 (선택)
└── README.md                      # 프로젝트 설명
```

---

## 💻 Claude Code 작업 프롬프트

```markdown
# Task: VOD 추천 시스템 PostgreSQL 데이터베이스 설계

## 입력 정보

### 1. 데이터 요약
[prepared_data/02_data_summary.json 내용]

### 2. 샘플 데이터
[user_sample_100rows.csv 첫 10행]
[vod_sample_100rows.csv 첫 10행]
[watch_history_sample_100rows.csv 첫 10행]

### 3. 결측치 정보
[rag_analysis/05_claude_prompt.md 내용]

## 요구사항

1. 3NF 정규화된 DDL 스크립트 작성
2. 성능 최적화 인덱싱
3. 3개 테이블: USER, VOD, WATCH_HISTORY
4. 설계 문서 (각 선택의 이유)
5. (선택) Python 마이그레이션 코드

## 제약조건

- 데이터: 4,000,000 시청이력, 1,200,000 사용자, 45,000 VOD
- 성능: 사용자별/VOD별/날짜별 조회 < 100ms
- 확장성: 향후 벡터 임베딩/추천 기능 고려
- 정규화: 최소 3NF
```

---

## 🎯 다음 단계

### 1단계: 데이터 준비 (이미 완료)
- [x] prepare_for_claude_code.py 실행
- [x] generate_rag_metadata.py 실행

### 2단계: Claude Code 작업 (현재)
- [ ] 이 문서 검토
- [ ] Claude Code에 프롬프트 제시
- [ ] DDL 스크립트 생성 확인
- [ ] 설계 문서 생성 확인

### 3단계: 검증 (다음)
- [ ] DDL 문법 검증
- [ ] 데이터 마이그레이션 테스트
- [ ] 성능 테스트

### 4단계: 통합 (그 다음)
- [ ] RAG Pipeline과 병렬 진행
- [ ] VOD_EMBEDDING, USER_EMBEDDING 테이블 추가 검토
- [ ] 최종 스키마 확정

---

## 📞 참고 문서

### 필수
- [VOD_RECOMMENDATION_LOGICAL_SCHEMA.md](../VOD_RECOMMENDATION_LOGICAL_SCHEMA.md) - 논리적 스키마 설계 (섹션 3 참고)

### 참고
- [00_FINAL_EXECUTION_GUIDE.md](../00_FINAL_EXECUTION_GUIDE.md) - 실행 가이드
- [HOW_TO_RUN_SCRIPTS.md](../HOW_TO_RUN_SCRIPTS.md) - 스크립트 실행 방법

---

## 🚀 Claude Code 활용 팁

### 명확한 요청
```
"3NF 정규화된 DDL을 작성해줘. 각 테이블의 정규화 이유를 설명해줘."
```

### 피드백 요청
```
"이 인덱스 전략으로 10,000 QPS를 처리할 수 있을까? 개선할 점이 있으면 제안해줘."
```

### 수정 요청
```
"WATCH_HISTORY에 rag_processed 컬럼을 추가해줘. 부울 타입, 기본값 FALSE."
```

---

**마지막 수정**: 2026-03-05  
**프로젝트 상태**: Database Design 시작 준비 완료
