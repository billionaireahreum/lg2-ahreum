# SKILL: 벡터 데이터베이스 및 임베딩

**목적**: 로컬 VOD 메타데이터를 벡터 DB에 저장하고 검색하기
**적용 대상**: RAG Pipeline Design 프로젝트

---

## 1️⃣ 한국어 임베딩 모델 설정

### 추천 모델

```python
from sentence_transformers import SentenceTransformer

# 추천 순서
models = [
    "snunlp/KR-SBERT-V40K-klueNLI-augmented",  # ⭐ 가장 권장
    "ko-sbert",  # 간단
    "KoSimCSE/KoSimCSE-roberta-multitask"  # 빠름
]

# 선택
model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augmented")
print(model.get_sentence_embedding_dimension())  # 768
```

### 모델 다운로드 및 캐싱

```python
from sentence_transformers import SentenceTransformer

def load_embedding_model(model_name, cache_dir="./embeddings_cache"):
    """임베딩 모델 로드 (로컬 캐시)"""
    
    model = SentenceTransformer(
        model_name,
        cache_folder=cache_dir,
        device='cuda'  # GPU 사용
    )
    
    return model

# 첫 실행시 자동 다운로드 (약 500MB)
embedding_model = load_embedding_model("snunlp/KR-SBERT-V40K-klueNLI-augmented")
```

---

## 2️⃣ VOD 메타데이터 임베딩

### 텍스트 결합 및 임베딩

```python
import numpy as np
import pandas as pd

def prepare_vod_texts(vods_df):
    """VOD를 임베딩용 텍스트로 변환"""
    
    texts = []
    
    for idx, row in vods_df.iterrows():
        # 메타데이터 결합
        text_parts = [
            row['asset_nm'],  # 영상명
            row['CT_CL'],     # 대분류
            row['genre'],     # 장르
            row['director'] if pd.notna(row['director']) else '',  # 감독
            row['smry'][:100] if pd.notna(row['smry']) else '',  # 요약 (처음 100자)
        ]
        
        # 공백 제거 및 결합
        text = ' '.join([str(p) for p in text_parts if p])
        texts.append(text)
    
    return texts

# 사용
vod_texts = prepare_vod_texts(vod_df)

# 배치 임베딩 (메모리 효율)
embeddings = embedding_model.encode(
    vod_texts,
    batch_size=32,
    show_progress_bar=True,
    convert_to_numpy=True  # numpy 배열로 반환
)

print(f"임베딩 shape: {embeddings.shape}")  # (45000, 768)
```

---

## 3️⃣ 로컬 벡터 데이터베이스 (Chroma 권장)

### 설치 및 설정

```bash
pip install chromadb
```

### Chroma를 이용한 저장 및 검색

```python
import chromadb
import json

def setup_vector_db(embeddings, vod_df, persist_dir="./chromadb"):
    """Chroma 벡터 DB 설정"""
    
    # Chroma 클라이언트 (로컬 저장)
    client = chromadb.Client()
    
    # 컬렉션 생성
    collection = client.create_collection(
        name="vod_metadata",
        metadata={"hnsw:space": "cosine"}
    )
    
    # 임베딩과 메타데이터 저장
    for idx, (embedding, row) in enumerate(zip(embeddings, vod_df.itertuples())):
        collection.add(
            ids=[str(row.Index)],
            embeddings=[embedding.tolist()],
            metadatas=[{
                'asset_id': row.full_asset_id,
                'asset_nm': row.asset_nm,
                'genre': row.genre,
                'director': row.director if pd.notna(row.director) else None,
                'cast': row.cast_lead if pd.notna(row.cast_lead) else None,
            }],
            documents=[f"{row.asset_nm} {row.genre}"]
        )
    
    # 저장
    client.persist()
    
    return client, collection

# 사용
client, collection = setup_vector_db(embeddings, vod_df)
print(f"DB에 저장된 VOD: {collection.count()}")
```

### 유사 VOD 검색

```python
def retrieve_similar_vods(query, collection, embedding_model, k=3):
    """쿼리와 유사한 VOD 검색"""
    
    # 쿼리 임베딩
    query_embedding = embedding_model.encode(query, convert_to_numpy=True)
    
    # 유사 검색
    results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=k,
        include=['embeddings', 'documents', 'metadatas', 'distances']
    )
    
    # 결과 포맷팅
    retrieved = []
    for i, (doc, meta, dist) in enumerate(zip(
        results['documents'][0],
        results['metadatas'][0],
        results['distances'][0]
    )):
        # 거리를 유사도(0-1)로 변환 (cosine distance)
        similarity = 1 - dist
        
        retrieved.append({
            'rank': i + 1,
            'asset_nm': meta['asset_nm'],
            'genre': meta['genre'],
            'director': meta['director'],
            'similarity': similarity
        })
    
    return retrieved

# 사용
query = "봉준호 감독 드라마 영화"
similar_vods = retrieve_similar_vods(query, collection, embedding_model, k=5)

for vod in similar_vods:
    print(f"{vod['rank']}. {vod['asset_nm']} ({vod['similarity']:.2%})")
```

