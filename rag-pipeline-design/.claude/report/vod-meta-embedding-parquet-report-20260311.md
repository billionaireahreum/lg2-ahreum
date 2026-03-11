# VOD 메타데이터 임베딩 Parquet 파이프라인 완료 보고서

**작업 일시**: 2026-03-11 19:00 ~ 21:09 (약 2h 9min)
**작업자**: 박아름
**작업 디렉토리**: `C:\Users\user\Desktop\dxshcool\VOD_Embedding`

---

## 1. 작업 개요

VOD 메타데이터 임베딩을 시리즈 단위로 생성하여 Parquet 파일로 저장하는 파이프라인을 구축하고 실행 완료하였다.
DB 직접 적재 대신 Parquet 중간 저장 방식을 채택하여, 황대원이 별도로 DB에 적재할 수 있도록 분리하였다.

---

## 2. 핵심 구조

### 2-1. 시리즈 단위 그룹핑
- 그룹핑 기준: `normalized_title + ct_cl` 조합
- `normalized_title`: 제목에서 `[자막]`, `1회`, `시즌2` 등 에피소드/서비스 구분자 제거
- 166,159 row → **23,541 시리즈 그룹**으로 축약 (86% 중복 연산 절감)

### 2-2. 대표 row 선택 (`pick_representative`)
- 시리즈 내 row 중 smry(줄거리), cast_lead(주연), director(감독) 등 메타데이터가 가장 풍부한 row를 대표로 선택
- 대표 row의 임베딩을 해당 시리즈 전체 row에 복사 저장

### 2-3. 배치 인코딩
- 모델: `paraphrase-multilingual-MiniLM-L12-v2` (384d)
- 배치 단위 인코딩 후 L2 정규화 → magnitude 1.0 유지

### 2-4. 체크포인트 구조
- 20 시리즈마다 체크포인트 저장
- 세션 중단 시 이어받기 가능 (재시작 비용 최소화)

---

## 3. 실행 결과

| 항목 | 값 |
|------|-----|
| 실행 시간 | 2026-03-11 19:00 ~ 21:09 (2h 9min) |
| 처리 시리즈 수 | 23,541개 |
| 최종 row 수 | 166,159행 (100% 커버리지) |
| 출력 파일 크기 | 102.3 MB |
| 출력 형식 | Parquet |
| 벡터 차원 | 384d |
| magnitude | 1.0 (L2 정규화) |

**특이사항**: 19:54 ~ 20:21 구간 약 26분 갭 발생 — 절전 모드 진입으로 추정, 체크포인트 덕분에 중단 없이 정상 완료.

---

## 4. 산출물 위치

| 파일 | 경로 |
|------|------|
| 실행 스크립트 | `C:\Users\user\Desktop\dxshcool\VOD_Embedding\scripts\run_meta_embed_parquet.py` |
| 핵심 모듈 | `C:\Users\user\Desktop\dxshcool\VOD_Embedding\src\meta_embedder.py` |
| 결과 Parquet | `C:\Users\user\Desktop\dxshcool\VOD_Embedding\data\vod_meta_embedding_20260311.parquet` |

### Parquet 컬럼 구조
| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `vod_id_fk` | int | vod 테이블 PK |
| `embedding` | float32[384] | 384차원 임베딩 벡터 |
| `input_text` | str | 임베딩 입력 텍스트 |
| `model_name` | str | 사용 모델명 |
| `embedding_dim` | int | 벡터 차원 (384) |
| `vector_magnitude` | float | 정규화 후 크기 (1.0) |
| `created_at` | datetime | 생성 일시 |

---

## 5. 핵심 모듈 (`src/meta_embedder.py`)

- `normalize_title(title)` — 에피소드/서비스 구분자 제거, 시리즈 제목 추출
- `group_by_series(df)` — normalized_title + ct_cl 기준 그룹핑
- `pick_representative(group_df)` — 메타데이터 풍부도 기준 대표 row 선택
- `build_input_text(row)` — 제목, 장르, 줄거리, 감독, 주연 등 조합 → 임베딩 입력 문자열 생성

---

## 6. 다음 단계

1. **황대원**: `ingest_to_db.py`를 384d CONTENT 임베딩 Parquet 적재용으로 수정 후 DB 업로드
   - 대상 테이블: `vod_embedding` (기존 테이블 활용 or `embedding_type='CONTENT'` 행으로 삽입)
   - Parquet 위치: `C:\Users\user\Desktop\dxshcool\VOD_Embedding\data\vod_meta_embedding_20260311.parquet`
2. **박아름**: DB 적재 완료 확인 후 유사도 검색 통합 테스트
3. **이가원**: DB 적재 완료 후 FastAPI 엔드포인트 연결 (Phase 4)

---

## 7. 참고 — git 커밋 이력 (dxshcool/VOD_Embedding 레포)

```
ba55e88 docs(VOD_Embedding): 메타 임베딩 Parquet 파이프라인 개발 리포트 추가
5570980 fix(VOD_Embedding): 메타 임베딩 체크포인트를 인코딩 도중에도 저장하도록 수정
9032313 docs(VOD_Embedding): add crawl/embed progress reports (2026-03-11 18:48)
```

모든 코드 변경사항은 `dxshcool/VOD_Embedding` 레포의 `VOD_Embedding` 브랜치에 커밋 완료 상태.
