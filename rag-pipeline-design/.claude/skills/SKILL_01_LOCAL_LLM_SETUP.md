# SKILL: 로컬 LLM 모델 설정 및 최적화

**목적**: 로컬에서 한국어 LLM을 설정하고 최적화하는 방법  
**대상**: VOD 메타데이터 추출을 위한 로컬 LLM 환경 구성  
**적용 대상**: RAG Pipeline Design 프로젝트

---

## 1️⃣ 한국어 LLM 모델 선택

### 추천 모델 비교

| 모델 | 크기 | VRAM | 처리속도 | 정확도 | 추천도 |
|------|------|------|--------|--------|--------|
| **Kullm-12B** | 12B | 24GB | 중간 | 높음 | ⭐⭐⭐⭐⭐ |
| EEVE-Korean | 10B | 20GB | 빠름 | 중간 | ⭐⭐⭐⭐ |
| LLaMA-2-KO-7B | 7B | 16GB | 매우빠름 | 중간 | ⭐⭐⭐ |
| Exaone-32B | 32B | 64GB | 느림 | 매우높음 | ⭐⭐⭐⭐⭐ |
| Mistral-KO | 7B | 14GB | 빠름 | 중간 | ⭐⭐⭐ |

### 추천 선택 기준

**당신의 상황에 맞는 선택:**
```
Q: VRAM이 24GB 이상이고 빠른 응답이 필요한가?
A: Kullm-12B 선택 (균형 잡힘)

Q: VRAM이 16GB만 가능한가?
A: LLaMA-2-KO-7B 선택 (경량)

Q: 최고 정확도가 필요한가?
A: Exaone-32B 선택 (고성능)
```

### Kullm-12B 선택 이유 (권장)
```
✅ 한국어 특화 학습
✅ 메타데이터 추출에 적합
✅ 처리 속도 적절 (5-10초/항목)
✅ VRAM 24GB (중급 GPU)
✅ 오픈소스 무료
```

---

## 2️⃣ 설치 방법 (3가지 옵션)

### Option A: Ollama (가장 간단 - 추천)

#### Step 1: Ollama 설치
```bash
# macOS
brew install ollama

# Windows/Linux
# https://ollama.ai 에서 다운로드

# 설치 확인
ollama --version
```

#### Step 2: Kullm 모델 다운로드
```bash
# 모델 다운로드 (약 30분, 24GB)
ollama pull kullm:latest

# 또는 특정 버전
ollama pull kullm:12b-instruct-q4_0
```

#### Step 3: 모델 실행
```bash
# Ollama 서버 시작 (백그라운드)
ollama serve

# 다른 터미널에서 모델 테스트
ollama run kullm:12b-instruct-q4_0
```

#### Step 4: Python에서 연동
```python
import requests
import json

def query_ollama(prompt, model="kullm:12b-instruct-q4_0"):
    """Ollama를 통한 로컬 LLM 쿼리"""
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "temperature": 0.3,  # 메타데이터 추출용 낮은 온도
        },
        timeout=300
    )
    
    if response.status_code == 200:
        return response.json()['response']
    else:
        raise Exception(f"Ollama 오류: {response.text}")

# 테스트
prompt = "한국 영화 '기생충'의 감독은?"
answer = query_ollama(prompt)
print(answer)  # "봉준호"
```

**장점:**
- 가장 간단한 설치
- GUI 지원 (Ollama 앱)
- 자동 메모리 관리
- API 제공

**단점:**
- 세부 최적화 제한
- 배치 처리 성능 낮음

---

### Option B: LM Studio (GUI 기반)

#### Step 1: LM Studio 설치
```bash
# https://lmstudio.ai 에서 다운로드 및 설치
```

#### Step 2: 모델 다운로드
```
1. LM Studio 열기
2. "Search Models" 탭
3. "kullm" 검색
4. "kullm:12b-instruct-q4_0" 선택
5. "Download" 클릭 (약 30분)
```

#### Step 3: 서버 시작
```
1. "Local Server" 탭 선택
2. 다운로드한 모델 선택
3. "Start Server" 클릭
4. 포트 8000에서 실행 확인
```

#### Step 4: Python 연동
```python
import requests

def query_lm_studio(prompt):
    """LM Studio 로컬 서버 쿼리"""
    response = requests.post(
        "http://localhost:8000/v1/completions",
        json={
            "prompt": prompt,
            "max_tokens": 100,
            "temperature": 0.3,
        }
    )
    return response.json()['choices'][0]['text']
```

**장점:**
- 매우 직관적 UI
- 모델 관리 쉬움
- 실시간 모니터링

**단점:**
- 고급 최적화 어려움
- 배치 처리 미지원

---

### Option C: vLLM (고성능 - 추천)

#### Step 1: vLLM 설치
```bash
pip install vllm torch transformers

# GPU 최적화 (CUDA)
pip install vllm torch transformers \
    --index-url https://download.pytorch.org/whl/cu118
```

