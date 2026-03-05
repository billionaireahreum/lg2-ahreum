# SKILL: 로컬 RAG 파이프라인 아키텍처

**목적**: 엔드-투-엔드 로컬 RAG 파이프라인 구성
**적용 대상**: RAG Pipeline Design 프로젝트

---

## 1️⃣ 엔드-투-엔드 RAG 워크플로우

```python
class LocalRAGPipeline:
    """로컬 LLM + 벡터 DB 기반 RAG 파이프라인"""
    
    def __init__(self, llm_client, embedding_model, collection):
        self.llm = llm_client
        self.embedding_model = embedding_model
        self.collection = collection
    
    def extract_director(self, vod_info):
        """감독 정보 추출"""
        
        # 1. Retrieval: 유사 VOD 검색
        context = self.retrieve_context(
            vod_info['asset_nm'],
            vod_info['genre'],
            column='director',
            k=3
        )
        
        # 2. Prompt 생성
        prompt = f"""
        영화명: {vod_info['asset_nm']}
        장르: {vod_info['genre']}
        
        참고 정보:
        {context}
        
        위 영화의 감독을 한 명 답하세요. 성과 이름을 모두 포함.
        답:
        """
        
        # 3. Generation: LLM 추론
        response = self.llm.generate(prompt, temperature=0.2, max_tokens=50)
        
        # 4. Post-processing: 형식 검증 및 정규화
        director = self.validate_and_clean(response, 'director')
        
        return director, {'confidence': self.calculate_confidence(response)}
    
    def retrieve_context(self, asset_nm, genre, column, k=3):
        """벡터 DB에서 관련 정보 검색"""
        
        query = f"{asset_nm} {genre} {column}"
        results = retrieve_similar_vods(
            query,
            self.collection,
            self.embedding_model,
            k=k
        )
        
        context_text = "\n".join([
            f"- {r['asset_nm']}: {r.get(column, 'N/A')}"
            for r in results
        ])
        
        return context_text
    
    def validate_and_clean(self, response, expected_type):
        """응답 검증 및 정규화"""
        
        # 개행 제거
        cleaned = response.strip()
        
        # 타입별 검증
        if expected_type == 'director':
            return self.clean_director_name(cleaned)
        elif expected_type == 'cast':
            return self.clean_cast_list(cleaned)
        elif expected_type == 'rating':
            return self.clean_rating(cleaned)
        
        return cleaned
    
    def clean_director_name(self, text):
        """감독명 정규화"""
        
        # 이름만 추출 (예: "감독: 봉준호" → "봉준호")
        import re
        match = re.search(r'[가-힣]+', text)
        if match:
            return match.group()
        return text
    
    def clean_cast_list(self, text):
        """배우 목록 정규화"""
        
        # 쉼표/슬래시로 분리
        import re
        names = re.split(r'[,/,\n]', text)
        # 공백 제거 및 필터링
        names = [n.strip() for n in names if n.strip()]
        return names[:3]  # 최대 3명
    
    def clean_rating(self, text):
        """등급 정규화"""
        
        ratings = ["전체이용가", "12세이용가", "15세이용가", "18세이용가"]
        for rating in ratings:
            if rating in text:
                return rating
        return None
    
    def calculate_confidence(self, response):
        """응답 신뢰도 계산"""
        
        # 응답 길이 (너무 길거나 짧으면 낮음)
        length_score = 1.0 if 5 < len(response) < 50 else 0.5
        
        # 한글 포함 비율
        korean_chars = sum(1 for c in response if ord(c) >= 0xAC00)
        korean_score = korean_chars / len(response) if response else 0
        
        # 종합 신뢰도
        confidence = (length_score + korean_score) / 2
        
        return min(confidence, 1.0)

# 사용
pipeline = LocalRAGPipeline(llm_client, embedding_model, collection)

vod = {
    'asset_nm': '기생충',
    'genre': '드라마'
}

director, metadata = pipeline.extract_director(vod)
print(f"감독: {director} (신뢰도: {metadata['confidence']:.2%})")
```

---

## 2️⃣ 메타데이터별 처리 전략

### director 추출 프롬프트

```python
def create_director_prompt(vod_info, context):
    return f"""
    영화명: {vod_info['asset_nm']}
    장르: {vod_info['genre']}
    개봉년도: {vod_info.get('release_date', '미정')}
    
    참고 정보:
    {context}
    
    위 영화의 감독 이름을 정확히 답하세요.
    (한 명만, 성과 이름 모두)
    
    답:
    """
```

### cast_lead 추출 프롬프트

