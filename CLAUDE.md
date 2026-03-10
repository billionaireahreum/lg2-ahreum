# LG헬로비전 VOD 추천 시스템 - 공통 개발 정책

**팀원**: 박아름, 황대원, 최기문, 이가원, 신정윤
**기술 스택**: PostgreSQL+pgvector, Matrix Factorization, LG Exaone 4.0, FastAPI, Streamlit, YOLOv8

---

## 1. 브랜치 정책

```
master (보호 브랜치 - 직접 push 금지)
├── database-design          → 황대원 (완료)
├── rag-pipeline-design      → 박아름 (완료)
├── phase3-mf-engine         → 최기문
├── phase4-llm-api           → 이가원
├── phase5-streamlit-ui      → 신정윤
├── phase6-yolo-marketplace  → 박아름 + 최기문
└── feature/*                → 각 담당자
```

- master에 직접 push 금지. PR + 1인 이상 리뷰 후 merge.
- 커밋 형식: `feat/fix/test/docs/refactor: <설명>`
- 새 브랜치 시작: `/new-branch` 커맨드 실행
- 작업 완료: `/done` 커맨드 실행

### 브랜치 폴더 격리 규칙 (필수)

- 각 브랜치는 **자기 담당 폴더만** 포함
- master는 전체 폴더 포함 (모든 브랜치 merge 결과)
- 새 브랜치 생성 시 다른 폴더가 딸려오면 **즉시 제거 후 push**
- 다른 브랜치 폴더 건드리는 것 **절대 금지**

| 브랜치 | 포함 폴더 |
|--------|----------|
| `database-design` | `database-design/` |
| `rag-pipeline-design` | `rag-pipeline-design/` |
| `embedding-design` | `user_embedding/` |
| `phase3-mf-engine` | `phase3-mf-engine/` |
| `phase4-llm-api` | `phase4-llm-api/` |
| `phase5-streamlit-ui` | `phase5-streamlit-ui/` |
| `phase6-yolo-marketplace` | `phase6-yolo-marketplace/` |

---

## 2. DB 접근 권한

| 역할 | 담당자 | 권한 |
|---|---|---|
| DB 관리자 | 황대원 | SELECT + 쓰기 + DDL |
| 개발자 | 나머지 4명 | SELECT 전용 |

**CSV 업로드 절차**: 개인 가공 완료 → 황대원 전달 → 황대원 DB 업로드

**절대 금지**:
- `database-design` 브랜치 외에서 DDL 실행
- DB 비밀번호 코드에 하드코딩

---

## 3. 보안 정책

- 모든 API 키·비밀번호는 환경변수(`os.getenv`) 사용
- `.env` 파일은 `.gitignore`에 포함 (커밋 금지)
- SQL은 반드시 파라미터 바인딩: `cursor.execute("... WHERE id = %s", (value,))`
- f-string SQL 조합 금지

**필수 환경변수**:
```
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
TMDB_API_KEY, ANTHROPIC_API_KEY, LG_EXAONE_KEY
```

---

## 4. TDD 정책

- 구현 전 테스트 먼저 작성 (Red → Green → Refactor)
- 테스트 없이 PR 생성 불가 (`/done` 커맨드가 강제)
- 커버리지: 전체 80%+, 핵심 모듈 90%+
- 테스트 위치: `<브랜치폴더>/tests/test_<모듈명>.py`

---

## 5. 에이전트·커맨드 사용

| 상황 | 커맨드/에이전트 |
|---|---|
| 새 기능 시작 | `/tdd-start` |
| 테스트 실행 | `/test` (test-agent) |
| PR 전 보안 점검 | `/security-check` |
| 작업 완료 | `/done` (보안+테스트+보고서 자동) |
| 장시간 배치 작업 | long-task-agent |

---

## 6. Phase 현황

| Phase | 내용 | 담당 | 상태 |
|---|---|---|---|
| 1 | DB 설계 | 황대원 | 완료 |
| 2 | RAG 파이프라인 | 박아름 | 완료 |
| 3 | MF 추천 엔진 | 최기문 | 예정 |
| 4 | LLM + FastAPI | 이가원 | 예정 |
| 5 | Streamlit UI | 신정윤 | 예정 |
| 6 | YOLOv8 마켓플레이스 | 박아름+최기문 | 예정 |