#### Step 2: 모델 다운로드
```bash
# HuggingFace에서 모델 다운로드
git lfs install
git clone https://huggingface.co/nlpai-lab/kullm-12b-instruct-q4_0

# 또는 자동 다운로드 (처음 실행시)
```

#### Step 3: vLLM 서버 시작
```bash
python -m vllm.entrypoints.openai_api_server \
    --model nlpai-lab/kullm-12b-instruct-q4_0 \
    --tensor-parallel-size 2 \
    --gpu-memory-utilization 0.9 \
    --port 8000 \
    --dtype float16
```

#### Step 4: Python 연동 (OpenAI 호환)
```python
from openai import OpenAI

client = OpenAI(
    api_key="not-needed",
    base_url="http://localhost:8000/v1",
)

def query_vllm(prompt):
    """vLLM 쿼리"""
    response = client.completions.create(
        model="kullm-12b-instruct-q4_0",
        prompt=prompt,
        max_tokens=100,
        temperature=0.3,
    )
    return response.choices[0].text

# 배치 처리 (최적화)
def batch_query_vllm(prompts, batch_size=8):
    """여러 프롬프트 동시 처리"""
    results = []
    for i in range(0, len(prompts), batch_size):
        batch = prompts[i:i+batch_size]
        
        # 동시 요청
        batch_results = []
        for prompt in batch:
            response = client.completions.create(
                model="kullm-12b-instruct-q4_0",
                prompt=prompt,
                max_tokens=100,
                temperature=0.3,
            )
            batch_results.append(response.choices[0].text)
        
        results.extend(batch_results)
        print(f"처리됨: {i+len(batch)}/{len(prompts)}")
    
    return results
```

**장점:**
- 가장 빠른 처리 (3-5배)
- OpenAI 호환 API
- 배치 처리 최적화
- GPU 메모리 최적화

**단점:**
- 설정이 복잡함
- CUDA 필수

---

## 3️⃣ 메모리 및 성능 최적화

### VRAM 요구사항 계산

```python
def calculate_vram_requirement(model_size_b, quantization):
    """모델별 VRAM 요구사항 계산"""
    
    # 기본 메모리 (fp32)
    base_memory = model_size_b * 4  # 4 bytes per parameter
    
    # 양자화 적용
    quantization_map = {
        'fp32': 1.0,
        'fp16': 0.5,
        'int8': 0.25,
        'int4': 0.125,
    }
    
    model_memory = base_memory * quantization_map[quantization]
    
    # 추가 메모리 (컨텍스트, 배치)
    context_memory = 5  # GB (배치 처리, KV 캐시)
    
    total = model_memory + context_memory
    
    return {
        'model_memory_gb': model_memory,
        'context_memory_gb': context_memory,
        'total_gb': total,
        'recommended_gpu': f'{int(total * 1.2)}GB'
    }

# 예시
print(calculate_vram_requirement(12, 'int4'))
# {'model_memory_gb': 1.5, 'context_memory_gb': 5, 'total_gb': 6.5, 'recommended_gpu': '8GB'}
```

### 양자화 (Quantization)

```python
# int4 양자화 모델 사용 (권장)
# 원본: 24GB → int4: 6GB (75% 감소)

from transformers import BitsAndBytesConfig, AutoModelForCausalLM, AutoTokenizer

def load_quantized_model(model_name="nlpai-lab/kullm-12b"):
    """4-bit 양자화 모델 로드"""
    
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype="float16",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )
    
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=quantization_config,
        device_map="auto"
    )
    
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    
    return model, tokenizer

model, tokenizer = load_quantized_model()
```

### 배치 처리 최적화

```python
def optimized_batch_process(vods, llm_function, batch_size=8):
    """메모리 효율적 배치 처리"""
    
    results = []
    
    for i in range(0, len(vods), batch_size):
        batch = vods[i:i+batch_size]
        
        # 배치 처리
        batch_results = llm_function(batch)
        results.extend(batch_results)
        
        # 메모리 정리
        import gc
        gc.collect()
        torch.cuda.empty_cache()
        
        # 진행상황
        progress = min(i + batch_size, len(vods))
        print(f"처리: {progress}/{len(vods)} ({progress/len(vods)*100:.1f}%)")
    
    return results
```

---

## 4️⃣ 한국어 처리 최적화

### 토크나이저 최적화

```python
from transformers import AutoTokenizer

def setup_korean_tokenizer(model_name="nlpai-lab/kullm-12b"):
    """한국어 처리 최적화 토크나이저"""
    
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    
    # 특수 토큰 추가
    special_tokens = {
        'additional_special_tokens': [
            '[영상명]', '[감독]', '[배우]', '[장르]', '[등급]', '[개봉일]'
        ]
    }
    tokenizer.add_special_tokens(special_tokens)
    
    return tokenizer

# 사용
tokenizer = setup_korean_tokenizer()

# 텍스트 인코딩
text = "영화 기생충의 감독은 [감독] 봉준호입니다"
tokens = tokenizer.encode(text)
print(f"토큰 수: {len(tokens)}")  # 효율적으로 인코딩됨
```

