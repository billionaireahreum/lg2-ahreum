# RAG Pipeline Design Project - Claude Code 작업 지침

**프로젝트명**: VOD 추천 시스템 - RAG 기반 결측치 채우기 파이프라인  
**목표**: 외부 정보 검색(RAG)을 통해 VOD 메타데이터 결측치 자동 채우기  
**소유자**: Data Engineering + AI Team  
**상태**: 설계 단계

---

## 📋 프로젝트 개요

### 목표
- 외부 소스(IMDB, Wiki, KMRB)에서 메타데이터 검색
- 73,000개 결측치 자동으로 채우기
- 높은 정확도와 빠른 처리 속도 달성
- 검증 및 모니터링 시스템 구축

### 처리 대상 결측치
- **HIGH (필수)**: director, cast_lead, rating, release_date (~53,000개)
- **MEDIUM (선택)**: cast_guest, smry (~20,000개)
- **총합**: ~73,000개 (약 1.8%)

### 예상 영향
- director: 15,000개 (0.38%) → 95% 채워질 예상
- cast_lead: 25,000개 (0.63%) → 90% 채워질 예상
- rating: 5,000개 (0.13%) → 98% 채워질 예상
- release_date: 8,000개 (0.20%) → 95% 채워질 예상

---

## 🏗️ 파이프라인 설계 원칙

### 1. 신뢰성
- **우선순위 기반**: HIGH → MEDIUM 순서로 처리
- **검증 강화**: 모든 검색 결과 품질 검증
- **에러 처리**: 검색 실패 시 대체 전략
- **재시도 메커니즘**: 일시적 오류는 자동 재시도

### 2. 성능
- **병렬 처리**: 다중 API 동시 요청
- **배치 처리**: 대량 데이터 효율적 처리
- **캐싱**: 중복 검색 제거
- **속도 목표**: HIGH 53,000개 처리 1-2주

### 3. 데이터 품질
- **정확도**: 검색 결과 일치도 > 90%
- **중복 제거**: 동일 정보에 대한 중복 저장 방지
- **타입 검증**: 데이터 타입 및 형식 검증
- **수동 검증**: 샘플링을 통한 품질 검증

### 4. 추적 가능성
- **로깅**: 모든 검색 작업 기록
- **메타데이터**: RAG 소스, 처리 시간, 신뢰도 점수
- **감사 추적**: 어느 값이 RAG로 채워졌는지 추적
- **롤백 가능**: 필요시 원래 상태로 복구 가능

---

## 🔍 RAG 대상 분석

### HIGH 우선순위 (필수 처리)

#### 1. director (15,000개, 0.38%)
```
검색 전략: asset_nm → IMDB/Wiki 검색 → director 추출
소스: IMDB API, Wikipedia
신뢰도: 높음 (98%)
처리 시간: ~2-3초/개
예상 성공률: 95%
```

#### 2. cast_lead (25,000개, 0.63%)
```
검색 전략: asset_nm + genre → 배우 검색
소스: IMDB API, 영화 데이터베이스
신뢰도: 중간 (85-90%)
처리 시간: ~3-5초/개 (여러 배우)
예상 성공률: 90%
```

#### 3. rating (5,000개, 0.13%)
```
검색 전략: asset_nm → 연령등급 조회
소스: KMRB (영상물등급위원회), IMDB
신뢰도: 매우 높음 (99%)
처리 시간: ~1-2초/개
예상 성공률: 98%
```

#### 4. release_date (8,000개, 0.20%)
```
검색 전략: asset_nm → 개봉일 검색
소스: IMDB API, Wikipedia
신뢰도: 높음 (95%)
처리 시간: ~1-2초/개
예상 성공률: 95%
```

### MEDIUM 우선순위 (선택적 처리)

#### 5. cast_guest (18,000개, 0.45%)
```
검색 전략: asset_nm + 조연 역할 검색
소스: IMDB API
신뢰도: 중간 (75-80%)
처리 시간: ~2-3초/개
예상 성공률: 85%
우선순위: 낮음 (조연은 선택적 정보)
```

#### 6. smry (2,000개, 0.05%)
```
검색 전략: asset_nm → 줄거리 검색
소스: IMDB API, Wikipedia
신뢰도: 중간 (70-80%)
처리 시간: ~2초/개
예상 성공률: 80%
우선순위: 낮음 (줄거리는 보강 목적)
```

---

## 🛠️ 파이프라인 구성 (아키텍처)

### Phase 1: 준비 (1주)
```
데이터 로드
  ↓
결측치 분석 (이미 완료)
  ↓
API 키 설정 (IMDB, Wiki, KMRB)
  ↓
검색 함수 개발
  ↓
테스트 샘플 검증 (100개)
```

### Phase 2: HIGH 우선순위 처리 (2주)
```
director 처리 (15,000개)
  ↓ (병렬)
cast_lead 처리 (25,000개)
  ↓ (병렬)
rating 처리 (5,000개)
  ↓ (병렬)
release_date 처리 (8,000개)
  ↓
품질 검증
  ↓
데이터베이스 UPDATE
```

