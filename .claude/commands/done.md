작업 브랜치 개발 완료 시 실행합니다. 보안 점검 → 테스트 → 보고서 → PR 준비를 순서대로 수행합니다.

## Step 1: 보안 점검
security-agent를 호출하여 점검합니다:
- 하드코딩된 API 키, 비밀번호
- SQL Injection 취약점
- DB 쓰기 권한 위반
- .gitignore 누락 항목

**이슈 발견 시 중단 → 수정 후 재실행.**

## Step 2: 테스트 실행
test-agent를 호출합니다:
```bash
pytest tests/ -v --tb=short --cov=. --cov-report=term-missing
```
**커버리지 80% 미만 시 중단 → 테스트 보완 후 재실행.**

## Step 3: 보고서 생성
report-agent를 호출하여 `.claude/report/<브랜치명>.md` 생성.

## Step 4: PR 준비
```bash
git log master..HEAD --oneline
git diff master --stat
```

PR 제목: `[Phase N] <작업명> 완료`
PR 본문: `.claude/report/<브랜치명>.md` 내용 포함.

## 완료 체크리스트
- [ ] 보안 점검 통과 (이슈 0건)
- [ ] 테스트 통과 (커버리지 80%+)
- [ ] 보고서 생성 (`.claude/report/`)
- [ ] PR 생성 + 리뷰어 1명 이상 지정