### 한글 형태소 분석

```python
from konlpy.tag import Mecab
import re

def preprocess_korean_text(text):
    """한국어 텍스트 전처리"""
    
    mecab = Mecab()
    
    # 형태소 분석
    morphs = mecab.pos(text)
    
    # 명사만 추출 (메타데이터 관련)
    nouns = [word for word, pos in morphs if pos in ['NNP', 'NNG']]
    
    # 동의어 처리 (시간 표현)
    cleaned = clean_temporal_expressions(text)
    
    return {
        'original': text,
        'morphemes': morphs,
        'nouns': nouns,
        'cleaned': cleaned
    }

def clean_temporal_expressions(text):
    """시간 표현 정규화"""
    
    # "2023년" → "2023", "1월" → "01"
    text = re.sub(r'(\d{4})년', r'\1', text)
    text = re.sub(r'(\d{1,2})월', lambda m: f"{int(m.group(1)):02d}", text)
    
    return text

# 예시
result = preprocess_korean_text("2023년 5월에 개봉한 영화 기생충")
print(result)
# {
#   'original': '2023년 5월에 개봉한 영화 기생충',
#   'nouns': ['2023', '영화', '기생충'],
#   'cleaned': '2023 05에 개봉한 영화 기생충'
# }
```

---

## 5️⃣ 성능 측정 및 모니터링

### 응답 시간 측정

```python
import time
import numpy as np

def benchmark_llm(prompts, llm_function, num_runs=3):
    """LLM 성능 벤치마킹"""
    
    times = []
    
    for run in range(num_runs):
        run_times = []
        
        for prompt in prompts:
            start = time.time()
            response = llm_function(prompt)
            elapsed = time.time() - start
            run_times.append(elapsed)
        
        times.append(run_times)
    
    # 통계
    all_times = np.array(times).flatten()
    
    return {
        'mean': np.mean(all_times),
        'std': np.std(all_times),
        'min': np.min(all_times),
        'max': np.max(all_times),
        'p95': np.percentile(all_times, 95),
        'throughput': len(prompts) / np.mean([sum(t) for t in times])  # items/sec
    }

# 사용
prompts = ["감독: ", "배우: ", "등급: "] * 10
benchmark = benchmark_llm(prompts, query_ollama)
print(f"평균 응답시간: {benchmark['mean']:.2f}초")
print(f"처리량: {benchmark['throughput']:.1f} items/sec")
```

### GPU 메모리 모니터링

```python
import torch
import psutil

def monitor_resources():
    """GPU/CPU 리소스 모니터링"""
    
    # CPU 메모리
    process = psutil.Process()
    cpu_memory = process.memory_info().rss / 1024**2  # MB
    
    # GPU 메모리
    if torch.cuda.is_available():
        gpu_memory = torch.cuda.memory_allocated() / 1024**2  # MB
        gpu_memory_reserved = torch.cuda.memory_reserved() / 1024**2  # MB
    else:
        gpu_memory = 0
        gpu_memory_reserved = 0
    
    return {
        'cpu_memory_mb': cpu_memory,
        'gpu_memory_allocated_mb': gpu_memory,
        'gpu_memory_reserved_mb': gpu_memory_reserved,
        'total_gpu_memory_mb': torch.cuda.get_device_properties(0).total_memory / 1024**2
    }

# 주기적 모니터링
def periodic_monitoring(interval=10, duration=3600):
    """주기적 모니터링"""
    
    import time
    start_time = time.time()
    history = []
    
    while time.time() - start_time < duration:
        resources = monitor_resources()
        history.append({
            'timestamp': time.time(),
            **resources
        })
        print(f"CPU: {resources['cpu_memory_mb']:.0f}MB, "
              f"GPU: {resources['gpu_memory_allocated_mb']:.0f}MB")
        
        time.sleep(interval)
    
    return history
```

---

## ✅ 최종 체크리스트

### 설치 완료 확인
```bash
# 1. 모델 다운로드 확인
ollama list  # 또는 ls ~/.ollama/models/

# 2. 서버 실행 확인
curl http://localhost:11434/api/tags

# 3. 모델 테스트
python -c "
import requests
r = requests.post('http://localhost:11434/api/generate',
    json={'model':'kullm:12b-instruct-q4_0','prompt':'안녕'})
print(r.json()['response'])
"
```

### 성능 확인
```python
import time
import requests

# 응답 시간 테스트
start = time.time()
response = requests.post("http://localhost:11434/api/generate",
    json={"model":"kullm:12b-instruct-q4_0",
          "prompt":"한국 영화 기생충의 감독은?",
          "stream":False})
elapsed = time.time() - start

print(f"응답시간: {elapsed:.2f}초")
print(f"응답: {response.json()['response']}")

# 목표: 5-10초/항목
```

---

**이제 로컬 LLM 환경 설정이 완료되었습니다! 🚀**

다음: VECTOR_DB_FOR_RAG.md로 벡터 데이터베이스 설정하기
