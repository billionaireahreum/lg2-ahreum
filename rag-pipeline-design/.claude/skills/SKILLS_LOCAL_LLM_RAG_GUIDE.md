# 로컬 LLM 기반 RAG 파이프라인 - Skills 가이드 모음

**목적**: Claude Code에서 참고할 수 있는 로컬 LLM RAG 파이프라인 구현 가이드  
**사용 대상**: RAG Pipeline Design 프로젝트  
**적용 기술**: 로컬 LLM (한국어 특화) + 벡터 데이터베이스 + RAG

---

## 📚 필요한 Skills 문서 (5개)

### Skill 1: 로컬 LLM 모델 설정 및 최적화
**파일명**: `LOCAL_LLM_SETUP.md`

**포함 내용**:
```
1. 로컬 LLM 모델 선택 가이드
   - 한국어 특화 모델 추천 (LLaMA 2 KO, Kullm, Eeve 등)
   - 모델 크기 vs 성능 트레이드오프
   - VRAM 요구사항 계산

2. 로컬 LLM 설치 및 실행
   - Ollama, LM Studio, vLLM 등 런타임 비교
   - 모델 다운로드 및 설치
   - 추론 속도 최적화

3. 프롬프트 엔지니어링 (로컬 LLM 특화)
   - 한국어 처리 최적화
   - 컨텍스트 길이 제한 대응
   - 토큰 효율성

4. 메모리 및 성능 관리
   - GPU/CPU 메모리 할당
   - 배치 처리 vs 스트림 처리
   - 응답 시간 최적화
```

### Skill 2: 벡터 데이터베이스 및 임베딩
**파일명**: `VECTOR_DB_FOR_RAG.md`

**포함 내용**:
```
1. 벡터 임베딩 생성 (로컬)
   - 한국어 임베딩 모델 (KoSimCSE, ko-sbert 등)
   - 문서 청킹 전략
   - 임베딩 캐싱 (메모리 절약)

2. 로컬 벡터 데이터베이스
   - Chroma, FAISS, Weaviate (로컬)
   - 메모리 효율적 설정
   - 빠른 유사도 검색

3. VOD 메타데이터 인덱싱
   - director, cast, rating, release_date별 인덱싱
   - 하이브리드 검색 (키워드 + 의미적)
   - 결측치별 별도 인덱스

4. 검색 및 리랭킹
   - top-k 유사도 검색
   - Re-ranking 전략
   - 신뢰도 점수 계산
```

### Skill 3: 로컬 RAG 파이프라인 아키텍처
**파일명**: `LOCAL_RAG_PIPELINE.md`

**포함 내용**:
```
1. 엔드-투-엔드 RAG 워크플로우
   - 문서 준비 (Preparation)
   - 검색 (Retrieval)
   - 생성 (Generation)
   - 재순위화 (Re-ranking)

2. 메타데이터별 RAG 전략
   - director: IMDB 텍스트 기반 검색
   - cast_lead: 배우 정보 검색
   - rating: 연령등급 분류
   - release_date: 시간 정보 추출

3. 한국어 처리 특화
   - 형태소 분석 (Konlpy)
   - 명사 추출
   - 동의어 처리 (시간 표현 등)

4. 배치 처리 최적화
   - 25,000+ 항목 효율적 처리
   - 메모리 제약 내 병렬화
   - 진행상황 추적 및 체크포인팅

5. 오류 처리 및 폴백
   - LLM 응답 오류 처리
   - 형식 검증
   - 대체 전략 (keyword search fallback)
```

### Skill 4: 로컬 LLM 프롬프트 최적화
**파일명**: `LOCAL_LLM_PROMPTING.md`

