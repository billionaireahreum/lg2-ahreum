# Plan 01 - 결측치 보완 설계 (Claude API)

**대상**: vod 테이블에서 director NULL(313건), smry NULL(28건)
**방법**: Claude Haiku API로 추론/생성
**스크립트**: `pipeline/01_fill_missing.py`

---

## 1. 결측치 현황

| 컬럼 | NULL 건수 | 비율 | 보완 방법 |
|------|----------|------|---------|
| director | 313건 | 0.19% | Claude 추론 (제목+장르+제공사 → 감독명) |
| smry | 28건 | 0.02% | Claude 생성 (제목+장르+감독+주연 → 줄거리) |

---

## 2. director 보완 전략

### 입력 정보
```
제목(asset_nm) + 분류(ct_cl) + 장르(genre/genre_detail) + 제공사(provider) + 방영일(release_date)
```

### Claude 프롬프트 설계
```
다음 VOD 정보를 바탕으로 감독명을 추론해주세요.
정확히 알 수 없으면 'UNKNOWN'을 반환하세요.

제목: {asset_nm}
장르: {genre} / {genre_detail}
분류: {ct_cl}
방영일: {release_date}
제공사: {provider}

감독명만 반환 (예: 봉준호 / 알프레드 히치콕 / UNKNOWN):
```

### 결과 처리
- 반환값 ≠ 'UNKNOWN' → vod.director UPDATE
- 반환값 = 'UNKNOWN' → NULL 유지 (억지 추론 방지)
- rag_source = 'CLAUDE_INFERENCE'

---

## 3. smry 보완 전략

### 입력 정보
```
제목(asset_nm) + 분류(ct_cl) + 장르(genre/genre_detail) + 감독(director) + 주연(cast_lead) + 방영일
```

### Claude 프롬프트 설계
```
다음 VOD 정보를 바탕으로 2-3문장의 한국어 줄거리를 작성해주세요.
정보가 너무 부족해 작성이 불가능하면 'UNKNOWN'을 반환하세요.

제목: {asset_nm}
장르: {genre} / {genre_detail}
분류: {ct_cl}
감독: {director}
주연: {cast_lead}
방영일: {release_date}

2-3문장 한국어 줄거리:
```

### 결과 처리
- 반환값 ≠ 'UNKNOWN' → vod.smry UPDATE
- 반환값 = 'UNKNOWN' → NULL 유지
- rag_source = 'CLAUDE_GENERATED'

---

## 4. DB 업데이트 쿼리

```sql
UPDATE vod
SET
    director         = %(director)s,          -- 또는 smry = %(smry)s
    rag_processed    = TRUE,
    rag_source       = %(rag_source)s,         -- 'CLAUDE_INFERENCE' | 'CLAUDE_GENERATED'
    rag_processed_at = NOW()
WHERE full_asset_id = %(full_asset_id)s;
```

---

## 5. 실행 제어

### 멱등성 조건
```sql
-- 미처리 director NULL VOD만 조회
SELECT ... FROM vod
WHERE director IS NULL
  AND rag_processed = FALSE;

-- 미처리 smry NULL VOD만 조회
SELECT ... FROM vod
WHERE smry IS NULL
  AND rag_processed = FALSE;
```

→ 스크립트 재실행 시 이미 처리된 VOD는 건너뜀

### API 레이트 리밋 대응
- Claude Haiku: 분당 4000 요청 (Tier 1 기준)
- 313 + 28 = 341건 → 레이트 리밋 걱정 없음
- 실패 시 개별 try/except + 로깅 → 실패한 VOD는 다음 실행에 재처리

---

## 6. 검증 쿼리

```sql
-- 처리 결과 확인
SELECT
    rag_source,
    COUNT(*) AS cnt,
    SUM(CASE WHEN director IS NOT NULL THEN 1 ELSE 0 END) AS director_filled,
    SUM(CASE WHEN smry IS NOT NULL THEN 1 ELSE 0 END) AS smry_filled
FROM vod
WHERE rag_processed = TRUE
GROUP BY rag_source;

-- 여전히 NULL인 건 확인 (UNKNOWN으로 판단된 케이스)
SELECT full_asset_id, asset_nm, ct_cl, genre
FROM vod
WHERE (director IS NULL OR smry IS NULL)
  AND rag_processed = TRUE;
```
