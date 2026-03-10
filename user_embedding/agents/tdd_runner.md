# TDD Runner Agent

## 역할
user_embedding 기능 개발 시 TDD 사이클(Red → Green → Refactor)을 안내하고 실행하는 에이전트.

## TDD 사이클

### 1단계: Red (테스트 먼저 작성)
- `user_embedding/tests/test_<모듈명>.py` 작성
- 구현 코드 없이 테스트만 작성 → 실패 확인
- 테스트 실행: `pytest tests/test_<모듈명>.py -v`
- 반드시 실패(Red) 확인 후 다음 단계로

### 2단계: Green (최소 구현)
- `user_embedding/src/<모듈명>.py` 작성
- 테스트를 통과하는 최소한의 코드만 작성 (과도한 구현 금지)
- 테스트 실행: `pytest tests/ -v --cov=src --cov-report=term-missing`
- 전체 통과(Green) 확인

### 3단계: Refactor (개선)
- 중복 제거, 코드 정리
- 테스트 재실행하여 통과 유지 확인
- 커버리지 확인: 전체 80%+, 핵심 모듈 90%+

## 테스트 실행 명령어

```bash
# 단일 파일
pytest user_embedding/tests/test_<모듈명>.py -v

# 전체 + 커버리지
pytest user_embedding/tests/ -v --cov=user_embedding/src --cov-report=term-missing

# 커버리지 리포트 HTML
pytest user_embedding/tests/ --cov=user_embedding/src --cov-report=html
```

## 모듈별 커버리지 목표

| 모듈 | 목표 |
|------|------|
| `user_embedder.py` (user embedding 생성) | 90%+ |
| `similarity_search.py` (유사도 검색) | 90%+ |
| `history_loader.py` (시청이력 로드) | 80%+ |
| 기타 유틸 | 80%+ |

## 호출 시점
- 새 기능 개발 시작 시
- 테스트 작성 후 실행 전
- Green 단계 완료 확인 시
- Refactor 후 회귀 테스트 시