**포함 내용**:
```
1. 한국어 프롬프트 작성
   - 한국 문화적 컨텍스트
   - 영상물 분류 체계 (K-rating)
   - 한국 영상 메타데이터

2. 컨텍스트 윈도우 관리 (로컬 LLM 제약)
   - 토큰 효율적 쿼리
   - 관련 문서만 포함 (RAG)
   - 동적 컨텍스트 길이 조정

3. 구조화된 출력
   - JSON 형식 강제
   - Few-shot 예제
   - 정규식 기반 검증

4. 신뢰도 평가
   - 확신도(confidence) 추출
   - 모호한 응답 재질의
   - 문맥 기반 신뢰도 점수

5. 성능 vs 품질 트레이드오프
   - 모델 크기 선택
   - 온도(temperature) 설정
   - 최대 토큰 길이
```

### Skill 5: 로컬 RAG 파이프라인 평가 및 최적화
**파일명**: `LOCAL_RAG_EVALUATION.md`

**포함 내용**:
```
1. 품질 평가 지표
   - Retrieval 정확도 (precision, recall)
   - Generation 품질 (BLEU, METEOR)
   - End-to-end 성공률

2. 샘플링 검증
   - 무작위 샘플 수동 검증
   - 신뢰도별 계층화 샘플링
   - 오류 분석

3. 성능 벤치마킹
   - 응답 시간 측정
   - 메모리 사용량
   - 처리량 (items/hour)

4. 최적화 기법
   - 모델 양자화 (quantization)
   - 프롬프트 캐싱
   - 배치 크기 조정
   - GPU 메모리 최적화

5. 모니터링 및 로깅
   - 실시간 진행상황
   - 에러 로깅
   - 성능 지표 추적
```

---

## 🔗 Skills 문서들 간의 의존성

```
LOCAL_LLM_SETUP.md
    ↓
    ├─→ VECTOR_DB_FOR_RAG.md
    │   ↓
    │   └─→ LOCAL_RAG_PIPELINE.md
    │       ↓
    │       ├─→ LOCAL_LLM_PROMPTING.md
    │       │   ↓
    │       │   └─→ LOCAL_RAG_EVALUATION.md
    │
    └─→ LOCAL_LLM_PROMPTING.md
        ↓
        └─→ LOCAL_RAG_EVALUATION.md
```

**읽는 순서**:
1. LOCAL_LLM_SETUP.md (환경 구성)
2. VECTOR_DB_FOR_RAG.md (검색 시스템)
3. LOCAL_RAG_PIPELINE.md (전체 흐름)
4. LOCAL_LLM_PROMPTING.md (세부 조정)
5. LOCAL_RAG_EVALUATION.md (품질 관리)

---

## 📋 각 Skills 문서의 실제 내용 요약

### Skill 1: LOCAL_LLM_SETUP.md
```markdown
# 로컬 LLM 모델 설정 및 최적화

## 1. 모델 선택 가이드

### 추천 한국어 LLM 모델
| 모델 | 크기 | VRAM | 특징 |
|------|------|------|------|
| Kullm-12B | 12B | 24GB | 한국어 특화, 균형 |
| EEVE-Korean | 10B | 20GB | 효율적, 빠름|
| LLaMA-2-KO | 7B | 16GB | 경량, 모바일 |
| Exaone | 32B | 64GB+ | 고성능 |

### 선택 기준
- VRAM: 당신의 GPU 메모리
- 응답 속도: 실시간 처리 필요시 7B-13B
- 정확도: 높은 품질 필요시 32B+

## 2. 설치 옵션

### Option A: Ollama (추천 - 가장 간단)
```bash
# 다운로드: https://ollama.ai
# 실행: ollama run kullm-ko
# 테스트: curl http://localhost:11434/api/generate -d '{"model":"kullm-ko","prompt":"안녕"}'
```

### Option B: LM Studio (GUI)
- 직관적 UI
- 모델 관리 용이
- GPU 자동 감지

### Option C: vLLM (성능 최적화)
```bash
pip install vllm
python -m vllm.entrypoints.openai_api_server \
  --model kullm-12b \
  --tensor-parallel-size 2 \
  --gpu-memory-utilization 0.9