---

## 4️⃣ 결측치별 별도 인덱싱

### 메타데이터별 임베딩

```python
def create_specialized_indices(vod_df, embedding_model):
    """결측치 종류별 전문화된 인덱스"""
    
    indices = {}
    
    # director 인덱스
    director_vods = vod_df[vod_df['director'].notna()].copy()
    director_texts = director_vods['director'] + " " + director_vods['asset_nm']
    director_embeddings = embedding_model.encode(
        director_texts.tolist(),
        batch_size=32,
        convert_to_numpy=True
    )
    indices['director'] = {
        'embeddings': director_embeddings,
        'vod_ids': director_vods.index.tolist(),
        'metadata': director_vods[['asset_nm', 'director', 'genre']].to_dict('records')
    }
    
    # cast_lead 인덱스
    cast_vods = vod_df[vod_df['cast_lead'].notna()].copy()
    cast_texts = cast_vods['cast_lead'] + " " + cast_vods['asset_nm']
    cast_embeddings = embedding_model.encode(
        cast_texts.tolist(),
        batch_size=32,
        convert_to_numpy=True
    )
    indices['cast_lead'] = {
        'embeddings': cast_embeddings,
        'vod_ids': cast_vods.index.tolist(),
        'metadata': cast_vods[['asset_nm', 'cast_lead', 'genre']].to_dict('records')
    }
    
    # 유사하게 rating, release_date 인덱스 생성
    
    return indices

# 사용
indices = create_specialized_indices(vod_df, embedding_model)
```

---

## 5️⃣ 하이브리드 검색 (키워드 + 의미적)

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from scipy.spatial.distance import cosine

def hybrid_search(query, collection, embedding_model, 
                  vod_df, semantic_weight=0.7, keyword_weight=0.3):
    """하이브리드 검색: 의미적 + 키워드"""
    
    # 1. 의미적 검색 (벡터 DB)
    semantic_results = retrieve_similar_vods(query, collection, embedding_model, k=10)
    semantic_scores = {r['asset_nm']: r['similarity'] for r in semantic_results}
    
    # 2. 키워드 검색 (TF-IDF)
    tfidf = TfidfVectorizer().fit(vod_df['asset_nm'].tolist())
    query_tfidf = tfidf.transform([query]).toarray()[0]
    
    keyword_scores = {}
    for idx, vod_name in enumerate(vod_df['asset_nm']):
        vod_tfidf = tfidf.transform([vod_name]).toarray()[0]
        # 코사인 유사도
        similarity = 1 - cosine(query_tfidf, vod_tfidf)
        keyword_scores[vod_name] = similarity
    
    # 3. 스코어 결합
    combined_scores = {}
    all_vods = set(semantic_scores.keys()) | set(keyword_scores.keys())
    
    for vod_name in all_vods:
        semantic = semantic_scores.get(vod_name, 0)
        keyword = keyword_scores.get(vod_name, 0)
        combined = semantic_weight * semantic + keyword_weight * keyword
        combined_scores[vod_name] = combined
    
    # 4. 정렬
    sorted_results = sorted(combined_scores.items(), 
                           key=lambda x: x[1], reverse=True)[:5]
    
    return [{'asset_nm': name, 'score': score} 
            for name, score in sorted_results]

# 사용
hybrid_results = hybrid_search("한국 드라마 영화", collection, embedding_model, vod_df)
for r in hybrid_results:
    print(f"{r['asset_nm']}: {r['score']:.2%}")
```

---

## 6️⃣ 신뢰도 점수 저장

```python
def add_confidence_scores(collection, confidence_dict):
    """검색 결과의 신뢰도 점수 저장"""
    
    for vod_id, confidence in confidence_dict.items():
        try:
            collection.update(
                ids=[vod_id],
                metadatas=[{'confidence_score': confidence}]
            )
        except:
            pass  # 업데이트 실패시 무시

# 신뢰도 점수 계산 예시
confidence_scores = {
    '0': 0.95,  # 매우 높음
    '1': 0.85,  # 높음
    '2': 0.70,  # 중간
}

add_confidence_scores(collection, confidence_scores)
```

---

## ✅ 최종 체크리스트

- [ ] 임베딩 모델 다운로드 (ko-sbert)
- [ ] VOD 메타데이터 임베딩 생성
- [ ] Chroma 벡터 DB 설정
- [ ] 검색 함수 테스트
- [ ] 하이브리드 검색 확인
- [ ] 신뢰도 점수 저장

**다음**: LOCAL_RAG_PIPELINE.md로 전체 파이프라인 구성하기