### Phase 3: MEDIUM 우선순위 처리 (2-3주, 선택)
```
cast_guest 처리 (18,000개)
  ↓
smry 처리 (2,000개)
  ↓
품질 검증
  ↓
데이터베이스 UPDATE
```

### Phase 4: 검증 및 모니터링 (지속)
```
채워진 데이터 샘플링 (5% 수동 검증)
  ↓
통계 리포트
  ↓
이슈 추적 및 개선
  ↓
최종 보고서
```

---

## 📝 구현 요구사항

### 필수

#### 1. 검색 함수 (search_functions.py)
```python
def search_director(asset_nm: str, provider: str) -> Optional[str]:
    """영화명으로 감독 검색"""
    
def search_cast_lead(asset_nm: str, genre: str) -> List[str]:
    """주연배우 검색"""
    
def search_rating(asset_nm: str) -> Optional[str]:
    """연령등급 검색"""
    
def search_release_date(asset_nm: str) -> Optional[str]:
    """개봉일 검색"""
```

#### 2. RAG 파이프라인 (rag_pipeline.py)
```python
class RAGPipeline:
    def process_high_priority(self):
        """HIGH 우선순위 처리"""
    
    def process_medium_priority(self):
        """MEDIUM 우선순위 처리"""
    
    def validate_results(self):
        """결과 검증"""
    
    def update_database(self):
        """데이터베이스 업데이트"""
    
    def generate_report(self):
        """통계 리포트 생성"""
```

#### 3. 검증 함수 (validation.py)
```python
def validate_director(director: str, source: str) -> bool:
    """감독명 유효성 검증"""
    
def validate_cast(cast_list: List[str]) -> bool:
    """배우명 유효성 검증"""
    
def validate_rating(rating: str) -> bool:
    """연령등급 유효성 검증"""
    
def validate_date(date_str: str) -> bool:
    """날짜 형식 검증"""
```

### 선택

#### 4. 모니터링 및 로깅 (monitoring.py)
```python
class RAGMonitor:
    def log_search(self, vod_id, column, result, source, duration):
        """검색 로그 기록"""
    
    def track_success_rate(self):
        """성공률 추적"""
    
    def detect_anomalies(self):
        """이상 탐지"""
    
    def generate_daily_report(self):
        """일일 리포트"""
```

#### 5. 품질 분석 (quality_analysis.py)
```python
class QualityAnalyzer:
    def sample_validation(self, sample_size=100):
        """샘플링 검증"""
    
    def confidence_score(self, result, source):
        """신뢰도 점수 계산"""
    
    def identify_failures(self):
        """실패 항목 식별"""
    
    def suggest_improvements(self):
        """개선사항 제안"""
```

---

## 📊 RAG 소스 전략

### IMDB API
```
장점: 감독, 배우, 개봉일 정보 풍부
단점: 비율 제한 있음
비용: API 키 필수
추천 사용: director, cast, release_date
```

### Wikipedia
```
장점: 무료, 풍부한 정보
단점: 파싱 복잡, 데이터 일관성
추천 사용: director, 줄거리, 기타 정보
```

### KMRB (영상물등급위원회)
```
장점: 공식 연령등급, 높은 신뢰도
단점: API 제한, 한국 영상만
추천 사용: rating (한국 영상)
```

### 폴백 전략
```
1차: 특정 소스로 검색
2차: 다른 소스로 재검색
3차: 수동 검증 큐에 추가
4차: NULL 유지 (나중에 수동)
```

---

## 🔄 워크플로우

### 검색 → 검증 → 저장 → 추적

```
1. 검색 (Search)
   asset_nm으로 외부 소스 검색
   ↓
2. 검증 (Validation)
   결과의 정확도, 형식, 신뢰도 검증
   ↓
3. 저장 (Store)
   데이터베이스에 결과 저장
   ↓
4. 추적 (Track)
   rag_processed = TRUE
   rag_source = 사용한 소스
   rag_processed_at = 처리 시간
```

---

## 💾 데이터베이스 통합

### 마이그레이션 전략
```sql
-- 1. 추적 컬럼 추가 (Database Design 프로젝트)
ALTER TABLE vod ADD COLUMN rag_processed BOOLEAN DEFAULT FALSE;
ALTER TABLE vod ADD COLUMN rag_source VARCHAR(50);
ALTER TABLE vod ADD COLUMN rag_processed_at TIMESTAMP;

-- 2. RAG 완료 후 UPDATE
UPDATE vod SET 
  director = '...',
  rag_processed = TRUE,
  rag_source = 'IMDB',
  rag_processed_at = NOW()
WHERE full_asset_id = '...';

-- 3. 검증
SELECT COUNT(*) FROM vod WHERE director IS NOT NULL AND rag_processed = TRUE;
```

---

## 📈 성공 지표