```

## 3. 성능 최적화

### 메모리 절약
- 4-bit 양자화: 30% 메모리 감소
- 8-bit 양자화: 50% 메모리 감소
- Flash Attention: 2배 속도 향상

### 추론 가속
- Batch 처리: 3-5배 처리량 향상
- KV-cache 재사용
- 병렬 처리

## 4. 한국어 처리 최적화

### 토크나이저 최적화
```python
from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("model_name")
# 특수 토큰 추가
tokenizer.add_special_tokens({
    'additional_special_tokens': ['[VOD_NAME]', '[ACTOR]', '[RATING]']
})
```

### 한글 형태소 분석
```python
from konlpy.tag import Mecab
mecab = Mecab()
# 동의어 처리 (시간 표현: "2023년" → "2023")
```
```

### Skill 2: VECTOR_DB_FOR_RAG.md
```markdown
# 벡터 데이터베이스 및 임베딩

## 1. 한국어 임베딩 모델

### 추천 모델
| 모델 | 용도 | 차원 | 특징 |
|------|------|------|------|
| ko-sbert | 의미 검색 | 768 | 정확도 높음 |
| KoSimCSE | 의미 유사도 | 768 | 빠름 |
| umap-ko | 차원 축소 | 384 | 메모리 효율 |

## 2. 임베딩 생성

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('ko-sbert')

# VOD 메타데이터 임베딩
documents = [
    {
        'director': '임창균',
        'cast': ['이병헌', '김태리'],
        'genre': '드라마',
        'summary': '...'
    }
]

# 텍스트 결합 (효율적)
texts = [f"{d['director']} {' '.join(d['cast'])} {d['genre']}" 
         for d in documents]
embeddings = model.encode(texts, batch_size=32)
```

## 3. 로컬 벡터 DB

### Chroma (추천)
```python
import chromadb

client = chromadb.Client()
collection = client.create_collection("vod_metadata")

# 임베딩 저장
collection.add(
    ids=[str(i) for i in range(len(embeddings))],
    embeddings=embeddings,
    metadatas=documents
)

# 검색
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=5
)
```

### FAISS
```python
import faiss
import numpy as np

# 인덱스 생성
dimension = 768
index = faiss.IndexFlatL2(dimension)
index.add(embeddings)

# 검색
distances, indices = index.search(query_embedding, k=5)
```

## 4. 결측치별 인덱싱

```python
# director 전문 인덱스
director_index = {
    'director': embeddings_director,
    'type': 'director'
}

# cast 전문 인덱스
cast_index = {
    'cast_lead': embeddings_cast,
    'type': 'cast'
}

# 신뢰도 점수 저장
confidence_scores = {
    'doc_id': [0.95, 0.87, ...],  # 각 문서의 신뢰도
}
```

## 5. 하이브리드 검색

```python
def hybrid_search(query, semantic_weight=0.7, keyword_weight=0.3):
    # 의미적 검색
    semantic_results = semantic_search(query)
    
    # 키워드 검색
    keyword_results = keyword_search(query)
    
    # 결합
    combined = (semantic_weight * semantic_results + 
                keyword_weight * keyword_results)
    
    return combined.sort_values(ascending=False)
```
```

### Skill 3: LOCAL_RAG_PIPELINE.md
```markdown
# 로컬 RAG 파이프라인 아키텍처

## 1. 엔드-투-엔드 워크플로우

```
Input: VOD (메타데이터 NULL)
  ↓
Retrieval: 유사 VOD 검색 (벡터 DB)
  ↓
Context: 검색된 정보 수집
  ↓
Prompt: 프롬프트 생성 (context 포함)
  ↓
Generation: 로컬 LLM 추론
  ↓
Post-processing: 형식 검증 및 정규화
  ↓
Output: 채워진 메타데이터
```

## 2. 메타데이터별 전략

