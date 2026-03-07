# Plan 02 - VOD 텍스트 임베딩 생성 전략

**목표**: VOD 메타데이터 → 384d 벡터 → pgvector 저장
**스크립트**: `pipeline/02_generate_embeddings.py`

---

## 1. 임베딩 모델 선택

| 모델 | 차원 | 언어 | 속도(CPU) | 비용 |
|------|------|------|----------|------|
| **paraphrase-multilingual-MiniLM-L12-v2** | **384** | **다국어(한국어 포함)** | **빠름** | **무료** |
| BAAI/bge-m3 | 1024 | 다국어 | 느림 | 무료 |
| OpenAI text-embedding-3-small | 1536 | 다국어 | API | 유료 |

**선택**: `paraphrase-multilingual-MiniLM-L12-v2`
이유: 한국어 지원, 로컬 실행, 384d로 pgvector HNSW 성능 충분

---

## 2. 입력 텍스트 구성

```python
def build_vod_text(vod: dict) -> str:
    parts = [
        vod.get('asset_nm', ''),       # 콘텐츠명 (가장 중요)
        vod.get('ct_cl', ''),          # 대분류 (영화/드라마/...)
        vod.get('genre', ''),          # 장르
        vod.get('genre_detail', ''),   # 상세 장르
    ]
    if vod.get('director'):
        parts.append(f"감독: {vod['director']}")
    if vod.get('cast_lead'):
        parts.append(f"주연: {vod['cast_lead']}")
    if vod.get('smry'):
        parts.append(vod['smry'])      # 줄거리 (가장 많은 의미 포함)
    return ' '.join(filter(None, parts))
```

### 텍스트 예시
```
도깨비 드라마 판타지/로맨스 판타지 감독: 이응복 주연: 공유,김고은
저승사자와 도깨비의 기묘한 동거, 그리고 운명적인 사랑 이야기...
```

---

## 3. 배치 처리 전략

```
전체 VOD: 166,159개
배치 크기: 256개
총 배치 수: ~649회
예상 소요: ~30분 (CPU) / ~5분 (GPU)
```

```python
# 배치 처리 (sentence-transformers 내장 배치 지원)
vectors = model.encode(
    texts,
    batch_size=256,
    normalize_embeddings=True,   # L2 정규화 → cosine similarity = dot product
    show_progress_bar=True,
)
```

**L2 정규화** 이유: pgvector cosine distance = 1 - dot_product (정규화 시 동일)
→ `<=>` 연산자 성능 최적화

---

## 4. 임베딩 타입

현재 구현: **METADATA** (384d) - 텍스트 메타데이터 기반

향후 확장 가능:
| 타입 | 차원 | 설명 |
|------|------|------|
| METADATA | 384 | 제목+장르+감독+줄거리 (현재) |
| CONTENT | 1536 | OpenAI multimodal (미래) |
| VISUAL | 512 | 썸네일 이미지 (미래) |
| HYBRID | 2432 | 전체 concat (미래) |

---

## 5. pgvector 저장

```sql
INSERT INTO vod_embedding (
    vod_id_fk, embedding_type, embedding_dimension,
    model_version, vector_magnitude, content_vector
)
VALUES (%s, 'METADATA', 384, %s, %s, %s::vector)
ON CONFLICT (vod_id_fk, embedding_type) DO UPDATE
    SET content_vector   = EXCLUDED.content_vector,
        vector_magnitude = EXCLUDED.vector_magnitude,
        model_version    = EXCLUDED.model_version,
        updated_at       = NOW();
```

---

## 6. 유사도 검색 사용법

```sql
-- 특정 VOD와 유사한 VOD Top-20 검색
SELECT
    ve.vod_id_fk,
    v.asset_nm,
    v.genre,
    1 - (ve.content_vector <=> (
        SELECT content_vector FROM vod_embedding
        WHERE vod_id_fk = 'cjc|M4996864LFOL10619201'
          AND embedding_type = 'METADATA'
    )) AS similarity
FROM vod_embedding ve
JOIN vod v ON ve.vod_id_fk = v.full_asset_id
WHERE ve.embedding_type = 'METADATA'
  AND ve.vod_id_fk != 'cjc|M4996864LFOL10619201'
ORDER BY ve.content_vector <=> (
    SELECT content_vector FROM vod_embedding
    WHERE vod_id_fk = 'cjc|M4996864LFOL10619201'
      AND embedding_type = 'METADATA'
)
LIMIT 20;
```

---

## 7. 검증 쿼리

```sql
-- 임베딩 생성 현황
SELECT
    embedding_type,
    COUNT(*) AS cnt,
    AVG(vector_magnitude) AS avg_magnitude,
    MIN(created_at) AS first_created,
    MAX(updated_at) AS last_updated
FROM vod_embedding
GROUP BY embedding_type;

-- 전체 대비 처리율
SELECT
    COUNT(*) AS total_vod,
    (SELECT COUNT(*) FROM vod_embedding WHERE embedding_type = 'METADATA') AS embedded,
    ROUND(
        (SELECT COUNT(*) FROM vod_embedding WHERE embedding_type = 'METADATA')::NUMERIC
        / COUNT(*) * 100, 2
    ) AS pct
FROM vod;
```
