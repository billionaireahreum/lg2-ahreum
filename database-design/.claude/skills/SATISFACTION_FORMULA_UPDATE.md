# VOD 추천 시스템 - 만족도(Satisfaction) 계산 공식 수정 요약

**수정 일시**: 2026-03-05  
**변경 항목**: 만족도 계산 공식  
**이전 방식**: 다중 가중치 기반 (완주율 40% + 재방문 30% + 평점 20% + 신속완주 10%)  
**현재 방식**: 베이지안 스코어 기반 신뢰도 가중 평점

---

## 변경된 만족도 계산 공식

### 베이지안 스코어 기반 공식

```
satisfaction = (v * R + m * C) / (v + m)

변수 정의:
- v: 영상별 시청 건수 (confidence indicator)
- R: 시청 비율 (completion_rate) = use_tms / disp_rtm (0 ~ 1)
- C: 전체 영상의 평균 시청 비율 (global average)
- m: 신뢰도 조절 파라미터 (기본값: 5.0)

범위: 0.0 ~ 1.0
```

### 공식 해석

1. **v (시청 건수)**
   - 영상을 시청한 누적 회수
   - v가 클수록: 해당 영상의 실제 완주율 R을 더 신뢰
   - v가 작을수록: 전체 평균 C로 보정되어 과대평가 방지

2. **R (시청 비율)**
   - 개별 사용자의 시청 시간 / 영상 전체 길이
   - 0 (미시청) ~ 1 (완주) 범위
   - 각 시청 이력별로 독립적으로 계산

3. **C (전체 평균)**
   - 데이터셋 전체의 평균 시청 비율
   - 어떤 영상이 "좋은" 완주율인지의 절대 기준
   - 모든 영상의 전체 context 제공

4. **m (신뢰도 조절)**
   - 기본값: 5.0 (시청 건수 5회를 신뢰도 기준으로 설정)
   - m이 작을수록: 개별 영상의 R을 중요하게 반영 (보수적)
   - m이 클수록: 전체 평균 C의 비중 증가 (보수적)
   - 권장 범위: 0.1 ~ 10.0

---

## 계산 예시

### 시나리오
```
C = 0.5 (전체 평균 시청 비율)
m = 5.0 (신뢰도 조절 파라미터)
```

### 사례 1: 인기 영상
```
asset_id: vod_001, v=100, R=0.8
satisfaction = (100*0.8 + 5*0.5) / (100+5) = 82.5/105 = 0.786

해석: 100명이 시청했고 평균 80% 완주 → 높은 신뢰도 + 높은 점수
```

### 사례 2: 신작 영상
```
asset_id: vod_002, v=1, R=0.9
satisfaction = (1*0.9 + 5*0.5) / (1+5) = 3.4/6 = 0.567

해석: 1명만 시청했고 90% 완주 → 낮은 신뢰도 → 평균에 가까운 점수로 보정
```

### 사례 3: 저품질 영상
```
asset_id: vod_003, v=10, R=0.3
satisfaction = (10*0.3 + 5*0.5) / (10+5) = 5.5/15 = 0.367

해석: 10명이 시청했지만 30% 완주 → 중간 신뢰도 + 낮은 점수
```

### 결론
시청 건수(신뢰도)를 가중치로 반영하여 영상의 실제 품질을 객관적으로 평가

---

## 데이터 품질 필터

```python
# 시청 시간 60초 이하 또는 정보미상(NaN) → 0점 처리
if use_tms_float <= 60 or use_tms_float.isna():
    satisfaction = 0.0
```

---

## 주요 변경점 비교

| 항목 | 이전 (다중 가중치) | 현재 (베이지안 스코어) |
|------|-----------|-----------|
| **공식 유형** | 선형 결합 | 신뢰도 가중 평점 |
| **변수 개수** | 4개 (완주율, 재방문, 평점, 신속완주) | 4개 (v, R, C, m) |
| **핵심 로직** | 각 컴포넌트 가중치 합산 | 시청 건수로 신뢰도 조정 |
| **신뢰도 반영** | 간접적 (컴포넌트별) | 직접적 (v의 가중치) |
| **콜드스타트 처리** | 별도 로직 필요 | C(전체 평균)로 자동 보정 |
| **파라미터 튜닝** | 4개 가중치 조정 | m 파라미터 1개만 조정 |
| **계산 복잡도** | 낮음 (선형) | 낮음 (선형) |

---

## 마이그레이션 전략