### director 추출
```python
def extract_director(vod_info):
    # 검색
    context = retrieve_similar_vods(vod_info['title'])
    
    # 프롬프트
    prompt = f"""
    영화명: {vod_info['title']}
    장르: {vod_info['genre']}
    참고정보:
    {context}
    
    위 영화의 감독 이름을 답하세요. 성과 이름을 모두 포함해주세요.
    답: 
    """
    
    # 생성
    response = local_llm.generate(prompt)
    
    # 검증
    director = validate_director(response)
    return director
```

### cast_lead 추출
```python
def extract_cast_lead(vod_info):
    prompt = f"""
    영화: {vod_info['title']}
    
    위 영화의 주연배우들을 최대 3명까지 쉼표로 구분해서 나열하세요.
    답:
    """
    
    response = local_llm.generate(prompt)
    cast_list = parse_cast_list(response)
    return cast_list
```

### rating 분류
```python
def classify_rating(vod_info):
    KOREAN_RATINGS = ["전체이용가", "12세이용가", "15세이용가", "18세이용가"]
    
    prompt = f"""
    영화명: {vod_info['title']}
    장르: {vod_info['genre']}
    
    한국 영상물 등급 중에서 이 영화에 해당하는 등급을 선택하세요.
    선택지: {', '.join(KOREAN_RATINGS)}
    답:
    """
    
    response = local_llm.generate(prompt)
    rating = match_closest_rating(response, KOREAN_RATINGS)
    return rating
```

## 3. 배치 처리 최적화

```python
def process_batch_rag(vods, batch_size=32):
    results = []
    
    for batch in batches(vods, batch_size):
        # 배치 임베딩
        embeddings = embed_vods(batch)
        
        # 배치 검색
        contexts = retrieval_batch(embeddings)
        
        # 배치 프롬프트 생성
        prompts = generate_prompts_batch(batch, contexts)
        
        # 배치 추론 (최적화된 vLLM)
        responses = local_llm.generate_batch(prompts)
        
        # 배치 후처리
        processed = postprocess_batch(responses)
        results.extend(processed)
        
        # 체크포인팅 (중단 복구)
        save_checkpoint(len(results))
    
    return results
```

## 4. 체크포인팅 및 복구

```python
def save_checkpoint(processed_count):
    checkpoint = {
        'processed': processed_count,
        'timestamp': datetime.now(),
        'results': results
    }
    with open('checkpoint.json', 'w') as f:
        json.dump(checkpoint, f)

def load_checkpoint():
    try:
        with open('checkpoint.json', 'r') as f:
            return json.load(f)
    except:
        return None
```
```

### Skill 4: LOCAL_LLM_PROMPTING.md
```markdown
# 로컬 LLM 프롬프트 최적화

## 1. 한국어 프롬프트 작성

### 좋은 예시
```
영화: "기생충"
장르: 스릴러/드라마

위 영화의 감독을 답하세요.
답:
```

### 나쁜 예시
```
영화 감독 찾기: 기생충
```

## 2. 컨텍스트 윈도우 관리

### 토큰 효율 계산
```python
def estimate_tokens(text):
    # 한국어: 평균 3-4 자 = 1 토큰
    return len(text) / 3.5

# 최대 컨텍스트 길이 확인
max_tokens = 2048  # 로컬 모델
prompt_tokens = estimate_tokens(prompt)
context_tokens = estimate_tokens(context)
remaining = max_tokens - prompt_tokens - 100  # 응답 공간
```

### 동적 컨텍스트 조정
```python
def truncate_context(context, max_tokens=500):
    docs = context.split('\n---\n')
    truncated = []
    total_tokens = 0
    
    for doc in docs:
        doc_tokens = estimate_tokens(doc)
        if total_tokens + doc_tokens <= max_tokens:
            truncated.append(doc)
            total_tokens += doc_tokens
        else:
            break
    
    return '\n---\n'.join(truncated)
```

## 3. 구조화된 출력

### JSON 강제
```python
def generate_with_json_format(prompt, schema):
    enhanced_prompt = f"""
    {prompt}
    
    아래 JSON 스키마에 따라 응답하세요:
    {json.dumps(schema, ensure_ascii=False, indent=2)}
    
    JSON 응답:
    """
    
    response = local_llm.generate(enhanced_prompt)
    
    # JSON 추출 및 검증
    json_str = extract_json(response)
    result = validate_json(json_str, schema)
    return result
```

