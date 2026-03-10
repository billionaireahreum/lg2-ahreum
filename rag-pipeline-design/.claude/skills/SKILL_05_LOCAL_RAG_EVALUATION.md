# SKILL: 로컬 RAG 파이프라인 평가 및 최적화

**목적**: RAG 파이프라인의 품질 평가 및 성능 최적화  
**적용 대상**: RAG Pipeline Design 프로젝트

---

## 1️⃣ 품질 평가 지표

### 샘플링 검증

```python
import random
import pandas as pd

def stratified_sampling_validation(results, sample_size=100):
    """신뢰도별 계층화 샘플링"""
    
    # 신뢰도별 분류
    high_conf = [r for r in results if r['confidence'] > 0.8]
    mid_conf = [r for r in results if 0.5 <= r['confidence'] <= 0.8]
    low_conf = [r for r in results if r['confidence'] < 0.5]
    
    # 각 계층에서 샘플
    sample = (
        random.sample(high_conf, min(50, len(high_conf))) +
        random.sample(mid_conf, min(30, len(mid_conf))) +
        random.sample(low_conf, min(20, len(low_conf)))
    )
    
    return sample

def manual_validation(samples):
    """샘플 수동 검증 (또는 전문가 검증)"""
    
    validated = []
    correct_count = 0
    
    for sample in samples:
        print(f"\n영화: {sample['asset_nm']}")
        print(f"추출된 값: {sample['director']}")
        print(f"신뢰도: {sample['confidence']:.2%}")
        
        # 사용자 입력 (또는 자동 검증)
        is_correct = input("맞음? (y/n): ").lower() == 'y'
        
        validated.append({
            **sample,
            'validated': is_correct
        })
        
        if is_correct:
            correct_count += 1
    
    accuracy = correct_count / len(validated)
    print(f"\n검증 정확도: {accuracy:.2%}")
    
    return accuracy, validated
```

### 신뢰도별 정확도 분석

```python
def analyze_accuracy_by_confidence(validated_results):
    """신뢰도별 정확도 패턴 분석"""
    
    df = pd.DataFrame(validated_results)
    
    # 신뢰도 구간별 정확도
    df['conf_bin'] = pd.cut(df['confidence'], 
                            bins=[0, 0.3, 0.6, 0.8, 1.0],
                            labels=['Low', 'Mid', 'High', 'VeryHigh'])
    
    accuracy_by_conf = df.groupby('conf_bin')['validated'].agg(['sum', 'count'])
    accuracy_by_conf['accuracy'] = accuracy_by_conf['sum'] / accuracy_by_conf['count']
    
    print("신뢰도별 정확도:")
    print(accuracy_by_conf)
    
    # 신뢰도 임계값 결정
    # confidence < 0.6이면 정확도가 50% 이하라면,
    # 이들 항목을 수동 검증이나 폴백 처리
    
    return accuracy_by_conf
```

---

## 2️⃣ 성능 벤치마킹

### 처리 시간 측정

```python
import time
import numpy as np

def benchmark_pipeline(vods_batch, pipeline, num_runs=3):
    """파이프라인 성능 벤치마킹"""
    
    results = []
    
    for run in range(num_runs):
        start_time = time.time()
        run_results = []
        
        for vod in vods_batch:
            item_start = time.time()
            
            try:
                director, conf = pipeline.extract_director(vod)
                item_time = time.time() - item_start
                
                run_results.append({
                    'asset_id': vod['full_asset_id'],
                    'time_sec': item_time,
                    'success': True
                })
            except:
                run_results.append({
                    'asset_id': vod['full_asset_id'],
                    'time_sec': 0,
                    'success': False
                })
        
        total_time = time.time() - start_time
        throughput = len(vods_batch) / total_time  # items/sec
        
        results.append({
            'run': run + 1,
            'total_time': total_time,
            'throughput': throughput,
            'avg_item_time': np.mean([r['time_sec'] for r in run_results]),
            'success_rate': sum(1 for r in run_results if r['success']) / len(run_results)
        })
    
    return pd.DataFrame(results)

# 사용
benchmark_df = benchmark_pipeline(vods_sample, pipeline)
print(benchmark_df)
print(f"\n평균 처리량: {benchmark_df['throughput'].mean():.2f} items/sec")
```

### GPU 메모리 모니터링

```python
import torch
import psutil

def monitor_memory_during_processing(pipeline, vods, log_interval=100):
    """처리 중 메모리 사용량 모니터링"""
    
    memory_log = []
    
    for idx, vod in enumerate(vods):
        # 처리
        pipeline.extract_director(vod)
        
        # 주기적 로깅
        if (idx + 1) % log_interval == 0:
            gpu_mem = torch.cuda.memory_allocated() / 1024**3  # GB
            cpu_mem = psutil.Process().memory_info().rss / 1024**3  # GB
            
            memory_log.append({
                'processed': idx + 1,
                'gpu_gb': gpu_mem,
                'cpu_gb': cpu_mem,
                'total_gb': gpu_mem + cpu_mem
            })
            
            print(f"처리: {idx+1} | GPU: {gpu_mem:.1f}GB | CPU: {cpu_mem:.1f}GB")
    
    return pd.DataFrame(memory_log)
```

---

## 3️⃣ 최적화 기법

### 배치 크기 최적화

