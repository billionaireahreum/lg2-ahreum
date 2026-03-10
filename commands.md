# LG헬로비전 VOD 추천 시스템 - 브랜치 초기 설정 자동화 가이드

**작성일**: 2026-03-10
**대상**: 전체 팀원 (박아름, 황대원, 최기문, 이가원, 신정윤)

---

## 1. 새 브랜치 시작 시 필수 절차

### Step 1. master에서 브랜치 생성

```bash
git checkout master
git pull origin master
git checkout -b <브랜치명>
```

브랜치명 규칙:
| Phase | 브랜치명 | 담당자 |
|-------|---------|--------|
| RAG 파이프라인 | `rag-pipeline-design` | 박아름 |
| DB 설계 | `database-design` | 황대원 |
| MF 추천 엔진 | `phase3-mf-engine` | 최기문 |
| LLM + FastAPI | `phase4-llm-api` | 이가원 |
| Streamlit UI | `phase5-streamlit-ui` | 신정윤 |
| YOLO 마켓플레이스 | `phase6-yolo-marketplace` | 박아름 + 최기문 |
| 임베딩 | `embedding-design` | 박아름 |

---

### Step 2. 브랜치 폴더 격리 (sparse-checkout)

각 브랜치는 **자신의 기능 폴더만** 보이도록 설정한다.

```bash
# 예시: embedding-design 브랜치라면
git sparse-checkout set user_embedding

# 예시: rag-pipeline-design 브랜치라면
git sparse-checkout set rag-pipeline-design

# master에서는 전체 해제
git sparse-checkout disable
```

> ⚠️ sparse-checkout 설정 후 다른 브랜치 파일이 사라진 것처럼 보이는 건 정상.
> 브랜치 전환 시 반드시 해당 브랜치의 폴더로 sparse-checkout을 재설정할 것.

---

### Step 3. .env 설정

`.env` 파일은 루트(`lg2-ahreum/.env`)에 위치한다.
**절대 커밋하지 말 것** (`.gitignore`에 포함됨).

```bash
# .env 파일 위치 확인
ls -la .env
```

필수 환경변수:
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=vod_recommendation
DB_USER=postgres
DB_PASSWORD=<비밀번호>
TMDB_API_KEY=<키>
ANTHROPIC_API_KEY=<키>
KMDB_SERVICE_KEY=<키>
```

---

### Step 4. Python 환경 확인

```bash
# Anaconda base 환경 사용
conda activate base
python --version  # 3.9+ 확인

# 패키지 설치 (최초 1회)
pip install psycopg2-binary sentence-transformers python-dotenv pgvector
```

---

### Step 5. DB 연결 테스트

```bash
# psql 직접 접속
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d vod_recommendation

# 인코딩 문제 시 먼저 실행
chcp 65001
```

---

## 2. 작업 완료 시 PR 절차

```bash
# 1. 변경사항 커밋
git add <파일명>
git commit -m "feat: <설명>"

# 2. 브랜치 push
git push origin <브랜치명>

# 3. GitHub에서 PR 생성 (master 타겟)
# 또는 gh CLI 사용
gh pr create --title "feat: ..." --body "..."

# 4. 팀원 1인 이상 리뷰 후 merge
```

커밋 메시지 형식:
| 태그 | 사용 시점 |
|------|----------|
| `feat:` | 새 기능 추가 |
| `fix:` | 버그 수정 |
| `refactor:` | 코드 개선 (기능 변경 없음) |
| `docs:` | 문서 작성/수정 |
| `test:` | 테스트 코드 |

---

## 3. 자주 쓰는 명령어 모음

### Git

```bash
# 브랜치 목록 확인
git branch -a

# 현재 sparse-checkout 확인
git sparse-checkout list

# 특정 브랜치 파일 열람 (체크아웃 없이)
git show <브랜치명>:<파일경로>

# 충돌 해결 후 머지 마무리
git add -A && git commit --no-edit
```

### PostgreSQL

```bash
# 테이블 목록 확인
\dt

# VOD 전체 row 수 확인
SELECT COUNT(*) FROM vod WHERE is_active = TRUE;

# 임베딩 현황 확인
SELECT embedding_type, COUNT(*) FROM vod_embedding GROUP BY embedding_type;

# NULL 잔량 집계
SELECT ct_cl,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE rating IS NULL) AS rating_null,
    COUNT(*) FILTER (WHERE cast_lead IS NULL) AS cast_null
FROM vod WHERE is_active = TRUE
GROUP BY ct_cl ORDER BY ct_cl;
```

### 임베딩 파이프라인 실행

```bash
# 콘텐츠 임베딩 재생성
cd user_embedding/pipeline
python generate_embeddings.py
```

---

## 4. 보안 체크리스트

PR 생성 전 반드시 확인:

- [ ] `.env` 파일이 커밋에 포함되지 않았는가?
- [ ] API 키가 코드에 하드코딩되지 않았는가?
- [ ] SQL에 f-string 대신 파라미터 바인딩(`%s`) 사용했는가?
- [ ] DB 비밀번호가 코드에 없는가?
