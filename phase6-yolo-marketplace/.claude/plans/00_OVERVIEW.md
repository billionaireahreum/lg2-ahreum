# Phase 6 - YOLOv8 영상인식 마켓플레이스

**담당자**: 박아름 + 최기문
**브랜치**: `phase6-yolo-marketplace`
**선행 조건**: Phase 5 완료

---

## 목표
YOLOv8으로 농산물 인식 → Naver API 상품 매칭 → 구매 연결 마켓플레이스

## 주요 기능
- 영상/이미지 업로드 → YOLOv8 객체 인식
- 인식된 농산물 → Naver Shopping API 상품 검색
- 상품 목록 표시 + 구매 링크 제공

## 기술 스택
- YOLOv8 (ultralytics)
- Naver Shopping API
- FastAPI (이미지 업로드 엔드포인트)
- Streamlit 연동

## TDD 테스트 위치
`phase6-yolo-marketplace/tests/`
- 인식 결과 파싱 테스트
- Naver API 연동 모킹 테스트

## 환경변수 추가 필요
```
NAVER_CLIENT_ID=<네이버 API 클라이언트 ID>
NAVER_CLIENT_SECRET=<네이버 API 시크릿>
```

## DB 정책
- 읽기 전용
- 마켓플레이스 결과 저장 필요 시 황대원에게 CSV 전달