```python
def find_optimal_batch_size(pipeline, sample_vods, max_memory_gb=8):
    """최적 배치 크기 찾기"""
    
    import torch
    
    results = []
    
    for batch_size in [4, 8, 16, 32]:
        torch.cuda.empty_cache()
        
        start_mem = torch.cuda.memory_allocated() / 1024**3
        start_time = time.time()
        
        try:
            for i in range(0, len(sample_vods), batch_size):
                batch = sample_vods[i:i+batch_size]
                
                for vod in batch:
                    pipeline.extract_director(vod)
            
            elapsed = time.time() - start_time
            end_mem = torch.cuda.memory_allocated() / 1024**3
            peak_mem = max([torch.cuda.max_memory_allocated() / 1024**3])
            
            results.append({
                'batch_size': batch_size,
                'time_sec': elapsed,
                'throughput': len(sample_vods) / elapsed,
                'peak_mem_gb': peak_mem,
                'success': True
            })
        except Exception as e:
            results.append({
                'batch_size': batch_size,
                'error': str(e),
                'success': False
            })
    
    df = pd.DataFrame(results)
    df = df[df['success']]
    
    # 메모리 제약 내에서 가장 높은 처리량
    optimal = df[df['peak_mem_gb'] <= max_memory_gb].nlargest(1, 'throughput')
    
    if len(optimal) > 0:
        print(f"최적 배치 크기: {optimal.iloc[0]['batch_size']}")
        print(f"예상 처리량: {optimal.iloc[0]['throughput']:.2f} items/sec")
    
    return df
```

---

## 4️⃣ 결과 분석 및 리포트

### 종합 분석 리포트

```python
def generate_comprehensive_report(results, validated_results, benchmark_df):
    """RAG 파이프라인 종합 분석 리포트"""
    
    report = f"""
    ╔════════════════════════════════════════════════════╗
    ║     RAG 파이프라인 평가 리포트                    ║
    ╚════════════════════════════════════════════════════╝
    
    📊 처리 현황
    - 총 처리: {len(results)}건
    - 성공: {sum(1 for r in results if r['status']=='success')}건
    - 실패: {sum(1 for r in results if r['status']!='success')}건
    - 성공률: {sum(1 for r in results if r['status']=='success')/len(results)*100:.1f}%
    
    🎯 품질 지표
    - 샘플 검증 정확도: {sum(1 for r in validated_results if r['validated'])/len(validated_results)*100:.1f}%
    - 평균 신뢰도: {np.mean([r['confidence'] for r in results]):.2%}
    - 고신뢰도(>0.8): {sum(1 for r in results if r['confidence']>0.8)/len(results)*100:.1f}%
    
    ⚡ 성능 지표
    - 평균 처리 시간: {benchmark_df['avg_item_time'].mean():.2f}초/항목
    - 처리량: {benchmark_df['throughput'].mean():.2f} items/sec
    - 예상 완료 시간: {25000/benchmark_df['throughput'].mean()/3600:.1f}시간
    
    💾 리소스 사용량
    - Peak GPU: {torch.cuda.max_memory_allocated()/1024**3:.1f}GB
    - Peak CPU: {psutil.virtual_memory().percent:.1f}%
    
    ✅ 결론
    - 신뢰도 80% 이상: {sum(1 for r in results if r['confidence']>0.8)}건
    - 수동 검증 필요: {sum(1 for r in results if r['confidence']<0.6)}건
    """
    
    return report

# 사용
report = generate_comprehensive_report(results, validated_results, benchmark_df)
print(report)
```

---

## 5️⃣ 지속적 모니터링

### 실시간 대시보드

```python
class RAGMonitor:
    """RAG 파이프라인 실시간 모니터링"""
    
    def __init__(self, log_file='rag_monitor.json'):
        self.log_file = log_file
        self.metrics = []
    
    def log_extraction(self, vod_id, column, result, confidence, time_ms):
        """추출 작업 로깅"""
        
        import json
        from datetime import datetime
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'vod_id': vod_id,
            'column': column,
            'result': result,
            'confidence': confidence,
            'time_ms': time_ms,
            'success': confidence > 0.7
        }
        
        self.metrics.append(log_entry)
        
        # 파일에 추가
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
        
        # 주기적 보고
        if len(self.metrics) % 1000 == 0:
            self.print_progress()
    
    def print_progress(self):
        """진행상황 출력"""
        
        total = len(self.metrics)
        success = sum(1 for m in self.metrics if m['success'])
        avg_confidence = np.mean([m['confidence'] for m in self.metrics])
        avg_time = np.mean([m['time_ms'] for m in self.metrics])
        
        print(f"""
        === RAG Pipeline Progress ===
        Processed: {total}
        Success Rate: {success/total*100:.1f}%
        Avg Confidence: {avg_confidence:.2%}
        Avg Time: {avg_time:.0f}ms
        ETA: {(25000-total)*avg_time/1000/3600:.1f}시간
        """)

# 사용
monitor = RAGMonitor()

for vod in vods:
    start = time.time()
    result, conf = pipeline.extract_director(vod)
    elapsed = (time.time() - start) * 1000
    
    monitor.log_extraction(vod['full_asset_id'], 'director', result, conf['confidence'], elapsed)
```

---

## ✅ 최종 평가 체크리스트

- [ ] 샘플링 검증 (100개) 완료
- [ ] 신뢰도별 정확도 분석 완료
- [ ] 성능 벤치마킹 완료
- [ ] 최적 배치 크기 결정
- [ ] 메모리 프로파일링 완료
- [ ] 종합 리포트 생성
- [ ] 실시간 모니터링 설정

---

**RAG 파이프라인 평가 및 최적화 완료!** 🎉

다음: Database Design 프로젝트와 통합하기
