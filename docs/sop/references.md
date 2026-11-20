# DC Test 동일성 검증 — 근거 문헌 대조표 (v3.4 기준)

- 대상: `/workspace/dc-method-sop-20261118/site-v3.4/` (index, step-0~6, reading, appendix, run)와 `/workspace/dc-infra-compare-review` (README.md, docs/method.html, por_doe_compare.py)
- 작성: Sec, 2026-11-18 23:29 KST. 모든 출처는 같은 날 23:15~23:29 KST에 원문 페이지·PDF를 직접 열어 대조함. 기억으로 쓴 인용 없음
- 상태 표기
  - 확인: 원문을 열어 SOP 식·주장과 맞는 문장/식을 찾음
  - 부분: 원문이 일부만 뒷받침하거나, 2차 출처로만 확인했거나, SOP가 원문 방법을 변형함
  - 근거 없음-내부 기준: 원문 근거를 찾지 못함. 사내 정책·설계·제안으로 표기해야 함
- 원문을 열지 못한 문헌은 "미열람"으로 따로 적음 (아래 4절). 미열람 문헌은 상태 판단에 쓰지 않음

## 1. 대조표

| # | 항목 | SOP 단계 | 출처 | 정확한 위치 | URL | 뒷받침 내용 | 상태 |
|---|---|---|---|---|---|---|---|
| 1 | 대응 차이 d = Cand − Ref 3회 평균 | ③ (개요 '차이 구하기') | NIST/SEMATECH e-Handbook<br>ASTM E2935-21 | 7.3.1.1 Analysis of paired observations<br>4.2.1, 4.2.1.1 (Significance and Use) | https://www.itl.nist.gov/div898/handbook/prc/section3/prc311.htm<br>https://store.astm.org/e2935-21.html | NIST: 같은 대상을 두 측정 장치로 재면 쌍을 이루고 d_i = Y_i − Z_i로 두 측정 체계의 호환성을 판단<br>ASTM: 현 시험 공정과 바뀐 공정의 동등성은 같은 재료를 양쪽으로 재고, 반복성 조건이 안 되면 쌍 차이의 평균으로 평가 | 확인 (쌍 설계). Ref를 J회 평균으로 쓰는 것은 설계 선택 |
| 2 | σ_die(σ_r) = 1.4826·MAD(이웃 회차 차이)/√2 | ① | NIST e-Handbook<br>NIST e-Handbook<br>JCGM 100:2008 (GUM)<br>Wikipedia (2차) | 1.3.5.6 Measures of Scale<br>1.3.5.17 Detection of Outliers ("Z-Scores and Modified Z-Scores")<br>5.1.2 (합성 분산)<br>"Median absolute deviation" | https://www.itl.nist.gov/div898/handbook/eda/section3/eda356.htm<br>https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm<br>https://www.bipm.org/documents/20126/2071204/JCGM_100_2008_E.pdf<br>https://en.wikipedia.org/wiki/Median_absolute_deviation | 1.3.5.6: MAD = median(\|Y_i − Ỹ\|) 정의, 극단값 영향이 적음<br>1.3.5.17: 수정 Z = 0.6745(x_i − x̃)/MAD (Iglewicz & Hoaglin). 0.6745 = Φ⁻¹(0.75), 역수 1.4826 (계산 확인: 1/0.67449 = 1.4826)<br>GUM 5.1.2: 독립 두 값 차이의 분산 = 합 → 같은 σ면 2σ², 그래서 /√2 | 확인. 단 SOP·README의 "1.3.5.6 (1.4826 상수)" 표기는 위치가 틀림. 1.3.5.6에는 1.4826이 없음 → 1.3.5.17로 고쳐야 함 |
| 3 | σ_run: Var(회차 중앙값 이동) − (π/2)σ_r²/n | ① | NIST e-Handbook<br>NIST e-Handbook<br>JCGM 200:2012 (VIM)<br>ISO 5725-3<br>Wikipedia "Median" (2차, Maindonald & Braun 2010 p.104 인용) | 2.4.4 Analysis of variability (3단 nested: Level 1 repeatability, Level 2 day-to-day, Level 3 run-to-run)<br>2.4 Gauge R & R studies, 2.6.1 Gauge study of resistivity probes<br>2.20, 2.21 (repeatability), 2.22, 2.23 (intermediate precision)<br>ISO 5725-3:2023 (1994판은 폐지) — 본문 미열람, 표준 소개 페이지만 확인<br>Efficiency 절 | https://www.itl.nist.gov/div898/handbook/mpc/section4/mpc44.htm<br>https://www.itl.nist.gov/div898/handbook/mpc/section4/mpc4.htm<br>https://www.itl.nist.gov/div898/handbook/mpc/section6/mpc61.htm<br>https://www.bipm.org/documents/20126/2071204/JCGM_200_2012.pdf<br>https://www.iso.org/standard/69420.html<br>https://en.wikipedia.org/wiki/Median | NIST 2.4.4: 회차 평균의 표준편차(level-3)를 따로 구하고, 1회 측정 불확도 s_R = √(s3² + (K−1)/K·s2² + (J−1)/J·s1²)로 반복성 몫을 보정<br>VIM 2.21: 반복성 = 반복성 조건의 정밀도. 2.22 NOTE 1: 중간 정밀도 조건은 새 교정·작업자·측정 시스템 변경 포함<br>Median: 중앙값 분산 ≈ (π/2)σ²/n | 부분. 회차 성분 분리 개념은 NIST 2.4.4로 확인. 평균 대신 중앙값을 쓰고 (π/2)/n로 반복성 몫을 빼는 식은 SOP 고유 변형(근사) |
| 4 | 분해능 항 Δx/√12 | ② | JCGM 100:2008 (GUM)<br>NIST e-Handbook | F.2.2.1 The resolution of a digital indication<br>4.3.7 (식 6, 7)<br>2.5.4 Type B evaluations ("Lack of resolution of the instrument") | https://www.bipm.org/documents/20126/2071204/JCGM_100_2008_E.pdf<br>https://www.itl.nist.gov/div898/handbook/mpc/section5/mpc54.htm | F.2.2.1: 반복 지시값이 모두 같아도 반복성 불확도는 0이 아님. 분해능 δx면 직사각형 분포, u² = (δx)²/12, u = 0.29δx<br>4.3.7: 폭 a₊ − a₋의 균일분포 분산 = (a₊ − a₋)²/12 | 확인. "데이터 분해능 = 고유값 간 최소 간격"으로 δx를 정하는 방법은 내부 근사 |
| 5 | LoQ = 10σ, LoD = 3.29σ | ② | Eurachem Guide "Fitness for Purpose of Analytical Methods" 2판 (2014)<br>Eurachem (같은 문서)<br>ICH Q2(R2) (2023)<br>ICH Q2(R1)<br>EPA MARLAP Manual Vol. III | 6.2.4 Estimating LOQ, Quick Reference 3<br>Annex B Statistical basis of limit of detection calculations<br>3.2.3.3 Based on the Standard Deviation of a Linear Response and a Slope (QL = 10σ/S)<br>7.3 (QL = 10σ/S), 7.2 (S/N 10:1)<br>20.2.7, 20.4.3 Minimum Quantifiable Concentration | https://www.eurachem.org/images/stories/Guides/pdf/MV_guide_2nd_ed_EN.pdf<br>https://database.ich.org/sites/default/files/ICH_Q2%28R2%29_Guideline_2023_1130.pdf<br>https://database.ich.org/sites/default/files/Q2%28R1%29%20Guideline.pdf<br>https://www.epa.gov/sites/default/files/2015-05/documents/402-b-04-001c-20_final.pdf | Eurachem 6.2.4: "The IUPAC default value for kQ is 10", σ가 낮은 농도에서 거의 일정하면 RSD 10%에 해당<br>Eurachem Annex B: α = β = 0.05면 LOD 계수 1.65 + 1.65 = 3.30<br>ICH: QL = 10σ/S, σ는 blank 응답 표준편차 등으로 추정<br>MARLAP 20.2.7: 정량한계 = 지정한 RSD(보통 10%)가 되는 농도, IUPAC(1995)를 따름 | 확인 (2차 문헌으로). Currie 1968·IUPAC 1995 원문은 미열람(4절). NIST e-Handbook에서는 LoQ 10σ 항목을 찾지 못함. σ = max(4개 후보) 구성은 내부 설계 |
| 6 | blank 항 σ_blank, LoQ_blank = \|평균\| + 10·SD | ② | ICH Q2(R2)<br>ICH Q2(R1)<br>Eurachem 2014 | 3.2.3.3 "Based on the Standard Deviation of the Blank"<br>7.3.1 Based on Standard Deviation of the Blank<br>Quick Reference 2 NOTES 3, Quick Reference 3 | 위 5번 URL과 같음 | ICH: blank 시료를 적절한 수만큼 재서 응답의 표준편차로 σ 추정<br>Eurachem QR2 NOTE 3: 신호 영역이면 LOD = blank 평균 신호 + 3s<br>Eurachem QR3: LOQ = kQ × s₀ (보통 10) | 부분. blank SD로 σ를 잡는 것은 확인. "\|평균\| + 10·SD"는 Eurachem의 신호 영역 LOD 식(평균 + 3s)을 LoQ로 옮긴 내부 확장. CALCVAL 환산 조건은 내부 규칙 |
| 7 | 최소 die 10개 (MIN_DIE = 10) | 개요 'die 수 확인', ⓪ | 출처 없음 (코드 por_doe_compare.py:38) | — | — | 부호검정 90% 구간은 n ≥ 5부터 만들 수 있음(n = 5: [d(1), d(5)] 포함 93.75%, n = 4: 87.5%로 부족). n = 10이면 구간 [d(2), d(9)], 실제 포함 확률 97.9% (계산 확인). 10이라는 값을 정한 문헌은 찾지 못함 | 근거 없음-내부 기준 |
| 8 | 이상치 die: \|d − median(d)\| > 5·robustσ, 세기만 하고 빼지 않음 | 개요, 참고 지표 | NIST e-Handbook<br>FDA "Statistical Approaches to Establishing Bioequivalence" (2001) | 1.3.5.17 Detection of Outliers<br>VII.C Outlier Considerations | https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm<br>https://www.gmp-compliance.org/files/guidemgr/3616fnl.pdf | NIST: MAD 기반 수정 Z가 \|M\| > 3.5면 잠재 이상치로 표시 (Iglewicz & Hoaglin)<br>FDA: "deletion of outlier values is generally discouraged" | 부분. MAD 기반 표시와 "빼지 않음"은 확인. 기준 5는 NIST 권고 3.5보다 느슨한 내부 기준 |
| 9 | 편향 b = median(d), 부호검정 90% 구간 [d(24), d(38)] (n = 61) | ③ | NIST Dataplot Reference Manual<br>NIST Dataplot Reference Manual<br>Hollander & Wolfe, Nonparametric Statistical Methods (2차: U. Minnesota Geyer 강의 페이지) | MEDIAN CONFIDENCE LIMITS (Method 1)<br>SIGN TEST<br>3장 예 3.5, 3.6 (부호검정과 중앙값 구간) | https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/mediancl.htm<br>https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/signtest.htm<br>https://www.stat.umn.edu/geyer/5601/examp/sign.html | Dataplot: W ~ Binomial(n, 0.5), γ_k = P(k ≤ W ≤ n − k), 구간 (X_k, X_{n−k+1})<br>Sign test: d_i = X_i − Y_i의 부호 개수가 Binomial(n, 0.5)<br>Geyer(H&W 예 3.6): 포함 확률 = 1 − 2·P(B ≤ k − 1)<br>계산 확인: n = 61, P(B ≤ 23) = 3.61%, P(B ≤ 24) = 6.19%, 구간 d(24)~d(38), 포함 확률 92.78% | 확인. 단 NIST e-Handbook 본문이 아니라 NIST Dataplot 매뉴얼. e-Handbook 본문에서는 중앙값 부호검정 구간 절을 찾지 못함. H&W 원서는 미열람 |
| 10a | Δ의 실용 한계 5%·\|Ref 중앙값\| | ④ | ASTM E2935-21 | 4.1.1 (Significance and Use) | https://store.astm.org/e2935-21.html | "equivalence limit ... is determined prior to the equivalence test and its value is usually set by consensus among subject-matter experts" | 근거 없음-내부 기준 (5%라는 값). ASTM은 "한계는 전문가 합의로 미리 정함"이라는 절차만 뒷받침 |
| 10b | Δ의 회차 예측 한계 t(0.95, J−1)·√(1 + 1/J)·σ_run | ④ | NIST Dataplot Reference Manual<br>NIST e-Handbook<br>Meeker, Hahn, Escobar, Statistical Intervals 2판 (Wiley 2017) | PREDICTION LIMITS (mean)<br>4.5.1.2 How can I predict the value and estimate the uncertainty of a single response?<br>4.7 Prediction Interval to Contain a Single Future Observation or the Mean of m Future Observations (목차만 확인) | https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/predlimi.htm<br>https://www.itl.nist.gov/div898/handbook/pmd/section5/pmd512.htm<br>https://www.oreilly.com/library/view/statistical-intervals-2nd/9780471687177/c04.xhtml | Dataplot: n개 표본으로 m개 새 관측 평균의 예측구간 x̄ ± t(α/2, n−1)·s·√(1/n + 1/m). n = J, m = 1이면 SOP 식과 같음. t(0.95)는 양쪽 90% 예측구간의 반폭<br>e-Handbook 4.5.1.2: 예측구간은 새 측정값의 불확도까지 포함해 신뢰구간보다 넓음 | 부분. 식은 확인. σ_run이 J개 값의 표본 SD가 아니라 보정·0 절단된 추정이라 자유도 J − 1은 근사. 5% 몫과 더하는 구성은 내부 설계 |
| 11 | 장비 정확도 한계 1.645·√((U_Ref² + U_Cand²)/3), A·V ITEM | ④ | JCGM 100:2008 (GUM)<br>NIST e-Handbook<br>Keysight P9001A 제품 페이지 | 4.3.7 (식 7: u² = a²/3), 5.1.2<br>2.5.4.1 Standard deviations from assumed distributions<br>제품 사양 요약 | https://www.bipm.org/documents/20126/2071204/JCGM_100_2008_E.pdf<br>https://www.itl.nist.gov/div898/handbook/mpc/section5/mpc541.htm<br>https://www.keysight.com/us/en/product/P9001A/massively-parallel-parametric-test-system.html | GUM 4.3.7, NIST 2.5.4.1: 끝점 ±a만 알면 균일분포 s = a/√3<br>GUM 5.1.2: 두 성분 합성<br>Keysight 페이지: 최소 전류 분해능 0.1 fA, 최소 전압 분해능 2 µV만 공개. 레인지별 정확도 표(Data sheet p.6-7, Programming Reference Table 2-19/2-22)는 공개 페이지에서 찾지 못함 | 부분. U/√3과 합성은 확인. 1.645는 차이가 정규분포라는 근사(아래 3절 D8). 장비 사양 숫자는 원본 미대조 |
| 12 | TOST, 90% 신뢰구간 ⊂ (−Δ, +Δ) | ⑤ | Schuirmann (1987) J. Pharmacokinet. Biopharm. 15:657-680<br>FDA (2001)<br>ASTM E2935-21 | 초록<br>IV (Average BE), VI.B.1.a Overview<br>1.1, 1.2 Scope | https://link.springer.com/article/10.1007/BF01068419<br>https://www.gmp-compliance.org/files/guidemgr/3616fnl.pdf<br>https://store.astm.org/e2935-21.html | Schuirmann: TOST는 (1 − 2α) 신뢰구간 방식과 같은 결론, α = 0.05<br>FDA VI.B.1.a: 90% 신뢰구간이 [−θ, θ] 안이면 동등, 정규이론 구간에서는 5% 한쪽 검정 2개와 같음 (Schuirmann 1987)<br>ASTM: 두 시험 공정·장비의 평균 동등성 평가에 적용 | 확인. 단 원문 동치는 정규이론(t) 구간 기준. 부호검정 구간에 적용하면 한쪽 수준이 3.6%(n = 61)로 보수적 |
| 13 | 3분 판정 동등 / 차이 / 미결 | ⑤ | 출처 없음 | — | — | "차이" = 구간 전체가 ±Δ 밖 → 한쪽 5% 검정으로 \|b\| > Δ를 보이는 것과 같은 논리적 귀결. 이 3분 체계를 정한 문헌은 찾지 못함. ASTM E2935 4.3은 소비자·생산자 위험만 다룸 | 근거 없음-내부 기준 (설계) |
| 14a | 표본 크기 n ≈ (1.25·(z0.95 + z0.90)·σ/(Δ − \|b\|))² | ⓪ | NCSS PASS "One-Sample Z-Tests for Equivalence" (Chow, Shao, Wang, Lokhnygina 2018 예 재현)<br>NIST e-Handbook | 517장 Example 2 "Validation using Chow, Shao, Wang, and Lokhnygina"<br>7.2.2.2 Sample sizes required | https://www.ncss.com/wp-content/themes/ncss/pdf/Procedures/PASS/One-Sample_Z-Tests_for_Equivalence.pdf<br>https://www.itl.nist.gov/div898/handbook/prc/section2/prc222.htm | NCSS: CSW(2018) pp.46-47 예, δ = 0.05, σ = 0.1, 진짜 차이 0, α = 0.05, 검정력 0.80 → n = 35. (1.645 + 1.282)²·(0.1/0.05)² = 34.3 → 35이므로 차이 0일 때 z_{1−β/2}를 씀<br>NIST 7.2.2.2: N = (z_{1−α} + z_{1−β})²(σ/δ)² 일반형 | 부분. 식 형태는 확인. z0.90의 뜻과 σ 선택이 원문과 어긋남(3절 D1, D2). CSW 원서는 미열람 |
| 14b | 1.25 = √(π/2), 중앙값 효율 2/π | ⓪ | Wikipedia "Efficiency (statistics)", "Median", "Sign test" (2차. 각각 Maindonald & Braun 2010 p.104, Conover 1999 인용) | Efficiency of the median 절, Sign test의 검정력 비교 절 | https://en.wikipedia.org/wiki/Efficiency_(statistics)<br>https://en.wikipedia.org/wiki/Median<br>https://en.wikipedia.org/wiki/Sign_test | 정규분포에서 중앙값 효율 2/π ≈ 0.64, 중앙값 표준오차는 평균의 (π/2)^½ ≈ 1.25배<br>부호검정의 대응 t검정 대비 ARE = 0.637<br>계산: √(π/2) = 1.2533, 1.25 사용 시 n 계수 1.5625 vs 1.5708 (0.5% 작음) | 부분 (2차 출처로만 확인. 1차 문헌 Hollander & Wolfe / Conover 원서 미열람) |
| 14c | J 선택: 흔들림 여유 ≤ 5% 몫, 구간 1.48% / 1.90% / 2.14%(또는 2.13%) | ⓪ | 출처 없음 | — | — | 계산 검증만 함: J=3 계수 3.3717 → 1.483%, J=4 2.6311 → 1.900%, J=5 2.3353 → 2.141%. "여유 ≤ 5% 몫" 규칙과 J=5에서 끊는 기준은 문헌 근거 없음 | 근거 없음-내부 기준 (Sec 제안, 정훈님 2026-11-18 22:57 KST 승인) |
| 15 | LoQ 미만은 "<LoQ"로 보고 (SOP 표기: "IUPAC 권고, Currie 1968") | ⑥ | EPA MARLAP Manual Vol. III (IUPAC 1995를 따른다고 명시) | 20.3 Recommendations | https://www.epa.gov/sites/default/files/2015-05/documents/402-b-04-001c-20_final.pdf | MARLAP: "report each measurement result and its uncertainty as obtained ... even if the result is less than zero. The laboratory should never report a result as less than MDC." → 검출한계 기준 절단 보고에 반대. LoQ 미만 절단 보고를 권하는 IUPAC 문장은 찾지 못함(원문 미열람) | 근거 없음-내부 기준. "IUPAC 권고" 표기는 확인 불가, 반대 방향 권고가 있음 |
| 16 | 참고 지표 t-test (판정에 안 씀) | 결과 읽는 법, 참고 지표 | NIST e-Handbook | 7.3.1.1 Analysis of paired observations | https://www.itl.nist.gov/div898/handbook/prc/section3/prc311.htm | 대응 차이의 평균·표준편차로 t 검정 | 확인 |
| 17 | 측정 정밀도 σ_meas = √(σ_die²+σ_run²), 측정 정밀도(%) = 100σ_meas/\|중앙값\| | 개념 σ_die와 σ_run (측정 정밀도) | JCGM 100:2008 (GUM)<br>JCGM 200:2012 (VIM)<br>NIST/SEMATECH e-Handbook<br>NIST/SEMATECH e-Handbook<br>NIST/SEMATECH e-Handbook | 5.1.2 식(10), 5.1.5<br>2.15 NOTE 1, 2.20/2.21, 2.22/2.23, 2.24/2.25<br>2.1.1.4<br>2.4.3.1 Simple design<br>1.3.6.6.1 Normal Distribution (표 "Coefficient of Variation σ/μ") | https://www.bipm.org/documents/20126/2071204/JCGM_100_2008_E.pdf<br>https://www.bipm.org/documents/20126/2071204/JCGM_200_2012.pdf<br>https://www.itl.nist.gov/div898/handbook/mpc/section1/mpc114.htm<br>https://www.itl.nist.gov/div898/handbook/mpc/section4/mpc431.htm<br>https://www.itl.nist.gov/div898/handbook/eda/section3/eda3661.htm | GUM 5.1.2: 합성 분산 = 각 분산의 합(무상관 입력), 5.1.5: 계수 ±1일 때 u_c² = Σu²<br>VIM 2.15 NOTE 1: "usually expressed numerically by measures of imprecision, such as standard deviation, variance, or coefficient of variation"<br>NIST 2.1.1.4: "Good precision implies a small standard deviation."<br>NIST 2.4.3.1: s_R = √(s_days² + s_1²)<br>NIST 1.3.6.6.1: Coefficient of Variation σ/μ | 확인. 회차(run)를 σ_run으로 보는 것을 VIM 중간 정밀도 조건에 대응시킨 것은 이 문서의 해석 |

