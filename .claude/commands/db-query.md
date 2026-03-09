PostgreSQL vod_recommendation DB에 읽기 전용 쿼리를 실행합니다.

조회하고 싶은 내용을 자연어로 설명하면 SQL을 생성하고 실행합니다.

## 허용 쿼리
- SELECT, EXPLAIN ANALYZE
- 집계 함수 (COUNT, AVG, SUM 등)
- pgvector 코사인 유사도 (`<=>` 연산자)

## 금지 쿼리
- INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE

## 주요 테이블
- `vod`: VOD 메타데이터 (166,159개)
- `users`: 사용자 (242,702명)
- `watch_history`: 시청 이력 (3,992,530건)
- `vod_embedding`: VOD 벡터 임베딩 (384d)

## pgvector 유사도 검색 예시
```sql
SELECT v.asset_nm, v.genre,
       1 - (e.content_vector <=> '[...]'::vector) AS similarity
FROM vod_embedding e
JOIN vod v ON e.vod_id_fk = v.full_asset_id
ORDER BY e.content_vector <=> '[...]'::vector
LIMIT 10;
```

## 주의사항
- 사용자 ID(sha2_hash) 전체 출력 금지
- 대용량 결과는 LIMIT 100 사용
- 느린 쿼리는 EXPLAIN으로 먼저 계획 확인
