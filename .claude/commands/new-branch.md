새 개발 브랜치를 시작할 때 실행합니다.

## 실행 절차

1. 현재 상태 확인:
```bash
git branch --show-current
git fetch origin master
git log master..HEAD --oneline
```

2. 브랜치 명명 규칙:
   - Phase 작업: `phase3-mf-engine`, `phase4-llm-api`, `phase5-streamlit-ui`, `phase6-yolo-marketplace`
   - 단위 기능: `feature/<기능명>`
   - 버그 수정: `fix/<이슈내용>`

3. 작업 디렉토리 구조 생성:
```
<브랜치폴더>/
├── tests/          # TDD 테스트 위치
├── README.md       # 목적 + 실행 방법
└── requirements.txt
```

4. DB 권한 확인:
   - DB 쓰기 필요 → 황대원에게 CSV 전달 후 업로드 요청
   - DB 읽기만 → 읽기 전용 계정 사용

5. security-agent 호출하여 초기 보안 점검 실행.

6. tdd-agent 호출하여 TDD 사이클 시작.

## 주의사항
- master 직접 push 금지
- API 키는 반드시 환경변수로 관리 (.env, .gitignore 포함)
- database-design 브랜치의 DB 스키마 직접 수정 금지