## 2. 집계

- 확인 7건: 1, 2, 4, 5, 9, 12, 16 (2는 인용 위치 수정 필요)
- 부분 7건: 3, 6, 8, 10b, 11, 14a, 14b
- 근거 없음-내부 기준 5건: 7, 10a, 13, 14c, 15

## 3. SOP 식·표기와 원문이 어긋나는 곳

- D1 (⓪, 큼) z0.90의 뜻
  - SOP: "z0.90은 실제로 같을 때 '동등'으로 나올 확률 90%"
  - 원문(CSW 2018 예, NCSS 517장): 진짜 차이 0이면 z_{1−β/2}를 씀. z0.90 = z_{1−0.20/2} → 검정력 80%
  - 계산: SOP 식대로 n을 잡고 b = 0이면 검정력 2Φ(1.282) − 1 = 80.0%
  - 고치는 방법 둘 중 하나: (가) 90% 목표면 z0.95(1.645)로 바꿈 → 예시 14개 → 17개, 54개 → 68개 (나) 식은 두고 설명을 "검정력 80%"로 고침
- D2 (⓪, 큼) 표본 크기 식의 σ
  - SOP: σ_die(1회 측정 반복성)를 씀
  - d = Cand − Ref 3회 평균이라 die별 d의 반복성 SD = σ_die·√(1 + 1/J) (GUM 5.1.2 분산 합성, J = 3이면 ×1.155, n ×4/3)
  - D1까지 같이 고치면 예시 14개 → 23개, 54개 → 91개
  - 이 항목은 문헌 인용이 아니라 분산 계산에서 나온 지적
