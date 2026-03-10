# user_embedding 프로젝트 - Claude Code 작업 지침

**프로젝트명**: VOD 추천 시스템 - 사용자 임베딩 (User Embedding) 개발
**담당자**: 박아름
**브랜치**: `embedding-design`
**목표**: 사용자 시청 이력 기반 user embedding 생성 및 VOD 콘텐츠 유사도 검색

---

## 폴더 구조

```
user_embedding/
├── .claude/
│   └── claude.md              # 이 파일
├── agents/
│   ├── report_writer.md       # 보고서 작성 에이전트
│   └── tdd_runner.md          # TDD 사이클 실행 에이전트
├── pipeline/
│   ├── generate_embeddings.py # VOD 콘텐츠 임베딩 재생성 (전제 작업)
│   ├── config.py
│   └── db.py
├── src/                       # user_embedding 핵심 구현 코드
│   ├── history_loader.py      # 시청 이력 로드
│   ├── user_embedder.py       # user embedding 생성
│   └── similarity_search.py   # 유사도 검색
├── tests/                     # TDD 테스트 코드
│   ├── test_history_loader.py
│   ├── test_user_embedder.py
│   └── test_similarity_search.py
└── reports/                   # 개발 진행 보고서 (날짜별)
    └── embedding-report-YYYYMMDD.md
```

---

## Step 0: VOD 콘텐츠 임베딩 재생성 (전제 조건)

user_embedding은 `vod_embedding` 테이블의 콘텐츠 벡터를 활용한다.
기존 임베딩(02번)은 cast_guest·release_date 누락 상태 → 재생성 필요.

### generate_embeddings.py (pipeline/)

**기존 02번 대비 변경사항:**
- 시리즈 단위 처리: (normalized_title + ct_cl) 그룹핑
  - 166,159번 연산 → ~22,414번 연산 (중복 제거)
  - 동일 시리즈 row 전체에 같은 벡터 복사
- 임베딩 입력 텍스트 추가: `cast_guest`(조연), `release_date`(개봉연도)
- 대표 row 선택: 메타데이터 완성도(채워진 필드 수) 기준

**입력 텍스트 구성:**
```
제목 / 유형 / 장르 / 세부장르 / 감독: xxx / 주연: xxx / 조연: xxx / 줄거리 / 개봉연도
```
※ rating은 임베딩 미포함 (필터링 전용)

**실행:**
```bash
cd user_embedding/pipeline
python generate_embeddings.py
```

**현재 상태**: 파일 작성 완료, 미실행 (vod_embedding에 기존 임베딩 존재)

---

## Step 1~N: user_embedding 기능 개발 (TDD)

### 개발 방식: TDD (Test Driven Development)

**Red → Green → Refactor** 순서를 반드시 지킨다.

1. 테스트 먼저 작성 (`tests/test_*.py`) → 실패 확인 (Red)
2. 최소한의 코드로 테스트 통과 (`src/*.py`) → (Green)
3. 코드 정리 후 테스트 재실행 확인 → (Refactor)
4. 보고서 작성 (`agents/report_writer.md` 참고)

### 커버리지 목표
- 전체: **80% 이상**
- 핵심 모듈 (user_embedder, similarity_search): **90% 이상**

### 테스트 실행
```bash
# 전체 + 커버리지
pytest tests/ -v --cov=src --cov-report=term-missing
```

---

## 개발 목표: user_embedding 핵심 기능

| 순서 | 모듈 | 기능 | 상태 |
|------|------|------|------|
| 1 | `history_loader.py` | 사용자 시청 이력 로드 (vod_log 테이블) | 🔜 예정 |
| 2 | `user_embedder.py` | 시청 VOD 임베딩 가중 평균 → user vector | 🔜 예정 |
| 3 | `similarity_search.py` | user vector ↔ 콘텐츠 임베딩 유사도 검색 | 🔜 예정 |

### 기능 상세

#### 1. history_loader.py
- `vod_log` (또는 시청이력) 테이블에서 사용자별 시청 VOD 목록 조회
- 시청일시, full_asset_id, 시청 완료 여부 반환

#### 2. user_embedder.py
- 시청한 VOD의 `vod_embedding` 벡터 조회
- 가중 평균 계산: 최근 시청일수록 가중치 높음 (지수 감쇠)
- 결과: 384d user embedding 벡터

#### 3. similarity_search.py
- user embedding 벡터 ↔ `vod_embedding` 콘텐츠 벡터 코사인 유사도
- pgvector `<=>` 연산자 활용 (HNSW 인덱스)
- 필터: rating, ct_cl 등 조건 적용 가능

---

## Agents

### report_writer (`agents/report_writer.md`)
- **역할**: 개발 진행 상황 보고서 작성
- **보고서 저장 위치**: `reports/embedding-report-YYYYMMDD.md`
- **호출 시점**: 기능 완료 시 / 테스트 통과 시 / 세션 종료 전 / 사용자 명시 요청 시

### tdd_runner (`agents/tdd_runner.md`)
- **역할**: TDD 사이클(Red→Green→Refactor) 안내 및 테스트 실행
- **호출 시점**: 새 기능 개발 시작 시 / 테스트 실행 필요 시

---

## 보안 정책

- 모든 API 키·비밀번호는 환경변수 (`os.getenv`) 사용
- `.env` 파일 위치: 루트 `lg2-ahreum/.env` (load_dotenv()가 상위 탐색)
- `.env` 파일은 `.gitignore`에 포함 — 커밋 금지
- SQL은 반드시 파라미터 바인딩 사용 (`%s`)
- f-string SQL 조합 금지

---

## DB 정보

- DB명: `vod_recommendation`
- 관련 테이블:
  - `vod` — VOD 메타데이터
  - `vod_embedding` — 콘텐츠 임베딩 (384d, pgvector, HNSW 인덱스)
  - 시청이력 테이블 — 이름 확인 필요 (`vod_log` 또는 유사)

---

## Git 정책

- `embedding-design` 브랜치에서 작업
- master 직접 push 금지 — PR + 리뷰 후 merge
- 커밋 형식: `feat/fix/test/docs/refactor: <설명>`