```python
def create_cast_prompt(vod_info, context):
    return f"""
    영화명: {vod_info['asset_nm']}
    장르: {vod_info['genre']}
    
    참고 정보:
    {context}
    
    위 영화의 주연배우들을 최대 3명까지 답하세요.
    (쉼표로 분리)
    
    답:
    """
```

### rating 분류 프롬프트

```python
def create_rating_prompt(vod_info, context):
    return f"""
    영화명: {vod_info['asset_nm']}
    장르: {vod_info['genre']}
    
    다음 중 이 영화에 해당하는 한국 영상물 등급을 선택하세요:
    1. 전체이용가
    2. 12세이용가
    3. 15세이용가
    4. 18세이용가
    
    답:
    """
```

---

## 3️⃣ 배치 처리 최적화

```python
def process_batch_rag(vods_list, pipeline, batch_size=8):
    """25,000+ 항목 효율적 배치 처리"""
    
    results = []
    failed = []
    
    for batch_idx in range(0, len(vods_list), batch_size):
        batch = vods_list[batch_idx:batch_idx+batch_size]
        
        for vod in batch:
            try:
                # director 추출
                director, conf = pipeline.extract_director(vod)
                
                results.append({
                    'asset_id': vod['full_asset_id'],
                    'director': director,
                    'confidence': conf['confidence'],
                    'status': 'success'
                })
                
                # 메모리 정리
                import gc
                gc.collect()
                
            except Exception as e:
                failed.append({
                    'asset_id': vod['full_asset_id'],
                    'error': str(e)
                })
        
        # 진행률 출력
        progress = min(batch_idx + batch_size, len(vods_list))
        print(f"처리: {progress}/{len(vods_list)} "
              f"({progress/len(vods_list)*100:.1f}%) "
              f"| 성공: {len(results)} | 실패: {len(failed)}")
        
        # 체크포인트 저장 (1000개마다)
        if (batch_idx + batch_size) % 1000 == 0:
            save_checkpoint(results, failed, batch_idx + batch_size)
    
    return results, failed

def save_checkpoint(results, failed, processed_count):
    """처리 진행 상황 저장 (중단 시 복구용)"""
    
    import json
    
    checkpoint = {
        'processed_count': processed_count,
        'results': results[-100:],  # 최근 100개만
        'failed_count': len(failed),
        'timestamp': str(datetime.now())
    }
    
    with open('rag_checkpoint.json', 'w') as f:
        json.dump(checkpoint, f, indent=2)

def load_checkpoint():
    """체크포인트 복구"""
    
    import json
    
    try:
        with open('rag_checkpoint.json', 'r') as f:
            return json.load(f)
    except:
        return None
```

---

## 4️⃣ 오류 처리 및 폴백

```python
def robust_extract_with_fallback(vod_info, pipeline):
    """다단계 폴백이 있는 견고한 추출"""
    
    # 1단계: 로컬 LLM 시도
    try:
        result, conf = pipeline.extract_director(vod_info)
        if conf['confidence'] > 0.7:
            return result, 'llm', conf['confidence']
    except Exception as e:
        print(f"LLM 오류: {e}")
    
    # 2단계: 키워드 검색 폴백
    try:
        result = keyword_search_director(vod_info['asset_nm'])
        if result:
            return result, 'keyword', 0.6
    except:
        pass
    
    # 3단계: 기존 데이터에서 유사 영상 찾기
    try:
        similar_vods = pipeline.retrieve_context(
            vod_info['asset_nm'],
            vod_info['genre'],
            'director',
            k=1
        )
        if similar_vods:
            # 첫 번째 유사 영상의 감독 사용
            return similar_vods[0]['director'], 'similar', 0.5
    except:
        pass
    
    # 최종: NULL 반환
    return None, 'null', 0.0

def keyword_search_director(asset_nm):
    """키워드 기반 감독 검색 (폴백용)"""
    
    # 간단한 규칙 기반 검색
    # 예: "기생충 봉준호" 형식의 기존 데이터 검색
    
    import pandas as pd
    
    director_data = pd.read_csv('director_keywords.csv')
    result = director_data[director_data['title'].str.contains(asset_nm)]
    
    if len(result) > 0:
        return result.iloc[0]['director']
    
    return None
```

---

## ✅ 최종 체크리스트

- [ ] RAGPipeline 클래스 구현
- [ ] director 추출 함수 테스트
- [ ] cast_lead 추출 함수 테스트
- [ ] rating 분류 함수 테스트
- [ ] 배치 처리 최적화 확인
- [ ] 체크포인트 저장/복구 확인
- [ ] 오류 처리 및 폴백 테스트

**다음**: LOCAL_LLM_PROMPTING.md로 프롬프트 최적화하기
