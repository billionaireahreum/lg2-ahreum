# Phase 5 - Streamlit UI 대시보드

**담당자**: 신정윤
**브랜치**: `phase5-streamlit-ui`
**선행 조건**: Phase 4 완료 (FastAPI 엔드포인트 동작 확인)

---

## 목표
VOD 추천 결과를 보여주는 Streamlit 대시보드

## 주요 화면
- 사용자 ID 입력 → TOP-N 추천 VOD + 감성 문구 표시
- VOD 검색 → 유사 콘텐츠 추천
- 관리자 뷰: 추천 현황 통계

## 기술 스택
- Streamlit
- FastAPI 연동 (requests)
- 시각화: plotly / altair

## TDD 테스트 위치
`phase5-streamlit-ui/tests/`
- UI 로직 단위 테스트 (화면 렌더링 제외)
- API 호출 모킹 테스트

## DB 정책
- 직접 DB 접근 금지
- FastAPI 엔드포인트를 통해서만 데이터 조회