- D3 (⓪) J = 5 상한
  - 2.14%는 반올림 계수 2.34로 5.008%(5% 초과), 정확한 계수 2.3353으로 4.998%. 정확한 경계 2.141%
  - 2.13%로 내리면 두 계수 모두 5% 이내. 정훈님께는 2.13%로 이미 안내함
- D4 (⓪) "2.14% 넘으면 반복을 늘려도 소용없음" 취지의 설명
  - 계산: J = 6 → 2.30%, J = 8 → 2.49%, J = 10 → 2.60%, J → ∞ → 3.04%
  - 반복으로 더 넓힐 수는 있음. J = 5에서 끊고 점검으로 넘기는 것은 비용 기준의 내부 선택으로 표기해야 함
- D5 (①, README) MAD 상수 위치
  - SOP: "NIST e-Handbook 1.3.5.6 (1.4826 = ...)"
  - 1.3.5.6은 MAD 정의만 있고 1.4826이 없음. 상수는 1.3.5.17의 0.6745(= 1/1.4826)
- D6 (⑥) "<LoQ 보고: IUPAC 권고, Currie 1968"
  - 원문 확인 불가. MARLAP 20.3(IUPAC 1995를 따름)은 결과를 있는 그대로 보고하고 "< MDC"로 보고하지 말라고 함
  - "내부 보고 규칙"으로 표기를 바꾸거나 IUPAC 원문 해당 문장을 확보해야 함