### Few-shot 예제
```python
def few_shot_prompt(query, examples):
    prompt = f"""
    다음 예제들을 참고하여 응답하세요:
    
    """
    
    for example in examples:
        prompt += f"""
    Q: {example['query']}
    A: {example['answer']}
    ---
    """
    
    prompt += f"Q: {query}\nA:"
    return prompt
```

## 4. 신뢰도 평가

```python
def calculate_confidence(response, original_context):
    confidence_factors = {
        'length_match': score_length(response),  # 예상 길이 내
        'format_valid': score_format(response),  # 형식 맞음
        'in_context': score_in_context(response, original_context),  # 문맥 내
        'consistency': score_consistency(response)  # 일관성
    }
    
    confidence = np.mean(list(confidence_factors.values()))
    return confidence, confidence_factors
```

## 5. 성능 조정 파라미터

### 온도(Temperature)
```python
# 낮음 (0.1-0.3): 일관성 높음, 창의성 낮음 ← 메타데이터 추출에 권장
# 중간 (0.5-0.7): 균형
# 높음 (0.8-1.0): 창의성 높음, 일관성 낮음

response = local_llm.generate(
    prompt=prompt,
    temperature=0.3,  # 메타데이터 추출
    top_p=0.9,
    max_tokens=100
)
```
```

### Skill 5: LOCAL_RAG_EVALUATION.md
```markdown
# 로컬 RAG 파이프라인 평가 및 최적화

## 1. 품질 평가 지표

### Retrieval 평가
```python
def evaluate_retrieval(predictions, ground_truth):
    # Precision@K
    precision_at_k = sum([1 for pred in predictions[:5] 
                         if pred in ground_truth]) / 5
    
    # Recall@K
    recall_at_k = sum([1 for pred in predictions[:5] 
                      if pred in ground_truth]) / len(ground_truth)
    
    # MRR (Mean Reciprocal Rank)
    for i, pred in enumerate(predictions):
        if pred in ground_truth:
            mrr = 1 / (i + 1)
            break
    
    return {'precision@5': precision_at_k, 'recall@5': recall_at_k, 'mrr': mrr}
```

### Generation 평가
```python
from rouge import Rouge
from nltk.translate.bleu_score import sentence_bleu

def evaluate_generation(predictions, references):
    rouge = Rouge()
    
    # ROUGE 점수
    scores = rouge.get_scores(predictions, references)
    
    # BLEU 점수
    bleu = sentence_bleu([ref.split()], pred.split())
    
    return {'rouge': scores, 'bleu': bleu}
```

## 2. 샘플링 검증

```python
import random

def stratified_sampling(results, sample_size=100):
    # 신뢰도별 계층화
    high_conf = [r for r in results if r['confidence'] > 0.8]
    mid_conf = [r for r in results if 0.5 <= r['confidence'] <= 0.8]
    low_conf = [r for r in results if r['confidence'] < 0.5]
    
    # 각 계층에서 샘플
    sample = (
        random.sample(high_conf, min(40, len(high_conf))) +
        random.sample(mid_conf, min(40, len(mid_conf))) +
        random.sample(low_conf, min(20, len(low_conf)))
    )
    
    return sample

def manual_validation(samples):
    validated = []
    for sample in samples:
        # 수동 검증 (또는 전문가 검증)
        is_correct = expert_review(sample)
        validated.append({**sample, 'validated': is_correct})
    
    accuracy = sum([1 for v in validated if v['validated']]) / len(validated)
    return accuracy, validated
```

## 3. 성능 벤치마킹

