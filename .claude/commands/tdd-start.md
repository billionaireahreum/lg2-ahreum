새로운 기능의 TDD 사이클을 시작합니다. tdd-agent를 호출합니다.

구현하려는 기능을 설명하면 테스트 우선 개발을 진행합니다.

## 진행 단계

1. **요구사항 명세** - 입력/출력/엣지케이스 정리
2. **테스트 파일 생성 (RED)** - `tests/test_<기능명>.py`
   - 정상 케이스, 엣지 케이스, 오류 케이스 포함
3. **테스트 실패 확인** - `pytest tests/test_<기능명>.py -v`
4. **최소 구현 (GREEN)** - 테스트 통과하는 최소 코드
5. **테스트 통과 확인** - `pytest tests/test_<기능명>.py -v`
6. **리팩토링** - 타입 힌트, docstring, 중복 제거
7. **전체 테스트** - `pytest tests/ -v --cov=. --cov-report=term-missing`

## Phase별 테스트 위치
| Phase | 브랜치 | 테스트 위치 |
|---|---|---|
| 3 MF엔진 | `phase3-mf-engine` | `phase3-mf-engine/tests/` |
| 4 LLM+API | `phase4-llm-api` | `phase4-llm-api/tests/` |
| 5 UI | `phase5-streamlit-ui` | `phase5-streamlit-ui/tests/` |
| 6 YOLO | `phase6-yolo-marketplace` | `phase6-yolo-marketplace/tests/` |
