# user_embedding 프로젝트 - Claude Code 작업 지침

**프로젝트명**: VOD 추천 시스템 - 사용자 임베딩 (User Embedding) 개발
**담당자**: 박아름
**브랜치**: `embedding-design`
**목표**: 사용자 시청 이력 기반 user embedding 생성 및 VOD 콘텐츠 유사도 검색

---

## 개발 방식: TDD (Test Driven Development)

**Red → Green → Refactor** 순서를 반드시 지킨다.

1. 테스트 먼저 작성 (`tests/test_*.py`)
2. 테스트 실패 확인 (Red)
3. 최소한의 코드로 테스트 통과 (Green)
4. 리팩토링 (Refactor)
5. 보고서 작성 (`agents/report_writer.md` 참고)

### 커버리지 목표
- 전체: **80% 이상**
- 핵심 모듈 (임베딩 생성, 유사도 검색): **90% 이상**

### 테스트 위치
```
user_embedding/tests/test_<모듈명>.py
```

---

## 폴더 구조

```
user_embedding/
├── .claude/
│   └── claude.md          # 이 파일
├── agents/
│   └── report_writer.md   # 보고서 작성 에이전트
├── reports/               # 개발 진행 보고서 (날짜별)
├── pipeline/              # 임베딩 생성 파이프라인 코드
└── tests/                 # TDD 테스트 코드
```

---

## 개발 목표: user_embedding 기능

### 핵심 기능
1. **사용자 시청 이력 로드** — `vod_log` 또는 유사 테이블에서 사용자별 시청 VOD 목록 조회
2. **콘텐츠 임베딩 조회** — `vod_embedding` 테이블에서 시청한 VOD의 벡터 조회
3. **user embedding 생성** — 시청한 VOD 임베딩들의 가중 평균 (최근 시청일수록 가중치 높음)
4. **유사 콘텐츠 추천** — user embedding과 콘텐츠 임베딩 간 코사인 유사도 검색 (pgvector)

### 임베딩 모델
- 콘텐츠 임베딩: `paraphrase-multilingual-MiniLM-L12-v2` (384d, 기존 `vod_embedding` 테이블)
- user embedding: 동일 차원(384d), 시청 이력 기반 가중 평균

---

## Agents

### report_writer
- 위치: `agents/report_writer.md`
- 역할: 개발 진행 상황 보고서 작성
- 보고서 저장 위치: `reports/embedding-report-YYYYMMDD.md`
- 호출 시점: 기능 완료 시, 테스트 통과 시, 세션 종료 전

---

## 보안 정책

- 모든 API 키·비밀번호는 환경변수 (`os.getenv`) 사용
- `.env` 파일은 `.gitignore`에 포함 — 커밋 금지
- SQL은 반드시 파라미터 바인딩 사용 (`%s`)
- f-string SQL 조합 금지

---

## DB 정보

- DB명: `vod_recommendation`
- 관련 테이블:
  - `vod` — VOD 메타데이터
  - `vod_embedding` — 콘텐츠 임베딩 (384d, pgvector)
  - `vod_log` 또는 시청이력 테이블 (확인 필요)

---

## Git 정책

- `embedding-design` 브랜치에서 작업
- master 직접 push 금지 — PR + 리뷰 후 merge
- 커밋 형식: `feat/fix/test/docs/refactor: <설명>`
