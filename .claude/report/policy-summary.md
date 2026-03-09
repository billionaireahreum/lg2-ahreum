# 공통 정책 요약 (Quick Reference)

> 전체 내용은 루트 `CLAUDE.md` 참조

---

## DB 권한
- 쓰기: **황대원만**
- 나머지: SELECT 전용
- CSV 가공 완료 → 황대원 전달 → 황대원 업로드

## 브랜치 규칙
1. master 직접 push 금지 → PR + 리뷰 필수
2. 새 작업: `/new-branch`
3. 완료: `/done` (보안+테스트+보고서 자동)

## 절대 금지
- `password = "abc123"` 하드코딩
- f-string SQL 조합
- .env 파일 git commit
- master force push

## 커맨드 순서
```
/new-branch → /tdd-start → (개발) → /security-check → /done
```

## 에이전트
| 에이전트 | 언제 |
|---|---|
| tdd-agent | 새 기능 시작 |
| test-agent | 테스트 실행 |
| security-agent | PR 전 보안 점검 |
| report-agent | 작업 완료 보고서 |
| long-task-agent | 임베딩/학습 장시간 작업 |

## Phase별 담당자
| Phase | 담당 | 브랜치 |
|---|---|---|
| 3: MF 추천엔진 | 최기문 | `phase3-mf-engine` |
| 4: LLM+FastAPI | 이가원 | `phase4-llm-api` |
| 5: Streamlit | 신정윤 | `phase5-streamlit-ui` |
| 6: YOLO | 박아름+최기문 | `phase6-yolo-marketplace` |