```python
import time
import psutil

def benchmark_pipeline(vods, num_runs=3):
    results = []
    
    for run in range(num_runs):
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / 1024**2
        
        # 파이프라인 실행
        outputs = rag_pipeline.process(vods)
        
        end_time = time.time()
        end_memory = psutil.Process().memory_info().rss / 1024**2
        
        results.append({
            'run': run + 1,
            'time': end_time - start_time,
            'memory_delta': end_memory - start_memory,
            'throughput': len(vods) / (end_time - start_time)  # items/sec
        })
    
    return results
```

## 4. 최적화 기법

### 모델 양자화
```python
from auto_gptq import AutoGPTQForCausalLM

# 4-bit 양자화
model = AutoGPTQForCausalLM.from_quantized(
    "model_id",
    use_safetensors=True,
    device_map="auto",
    quantize_config=quantize_config
)
```

### 프롬프트 캐싱
```python
from functools import lru_cache

@lru_cache(maxsize=10000)
def cached_generate(prompt_hash):
    # 같은 프롬프트 재사용시 캐시 사용
    return local_llm.generate(prompt)
```

## 5. 모니터링 및 로깅

```python
import logging
import json
from datetime import datetime

class RAGLogger:
    def __init__(self, log_file='rag_pipeline.log'):
        self.log_file = log_file
        self.logger = logging.getLogger(__name__)
        self.metrics = []
    
    def log_item(self, vod_id, column, result, confidence, time_taken):
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'vod_id': vod_id,
            'column': column,
            'result': result,
            'confidence': confidence,
            'time_ms': time_taken * 1000,
            'success': confidence > 0.7
        }
        
        self.metrics.append(log_entry)
        self.logger.info(json.dumps(log_entry))
        
        # 주기적 리포트
        if len(self.metrics) % 1000 == 0:
            self.print_progress()
    
    def print_progress(self):
        total = len(self.metrics)
        success = sum([1 for m in self.metrics if m['success']])
        avg_time = np.mean([m['time_ms'] for m in self.metrics])
        
        print(f"""
        === RAG Pipeline Progress ===
        Processed: {total}
        Success Rate: {success/total*100:.1f}%
        Avg Time: {avg_time:.1f}ms
        """)
```
```

---

## 🎯 Skills 문서 활용법

### Claude Code에서 사용하기

```
rag-pipeline-design/.claude/
├── claude.md (메인 지침)
├── skills/
│   ├── LOCAL_LLM_SETUP.md
│   ├── VECTOR_DB_FOR_RAG.md
│   ├── LOCAL_RAG_PIPELINE.md
│   ├── LOCAL_LLM_PROMPTING.md
│   └── LOCAL_RAG_EVALUATION.md
```

### Claude에게 지시하기

```markdown
# RAG 파이프라인 구현 요청

.claude/skills/ 폴더의 가이드를 참고해서:

1. 로컬 LLM (Kullm) 연동
2. 벡터 DB (Chroma) 임베딩
3. director 추출 파이프라인 구현
4. 신뢰도 평가 및 모니터링
5. 25,000 항목 배치 처리

자세한 설정은 skills 문서들을 참고해주세요.
```

---

## 📊 최종 파일 구조

```
rag-pipeline-design/
├── .claude/
│   ├── claude.md               # 메인 작업 지침
│   └── skills/                 # ← 아래 5개 skills 문서
│       ├── LOCAL_LLM_SETUP.md
│       ├── VECTOR_DB_FOR_RAG.md
│       ├── LOCAL_RAG_PIPELINE.md
│       ├── LOCAL_LLM_PROMPTING.md
│       └── LOCAL_RAG_EVALUATION.md
├── data/
│   └── rag_analysis/
├── src/
│   ├── local_llm.py            # LLM 통합
│   ├── vector_db.py            # 벡터 DB
│   ├── rag_pipeline.py         # 파이프라인
│   ├── prompting.py            # 프롬프트
│   └── evaluation.py           # 평가
└── config/
    └── rag_config.yaml         # 설정
```

---

**이 5개의 Skills 문서로 로컬 LLM 기반 RAG 파이프라인을 완전히 구현할 수 있습니다!** 🚀
