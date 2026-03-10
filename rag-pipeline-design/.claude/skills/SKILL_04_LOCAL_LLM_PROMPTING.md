# SKILL: 로컬 LLM 프롬프트 최적화

**목적**: 로컬 LLM에서 고품질 메타데이터를 추출하는 프롬프트 작성  
**적용 대상**: RAG Pipeline Design 프로젝트

---

## 1️⃣ 한국어 프롬프트 작성 원칙

### ✅ 좋은 예시

```python
prompt = """
영화명: 기생충
장르: 드라마/스릴러
개봉연도: 2019
시간: 132분

위 영화의 감독 이름을 정확히 답하세요.
형식: [감독 성과 이름]

답:
"""
```

### ❌ 나쁜 예시

```python
prompt = "기생충 감독이?"  # 너무 짧음
prompt = "이 영화 누가 만들었어? 자세히 설명해."  # 모호함
```

---

## 2️⃣ 컨텍스트 윈도우 관리 (로컬 LLM 제약)

### 토큰 효율 계산

```python
def estimate_tokens_korean(text):
    """한국어 텍스트의 토큰 수 추정"""
    # 한국어: 평균 3-4자 = 1토큰
    return len(text.encode('utf-8')) // 4

def optimize_prompt_length(prompt, max_tokens=1024):
    """프롬프트 길이 최적화"""
    
    estimated = estimate_tokens_korean(prompt)
    
    if estimated > max_tokens:
        # 문맥 축약
        parts = prompt.split('\n')
        # 중요한 부분만 유지
        optimized = '\n'.join(parts[:5])
        return optimized
    
    return prompt

# 사용
original = "매우 긴 프롬프트..."
optimized = optimize_prompt_length(original, max_tokens=800)
print(f"원본: {estimate_tokens_korean(original)}토큰")
print(f"최적화: {estimate_tokens_korean(optimized)}토큰")
```

---

## 3️⃣ 구조화된 출력 강제

### JSON 형식 강제

```python
def generate_structured_output(llm, vod_info, output_schema):
    """구조화된 JSON 출력 강제"""
    
    prompt = f"""
    영화명: {vod_info['asset_nm']}
    장르: {vod_info['genre']}
    
    다음 JSON 스키마에 맞춰 응답하세요:
    {{
        "감독": "감독 이름",
        "신뢰도": 0.95,
        "설명": "이유"
    }}
    
    응답 (JSON만):
    """
    
    response = llm.generate(prompt, temperature=0.2)
    
    # JSON 추출
    import json
    import re
    
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            return None
    
    return None
```

### Few-shot 예제

```python
def few_shot_extraction(llm, vod_info, examples=None):
    """Few-shot 학습 기반 추출"""
    
    if not examples:
        examples = [
            {
                'title': '기생충',
                'genre': '드라마',
                'director': '봉준호'
            },
            {
                'title': '응답하라1988',
                'genre': '드라마',
                'director': '이준호'
            }
        ]
    
    prompt = "다음 영화들의 감독을 보세요:\n\n"
    
    for ex in examples:
        prompt += f"Q: 영화: {ex['title']}, 장르: {ex['genre']}\n"
        prompt += f"A: {ex['director']}\n"
    
    prompt += f"\nQ: 영화: {vod_info['asset_nm']}, 장르: {vod_info['genre']}\n"
    prompt += "A:"
    
    response = llm.generate(prompt, temperature=0.2, max_tokens=50)
    return response.strip()
```

---

## 4️⃣ 신뢰도 평가

```python
def evaluate_confidence(response, original_context):
    """응답 신뢰도 점수 계산"""
    
    confidence_factors = {}
    
    # 1. 길이 검증 (너무 짧거나 길면 낮음)
    response_len = len(response.split())
    confidence_factors['length'] = (
        1.0 if 1 < response_len < 10 else 0.3
    )
    
    # 2. 한글 비율 (한글이 80% 이상이면 높음)
    korean_count = sum(1 for c in response if ord(c) >= 0xAC00)
    confidence_factors['korean_ratio'] = (
        korean_count / len(response) if response else 0
    )
    
    # 3. 특수문자 확인 (특수문자가 있으면 낮음)
    special_chars = sum(1 for c in response if c in '!@#$%^&*()')
    confidence_factors['special_chars'] = (
        1.0 if special_chars == 0 else 0.5
    )
    
    # 4. 문맥 연관성
    context_keywords = original_context.split()
    matching_keywords = sum(
        1 for kw in context_keywords 
        if kw in response
    )
    confidence_factors['context_match'] = (
        matching_keywords / len(context_keywords) 
        if context_keywords else 0
    )
    
    # 5. 종합 신뢰도
    weights = {
        'length': 0.2,
        'korean_ratio': 0.3,
        'special_chars': 0.2,
        'context_match': 0.3
    }
    
    overall_confidence = sum(
        confidence_factors[k] * weights[k] 
        for k in weights.keys()
    )
    
    return min(overall_confidence, 1.0)

# 사용
response = "봉준호"
context = "기생충 드라마 한국"
confidence = evaluate_confidence(response, context)
print(f"신뢰도: {confidence:.2%}")
```

---

## 5️⃣ 온도 및 파라미터 최적화

### 메타데이터 추출용 설정

```python
def get_optimal_llm_params(task_type='extraction'):
    """작업 유형별 최적 파라미터"""
    
    params = {
        'extraction': {
            'temperature': 0.2,      # 일관성 중시
            'top_p': 0.9,
            'max_tokens': 100,
            'top_k': 40,
            'repetition_penalty': 1.0
        },
        'generation': {
            'temperature': 0.7,      # 균형
            'top_p': 0.9,
            'max_tokens': 256,
            'top_k': 40,
            'repetition_penalty': 1.2
        }
    }
    
    return params.get(task_type, params['extraction'])

# 사용
extraction_params = get_optimal_llm_params('extraction')
response = llm.generate(prompt, **extraction_params)
```

### 동적 파라미터 조정

```python
def adaptive_llm_params(vod_info):
    """VOD 특성에 따른 파라미터 동적 조정"""
    
    base_params = {
        'temperature': 0.2,
        'max_tokens': 100
    }
    
    # 장르별 조정
    if vod_info.get('genre') == '드라마':
        base_params['temperature'] = 0.25  # 약간 더 보수적
    elif vod_info.get('genre') == '코메디':
        base_params['temperature'] = 0.3   # 약간 더 자유로움
    
    # 정보 부족도에 따른 조정
    missing_fields = sum(1 for v in vod_info.values() if not v)
    if missing_fields > 3:
        base_params['max_tokens'] = 150  # 더 많은 설명 허용
    
    return base_params
```

---

## ✅ 최종 프롬프트 템플릿

### director 추출 (최종 버전)

```python
def final_director_prompt(vod_info, context):
    return f"""
    영화 정보:
    - 제목: {vod_info['asset_nm']}
    - 장르: {vod_info.get('genre', '미정')}
    - 개봉: {vod_info.get('release_year', '미정')}
    
    참고 정보:
    {context}
    
    질문: 위 영화의 감독은?
    형식: [감독 이름만]
    
    답:
    """
```

---

**다음**: LOCAL_RAG_EVALUATION.md로 품질 평가하기
