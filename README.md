# dc-infra-compare

같은 웨이퍼, 같은 die를 POR(기존 프로그램)로 여러 번, DOE(새 프로그램)로 한 번 잰 DCNORMAL 결과를 ITEM별로 비교해서 **동등 / 차이 / 미결**로 판정합니다. 통계를 낼 수 없는 ITEM은 **판정 제외**입니다.

원칙은 하나입니다. **DOE와 POR의 차이가, POR을 자기 자신과 다시 잰 차이보다 크지 않으면 같다고 본다.**

판정 흐름과 기법별 수식, 시각화는 [`docs/method.html`](docs/method.html)에 있습니다. GitHub 화면에서는 소스만 보이니, 내려받아 브라우저로 여세요.

## 설치

```bash
pip install -r requirements.txt   # Python 3.9+, pandas, numpy, scipy
```

## 실행

### run_all.py로 한 번에

판정 → 요약 → Fail 근거 → 판정 요약 그림을 차례로 돌리고, 모든 산출물을 `--out` 폴더 하나에 모읍니다. 입력 옵션은 `por_doe_compare.py`와 같습니다(아래 표). 각 도구는 실행을 시작할 때 같은 --out 폴더에서 자기가 만드는 그림·표 파일만 지우고 다시 만듭니다(다른 파일은 그대로).

```bash
python run_all.py --por POR1/ --por POR2/ --por POR3/ --doe DOE/ \
  --level item_info.csv --out 결과
```

- `--before 이전결과/items.csv`: 기존·개선 비교(`compare_before_after.py compare`)를 추가해 `결과/compare/`에 둡니다.
- `--groups groups.csv`: ITEM,그룹 두 열 파일입니다. 그룹마다 대시보드 `결과/plots/summary_group_<이름>.png`를 그립니다. `--before`도 함께 주면 그룹별 비교 요약(`group_summary.py`)을 추가해 `결과/groups/`에 둡니다.

어느 단계든 실패하면 `[실패] 단계 N/M <이름>: <명령>`, `rc=…`, 그 단계 오류 끝 20줄을 보여 주고 멈춥니다. 출력 형태 예시(실제 실행값이 아님):

```text
[단계 1/4] por_doe_compare
[단계 2/4] summarize
[단계 3/4] fail_evidence
[단계 4/4] plot_verdicts

생성 파일
items.csv  ITEM별 판정·상태
…
```

끝에 보이는 "생성 파일" 목록은 아래 표의 파일 중 실제로 생긴 것입니다.

### 출력 폴더 구조

경로는 `--out`(예: `결과/`) 기준입니다. 지표 그림 6장은 `sigma_die_ratio.png`, `sigma_run_ratio.png`, `meas_precision_ratio.png`, `stability_sigma_die_pct.png`, `stability_meas_precision_pct.png`, `verdict_center_delta.png`입니다(`compare_metrics.METRICS`).

| 경로 | 파일 | 만드는 도구·옵션 |
|---|---|---|
| `./` | `items.csv`(ITEM별 판정·상태), `outlier_dies.csv`(튀는 die) | `por_doe_compare.py` (항상) |
| `./` | `summary_items.txt`(summarize 출력) | `summarize.py` (항상) |
| `fail_evidence/` | `fail_evidence.csv`(Fail 근거), `forest.png`(전체 그림) 등 | `fail_evidence.py` (항상) |
| `plots/` | `summary.png`, `summary_loq.png`(판정 요약 그림) | `plot_verdicts.py` (항상) |
| `plots/` | `summary_group_<이름>.png`(그룹 수만큼) | `plot_verdicts.py`, `--groups` |
| `compare/` | `compare.csv`, `summary.txt`, `stability_overall.csv`, `worst_items.csv`, 지표 그림 6장 | `compare_before_after.py compare`, `--before` (`--groups` 없어도 생김) |
| `groups/` | `group_summary.csv`, `verdict_by_group.csv`, `stability_by_group.csv`, `group_dirs.csv`, 지표 그림 6장(그룹 비교) | `group_summary.py`, `--before`와 `--groups` 둘 다 |
| `groups/<그룹>/` | 지표 그림 6장(그 그룹만) | `group_summary.py`, `--before`와 `--groups` 둘 다 |