### 정량 지표
- [ ] HIGH 우선순위: 95% 이상 채워짐
- [ ] 정확도: 90% 이상
- [ ] 처리 시간: 1-2주 (병렬 처리)
- [ ] 신뢰도 점수: 평균 0.90 이상

### 정성 지표
- [ ] 모든 결과 샘플링 검증 완료
- [ ] 이슈 없음 또는 문서화됨
- [ ] 롤백 가능한 상태 유지
- [ ] 명확한 로깅 및 추적

---

## 📂 파일 구조

```
rag-pipeline-design/
├── .claude/
│   └── claude.md                    # 이 파일
├── data/
│   └── rag_analysis/                # generate_rag_metadata.py 결과
│       ├── 03_rag_metadata.csv      # RAG 메타데이터
│       └── 05_claude_prompt.md      # 결측치 정보
├── src/
│   ├── search_functions.py          # ← Claude가 생성할 파일
│   ├── rag_pipeline.py              # ← Claude가 생성할 파일
│   ├── validation.py                # ← Claude가 생성할 파일
│   ├── monitoring.py                # ← Claude가 생성할 파일 (선택)
│   └── quality_analysis.py          # ← Claude가 생성할 파일 (선택)
├── config/
│   ├── api_keys.env                 # API 키 (보안)
│   └── rag_config.yaml              # 파이프라인 설정
├── output/
│   ├── results.csv                  # RAG 결과
│   ├── validation_report.json       # 검증 리포트
│   └── daily_report.md              # 일일 리포트
└── README.md                        # 프로젝트 설명
```

---

## 💻 Claude Code 작업 프롬프트

### 첫 번째 작업: 검색 함수 개발
```markdown
# Task: RAG 검색 함수 개발

## 요구사항

1. director 검색 함수
   - asset_nm으로 IMDB 검색
   - 감독명 추출
   - 에러 처리

2. cast_lead 검색 함수
   - asset_nm으로 주연배우 검색
   - 배우 목록 반환
   - 최대 3명 제한

3. rating 검색 함수
   - asset_nm으로 연령등급 조회
   - 한국 기준 우선
   - KMRB/IMDB 폴백

4. release_date 검색 함수
   - asset_nm으로 개봉일 검색
   - YYYY-MM-DD 형식
   - 형식 검증

## 입력
[rag_analysis/03_rag_metadata.csv 샘플]

## 출력
search_functions.py
```

### 두 번째 작업: RAG 파이프라인
```markdown
# Task: RAG 파이프라인 구현

## 요구사항

1. 검색 및 처리
   - HIGH 우선순위부터 처리
   - 병렬 처리 지원
   - 배치 처리

2. 검증
   - 각 결과 검증
   - 신뢰도 점수 계산
   - 실패 항목 추적

3. 로깅
   - 모든 작업 기록
   - 통계 수집
   - 진행률 표시

4. 데이터베이스 통합
   - 결과 저장
   - 추적 정보 기록
   - 검증

## 출력
rag_pipeline.py, validation.py, monitoring.py
```

---

## 🎯 다음 단계

### 1단계: 분석 (완료)
- [x] 결측치 분석
- [x] 우선순위 분류
- [x] RAG 전략 수립

### 2단계: 설계 (현재)
- [ ] 이 문서 검토
- [ ] Claude Code에 프롬프트 제시
- [ ] 검색 함수 생성
- [ ] 파이프라인 생성

### 3단계: 구현 (다음)
- [ ] API 키 설정
- [ ] 검색 함수 테스트
- [ ] 파이프라인 테스트

### 4단계: 실행 (그 다음)
- [ ] HIGH 우선순위 처리
- [ ] 검증 및 리포트
- [ ] 데이터베이스 업데이트
- [ ] MEDIUM 우선순위 처리 (선택)

---

## 📞 참고 문서

### 필수
- [RAG_MISSING_DATA_STRATEGY.md](../RAG_MISSING_DATA_STRATEGY.md) - RAG 전략 상세

### 참고
- [rag_analysis/03_rag_metadata.csv](../rag_analysis/03_rag_metadata.csv) - 메타데이터
- [rag_analysis/05_claude_prompt.md](../rag_analysis/05_claude_prompt.md) - 결측치 정보

---

## 🚀 Claude Code 활용 팁

### API 통합
```
"IMDB API를 사용해서 감독명을 검색하는 함수를 작성해줘.
오류 처리와 재시도 로직도 포함해줘."
```

### 성능 최적화
```
"25,000개의 배우 검색을 병렬로 처리할 수 있도록 최적화해줘.
처리 시간을 2주 이내로 줄일 수 있는 전략을 제안해줘."
```

### 검증 강화
```
"검색 결과의 신뢰도를 점수화하는 로직을 추가해줘.
신뢰도가 70% 이하면 수동 검증 큐에 추가하도록."
```

---

**마지막 수정**: 2026-03-05  
**프로젝트 상태**: RAG Pipeline Design 시작 준비 완료