- D7 (①) ISO 5725-3 연도 미표기
  - 1994판은 폐지, 현행 2023판. 연도를 적어야 함
- D8 (④, 작음) 장비 정확도 한계의 1.645
  - 두 균일분포 차이는 정규가 아님. U가 같으면 삼각분포이고 정확한 90% 양쪽 경계는 1.368·U, SOP 식은 1.343·U (약 1.8% 작음)
  - 실무 영향은 작음. "정규 근사"라고 적으면 됨
- D9 (⑤, 작음) TOST ⇔ 90% CI 동치
  - FDA 2001은 정규이론 구간에서의 동치로 설명. 부호검정 구간(포함 92.8%)에서는 한쪽 수준 3.6%로 보수적
  - "부호검정 구간에 적용, 보수적"이라고 적으면 됨
- D10 (②) LoQ의 σ에 σ_run이 빠짐
  - IUPAC·MARLAP의 정량한계는 그 수준에서 "결과 1개의 SD"로 정의하고, MARLAP 20.3은 "all sources of variance"를 넣으라고 함
  - SOP는 σ_r(반복성)만 씀 → 회차 간 흔들림이 크면 LoQ가 작게 잡힘. 의도된 선택이면 그렇다고 적어야 함
- D11 (④) 회차 예측 한계의 자유도
  - σ_run은 회차 중앙값 분산에서 반복성 몫을 빼고 0에서 자른 값이라 t(J − 1)은 근사