### 1단계: 기존 코드 유지
```python
# 기존 코드 (그대로 유지 가능)
main_final['disp_rtm_sec'] = main_final['disp_rtm'].apply(safe_rtm_to_sec)
main_final['use_tms_float'] = main_final['use_tms'].astype(float)
main_final['watch_ratio'] = (main_final['use_tms_float'] / main_final['disp_rtm_sec'])...
main_final['v'] = main_final.groupby('asset_id')['asset_id'].transform('count')
C = main_final[main_final['watch_ratio'] > 0]['watch_ratio'].mean()
m = 5.0
main_final['bayesian_score'] = (main_final['v'] * main_final['watch_ratio'] + m * C) / (main_final['v'] + m)
```

### 2단계: 구조화된 방식으로 리팩토링
```python
# 새 코드 (클래스 기반)
from satisfaction_score_calculator import SatisfactionScoreCalculator

calculator = SatisfactionScoreCalculator(bayesian_m=5.0, min_watch_time_sec=60)
result_df = calculator.calculate_satisfaction(
    main_final,
    vod_column='asset_id',
    use_tms_column='use_tms',
    disp_rtm_column='disp_rtm'
)
```

### 3단계: 통합 검증
```python
from satisfaction_integration_guide import (
    analyze_bayesian_components,
    validate_satisfaction_scores
)

result_df = analyze_bayesian_components(result_df)
validation = validate_satisfaction_scores(result_df)
```

---

## 파라미터 조정 가이드

### m (신뢰도 조절) 값 조정

| m 값 | 특성 | 사용 사례 |
|-----|------|---------|
| **0.1 ~ 1.0** | 개별 영상의 R을 강하게 반영 | 신작 중심 추천 필요 시 |
| **5.0** | 균형잡힌 신뢰도 (기본값) | 일반적인 추천 |
| **10.0 ~ 50.0** | 전체 평균 C를 강하게 반영 | 안정성 중심 추천 |

### 실험 권장
```python
# A/B 테스트를 통해 최적값 찾기
for m in [1.0, 5.0, 10.0]:
    calculator = SatisfactionScoreCalculator(bayesian_m=m)
    result_df = calculator.calculate_satisfaction(data)
    # 추천 품질 평가 → 최적값 선택
```

---

## 논리적 스키마 문서 변경사항

### 수정된 부분

1. **2.3 WATCH_HISTORY 엔티티**
   - 만족도 지표 설명 업데이트
   - 베이지안 공식 명시

2. **3.3 WATCH_HISTORY 테이블 DDL**
   - 만족도 트리거 로직 완전히 재작성
   - 베이지안 스코어 계산 방식 구현

3. **섹션 9.2 만족도 계산 방식**
   - 기존 설명 전체 변경
   - 베이지안 스코어 기반으로 재구성

---

## 제공 파일

### 1. 논리적 스키마 문서
**파일**: `VOD_RECOMMENDATION_LOGICAL_SCHEMA.md`
- 전체 데이터베이스 설계
- 만족도 계산 공식 (업데이트됨)
- 트리거 및 인덱싱 전략

### 2. Python 계산 모듈
**파일**: `satisfaction_score_calculator.py`
- `SatisfactionScoreCalculator` 클래스
- 베이지안 스코어 기반 계산
- 통계 분석 기능

### 3. 통합 가이드
**파일**: `satisfaction_integration_guide.py`
- 기존 코드 마이그레이션
- 변수 분석 기능
- 검증 및 모니터링

---

## 구현 체크리스트

- [ ] 논리적 스키마 문서 검토
- [ ] `satisfaction_score_calculator.py` 설치
- [ ] `satisfaction_integration_guide.py` 설치
- [ ] 샘플 데이터로 테스트
- [ ] 기존 코드와 비교 검증
- [ ] 프로덕션 배포
- [ ] 모니터링 대시보드 설정

---

## 주의사항

1. **데이터 형식 확인**
   - `disp_rtm`: "HH:MM:SS" 또는 "HH:MM" 형식
   - `use_tms`: 초(sec) 단위 숫자
   - `asset_id`: VOD 식별자

2. **최소 시청 시간**
   - 기본값: 60초 이상만 계산
   - 그 이하: 자동으로 0점 처리

3. **NaN 처리**
   - 시청 시간이 NaN → 0점 처리
   - 영상 길이가 NaN → 에러 처리

4. **성능**
   - 대규모 데이터셋: 배치 처리 권장
   - 실시간 계산: 캐싱 적용

---

**문서 버전**: 1.0  
**마지막 수정**: 2026-03-05