모든 ITEM을 장으로 나눈 `summary_001.png …`는 `plot_verdicts.py --full`로 따로 돌릴 때만 생깁니다. `compare/`·`groups/` 파일 설명은 아래 [기존·개선 비교](#기존개선-비교-compare_before_afterpy)와 [그룹별 요약](#그룹별-요약-group_summarypy)에 있습니다.

환경변수 `RUN_ALL_FAIL_STEP=<단계 이름>`은 테스트용입니다(그 단계를 일부러 실패시킴).

단계별로 따로 돌리려면:

```bash
python por_doe_compare.py --por POR1/ --por POR2/ --por POR3/ --doe DOE/ \
  --level item_info.csv --blank blank.csv --blank-map blank_map.csv --out 결과
python summarize.py 결과/items.csv
```

| 옵션 | 내용 |
|---|---|
| `--por` | POR 1회분 (파일이나 폴더). **회차마다 따로** 씁니다. 2회 이상, 권장 3회 이상(매번 재터치다운) |
| `--doe` | DOE 1회분 |
| `--r` | 허용폭의 정책 몫. 기본 0.05 (POR 값의 5%) |
| `--level` | ITEM 정보 표 (선택, 아래). 장비 분해능·정확도와 blank 환산에 씀 |
| `--blank`, `--blank-map` | blank 데이터와 연결표 (선택, 아래). LoQ 하한으로만 씀 |
| `--key` | 짝짓기 키. 기본 `WAFERID,COORD_X_Y,ITEM` |
| `--encoding` | 기본 `auto` (UTF-8, 안 되면 CP949) |

UNIT, SPECLOW, SPECHIGH 열은 판정에 쓰지 않습니다(값이 잘못 들어간 경우가 많음). 판정은 모두 비율 기준이라 단위나 정규화 계수가 무엇이든 결과가 같습니다.

## 판정 방법

**1. 흔들림 (POR 회차 반복).** NIST e-Handbook 2.4.4의 die·회차 분리를 튀는 die에 강한 robust 통계로 합니다.

| 값 | 뜻 |
|---|---|
| `sigma_die` | 같은 die를 다시 잰 1회 측정 흔들림. 이웃 회차 차이(2−1, 3−2)를 회차쌍마다 중앙값으로 맞춘 뒤 robust σ(1.4826 × MAD) / √2 |
| `sigma_run` | 회차마다 전체가 같이 움직이는 크기(컨택, 온도 등). 회차별 중앙값으로 구함 |

**2. LoQ (Currie, IUPAC).** LoD = 3.29σ, LoQ = 10σ. σ는 아래 중 가장 큰 값입니다(`limit_source` 열).
- `sigma_die` (POR 반복)
- 데이터 분해능 / √12: 값 사이의 가장 작은 간격. 계단값 항목 대비 (GUM F.2.2.1)
- 장비 분해능 / √12: `--level`이 있을 때
- blank: `--blank`가 있고 변형이 아니며 CALCVAL이 있을 때

**3. 판정.** die별 d = DOE − POR 회차 평균. shift = d의 **중앙값**, 90% 신뢰구간 = **부호검정**(순서통계량, 분포 가정 없음, Hollander & Wolfe). 튀는 die의 개수만 영향을 주고 크기는 영향이 없어서, die의 40% 가까이가 튀어도 버팁니다.

허용폭 Δ = r × |POR 중앙값| + t(0.95, J−1) × √(1 + 1/J) × `sigma_run`

- 뒤쪽은 DOE 1회가 POR J회 평균에서 **같은 프로그램 안에서도** 벗어날 수 있는 폭입니다(90% 예측구간 한쪽). `sigma_run`을 회차 J개로 추정하므로 t를 씁니다(J = 3이면 2.92, 5면 2.13).
- `--level`의 A, V ITEM은 장비 정확도로 구한 폭이 더 크면 그쪽을 씁니다(`delta_source`).
- log 판정(`verdict_log`, 아래 [log 판정](#log-판정-verdict_log))의 허용폭은 Δ_log = log10(1 + r) + `sigma_rep_log`입니다. t(0.95, J−1) × √(1 + 1/J) 배수는 없습니다.
  - `sigma_rep_log` = die마다 L(= log10\|값\|) 회차값의 표준편차(ddof=1)를 구하고, 그 die 중앙값. 유효한 회차값이 2개 미만인 die는 뺍니다.
  - `sigma_run_log`(L에서 구한 회차 이동)는 분석용이며 판정에 쓰지 않습니다.
- Open 코드 값(예: 1E+97처럼 측정 대신 찍힌 큰 숫자) 처리: 미결(처리 방식 정해지지 않음). 판정 값 '미결'과는 다른 뜻입니다.

| 구간 (\|POR 중앙값\|) | 판정 |
|---|---|
| 정량 (≥ LoQ) | 신뢰구간이 ±Δ 안 → **동등**, 통째로 밖 → **차이**, 걸침 → **미결** (반폭 ≥ Δ면 해상도 부족, 아니면 경계) |
| LoQ 미만 | LoQ 미만 값은 "<LoQ"로 보고합니다(IUPAC). 신뢰구간이 통째로 ±Δ 밖이고 **DOE 중심(POR 중앙값 + shift)이 LoQ 이상**이라 보고가 달라질 때만 **차이**, 그 밖은 **동등**("<LoQ 보고 일치") |

**판정 제외**는 통계를 낼 수 없어 판정하지 않은 ITEM입니다. 아래 1~3을 모두 보고, 맞는 원인을 모두 이 순서대로 `; `로 이어 `reason`에 적습니다. `판정 제외: `는 첫 원인 앞에만 붙습니다. 예: `판정 제외: die 산포 0 (σ_die=0); 고정값 (중앙값 0·σ_run 0)`.

1. center·ci_low·ci_high 중 하나가 NaN이나 inf → `판정 제외: 중심·신뢰구간 계산 불가 (…)`
2. die 산포 0: `sigma_die` = 0이면 `판정 제외: die 산포 0 (σ_die=0)`, 아니고 고정값 비율(R·z 최빈 비율 중 큰 쪽)이 50%를 넘으면 `판정 제외: die 산포 0 (고정값 NN%)`. 즉 `status`가 `산포 0`인 ITEM은 판정 제외입니다.
3. POR 중앙값이 0이고 `sigma_run` = 0 → `판정 제외: 고정값 (중앙값 0·σ_run 0)`
4. 그 밖은 zone 판정을 합니다. LoQ 미만은 Δ와 무관하게 판정합니다.
5. 정량 zone은 장비 정확도 대체 후 최종 Δ가 0 이하이거나 NaN일 때만 `판정 제외: 최종 Δ가 0 이하이거나 유효하지 않음 (Δ=…, 출처 …)`입니다.

고정값 비율이 50% 이하면 판정은 그대로 합니다. die 수 부족(MIN_DIE)은 그대로 **미결**입니다.

**4. 참고 (판정에 쓰지 않음).** t-test(NIST 7.3.1.1), POR 회차끼리 t-test(`por_ttest_sig`), 튀는 die(\|d − 중앙값\| > 5 robust σ, `n_outlier_die`).

## ITEM 정보 표 (`--level`, 선택)

```
ITEM,LEVEL,CALCVAL,DERIVED
IOFF_N1,10fA,1e12,N     ← 원측정값 10~100 fA, 파일 값 = 원측정값 × 1e12 (pA로 찍힘)
ION_N1,100nA,,N         ← CALCVAL 모름
VT_N1,,,Y               ← 변형 값 (여러 측정 조합·추출: Vt 추출, 저항 = V / I, 비율 등)
```

| 열 | 뜻 |
|---|---|
| LEVEL | 원측정값 \|값\|의 자릿수 아래 끝. 10fA = 10~100 fA, 1nA = 1~10 nA. 1fA … 100mA, 1uV … 1V (A, V는 장비 사양 적용), fF, pF, kHz, MHz (기록만) |
| CALCVAL | 파일 값 = 원측정값 × CALCVAL (단위 환산, 정규화, 부호 포함). 모르면 비움 |
| DERIVED | Y = 변형 값. 장비 사양과 blank를 쓰지 않음 (LEVEL 비워도 됨) |

| 경우 | 장비 분해능·정확도 | blank |
|---|---|---|
| 변형 | 안 씀 | 안 씀 |
| 변형 아님 + CALCVAL 있음 | 원측정값 = 파일 값 / \|CALCVAL\|로 정확히 환산 | × \|CALCVAL\| 해서 씀 |
| 변형 아님 + CALCVAL 없음 | 자릿수 상한 10L로 보수적 환산 | 안 씀 |

- 장비 사양: Keysight P9001A Per-pin SMU (P9001 Data sheet p.6-7, Programming Reference Table 2-19/2-22). auto range는 값이 들어가는 가장 작은 range입니다. 표는 `por_doe_compare.py`의 `I_RANGES`, `V_RANGES`. 원본과 대조해서 쓰세요.
- 장비 정확도 허용폭: 두 측정이 각자 사양 정확도 ±(a × \|값\| + b × range + c) 안일 때 생길 수 있는 차이 1.645 × √((U_POR² + U_DOE²) / 3) (균일분포, GUM 4.3.7). 사양의 Vo, Rres × Io 항은 0으로 둡니다.
- `level_check`: CALCVAL로 환산한 원측정값이 LEVEL 자릿수와 다르면 "불일치". 자릿수 경계는 1.15배까지 일치로 봅니다. CALCVAL이 맞으면 판정에는 영향이 없습니다.

## blank 넣기 (`--blank`, `--blank-map`, 선택)

blank는 원측정값(A, V 기본 단위)이어야 합니다. 가로형 CSV가 가장 쉽습니다. 맨 윗줄에 blank 조건 이름을 쓰고, 그 아래에 측정값을 측정 순서대로 붙입니다.

```
OPEN_I_1PA,OPEN_I_10PA,SHORT_V
1.2e-12,3.1e-12,0.00012
-0.8e-12,-1.5e-12,-0.00008
```

제품 ITEM과 이름이 다르면 연결표를 만듭니다. 같은 측정 종류, 같은 range끼리 연결합니다.

```
ITEM,BLANK_ITEM
IOFF_N1,OPEN_I_1PA
VT_N1,SHORT_V
```

그 밖에 DCNORMAL blank 파일·폴더, CSV `ITEM,VALUE`, CSV `ITEM,SIGMA0`도 읽습니다. blank 측정 구성은 전류와 용량은 open, 전압은 short입니다. blank LoQ = \|평균\| + 10 × 표준편차를 CALCVAL로 ITEM 단위로 바꿔, POR 반복 LoQ보다 크면 그쪽을 씁니다(`blank_status`).

## 결과

| 파일 | 내용 |
|---|---|
| `items.csv` | ITEM별 판정. 차이, 미결, 동등, 판정 제외 순 |
| `outlier_dies.csv` | ITEM마다 튀는 die와 POR 회차별, DOE 값 |
| `summary.txt` | `summarize.py`가 만드는 공유용 요약 (ITEM 이름 대신 익명 번호) |
| `item_map.csv` | 익명 번호 ↔ ITEM. 공유하지 마세요. `items.csv`에도 `ID` 열이 들어갑니다. 번호는 ITEM 이름 순서로 매겨서 실행마다 같습니다 |

`items.csv` 주요 열

| 열 | 내용 |
|---|---|
| `zone`, `verdict`, `reason` | 구간, 판정, 사유 |
| `por_median`, `POR1_mean` …, `DOE_mean` | POR 값, 회차별 평균 |
| `center`, `ci_low`, `ci_high`, `rel_shift` | shift와 90% 신뢰구간, POR 대비 비율 |
| `delta`, `policy_margin`, `run_margin`, `delta_source` | 허용폭과 그 구성 |
| `sigma_die`, `sigma_run`, `LoQ`, `LoD`, `limit_source` | 흔들림과 LoQ |
| `doe_center` | LoQ 미만: DOE 중심 |
| `n_outlier_die`, `ttest`, `ttest_p`, `por_ttest_sig` | 참고 지표 |
| `spec_status`, `level_check`, `range_por`, `range_doe`, `spec_resolution`, `accuracy_margin`, `verdict_no_accuracy` | `--level` 관련 |
| `blank_item`, `blank_status`, `blank_LoQ_item`, `verdict_no_blank` | `--blank` 관련 |
| `status` | 데이터 상태 (아래). 끝에서 서른두째 열 |
| `por_gap_over_delta`, `por_gap_over_noise` | 조건 불안정 근거 값 (아래). 끝에서 서른한째~서른째 열 |
| `run_jitter_pct`, `run_jitter_over_delta`, `spearman_size_jitter` | 회차 흔들림·작을수록/클수록 흔들림 근거 값 (아래). 끝에서 스물아홉째~스물일곱째 열 |
| `resolution_step`, `resolution_over_delta`, `fixed_share` | 분해능 부족·산포 0 근거 값 (아래). 끝에서 스물여섯째~스물넷째 열 |
| `decades`, `skew_lin`, `skew_log`, `log_fit`, `bimodality_log` | 분포 모양 (log 후보·두 덩어리 근거, 아래). 끝에서 스물셋째~열아홉째 열 |
| `mean_median_ratio` | 평균−중앙값 치우침 (아래). 끝에서 열여덟째 열 |
| `sigma_meas` | 측정 산포 = √(`sigma_die`² + `sigma_run`²). 낮을수록 좋음 |
| `meas_precision_pct` | 측정 정밀도 (%, 상대표준편차, 낮을수록 좋음) = 100 × `sigma_meas` / \|`por_median`\|. `por_median`이 0이면 빈 칸 |
| `sigma_meas_over_delta` | `sigma_meas` / `delta`. 허용폭 대비 측정 산포. 낮을수록 좋음. `delta`가 0이면 빈 칸 |
| `verdict_log`, `center_log`, `ci_low_log`, `ci_high_log`, `delta_log`, `ci_half_over_delta`, `ci_half_over_delta_log`, `spearman_size_jitter_log`, `log_reason` | log 판정 (아래). 끝에서 열넷째~여섯째 열 |
| `sigma_die_log`, `sigma_run_log`, `below_linear_loq`, `policy_margin_log` | log 분석용 (판정에 안 씀, 아래). 끝에서 다섯째~둘째 열 |
| `sigma_rep_log` | log 판정 Δ_log의 회차 항 (아래). 맨 끝 열 |

`items.csv`의 마지막 서른두 열은 항상 `status`, `por_gap_over_delta`, `por_gap_over_noise`, `run_jitter_pct`, `run_jitter_over_delta`, `spearman_size_jitter`, `resolution_step`, `resolution_over_delta`, `fixed_share`, `decades`, `skew_lin`, `skew_log`, `log_fit`, `bimodality_log`, `mean_median_ratio`, `sigma_meas`, `meas_precision_pct`, `sigma_meas_over_delta`, `verdict_log`, `center_log`, `ci_low_log`, `ci_high_log`, `delta_log`, `ci_half_over_delta`, `ci_half_over_delta_log`, `spearman_size_jitter_log`, `log_reason`, `sigma_die_log`, `sigma_run_log`, `below_linear_loq`, `policy_margin_log`, `sigma_rep_log` 순서입니다(`por_doe_compare.py`의 `STATUS_COLS` + `PRECISION_COLS` + `LOG_COLS`). 마지막 열네 열이 `LOG_COLS`입니다.

### log 판정 (`verdict_log`)

`verdict_log`는 log형 ITEM의 판정입니다. 같은 판정을 L = log10\|값\| 공간에서 한 번 더 해서 `LOG_COLS`(마지막 열네 열)에 적습니다. 선형 `verdict`·`reason`은 그대로 둡니다.

- 대상: `status`와 무관하게 POR·DOE 값에 0이 없고 부호가 하나인 ITEM 전부입니다.
- POR·DOE 값에 0이 있거나 부호가 섞이면 log를 취할 수 없어 `verdict_log` = `판정 제외`, `log_reason`에 `0값 있음`, `부호 섞임` 중 맞는 것을 `; `로 잇고, `_log` 숫자 열은 빈 칸입니다(`ci_half_over_delta`, `below_linear_loq`는 선형 값이라 그대로 씁니다).
- 그 밖은 L = log10\|Y\|(POR), w = log10\|z\|(DOE)를 선형 판정과 같은 절차(중심·90% CI·zone·TOST)에 넣습니다. `log_reason`은 그 판정의 사유입니다.
- Δ_log = log10(1 + r) + `sigma_rep_log`. 정책 항은 선형의 r × \|POR\|가 log 공간에서 더하는 폭 log10(1 + r)입니다. 회차 항에는 t(0.95, J−1) × √(1 + 1/J) 배수가 없습니다.
- `sigma_rep_log` = die마다 L 회차값의 표준편차(ddof=1) → 그 die 중앙값. 유효한 회차값이 2개 미만인 die는 빼고, 남는 die가 없으면 빈 칸입니다.
- LoQ는 L에서 구한 값을 그대로 씁니다. blank LoQ, 장비 분해능, 장비 정확도는 원측정값 단위라 쓰지 않습니다.
- `ci_half_over_delta` = (`ci_high` − `ci_low`) / 2 / `delta`(선형), `ci_half_over_delta_log`는 같은 값을 log 판정으로 계산. Δ ≤ 0이나 NaN이면 빈 칸입니다. 두 값을 비교해 어느 공간에서 해상도가 나은지 봅니다.
- `spearman_size_jitter_log` = Spearman ρ(log10\|회차 평균\|, die별 L 회차 범위). `spearman_size_jitter`와 같은 계산이며, POR가 1회뿐이거나 유효 die < 3이면 빈 칸입니다.

분석용 열 (판정에 쓰지 않음)

- `sigma_die_log`, `sigma_run_log` = L에서 구한 σ_die, σ_run. `verdict_log`가 판정 제외면 빈 칸. `sigma_run_log`(웨이퍼 공통 회차 이동)는 Δ_log에 쓰지 않습니다.
- `below_linear_loq` = 선형 DOE 중심 \|`por_median` + `center`\| < 선형 `LoQ`이면 True. 모든 ITEM에 쓰고, LoQ나 중심이 NaN이면 빈 칸.
- `policy_margin_log` = log10(1 + r). log 판정이 된 ITEM만.

log 진단 대상(`is_log_target`: `fail_evidence.py`의 log 진단 그림, `log_compare.py`)은 판정 대상과 다릅니다. `status`에 `작을수록 흔들림`이나 `클수록 흔들림`이 있거나, `verdict`와 `verdict_log`가 둘 다 값이 있고 다른 ITEM입니다(`verdict_log`가 판정 제외면 다르다고 보지 않음).

`sigma_meas`를 제곱합의 제곱근으로 잡는 이유: die 간 산포와 회차 산포는 서로 독립이므로 분산이 더해집니다. 표준편차를 단순히 더하면 과대 추정이 됩니다.

주의: `status`가 `산포 0`이면 `sigma_die`가 0이라 `meas_precision_pct`가 0(또는 0에 가깝게)으로 나올 수 있습니다. 측정이 정밀하다는 뜻이 아니라 값이 고정되어 산포를 못 잰 것이니 좋은 값으로 읽지 마세요. 이런 ITEM은 판정 제외라 판정에는 쓰이지 않습니다.

`status`는 판정(동등/차이/미결/판정 제외)과 별개인 데이터 상태 열입니다. 판정 값은 바꾸지 않고, 이상 die를 빼고 다시 판정하지도 않습니다. 여러 개가 해당하면 아래 표 순서대로 `;`로 잇습니다. 하나도 없으면 `정상`. Δ는 그 ITEM의 최종 `delta`, R은 POR die별 회차 평균, z는 DOE die 값입니다.

| 열 값 | 조건 | 기준 상수 |
|---|---|---|
| `정상` | 아래 어느 것도 해당 없음 | |
| `조건 불안정` | 짝지은 회차 차 gap ≥ Δ 이고 gap ≥ 3·se (아래). se가 0이거나 유한하지 않으면 gap ≥ Δ만 봄. Δ ≤ 0이나 NaN이면 건너뜀 | `POR_GAP_NOISE_K` = 3 |
| `회차 흔들림` | `run_jitter_over_delta` ≥ 1. die가 회차마다 다 같이 움직이는 ITEM(short, mA급). Δ가 없으면 열만 쓰고 상태는 붙이지 않음 | `RUN_JITTER_OVER_DELTA` = 1.0 |
| `작을수록 흔들림` | `spearman_size_jitter` ≤ −0.5이고 유효 die ≥ 10 | `SIZE_JITTER_RHO` = −0.5, `SIZE_JITTER_MIN_DIE` = 10 |
| `클수록 흔들림` | `spearman_size_jitter` ≥ +0.5이고 유효 die ≥ 10. 값이 큰 die일수록 log 범위가 큼 | `SIZE_JITTER_RHO_POS` = 0.5, `SIZE_JITTER_MIN_DIE` = 10 |
| `분해능 부족` | `resolution_step` ≥ 0.1·Δ. 값이 1개뿐이거나 Δ ≤ 0·NaN이면 건너뜀 | |
| `산포 0` | sigma_die = 0, 또는 `fixed_share` > 50%. 이 ITEM은 판정 제외 | |
| `log 후보` | `decades` ≥ 2.0이고 `log_fit` > 0 | `LOG_DECADES_MIN` = 2.0 |
| `두 덩어리` | `bimodality_log` > 5/9(≈ 0.556)이고 R이 유한한 die ≥ 10 | `BIMODAL_BC_MIN` = 5/9, `BIMODAL_MIN_DIE` = 10 |
| `조건 설정 오류` | 예약 값. 판정할 입력이 없어 지금은 판정하지 않음 | |

상태 지표 열 8개(`METRIC_COLS`)는 `por_gap_over_delta`, `por_gap_over_noise`, `run_jitter_pct`, `run_jitter_over_delta`, `spearman_size_jitter`, `resolution_step`, `resolution_over_delta`, `fixed_share`입니다. 상태와 상관없이 계산할 수 있으면 채우고, 못 하면 빈 칸입니다.
- `resolution_step` = POR 전 회차·DOE 값의 서로 다른 값 사이 최소 간격, `resolution_over_delta` = `resolution_step` / Δ
- `fixed_share` = R과 z 각각에서 가장 흔한 값의 die 비율 중 큰 쪽 (판정 제외 '고정값 NN%'와 같은 값)

분포 모양 열 5개(`SHAPE_COLS`)는 R(POR die별 회차 평균, 유한한 값만)로 구합니다. R에 0이 있거나 부호가 섞이면 `skew_lin` 말고는 빈 칸입니다.
- `decades` = log10(max\|R\| / min\|R\|). 값이 몇 자릿수에 걸쳐 있는지
- `skew_lin` = R의 표본 왜도, `skew_log` = log10\|R\|의 표본 왜도 (보정식. die < 3이거나 값이 모두 같으면 빈 칸)
- `log_fit` = \|`skew_lin`\| − \|`skew_log`\|. 양수면 log 쪽이 더 대칭
- `bimodality_log` = log10\|R\|의 bimodality coefficient BC = (g² + 1) / (k + 3(n−1)² / ((n−2)(n−3))). g = 표본 왜도, k = 표본 초과 첨도. die < 4이거나 값이 모두 같으면 빈 칸. 균일분포의 BC가 5/9

`mean_median_ratio` = (mean(R) − median(R)) / |median(R)|. R은 POR die별 회차 평균. median(R) = 0이면 빈 칸. 분포가 한쪽으로 끌려간 정도를 보는 경고 근거로만 쓰고 판정에는 쓰지 않습니다.

`run_jitter_pct`, `run_jitter_over_delta`, `spearman_size_jitter`는 POR 회차만 씁니다(die × POR 회차). POR가 1회뿐이면 세 열 모두 빈 칸이고 두 상태도 건너뜁니다. 기준 상수는 `por_doe_compare.py` 맨 위에 있고, 실제 데이터로 나중에 맞춥니다.
- `run_jitter_pct` = 100 × 중앙값(die별 회차 범위 / \|회차 평균\|). 회차 범위 = max − min, 회차 평균이 0인 die는 뺌
- `run_jitter_over_delta` = 중앙값(die별 회차 범위) / Δ. Δ가 없거나 ≤ 0, NaN이면 빈 칸
- `spearman_size_jitter` = Spearman ρ(x, y). x = log10\|회차 평균\|, y = log10\|값\|의 회차 범위. 0값이 있는 die는 뺌. 유효 die < 3이거나 x, y 중 하나가 상수면 빈 칸. 상태와 상관없이 항상 씀

`por_gap_over_delta`, `por_gap_over_noise`는 조건 불안정의 근거 값입니다. Y는 POR 값(die × 회차)입니다. 각 die에서 그 die의 회차 평균을 먼저 빼므로 die 사이 차이는 지워집니다(짝지은 회차 차). POR가 1회뿐이거나 계산할 수 없으면 빈 칸이고, 상태와 상관없이 항상 씁니다.
- rr = 회차별 중앙값(Y − die별 회차 평균)
- gap = max(rr) − min(rr)
- se = 1.2533 × `sigma_die` × √2 / √n. n = die 수. 회차 중앙값 두 개의 차의 표준오차
- `por_gap_over_delta` = gap / Δ
- `por_gap_over_noise` = gap / se

예전 규칙은 (회차별 die 중앙값의 max − min)/Δ ≥ 1이었습니다. die 잡음만으로도 붙었습니다.

예 (조건 불안정): n = 25 die, `sigma_die` = 2, Δ = 1 → se = 1.2533 × 2 × 1.414 / 5 = 0.709, 3·se = 2.13.
- A: rr = (−0.6, +0.1, +0.5) → gap = 1.1. Δ 이상이지만 2.13 미만 → 상태 없음. `por_gap_over_delta` = 1.1, `por_gap_over_noise` = 1.55.
- B: rr = (−1.5, +0.2, +1.3) → gap = 2.8. Δ 이상이고 2.13 이상 → `조건 불안정`. `por_gap_over_delta` = 2.8, `por_gap_over_noise` = 3.95.

`examples/make_por3_data.py` 예제에서 조건 불안정은 예전 규칙으로 3 ITEM(VOS_OFFSET, IOFF_FLOOR, IOFF_LEAK), 새 규칙으로 0 ITEM입니다. IOFF_FLOOR는 gap/Δ 21.9지만 gap/se 0.85라 die 잡음입니다.

예 (회차 흔들림): die A 회차 10, 14, 6 → 범위 8, 평균 10 → 80%. die B 20, 26, 14 → 12, 20 → 60%. die C 5, 6, 4 → 2, 5 → 40%. `run_jitter_pct` = 중앙값(80, 60, 40) = 60%. 중앙값(범위) = 중앙값(8, 12, 2) = 8. Δ = 5면 `run_jitter_over_delta` = 8/5 = 1.6 ≥ 1 → `회차 흔들림`.

예 (작을수록 흔들림): die 5개, 회차 평균 1e-9, 1e-8, 1e-7, 1e-6, 1e-5 → x = −9, −8, −7, −6, −5. log 범위 y = 0.8, 0.5, 0.3, 0.2, 0.1. x 순위 1..5, y 순위 5..1 → ρ = −1.00 ≤ −0.5. 유효 die 5 < 10이라 `spearman_size_jitter` = −1.00만 쓰고 상태는 붙이지 않습니다. 같은 모양이 die 10개 이상이면 `작을수록 흔들림`.

`summary.txt` 구성: 구간 × 판정, 동등 아닌 사유, 정량·LoQ 미만 차이·미결 표(회차별 평균), 항목군별 판정, t-test로 판정했다면, 판정 근거 점검(회차 흔들림 몫, LoQ를 정한 쪽, blank·장비 정확도가 바꾼 판정 수), 입력 점검, 반복해서 튀는 die.

## 예제

```bash
python examples/make_por3_data.py p3
python por_doe_compare.py --por p3/por_run1 --por p3/por_run2 --por p3/por_run3 --doe p3/doe \
  --level p3/level.csv --blank p3/blank --blank-map p3/blank_map.csv --out p3/out
python summarize.py p3/out/items.csv
```

## 판정 그림 만들기

`plot_verdicts.py`는 `items.csv`로 요약 그림을 만들고, 원시 측정 데이터를 함께 주면 ITEM별 상세 그림도 만듭니다.

- **요약**은 기본으로 만듭니다. 한 장짜리 대시보드 `summary.png`와 `summary_loq.png`를 저장합니다.
  - `summary.png` 위쪽은 정량 ITEM의 중심/Δ 히스토그램입니다. 판정별로 색을 쌓고 판정별 개수와 ±1 선을 표시합니다. `--xlim X`(기본 범위 ±X) 밖의 값은 끝에 모아 그립니다.
  - 아래쪽은 차이·미결 ITEM만 막대로 여러 열에 나누어 그립니다. 그림 높이는 16 in까지이며, 다 못 넣으면 '표시 n / 전체 m · 나머지는 --full'이라고 적습니다. 작은 LoQ 패널도 함께 들어갑니다.
  - `--full`을 주면 모든 정량 ITEM을 그린 `summary_001.png`, `summary_002.png` …도 만듭니다. 한 장에는 최대 `--per-page`개의 ITEM을 넣습니다(기본 1200). 점은 차이/Δ의 중심이고 가로선은 90% 신뢰구간입니다.
  - `--groups FILE`(ITEM,group 두 열)을 주면 그룹마다 같은 모양의 `summary_group_<이름>.png`를 만듭니다. 파일에 없는 ITEM은 '(그룹 없음)'으로 모으고 경고를 냅니다.
- **상세**는 `--detail`을 줄 때만 만듭니다. 대상을 정하지 않으면 차이와 미결 ITEM을 그리고, `--items A,B`로 ITEM 코드를 고르거나 `--all`로 전체를 고릅니다. `--jobs N`은 상세 그림을 그리는 작업 프로세스 수입니다(기본 1).
- 그림에는 `item_map.csv`의 실제 항목 이름을 쓰지 않습니다. 상세 파일은 `detail/` 아래에 저장하며, 파일명은 ITEM 코드를 `safe_item_name()`에 통과시켜 만듭니다.

판정 제외 ITEM은 요약·LoQ 그림에서 빠지고, 경고 '판정 제외 n개'가 나옵니다.

`summary_loq.png` 읽는 법: x축은 |DOE 중심|/LoQ, y축은 |중심|/Δ이고 두 축 모두 로그 눈금입니다. x=1 선 왼쪽은 DOE 값이 LoQ보다 작고, y=1 선 위쪽은 차이가 Δ보다 큽니다. 두 선이 만드는 네 칸에 각 칸의 뜻을 적어 두었습니다. 축 범위를 벗어난 값과 0인 값(로그 눈금에 못 그림)은 축 끝에 다른 모양의 점으로 그리고, 그 개수를 따로 적습니다.

요약만 그릴 때는 판정 결과 `items.csv` 하나면 충분합니다.

```bash
python plot_verdicts.py --items-csv p3/out/items.csv --out p3/out/plots
```

상세 그림에는 판정 때 쓴 같은 `--por`, `--doe`, `--level`, `--blank` 입력을 다시 줍니다. 아래는 두 ITEM만 고르는 예이며, `--items VT_SHIFT,VT_NOISY_DOE` 대신 `--all`을 쓰면 모든 ITEM을 그립니다.

```bash
python plot_verdicts.py --items-csv p3/out/items.csv --out p3/out/plots \
  --detail --items VT_SHIFT,VT_NOISY_DOE --jobs 4 \
  --por p3/por_run1 --por p3/por_run2 --por p3/por_run3 --doe p3/doe \
  --level p3/level.csv --blank p3/blank --blank-map p3/blank_map.csv
```

예시 그림은 다음과 같습니다. 앞의 네 그림은 `examples/make_por3_data.py`가 만든 데이터에서 나왔습니다.

- [요약](examples/plots/summary_001.png)
- [LoQ 패널](examples/plots/summary_loq.png)
- [차이 상세](examples/plots/detail_diff_VT_SHIFT.png)
- [미결-해상도 부족 상세](examples/plots/detail_resolution_VT_NOISY_DOE.png)
- [미결-경계 상세](examples/plots/detail_border_IT00025.png) — 6,000 ITEM 부하 데이터에서 만든 그림

6,000 ITEM × die 60 × POR 3회 + DOE, `examples/make_load_data.py OUT --items 6000 --dies 60 --seed 7`; 측정 기계: 공유 박스 Linux, Intel Xeon 8코어, RAM 15 GB, Python 3.13.5, matplotlib 3.11.2, pandas 3.1.1, numpy 2.5.5; `--dpi 100`. 최대 메모리는 가장 큰 단일 프로세스 값(`ru_maxrss`), `--jobs 4`는 작업자 합이 아님.

| 단계 | 명령 | 시간 | 최대 메모리 | 출력 용량 |
|---|---|---|---|---|
| 데이터 생성 | `make_load_data.py` | 1.8 s | - | 73 MB |
| 판정 계산 | `por_doe_compare.py` | 12.0 s | 683 MB | items.csv 등 3.2 MB |
| 요약 (기본) | `plot_verdicts.py --items-csv` | 2.1 s (5장 + LoQ 1장) | 199 MB | 500 KB |
| 상세 `--all`, `--jobs 1` | | 2,045 s (ITEM당 평균 0.34 s) | 714 MB | 447 MB (6,000장, 장당 평균 74 KB) |
| 상세 `--all`, `--jobs 4` | | 329 s (ITEM당 평균 0.055 s) | 714 MB | 447 MB |
| 요약 + 상세 `--all`, `--jobs 4` | | 330 s | 719 MB | 448 MB |

`--jobs 1` 측정 중에는 다른 짧은 작업(테스트 실행)이 같은 기계에서 잠깐 겹쳐 실제보다 조금 느릴 수 있습니다. 전체 상세는 `--jobs 4` 이상을 쓰고, 보통은 요약과 `--items`로 고른 ITEM만 그립니다.

미결-해상도 부족 사례는 `examples/make_por3_data.py`의 `VT_NOISY_DOE`입니다. DOE die 값이 ±0.3 V로 고르게 퍼져 90% 신뢰구간 반폭이 Δ보다 큽니다. `examples/make_load_data.py`의 `IOFF_STEP` 템플릿은 DOE die 일부만 한 계단 올라가 중앙값 신뢰구간이 [0, 0]이므로 동등으로 판정됩니다.

요약은 `items.csv`만으로 빠르게 만들 수 있습니다.  
상세는 원시 데이터를 함께 주고, 필요한 ITEM만 골라 만드는 것이 좋습니다.

## 근거

- 반복 측정으로 흔들림 구하기: NIST/SEMATECH e-Handbook 2.4 (Gauge R&R), 2.6.1 (반도체 사례)
- MAD, robust σ: NIST e-Handbook 1.3.5.6
- LoD / LoQ: Currie 1968, IUPAC
- 분해능, 균일분포 불확도: GUM (JCGM 100) F.2.2.1, 4.3.7
- 동등성 검정: TOST (Schuirmann 1987), ASTM E2935
- 중앙값 부호검정 신뢰구간: Hollander & Wolfe, Nonparametric Statistical Methods
- t-test: NIST e-Handbook 7.3.1.1

허용폭의 정책 몫 r(기본 5%)은 표준이 정하지 않는 사내 정책 값입니다.

## Fail ITEM 근거 (`fail_evidence.py`)

`python fail_evidence.py --input <items.csv> --out <폴더> [--items ID,...]` — por_doe_compare.py 결과 표(`--out` 폴더의 `items.csv`, 탭 구분 표도 됨. `ITEM` 열과 `<이름>_mean` 회차 열은 compare_before_after.py와 같은 방식으로 읽음)에서 verdict가 '차이'·'미결'인 ITEM의 근거를 규칙으로 계산해 `fail_evidence.csv`, `forest.png`, `items/<ID>.png`, `summary.txt`를 만듭니다. `fail_evidence.csv` 첫 열은 실제 `ITEM` 이름이고, 익명 `ID` 열이 있으면 그 옆에 붙습니다. `--items`를 주면 그 ID만 ITEM 그림을 그립니다(CSV·forest는 전체).

입력에 items.csv의 `status`~`mean_median_ratio` 열(`por_gap_over_delta`는 이 도구가 따로 계산해 빼고, 열 순서는 위 items.csv 순서)과 `sigma_meas`, `meas_precision_pct`, `sigma_meas_over_delta` 열이 있으면 `fail_evidence.csv` 맨 끝에 이 순서로 값을 그대로 옮기고, 없으면 빈 칸 열로 둡니다(판정에는 쓰지 않음).

열은 이름으로 찾습니다(`POR{k}_mean`은 2개 이상, k 가변). 대상 행에서 `por_median DOE_mean center ci_low ci_high delta LoQ` 열이 없거나 값이 빈칸·숫자 아님(엑셀 넘침 `####`, `***` 등)이면, 또는 값이 있는 POR 회차가 2개 미만이면 judgement='계산 불가'로 쓰고 사유를 note에 남깁니다. 빈 `POR{k}_mean`은 그 회차가 없는 것으로 봅니다. 대상이 아닌 행은 '대상 아님'으로 CSV에만 남깁니다.

| 상수 | 값 | 뜻 |
|---|---|---|
| `ITEM_AXIS_OVER_DELTA` | 3 | ITEM 그림 x축 범위 ±3·Δ% (밖은 화살표+숫자) |

`por_gap_pct`, `por_gap_over_delta`, `por_gap_def`, `median_out_over_delta` 열은 참고용이며 판단에 쓰지 않습니다. por_gap(`por_gap_over_delta`)은 items.csv에 `por_gap_over_delta` 열이 있고 값이 유한하면 그 값을 씁니다(`por_gap_def` = '짝지은 회차 차'). 아니면 POR 회차 평균 열로 옛 방식대로 계산합니다(`por_gap_def` = '옛 정의(회차 평균 차)'). `por_gap_def` 열은 `por_gap_over_delta` 바로 뒤에 있습니다. 옛 정의로 계산한 행이 있으면 `summary.txt`에 `por_gap: 옛 정의(회차 평균 차) n행 (items.csv에 짝지은 회차 차 열 없음)` 줄이 붙습니다.

median_out_over_delta는 por_median이 POR·DOE 평균들의 [min, max] 밖으로 벗어난 거리/Δ입니다. 분류:

1. **차이**: CI 전체가 ±Δ 밖 (ci_high < −Δ 또는 ci_low > Δ)
2. **미결**: 나머지 (하위 분류 없음, 원인은 `status` 열)

미결의 원인은 items.csv `status` 열(조건 불안정, 회차 흔들림 …)로만 읽으며, `fail_evidence.csv`는 이 값을 그대로 옮깁니다.

verdict와 규칙 결과가 어긋나면 note에 'verdict와 다름'을 적습니다.

verdict가 '판정 제외'인 행은 근거 대상이 아니며, '계산 불가'·'대상 아님'과 따로 judgement='판정 제외'로 둡니다.

## 기존·개선 비교 (`compare_before_after.py`)

`python compare_before_after.py compare <기존_items.csv> <개선_items.csv> -o <폴더>` — 입력은 `por_doe_compare.py --out 폴더`의 `items.csv` 두 개(기존 실행, 개선 실행)입니다. 첫 열 `ITEM`은 ID로 읽고(탭 구분 표의 `ID` 열도 됨), 회차 평균 열 `<이름>_mean`은 나온 순서대로 POR1, POR2로 읽습니다. 두 표를 ITEM으로 맞춰 ITEM별 σ_die·σ_run·Δ·CI 폭(|por_median| 대비 %)과 판정 변화를 `compare.csv`(`center_delta_before`·`center_delta_after` 열 포함), `summary.txt`, `stability_overall.csv`(전체 안정성 한 행, group_summary.py 결과의 '전체' 행과 같은 값), `worst_items.csv`(비율 지표별 악화 상위 N ITEM), 지표 그림 6장(`sigma_die_ratio.png`, `sigma_run_ratio.png`, `meas_precision_ratio.png`, `stability_sigma_die_pct.png`, `stability_meas_precision_pct.png`, `verdict_center_delta.png`)으로 냅니다. run_all.py에서는 `--before`만 주면(`--groups` 없이도) `결과/compare/`에 생깁니다. 출력 `compare.csv`와 `evidence.csv`의 첫 열은 실제 `ITEM` 이름이고, 입력에 summarize.py의 익명 `ID` 열이 같이 있으면 그 옆에 `ID` 열로 붙습니다. 비교 키는 항상 실제 ITEM입니다. 한쪽에만 있는 ITEM은 따로 표시하고 σ 집계에서 뺍니다. 정렬 의심 행(같은 ITEM인데 por_median 상대차 > 20%, 내부 기준)은 `misaligned` 열에 표시만 하고 기본으로 σ 집계에 포함합니다. 빼려면 `--exclude-misaligned`를 붙입니다. `compare.csv`에는 측정 정밀도 열 `meas_precision_pct_before`·`meas_precision_pct_after`·`meas_precision_pct_change`(개선−기존)와 `meas_precision_status`(`sigma_die_status`와 같은 규칙: lower/higher/same, 낮을수록 좋음)도 붙습니다. 입력 items.csv에 `meas_precision_pct` 열이 없으면(예전 결과) 100 × √(σ_die² + σ_run²) / |por_median|으로 계산합니다. `evidence <items.csv> -o <폴더>` 모드도 있고, 그 `evidence.csv`에도 같은 방식의 `meas_precision_pct` 열이 붙습니다. `evidence.csv`의 group은 fail_evidence.py와 같이 '차이'/'미결' 둘뿐입니다. `judgment` 바로 앞의 `status` 열에는 items.csv `status` 값을 그대로 옮기고(열이 없는 옛 items.csv면 빈 칸), status가 '정상'이 아니면 `judgment` 끝에 `원인(status): <status>`를 덧붙입니다. `evidence.csv`의 `por_gap_over_delta`(참고용, 판단에 쓰지 않음)도 fail_evidence.py와 같은 규칙입니다. items.csv의 짝지은 회차 차를 쓰고(`por_gap_def` = '짝지은 회차 차'), 열이 없는 옛 items.csv면 회차 평균의 max − min으로 계산하며(`por_gap_def` = '옛 정의(회차 평균 차)'), 그런 행이 있으면 `summary.txt`에 `por_gap: 옛 정의(회차 평균 차) n행 (items.csv에 짝지은 회차 차 열 없음)` 줄이 붙습니다.

`--plot-top N`(기본 10, 1 이상)은 각 비율 지표 그림 아래 악화 상위 표와 `worst_items.csv`에 넣을 ITEM 수입니다. 그림 자체는 모든 ITEM의 분포를 그립니다. `run_all.py --plot-top N`으로도 넘길 수 있습니다.

`sigma_run`은 회차 중앙값 분산에서 die 잡음 몫을 뺀 값의 제곱근이라, 뺀 값이 0보다 작으면 0으로 잘립니다(`por_doe_compare.robust_noise`). 그래서 `sigma_run_ratio`의 0/0(둘 다 0)과 σ_run=0 비율이 생길 수 있습니다.

지표 그림 공통 규칙: 비율·σ%는 로그 축, 축 범위는 1~99 백분위이고 밖의 값은 경계에 붙여 그 개수를 적습니다. 0·음수 값은 로그 축에 그릴 수 없어 빼고 그 개수를 적습니다. 기준선은 비율 1, center/Δ 그림은 0과 ±1입니다. n과 중앙값을 적고, 제목은 한 줄 한글입니다.

기존·개선 어느 쪽이든 판정 제외인 행은 σ 집계에서 빼고, 1개 이상이면 `summary.txt`에 "- 판정 제외 (기존 또는 개선, σ 집계에서 뺌): n" 줄을 넣습니다.

## 그룹별 요약 (`group_summary.py`)

`python group_summary.py --compare compare.csv --groups 그룹.csv --out group_out` — `compare_before_after.py compare`가 만든 `compare.csv`를 ITEM 그룹별로 요약합니다. 그룹 파일은 첫 열 ITEM, 둘째 열 그룹(쉼표 또는 탭, 헤더는 있어도 없어도 됨)이고, 그룹 파일 ITEM은 이름 그대로 먼저 맞추고, 안 맞으면 앞의 `F<숫자>_` 접두어를 떼고 다시 맞춥니다. 그래도 없는 ITEM은 '미지정'으로 묶습니다. presence=matched인 행을 씁니다. 정렬 의심 행도 기본으로 포함하고, `--exclude-misaligned`를 주면 뺍니다(제외 열 이름은 기본 '제외(짝 없음)', 옵션을 주면 '제외(짝 없음, 정렬 의심)'). 출력은 `group_summary.csv`(맨 위 '전체' 행), `verdict_by_group.csv`(그룹별 판정 변화), `stability_by_group.csv`(그룹별 안정성: 기존끼리·개선끼리 σ_die%·σ_run% 중앙값과 사분위, 측정정밀도% 중앙값·25%·75%, σ_run=0 비율, 안정 순위), `group_dirs.csv`(그룹 이름 → 폴더 이름 변환표), compare와 같은 이름의 지표 그림 6장(그룹 비교: 가로 배치, 그룹별 분포와 전체 기준선), 그리고 그룹마다 `<폴더 이름>/` 안에 같은 6장(그 그룹 ITEM만)입니다. 그림 규칙은 위 compare 지표 그림과 같습니다. 안정성은 compare.csv의 `sigma_*_pct_*`·`meas_precision_pct_*` 열을 쓰고, 없으면 σ와 `por_median_*`로 계산하며, 둘 다 없으면 그림을 건너뜁니다.

그룹 폴더 이름(`compare_metrics.safe_group_name`): 한글·영문·숫자·`-`·`_`만 남기고 나머지는 `_`로 바꾸며, 빈 이름은 `_`입니다. 바꾼 이름이 겹치면 뒤에 `_2`, `_3`…을 붙입니다. 실제 대응은 `group_dirs.csv`에서 확인합니다.

판정 제외 행은 쓰는 행에서 빼고, 그런 행이 있을 때만 '판정 제외' 열을 붙입니다.

## infra_compare.py (이전 방식)

POR 1회(+ 일부 재측정)와 DOE 1회를 비교하던 첫 버전입니다. `python infra_compare.py --ref ref/ --new new/ --blank ... --blank-map ... --out 결과`. 새 분석에는 `por_doe_compare.py`를 쓰세요. `por_doe_compare.py`가 파일 읽기와 blank 읽기 함수를 여기서 가져다 씁니다.