- D12 (④) "Hahn & Meeker, Statistical Intervals" 표기
  - 현행 2판(2017)은 Meeker, Hahn, Escobar 공저. 해당 절은 4.7

## 4. 원문을 열지 못한 문헌 (상태 판단에 쓰지 않음)

- Currie, L.A. (1968) Anal. Chem. 40, 586 — ACS 유료. MARLAP 20장, Eurachem Annex B가 인용하는 것만 확인
- Currie, L.A. (1995) IUPAC Recommendations, Pure Appl. Chem. 67, 1699 — iupac.org PDF가 봇 차단(403, Cloudflare). 검색 결과에 "LQ = kQ·σQ, RSD 보통 10%" 문구가 보였지만 원문을 열지 못해 근거로 쓰지 않음
- ISO 11843, ISO 5725-3 본문 — 유료. iso.org 소개 페이지만 확인(5725-3:2023)
- Hollander & Wolfe 원서 — Geyer 강의 페이지의 예 3.5·3.6 재현으로만 확인
- Chow, Shao, Wang (Lokhnygina) 원서 — NCSS PASS 문서의 재현 예로만 확인
- Keysight P9001A Data sheet p.6-7, Programming Reference Table 2-19/2-22 — 공개 위치를 찾지 못함
- Julious (2004) — 열지 않음

## 5. 계산 검증 (scipy로 직접 계산)

- t(0.95, J−1)·√(1 + 1/J): J=2 7.7327, J=3 3.3717, J=4 2.6311, J=5 2.3353, J=6 2.1765, J=10 1.9226
- 5% ÷ 계수: J=3 1.483%, J=4 1.900%, J=5 2.141%, J=6 2.297%, J=10 2.601%, J=∞ 3.040%
- 부호검정 구간: n = 61 → d(24)~d(38), 92.78%. n = 10 → d(2)~d(9), 97.85%
- 1/Φ⁻¹(0.75) = 1.4826, 2/π = 0.6366, √(π/2) = 1.2533
- n 예시(SOP 식 그대로): (Δ − \|b\|) = σ → 13.38(14개), 0.5σ → 53.52(54개). SOP 숫자와 일치
