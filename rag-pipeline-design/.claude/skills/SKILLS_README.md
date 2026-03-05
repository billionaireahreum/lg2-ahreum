# 로컬 LLM RAG 파이프라인 - 5개 Skills 문서 가이드

**목적**: Claude Code에서 로컬 LLM 기반 RAG 파이프라인을 구현하기 위한 완전한 가이드  
**적용**: RAG Pipeline Design 프로젝트

---

## 📚 5개 Skills 문서

### 1️⃣ SKILL_01_LOCAL_LLM_SETUP.md
**내용**: 로컬 LLM 환경 구성
- Kullm-12B 선택 이유
- Ollama/LM Studio/vLLM 설치 비교
- VRAM 최적화 (양자화)
- 한국어 처리 최적화
- 성능 측정

**다음 문서**: SKILL_02_VECTOR_DB_FOR_RAG.md

---

### 2️⃣ SKILL_02_VECTOR_DB_FOR_RAG.md
**내용**: 벡터 데이터베이스 및 임베딩
- 한국어 임베딩 모델 선택
- VOD 메타데이터 임베딩
- Chroma 벡터 DB 설정
- 유사도 검색
- 결측치별 전문화 인덱싱
- 하이브리드 검색

**다음 문서**: SKILL_03_LOCAL_RAG_PIPELINE.md

---

### 3️⃣ SKILL_03_LOCAL_RAG_PIPELINE.md
**내용**: 엔드-투-엔드 RAG 파이프라인
- LocalRAGPipeline 클래스 구조
- director/cast/rating/date 추출
- 배치 처리 최적화 (25,000+ 항목)
- 체크포인팅 (중단 복구)
- 오류 처리 및 폴백 전략

**다음 문서**: SKILL_04_LOCAL_LLM_PROMPTING.md

---

### 4️⃣ SKILL_04_LOCAL_LLM_PROMPTING.md
**내용**: 프롬프트 엔지니어링 (로컬 LLM 특화)
- 한국어 프롬프트 작성 원칙
- 컨텍스트 윈도우 관리
- 구조화된 출력 (JSON) 강제
- Few-shot 학습
- 신뢰도 평가
- 온도 및 파라미터 최적화

**다음 문서**: SKILL_05_LOCAL_RAG_EVALUATION.md

---

### 5️⃣ SKILL_05_LOCAL_RAG_EVALUATION.md
**내용**: 품질 평가 및 최적화
- 샘플링 검증 (100개)
- 신뢰도별 정확도 분석
- 성능 벤치마킹
- GPU 메모리 모니터링
- 배치 크기 최적화
- 종합 분석 리포트
- 실시간 모니터링

---

## 🔗 Skills 학습 경로

```
Step 1: LOCAL_LLM_SETUP
    ↓ (로컬 LLM 설치 및 실행)
    ↓
Step 2: VECTOR_DB_FOR_RAG
    ↓ (벡터 DB 설정 및 검색)
    ↓
Step 3: LOCAL_RAG_PIPELINE
    ↓ (전체 파이프라인 구현)
    ↓
Step 4: LOCAL_LLM_PROMPTING
    ↓ (프롬프트 최적화)
    ↓
Step 5: LOCAL_RAG_EVALUATION
    ↓ (품질 평가 및 개선)
```

---

## 📂 프로젝트 구조

```
rag-pipeline-design/
├── .claude/
│   ├── claude.md              # 메인 작업 지침
│   └── skills/
│       ├── SKILL_01_LOCAL_LLM_SETUP.md
│       ├── SKILL_02_VECTOR_DB_FOR_RAG.md
│       ├── SKILL_03_LOCAL_RAG_PIPELINE.md
│       ├── SKILL_04_LOCAL_LLM_PROMPTING.md
│       └── SKILL_05_LOCAL_RAG_EVALUATION.md
├── src/
│   ├── local_llm.py           # Skill 1 구현
│   ├── vector_db.py           # Skill 2 구현
│   ├── rag_pipeline.py        # Skill 3 구현
│   ├── prompting.py           # Skill 4 구현
│   └── evaluation.py          # Skill 5 구현
├── config/
│   └── rag_config.yaml
└── output/
    ├── results.csv
    ├── validation_report.json
    └── performance_report.md
```

---

## 🚀 Claude Code 활용

### Claude에게 지시하기

```markdown
# RAG Pipeline 구현

rag-pipeline-design/.claude/skills/ 폴더의 5개 가이드를 순서대로 참고해서:

1. LOCAL_LLM_SETUP: Kullm-12B + Ollama 설정
2. VECTOR_DB_FOR_RAG: Chroma + ko-sbert 설정
3. LOCAL_RAG_PIPELINE: director/cast/rating 추출 파이프라인
4. LOCAL_LLM_PROMPTING: 프롬프트 최적화
5. LOCAL_RAG_EVALUATION: 품질 평가 및 모니터링

구체적 요구사항:
- 25,000+ 항목 배치 처리
- director: 95% 성공률 목표
- 배치 크기 자동 최적화
- 실시간 진행상황 추적
```

---

## 📊 예상 성과

### 처리량
```
배치 크기: 8
처리량: 5-10 items/sec
완료 시간: 25,000 ÷ 7.5 items/sec ÷ 3600 = 약 55분
```

### 정확도
```
HIGH (신뢰도>0.8): 90%
MEDIUM (신뢰도 0.6-0.8): 75%
LOW (신뢰도<0.6): 50%

전체 정확도: ~85% (조정 가능)
```

### 리소스 사용
```
GPU: 최대 8GB (int4 양자화)
CPU: 4-6GB
저장소: ~5GB (Chroma DB)
```

---

## ✅ 시작 체크리스트

- [ ] 5개 Skills 문서 모두 다운로드
- [ ] rag-pipeline-design/.claude/skills/ 폴더에 배치
- [ ] Claude Code에서 프로젝트 열기
- [ ] claude.md에서 claude.md 가이드 로드 확인
- [ ] Skills 문서 순서대로 구현 시작

---

## 💡 팁

1. **Skills 문서 구성**
   - 각 파일은 독립적으로 학습 가능
   - 하지만 순서대로 구현해야 전체 파이프라인 완성

2. **코드 재사용**
   - 각 Skill의 코드 예시를 복사-붙여넣기 가능
   - 필요에 따라 수정/확장

3. **문제 해결**
   - SKILL 5의 모니터링으로 병목 지점 파악
   - 각 Skill의 최적화 기법 적용

4. **프로덕션화**
   - SKILL 5의 평가 기준 충족시 프로덕션 배포
   - 지속적 모니터링 및 개선

---

**이제 로컬 LLM 기반 RAG 파이프라인을 완전히 구현할 준비가 되었습니다!** 🚀
