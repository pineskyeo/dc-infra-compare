# 합성 예시 ITEM (EX_ITEM)

- 실행 결과가 아닌 합성 데이터. 기준 조건 3회 + 비교 조건 1회, die 60개
- `make_example.py` (seed 20263255) → `data/ref_run1~3/REF.dcn`, `data/cand/CAND.dcn`, `example_wide.csv`
- 도구 실행 (저장소 루트에서):
  `python por_doe_compare.py --por examples/data/ref_run1 --por examples/data/ref_run2 --por examples/data/ref_run3 --doe examples/data/cand --out tool_out`
- `tool_items.csv` = 위 실행의 items.csv (por_doe_compare.py @5e6ddae)
- `compute_example.py` = 단계별 손계산 → `example.json`. 도구 출력과 11개 값 모두 일치 (`tool_match`)
- `sim_sliders.py` = 그림 슬라이더용 확률 표 → `sliders.json` (같은 모형, judge() 2000회씩) · 모형의 σ_die 0.98965, σ_run 0.50389 = 예시 ITEM의 도구 추정값
