# dc-infra-compare

같은 웨이퍼, 같은 die를 POR(기존 프로그램)로 여러 번, DOE(새 프로그램)로 한 번 잰 DCNORMAL 결과를 ITEM별로 비교해서 **동등 / 차이 / 미결**로 판정합니다. 통계를 낼 수 없는 ITEM은 **판정 제외**입니다.

원칙은 하나입니다. **DOE와 POR의 차이가, POR을 자기 자신과 다시 잰 차이보다 크지 않으면 같다고 본다.**

판정 흐름과 기법별 수식, 시각화는 [`docs/method.html`](docs/method.html)에 있습니다. GitHub 화면에서는 소스만 보이니, 내려받아 브라우저로 여세요.

## 설치

```bash
pip install -r requirements.txt   # Python 3.9+, pandas, numpy, scipy
```

## 실행

### dcc.py로 이름 붙인 조합 실행

데이터 묶음(POR 회차들, DOE, item_info 등)을 설정 파일에 한 번 적고 짧은 이름으로 부릅니다. `combos.example.ini`를 `combos.ini`로 복사해 경로를 바꿔 쓰세요(`combos.ini`는 git에 올리지 않습니다). 기본은 현재 폴더의 `combos.ini`이고, 다른 파일은 `--config 파일`로 줍니다.

```ini
[defaults]
out = 결과
level = item_info.csv
groups = groups.csv
scales = scales.csv

[A1]
por = data/A/POR1
      data/A/POR2
      data/A/POR3
doe = data/A/DOE
```

- `[defaults]` 밖의 섹션 하나가 조합 하나이고, 섹션 이름이 조합 이름입니다. 조합에 적은 키가 `[defaults]`보다 우선합니다.
- 키는 `por`(한 줄에 회차 하나, 2회 이상), `doe`, 그리고 선택으로 `level`, `blank`(한 줄에 하나), `blank_map`, `key`, `encoding`, `r`, `groups`, `scales`, `before`, `out`입니다. 뜻은 아래 옵션 표와 같습니다.
- `scales`를 적으면 판정 단계(`por_doe_compare.py`)에 `--groups`와 `--scales`를 같이 넘깁니다. 그래서 `scales`에는 `groups`가 필요합니다. 적지 않으면 판정은 그룹을 보지 않습니다(`groups`는 그룹 그림·요약에만 씀).
- 상대 경로는 현재 폴더가 아니라 설정 파일이 있는 폴더 기준입니다.
- 모르는 이름·키, POR 1회, 없는 경로는 아무것도 실행하기 전에 알려 주고 끝납니다(rc=2).

```bash
python dcc.py list                          # 조합 이름, POR 회차 수, DOE, 출력 폴더
python dcc.py judge A1                      # 판정(por_doe_compare) → LoQ·log 재확인(review) → 판정 지도(plot_verdicts)
python dcc.py judge A1 --detail             # + 최종 판정이 차이·미결인 ITEM 전부 item 분석
python dcc.py judge all                     # 모든 조합을 파일 순서대로. 실패한 조합이 있어도 계속하고 끝에 조합별 결과 한 줄
python dcc.py item A1 VT_SAME,VT_SHIFT      # 그 ITEM만 Fail 근거 (원데이터 포함: item_view.png, evidence.csv)
python dcc.py item A1 --items-file 볼항목.txt  # ITEM 목록 파일 (한 줄에 하나, # 뒤는 주석, 또는 ITEM·ID 열이 있는 CSV)
python dcc.py item A1 VT_SAME --plots       # + ITEM 상세 그림 (원데이터 전체를 읽어 느림)
python dcc.py group A1                      # 그룹별 판정 지도 (groups 필요)
python dcc.py group A1 --before 이전/items.csv  # + 기존·개선 비교와 그룹별 비교 요약
```

`--items-file`에는 명령행 ITEM을 같이 줄 수 있고, 둘을 합쳐 중복 없이 씁니다. `items_index.csv`나 `worst_items.csv`처럼 `ITEM` 열이 있는 결과 표를 그대로 넘겨도 됩니다.

조합 하나의 산출물은 `<out>/<이름>/`에 모입니다.

| 경로 | 내용 | 명령 |
|---|---|---|
| `items.csv`, `outlier_dies.csv` | 판정 결과 | `judge` |
| `stability/` | 측정 안정도 ([아래](#측정-안정도-stability)) | `judge` |
| `review/` | LoQ·log 판정 재확인 ([아래](#loqlog-판정-재확인-review)) | `judge` |
| `plots/` | 판정 지도 `summary.png`, LoQ 아래 ITEM 그림 `summary_loq.png` | `judge` |
| `item/` | 고른 ITEM의 Fail 근거(`fail_evidence.py --only`), `item/plots/`는 `--plots` 상세 그림 | `item`, `judge --detail` |
| `group/plots/` | 그룹별 판정 지도 | `group` |
| `group/compare/`, `group/summary/` | 기존·개선 비교, 그룹별 비교 요약 | `group --before`(또는 조합의 `before` 키) |

`item`과 `group`은 `items.csv`를 다시 쓰고, 없을 때만 `judge` 단계를 먼저 돌립니다. 각 단계 이름과 실행 명령을 찍고, 실패하면 그 단계에서 멈추고 오류 끝 20줄을 보여 줍니다. 요약(summarize)과 전체 Fail 근거까지 한 번에 돌리려면 아래 `run_all.py`를 씁니다.

### run_all.py로 한 번에

판정 → 요약 → LoQ·log 재확인 → Fail 근거 → 판정 지도를 차례로 돌리고, 모든 산출물을 `--out` 폴더 하나에 모읍니다. 입력 옵션은 `por_doe_compare.py`와 같습니다(아래 표). 각 도구는 실행을 시작할 때 같은 --out 폴더에서 자기가 만드는 그림·표 파일만 지우고 다시 만듭니다(다른 파일은 그대로).

```bash
python run_all.py --por POR1/ --por POR2/ --por POR3/ --doe DOE/ \
  --level item_info.csv --out 결과
```

- `--before 이전결과/items.csv`: 기존·개선 비교(`compare_before_after.py compare`)를 추가해 `결과/compare/`에 둡니다.
- `--groups groups.csv`: ITEM,그룹 두 열 파일입니다. 그룹마다 판정 지도 `결과/plots/summary_group_<이름>.png`를 그립니다. `--before`도 함께 주면 그룹별 비교 요약(`group_summary.py`)을 추가해 `결과/groups/`에 둡니다.

어느 단계든 실패하면 `[실패] 단계 N/M <이름>: <명령>`, `rc=…`, 그 단계 오류 끝 20줄을 보여 주고 멈춥니다. 출력 형태 예시(실제 실행값이 아님):

```text
[단계 1/5] por_doe_compare
[단계 2/5] summarize
[단계 3/5] review
[단계 4/5] fail_evidence
[단계 5/5] plot_verdicts

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
| `stability/` | `overall.csv`, `dies.csv`, `runs.csv`, `stability.png`(측정 안정도), `groups.csv`(`--groups`일 때) | `por_doe_compare.py` (항상) |
| `review/` | `loq_review.csv`, `log_review.csv`, `loq_review.png`, `log_review.png`, `items/<ITEM>.png`(확인 필요 ITEM) | `review.py` (항상) |
| `fail_evidence/` | `fail_evidence.csv`(Fail 근거), `forest.png`(전체 그림), `items_index.csv`, `items/<유형>_<ITEM>/`(`item_view.png`, `evidence.csv` 등) | `fail_evidence.py` (항상) |
| `plots/` | `summary.png`(판정 지도), `summary_loq.png`(LoQ 아래 ITEM) | `plot_verdicts.py` (항상) |
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
| `--groups`, `--scales` | ITEM,group 파일과 group,scale 파일 (선택, 같이 씀). 그룹마다 log 옵션 대상을 정함 ([최종 판정](#최종-판정-verdict_final)). `--scales`가 없으면 그룹을 보지 않음 |

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
- `--level`의 A, V ITEM에서 구한 장비 정확도 폭(`accuracy_margin`)은 기본 판정에 쓰지 않습니다. Δ' = max(Δ, `accuracy_margin`)으로 낸 정량 TOST 판정을 `verdict_with_accuracy`에 적고(`accuracy_margin`이 없으면 빈 칸), LoQ 근처 ITEM에서만 최종 판정의 accuracy 옵션이 씁니다([최종 판정](#최종-판정-verdict_final)). 그 밖의 ITEM에서는 참고입니다. `delta`, `delta_source`는 기본 판정에 쓴 Δ입니다.
- log 판정(`verdict_log`, 아래 [log 판정](#log-판정-verdict_log))의 허용폭은 Δ_log = log10(1 + r) + `sigma_rep_log`입니다. t(0.95, J−1) × √(1 + 1/J) 배수는 없습니다.
  - `sigma_rep_log` = die마다 L(= log10\|값\|) 회차값의 표준편차(ddof=1)를 구하고, 그 die 중앙값. 유효한 회차값이 2개 미만인 die는 뺍니다.
  - `sigma_run_log`(L에서 구한 회차 이동)는 분석용이며 판정에 쓰지 않습니다.
- Open 코드 값(예: 1E+97처럼 측정 대신 찍힌 큰 숫자) 처리: 미결(처리 방식 정해지지 않음). 판정 값 '미결'과는 다른 뜻입니다.

| 구간 (\|POR 중앙값\|) | 판정 |
|---|---|
| 정량 (≥ LoQ) | 신뢰구간이 ±Δ 안 → **동등**, 통째로 밖 → **차이**, 걸침 → **미결** (반폭 ≥ Δ면 해상도 부족, 아니면 경계) |
| LoQ 미만 | LoQ 미만 값은 "<LoQ"로 보고합니다(IUPAC). 신뢰구간이 통째로 ±Δ 밖이고 **DOE 중심(POR 중앙값 + shift)이 LoQ 이상**이라 보고가 달라질 때만 **차이**, 그 밖은 **동등**("<LoQ 보고 일치") |

**판정 제외**는 판정할 것이 없는 ITEM입니다. 아래 원인 표(`EXCLUSION_CAUSES`)를 모두 보고, 맞는 원인을 모두 이 순서대로 `; `로 이어 `reason`에 적습니다. `판정 제외: `는 첫 원인 앞에만 붙습니다. 예: `판정 제외: 모든 값 같음; die 산포 0 (σ_die=0)`.

1. center·ci_low·ci_high 중 하나가 NaN이나 inf → `중심·신뢰구간 계산 불가 (…)`
2. 회차 0값: POR 회차 하나나 DOE가 die 절반 넘게 정확히 0인데, 다른 회차나 DOE 중 하나라도 die 절반 넘게 0이 아님 → `회차 0값 (POR2, DOE)`처럼 그 이름을 적음
3. POR·DOE 값이 모두 같음(서로 다른 값이 하나) → `모든 값 같음`
4. die 산포 0(`sigma_die` = 0이거나 고정값 비율 `fixed_share` > 50%, `status` `산포 0`과 같은 비율): **정량 zone이고 데이터가 거칠 때만**. 거칠다 = `resolution_step` ≥ 0.1 × Δ(`status` `분해능 부족`과 같은 검사)이거나 계산할 수 없음. `sigma_die` = 0이면 `die 산포 0 (σ_die=0)`, 아니면 `die 산포 0 (고정값 NN%)`. 분해능이 Δ에 비해 고우면 그대로 TOST를 합니다(신뢰구간이 한 점이어도 됨)
5. POR 중앙값 0이고 `sigma_run` = 0: **정량 zone일 때만**, 곧 LoQ가 0이거나 유효하지 않을 때만 → `고정값 (중앙값 0·σ_run 0)`

LoQ 미만이면 4, 5는 보지 않고 LoQ 판정으로 갑니다. 그 밖은 zone 판정을 합니다. LoQ 미만은 Δ와 무관하게 판정하고, 정량 zone은 Δ가 0 이하이거나 NaN일 때만 `판정 제외: 최종 Δ가 0 이하이거나 유효하지 않음 (Δ=…, 출처 …)`입니다. die 수 부족(MIN_DIE)은 그대로 **미결**입니다.

**4. 참고 (판정에 쓰지 않음).** t-test(NIST 7.3.1.1), POR 회차끼리 t-test(`por_ttest_sig`), 튀는 die(\|d − 중앙값\| > 5 robust σ, `n_outlier_die`).

### 최종 판정 (`verdict_final`)

기본 판정(`verdict`, 위 1~3)이 먼저입니다. 동등이나 판정 제외면 그대로 최종 판정입니다. 차이·미결인 ITEM만 +@ 옵션(`OPTIONS`)이 다시 판정합니다. 옵션은 모두 TOST만 하고 LoQ 판정은 하지 않습니다.

| 순서 | 옵션 (`verdict_basis`) | 대상 | 규칙 (판정 열) |
|---|---|---|---|
| 1 | `log` | `scale`이 `item`이면 `status` `log 후보`(`decades` ≥ 1, `log_fit` > 0.1). `auto→log`면 `decades` ≥ 1, `log_fit` > 0 | log10 값에서 TOST (`verdict_log`, [log 판정](#log-판정-verdict_log)) |
| 2 | `accuracy` | `status` `LoQ 근처`이고 `accuracy_margin`이 있음 | Δ' = max(Δ, `accuracy_margin`)의 TOST (`verdict_with_accuracy`) |
| 3 | `log_physics` | `scale`이 `log`이고 `decades` ≥ 1, `log_fit` > 0 (`LOG_FIT_MIN_SCALE`) | 1과 같은 log10 TOST (`verdict_log`) |

- 표 순서로 대상인 옵션을 보고, **동등을 주는 첫 옵션**이 최종 판정을 정합니다(동등, 그 옵션).
- 동등을 주는 옵션이 없으면, 대상이고 판정(동등·차이·미결)이 나온 log 옵션(`log`나 `log_physics`)의 판정이 최종입니다. 그것도 없으면 기본 판정(`linear`)입니다.
- accuracy 옵션은 동등일 때만 판정을 바꿉니다.
- `scale`이 `linear`, `auto→linear`인 ITEM은 어느 log 옵션의 대상도 아닙니다. 한 ITEM은 두 log 옵션 중 많아야 하나의 대상입니다.

`LoQ 근처`는 LoQ ≤ \|POR 중앙값\| < LoQ / (10 r)인 구간입니다(r = 0.05면 LoQ의 1~2배). LoQ = 10σ라서 이 구간에서는 1회 측정 잡음(σ = LoQ / 10)이 허용폭의 정책 몫 r × \|POR\|보다 큽니다. 그래서 이 구간에서만 장비 정확도 폭을 허용폭으로 씁니다. 그 밖의 ITEM에서 `verdict_with_accuracy`는 참고입니다.

`scale`은 ITEM 그룹마다 정합니다(`--groups ITEM,group`과 `--scales group,scale`).

| `scale` 값 | 뜻 |
|---|---|
| `log`, `linear` | `scales` 파일에 그 그룹을 그렇게 적음 |
| `auto→log`, `auto→linear` | `scales` 파일에 `auto`로 적었거나 그룹이 파일에 없어, 이번 실행의 그 그룹 ITEM으로 정함 |
| `item` | 그룹이 없거나 `--scales`를 주지 않음. ITEM마다 `log 후보`로 봄(그룹 scale 전의 규칙) |

- `scales` 파일은 `group,scale` 두 열(쉼표나 탭, 머리줄 선택)이고 scale은 `log`, `linear`, `auto`입니다. 다른 값이 있으면 실행하지 않고 끝납니다.
- auto: 그룹 ITEM 중 `decades`와 `log_fit`이 둘 다 있는 ITEM(`n_items`)의 절반 넘게 `decades` ≥ 1이고, 그 ITEM들의 `log_fit` 중앙값이 0보다 크면 log, 아니면 linear입니다. 결정은 `items.csv` 옆 `scales_auto.csv`(`group`, `decision`, `n_items`, `n_decades_ge_1`, `median_log_fit`)에 적습니다. 확인한 뒤 `scales` 파일에 옮겨 적으면 다음 실행부터 고정됩니다.
- `--scales`가 없으면 모든 ITEM이 `item`이고 결과는 그룹 scale 이전과 같습니다. 같은 `--out`에 남은 지난 `scales_auto.csv`는 지웁니다.
- 예전 `items.csv`(`scale` 열 없음)를 다시 읽는 도구(`plot_verdicts.py` 재계산 등)는 모든 ITEM을 `item`으로 봅니다.

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
- 장비 정확도 폭(`accuracy_margin`, 기본 판정에 안 씀, LoQ 근처 ITEM의 accuracy 옵션에서만 씀): 두 측정이 각자 사양 정확도 ±(a × \|값\| + b × range + c) 안일 때 생길 수 있는 차이 1.645 × √((U_POR² + U_DOE²) / 3) (균일분포, GUM 4.3.7). 사양의 Vo, Rres × Io 항은 0으로 둡니다.
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
| `scales_auto.csv` | `--scales`를 줄 때만. auto 그룹마다 정한 scale과 근거 ([최종 판정](#최종-판정-verdict_final)) |
| `summary.txt` | `summarize.py`가 만드는 공유용 요약 (ITEM 이름 대신 익명 번호) |
| `item_map.csv` | 익명 번호 ↔ ITEM. 공유하지 마세요. `items.csv`의 `ID` 열과 같은 번호입니다(`--family-regex`·`--keep-family`를 주면 `summarize.py`가 `ID` 열을 그 번호로 다시 씁니다). 번호는 ITEM 이름 순서로 매겨서 실행마다 같습니다 |

`items.csv` 열은 아래 묶음 순서입니다(`por_doe_compare.py`의 `COLUMN_GROUPS`, 열 순서는 이 표 하나가 정합니다). 묶음 안은 적힌 순서이고, 해당 경로·옵션에서만 생기는 열(`--level`, `--blank`, LoQ 미만의 `doe_center` 등)은 없으면 빠집니다. 표에 없는 열이 생기면 맨 끝에 붙습니다.

| 묶음 | 열 | 내용 |
|---|---|---|
| 식별 | `ID`, `ITEM`, `UNIT` | `ID`는 익명 번호(항목군 + ITEM 이름 순서 번호, `summarize.py`와 같은 값). 맨 앞 열 |
| 판정 | `verdict_final`, `verdict_basis`, `scale` | 최종 판정, 그 근거(`linear`, `log`, `accuracy`, `log_physics`), log 옵션 대상을 정한 scale. 규칙은 [최종 판정](#최종-판정-verdict_final). 판정 집계와 차이/미결 선택(`summarize`, `plot_verdicts`, `fail_evidence`, `group_summary`)은 `verdict_final` 기준 |
| | `verdict`, `verdict_log`, `verdict_with_accuracy`, `verdict_no_blank` | 기본(선형) 판정, log 판정(아래), Δ' = max(Δ, 장비 정확도 폭)의 정량 판정(`--level`, LoQ 근처에서만 옵션), blank 없이 낸 판정(`--blank`) |
| | `zone`, `reason`, `log_reason`, `status` | 구간, 사유, log 판정 사유, 데이터 상태(아래) |
| TOST | `n_die`, `center`, `ci_low`, `ci_high` | die 수, shift와 90% 신뢰구간 |
| | `delta`, `policy_margin`, `run_margin`, `delta_source`, `ci_half_over_delta` | 허용폭과 그 구성, 신뢰구간 반폭 / 허용폭 (아래) |
| LoQ | `por_median`, `doe_center`, `LoQ`, `LoD`, `limit_source` | POR 값, LoQ 미만의 DOE 중심, LoQ와 그 출처 |
| 값 | `POR1_mean` …, `DOE_mean` | 회차별 평균 |
| 흔들림 | `sigma_die`, `sigma_run`, `sigma_meas`, `meas_precision_pct`, `sigma_meas_over_delta`, `n_outlier_die` | 흔들림, 측정 정밀도(아래), 튀는 die 수 |
| 데이터 상태 지표 | `por_gap_over_delta`, `por_gap_over_noise`, `run_jitter_pct`, `run_jitter_over_delta`, `spearman_size_jitter`, `resolution_step`, `resolution_over_delta`, `fixed_share` | `status` 근거 값 (`METRIC_COLS`, 아래) |
| 분포 모양 | `decades`, `skew_lin`, `skew_log`, `log_fit`, `bimodality_log`, `mean_median_ratio` | log 후보·두 덩어리 근거(`SHAPE_COLS`), 평균−중앙값 치우침 (아래) |
| log 판정 숫자 | `center_log`, `ci_low_log`, `ci_high_log`, `delta_log`, `ci_half_over_delta_log`, `sigma_rep_log`, `sigma_die_log`, `sigma_run_log` | log 판정 값 (아래). 끝의 둘은 분석용 |
| 참고 | `ttest`, `ttest_p`, `por_ttest_sig` | 참고 지표 (판정에 안 씀) |
| | `spec_status`, `level_check`, `range_por`, `range_doe`, `spec_resolution`, `accuracy_margin` | `--level` 관련 |
| | `blank_item`, `blank_status`, `blank_LoQ_item` | `--blank` 관련 |

`sigma_meas` = √(`sigma_die`² + `sigma_run`²), 측정 산포, 낮을수록 좋음. `meas_precision_pct` = 100 × `sigma_meas` / \|`por_median`\| (%, 상대표준편차, `por_median`이 0이면 빈 칸). `sigma_meas_over_delta` = `sigma_meas` / `delta` (`delta`가 0이면 빈 칸).

예전 `items.csv`에 있던 `rel_shift`(= `center` / \|`por_median`\|), `policy_margin_log`(= log10(1 + r) = `delta_log` − `sigma_rep_log`), `below_linear_loq`(= \|`por_median` + `center`\| < `LoQ`), `spearman_size_jitter_log`(log 판정이 된 ITEM에서 `spearman_size_jitter`와 같은 값)는 남은 열에서 바로 나와서 뺐습니다. 그 열이 있는 예전 파일도 `summarize.py`, `plot_verdicts.py`, `fail_evidence.py`, `compare_before_after.py`가 그대로 읽습니다.

### log 판정 (`verdict_log`)

`verdict_log`는 log형 ITEM의 판정입니다. L = log10\|값\| 공간에서 TOST만 해서 `LOG_COLS`에 적습니다. 선형 `verdict`·`reason`은 그대로 둡니다.

- 대상: `status`와 무관하게 POR·DOE 값에 0이 없고 부호가 하나인 ITEM 전부입니다.
- POR·DOE 값에 0이 있거나 부호가 섞이면 log를 취할 수 없어 `verdict_log` = `판정 제외`, `log_reason`에 `0값 있음`, `부호 섞임` 중 맞는 것을 `; `로 잇고, `_log` 숫자 열은 빈 칸입니다(`ci_half_over_delta`는 선형 값이라 그대로 씁니다).
- 그 밖은 L = log10\|Y\|(POR), w = log10\|z\|(DOE)에서 die별 d = w − L 회차 평균, 중앙값과 부호검정 90% CI를 구해 TOST로 판정합니다. die가 10개 미만이면 미결, 판정 제외 원인 1~4(LoQ가 없어 정량 zone으로 봄. 4의 분해능은 log 값으로 봄)나 Δ_log ≤ 0이면 판정 제외입니다. `log_reason`은 그 판정의 사유입니다.
- Δ_log = log10(1 + r) + `sigma_rep_log`. 정책 항은 선형의 r × \|POR\|가 log 공간에서 더하는 폭 log10(1 + r)입니다. 회차 항에는 t(0.95, J−1) × √(1 + 1/J) 배수가 없습니다.
- `sigma_rep_log` = die마다 L 회차값의 표준편차(ddof=1) → 그 die 중앙값. 유효한 회차값이 2개 미만인 die는 빼고, 남는 die가 없으면 빈 칸입니다.
- LoQ 판정은 하지 않습니다. L이 0 근처라는 것은 그 단위에서 값이 1 근처라는 뜻일 뿐이라, 단위(kΩ, Ω)를 바꾸면 달라지기 때문입니다. blank, 장비 분해능, 장비 정확도도 원측정값 단위라 쓰지 않습니다.
- `ci_half_over_delta` = (`ci_high` − `ci_low`) / 2 / `delta`(선형), `ci_half_over_delta_log`는 같은 값을 log 판정으로 계산. Δ ≤ 0이나 NaN이면 빈 칸입니다. 두 값을 비교해 어느 공간에서 해상도가 나은지 봅니다.

분석용 열 (판정에 쓰지 않음)

- `sigma_die_log`, `sigma_run_log` = L에서 구한 σ_die, σ_run. `verdict_log`가 판정 제외면 빈 칸. `sigma_run_log`(웨이퍼 공통 회차 이동)는 Δ_log에 쓰지 않습니다.

log 진단 대상(`is_log_target`: `fail_evidence.py`의 log 진단 그림)은 판정 대상과 다릅니다. `status`에 `작을수록 흔들림`이나 `클수록 흔들림`이 있거나, `verdict`와 `verdict_log`가 둘 다 값이 있고 다른 ITEM입니다(`verdict_log`가 판정 제외면 다르다고 보지 않음).

`sigma_meas`를 제곱합의 제곱근으로 잡는 이유: die 간 산포와 회차 산포는 서로 독립이므로 분산이 더해집니다. 표준편차를 단순히 더하면 과대 추정이 됩니다.

주의: `status`가 `산포 0`이면 `sigma_die`가 0이라 `meas_precision_pct`가 0(또는 0에 가깝게)으로 나올 수 있습니다. 측정이 정밀하다는 뜻이 아니라 값이 고정되어 산포를 못 잰 것이니 좋은 값으로 읽지 마세요. 이런 ITEM은 정량 zone에서 분해능이 Δ에 비해 거칠 때만 판정 제외이고, 그 밖은 판정합니다.

`status`는 판정(동등/차이/미결/판정 제외)과 별개인 데이터 상태 열입니다. 판정 값은 바꾸지 않고, 이상 die를 빼고 다시 판정하지도 않습니다. 여러 개가 해당하면 아래 표 순서대로 `;`로 잇습니다. 하나도 없으면 `정상`. Δ는 그 ITEM의 최종 `delta`, R은 POR die별 회차 평균, z는 DOE die 값입니다.

| 열 값 | 조건 | 기준 상수 |
|---|---|---|
| `정상` | 아래 어느 것도 해당 없음 | |
| `조건 불안정` | 짝지은 회차 차 gap ≥ Δ 이고 gap ≥ 3·se (아래). se가 0이거나 유한하지 않으면 gap ≥ Δ만 봄. Δ ≤ 0이나 NaN이면 건너뜀 | `POR_GAP_NOISE_K` = 3 |
| `회차 흔들림` | `run_jitter_over_delta` ≥ 1. die가 회차마다 다 같이 움직이는 ITEM(short, mA급). Δ가 없으면 열만 쓰고 상태는 붙이지 않음 | `RUN_JITTER_OVER_DELTA` = 1.0 |
| `작을수록 흔들림` | `spearman_size_jitter` ≤ −0.5이고 유효 die ≥ 10 | `SIZE_JITTER_RHO` = −0.5, `SIZE_JITTER_MIN_DIE` = 10 |
| `클수록 흔들림` | `spearman_size_jitter` ≥ +0.5이고 유효 die ≥ 10. 값이 큰 die일수록 log 범위가 큼 | `SIZE_JITTER_RHO_POS` = 0.5, `SIZE_JITTER_MIN_DIE` = 10 |
| `분해능 부족` | `resolution_step` ≥ 0.1·Δ. 값이 1개뿐이거나 Δ ≤ 0·NaN이면 건너뜀 | |
| `산포 0` | sigma_die = 0, 또는 `fixed_share` > 50%. 정량 zone이고 `분해능 부족`이면 판정 제외 | |
| `log 후보` | `decades` ≥ 1.0이고 `log_fit` > 0.1(LOG_FIT_MIN). `scale` `item`인 ITEM의 log 옵션 대상 | `LOG_DECADES_MIN` = 1.0, `LOG_FIT_MIN` = 0.1 |
| `두 덩어리` | `bimodality_log` > 5/9(≈ 0.556)이고 R이 유한한 die ≥ 10 (\|R\| ≥ 1E+90 die는 세지 않음) | `BIMODAL_BC_MIN` = 5/9, `BIMODAL_MIN_DIE` = 10 |
| `LoQ 근처` | LoQ ≤ \|POR 중앙값\| < LoQ / (10 r). accuracy 옵션 대상 (`accuracy_margin`이 있을 때) | |
| `조건 설정 오류` | 예약 값. 판정할 입력이 없어 지금은 판정하지 않음 | |

상태 지표 열 8개(`METRIC_COLS`)는 `por_gap_over_delta`, `por_gap_over_noise`, `run_jitter_pct`, `run_jitter_over_delta`, `spearman_size_jitter`, `resolution_step`, `resolution_over_delta`, `fixed_share`입니다. 상태와 상관없이 계산할 수 있으면 채우고, 못 하면 빈 칸입니다.
- `resolution_step` = POR 전 회차·DOE 값의 서로 다른 값 사이 최소 간격, `resolution_over_delta` = `resolution_step` / Δ
- `fixed_share` = R과 z 각각에서 가장 흔한 값의 die 비율 중 큰 쪽 (판정 제외 '고정값 NN%'와 같은 값)

분포 모양 열 5개(`SHAPE_COLS`)는 R(POR die별 회차 평균, 유한한 값만)로 구합니다. R에 0이 있거나 부호가 섞이면 `skew_lin` 말고는 빈 칸입니다. \|R\| ≥ 1E+90(Open 코드 등)인 die는 분포 모양 계산에서만 뺍니다.
- `decades` = log10(P99\|R\| / P1\|R\|). 값이 몇 자릿수에 걸쳐 있는지
- `skew_lin` = R의 Bowley 사분위 왜도 (Q3 + Q1 − 2·Q2) / (Q3 − Q1), `skew_log` = log10\|R\|의 같은 값 (범위 −1~1. IQR이 0이면 빈 칸)
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

`summary.txt` 구성: 구간 × 판정, 동등 아닌 사유, 정량·LoQ 미만 차이·미결 표(회차별 평균), 항목군별 판정, t-test로 판정했다면, 판정 근거 점검(회차 흔들림 몫, LoQ를 정한 쪽, blank가 바꾼 판정 수, 장비 정확도 폭을 쓰면 바뀔 판정 수), 입력 점검, 반복해서 튀는 die.

## 예제

```bash
python examples/make_por3_data.py p3
python por_doe_compare.py --por p3/por_run1 --por p3/por_run2 --por p3/por_run3 --doe p3/doe \
  --level p3/level.csv --blank p3/blank --blank-map p3/blank_map.csv --out p3/out
python summarize.py p3/out/items.csv
```

## 판정 그림 만들기

`plot_verdicts.py`는 `items.csv`로 요약 그림을 만들고, 원시 측정 데이터를 함께 주면 ITEM별 상세 그림도 만듭니다.

- **요약**은 기본으로 만듭니다. 판정 지도 `summary.png`와 `summary_loq.png`를 저장합니다. 읽는 법은 [아래](#판정-지도-summarypng).
  - `--xlim X`(기본 3)는 판정 지도 가로축 범위 ±X입니다. 밖의 값은 축 끝에 삼각형으로 붙입니다.
  - `--full`을 주면 모든 정량 ITEM을 그린 `summary_001.png`, `summary_002.png` …도 만듭니다. 한 장에는 최대 `--per-page`개의 ITEM을 넣습니다(기본 1200). 점은 차이/Δ의 중심이고 가로선은 90% 신뢰구간입니다.
  - `--groups FILE`(ITEM,group 두 열)을 주면 그룹마다 같은 모양의 `summary_group_<이름>.png`를 만듭니다. 파일에 없는 ITEM은 '(그룹 없음)'으로 모으고 경고를 냅니다.
- **상세**는 `--detail`을 줄 때만 만듭니다. 대상을 정하지 않으면 차이와 미결 ITEM을 그리고, `--items A,B`로 ITEM 코드를 고르거나 `--all`로 전체를 고릅니다. `--jobs N`은 상세 그림을 그리는 작업 프로세스 수입니다(기본 1).
- 그림에는 `item_map.csv`의 실제 항목 이름을 쓰지 않습니다. 상세 파일은 `detail/` 아래에 저장하며, 파일명은 ITEM 코드를 `safe_item_name()`에 통과시켜 만듭니다.

판정 제외 ITEM은 요약·LoQ 그림에서 빠지고, 경고 '판정 제외 n개'가 나옵니다.

`summary_loq.png` 읽는 법: 점 하나가 LoQ 아래 ITEM 하나입니다. 가로는 DOE 값 ÷ LoQ(1을 넘으면 DOE가 숫자로 보고됨), 세로는 이동량 ÷ 허용폭(1을 넘으면 허용폭보다 크게 움직임)이고 두 축 모두 로그 눈금입니다. 네 칸에 쉬운 이름을 적었습니다. 왼쪽 위 주황 칸은 둘 다 '<LoQ'로 보고되어 동등이지만 실제로는 움직였을 수 있는 곳입니다. `items.csv` 옆에 `review/loq_review.csv`가 있으면 LoQ 재확인이 '확인 필요'로 본 ITEM을 검은 마름모로 겹쳐 그립니다. 축 범위를 벗어난 값과 0인 값(로그 눈금에 못 그림)은 축 끝에 삼각형으로 그리고, 그 개수를 따로 적습니다. 색은 최종 판정입니다.

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
| 요약 (기본) | `plot_verdicts.py --items-csv` | 2.1 s (5장 + LoQ 1장, 판정 지도로 바뀌기 전 대시보드) | 199 MB | 500 KB |
| 상세 `--all`, `--jobs 1` | | 2,045 s (ITEM당 평균 0.34 s) | 714 MB | 447 MB (6,000장, 장당 평균 74 KB) |
| 상세 `--all`, `--jobs 4` | | 329 s (ITEM당 평균 0.055 s) | 714 MB | 447 MB |
| 요약 + 상세 `--all`, `--jobs 4` | | 330 s | 719 MB | 448 MB |

판정 지도로 바꾼 뒤 같은 6,000 ITEM 데이터의 요약(판정 지도 + LoQ 그림 2장)은 다른 기계(macOS, Apple 실리콘, Python 3.13.15, matplotlib 3.11.2)에서 1.25 s였습니다(3회 중앙값). 위 표와 기계가 달라 표의 숫자는 바꾸지 않았습니다.

`--jobs 1` 측정 중에는 다른 짧은 작업(테스트 실행)이 같은 기계에서 잠깐 겹쳐 실제보다 조금 느릴 수 있습니다. 전체 상세는 `--jobs 4` 이상을 쓰고, 보통은 요약과 `--items`로 고른 ITEM만 그립니다.

미결-해상도 부족 사례는 `examples/make_por3_data.py`의 `VT_NOISY_DOE`입니다. DOE die 값이 ±0.3 V로 고르게 퍼져 90% 신뢰구간 반폭이 Δ보다 큽니다. `examples/make_load_data.py`의 `IOFF_STEP` 템플릿은 DOE die 일부만 한 계단 올라가 중앙값 신뢰구간이 [0, 0]이므로 동등으로 판정됩니다.

요약은 `items.csv`만으로 빠르게 만들 수 있습니다.  
상세는 원시 데이터를 함께 주고, 필요한 ITEM만 골라 만드는 것이 좋습니다.

## 결과 읽기

판정은 `items.csv`가 정합니다. 아래 결과는 그 판정을 사람이 읽고, 의심 가는 ITEM을 데이터로 다시 확인하라고 만든 것입니다. 어느 것도 판정을 바꾸지 않습니다. 그림마다 아래에 "읽는 법"과 "이번 결과" 두 줄이 붙습니다.

### 판정 지도 (`summary.png`)

- 점 하나가 ITEM 하나입니다. 가로는 DOE가 움직인 양 ÷ 허용폭(0 = 그대로, ±1 = 허용폭만큼), 세로는 측정이 흔들리는 정도(90% 신뢰구간 반폭) ÷ 허용폭입니다.
- 가운데 아래 초록 삼각형(|x| + y ≤ 1)은 "같다 (동등)", 좌우 주황 칸(|x| − y > 1)은 "달라졌다 (차이)", 그 사이는 "경계에 걸침 (미결)", 위쪽은 "흔들려서 판단 불가 (미결)"입니다. 가로는 신뢰구간 가운데라서 점 색(최종 판정)과 칸이 늘 같습니다. die가 모자라 미결인 ITEM은 지도에 그리지 않습니다.
- 점 색은 최종 판정(`verdict_final`)입니다. log·장비 정확도 옵션이 판정을 정한 ITEM은 검은 테두리이고, 그 옵션의 이동·신뢰구간·허용폭 자리에 놓입니다.
- 맨 위 두 줄은 최종 판정별 개수와 판정 근거별 개수입니다. 오른쪽 위 막대는 차이·미결 ITEM이 + 방향(DOE가 높음)과 − 방향 중 어느 쪽으로 움직였는지 셉니다. 한쪽으로 몰리면 "이번 결과"에 공정 변화일 수 있다고 적습니다.
- LoQ 아래 ITEM은 이 지도에 없고 `summary_loq.png`에 있습니다.

### LoQ·log 판정 재확인 (`review/`)

`review.py`가 판정 뒤에 원데이터를 다시 읽어 두 가지를 봅니다. `dcc.py judge`와 `run_all.py`가 같이 돌립니다. 따로 돌리려면 `python review.py --input <items.csv> --out <폴더> --por ... --doe ...`입니다(원데이터 인자는 판정 때와 같게).

- **LoQ 재확인** (`loq_review.csv`, `loq_review.png`): LoQ 아래이거나 LoQ 근처인 ITEM은 "둘 다 '<LoQ'면 동등"으로 끝나서, 바닥 아래에서 실제로 늘어난 것이 가려질 수 있습니다. LoQ 규칙과 상관없이 die 대부분이 같은 방향으로 움직였는지(배수가 1.3배 넘게), 일부 die만 크게 벗어났는지(꼬리, 5% 이상)를 보고, 둘 중 하나가 여러 ITEM 동시 검정 보정(BH q < 0.05) 뒤에도 유의하면 "확인 필요"로 표시합니다.
- **log 재확인** (`log_review.csv`, `log_review.png`): log로 판정했거나 log 대상인 ITEM을 선형과 log로 나란히 보여 줍니다. 선형으로는 차이인데 log로 동등이 된 ITEM과, log 값에서 꼬리가 유의한 ITEM이 "확인 필요"입니다.
- `items/<ITEM>.png`: 확인 필요 ITEM마다 회차별 die 값, 같은 die의 POR·DOE 짝, die별 차이를 한 장에 그립니다.
- "확인 필요"는 다시 볼 ITEM 목록입니다. 판정에 넣을지는 결과를 보고 정합니다.

### 측정 안정도 (`stability/`)

같은 die를 POR로 다시 쟀을 때 얼마나 같게 나오는지 봅니다(참고, 판정에 안 씀). `por_doe_compare.py`가 판정 뒤에 같이 씁니다.

- `overall.csv`: 한 행. ITEM을 판정력(신뢰구간 반폭 ÷ 허용폭)으로 0.5 이하 안정, 0.8 이하 주의, 그 위 불안정으로 나눈 비율과 정밀도 중앙값 등. `groups.csv`는 같은 것을 그룹마다 씁니다(`--groups`를 줄 때만).
- `dies.csv`: die 위치마다 흔들림 점수(1이 보통). 여러 ITEM에서 같이 크게 흔들리는 die는 프로빙을 의심합니다.
- `runs.csv`: POR 회차마다 다른 회차 대비 밀린 정도. 회차 하나가 통째로 밀렸는지 봅니다.
- `stability.png`: 위 네 가지를 한 장에 그립니다.

### ITEM 한 장 보기 (`item_view.png`, `evidence.csv`)

`fail_evidence.py`가 원데이터를 받으면 ITEM 폴더(`items/<유형>_<ITEM>/`)마다 만듭니다. `dcc.py item`과 `dcc.py judge --detail`도 같은 것을 만듭니다.

- `item_view.png`: 맨 위 판정 카드(최종 판정과 근거, 이동량, 신뢰구간, 허용폭 구성, 쉬운 말 사유)와 같은 die의 POR·DOE 짝 그림, die별 차이 순서 막대, 웨이퍼맵(좌표가 있을 때), 값 분포, Blank(이 ITEM에 blank를 쓸 때)입니다.
- `evidence.csv`: 같은 근거를 한 행으로 적습니다. 신뢰구간 양 끝을 정한 die와 그 값, 올라간·내려간 die 수, 허용폭 구성, 튀는 die, LoQ 배수.

### 열 사전 ([`docs/sop/columns.html`](docs/sop/columns.html))

모든 결과 CSV의 열마다 쉬운 이름, 뜻, 수식, 볼 것을 한 쪽에 모았습니다. 내용은 `docs/columns/*.csv`에서 `python tools/build_columns_doc.py`로 만듭니다. 결과 폴더에 열 사전에 없는 열이 있는지는 `python columns_doc.py <결과 폴더>`로 확인합니다.

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

`python fail_evidence.py --input <items.csv> --out <폴더> [--items ID,...]` — por_doe_compare.py 결과 표(`--out` 폴더의 `items.csv`, 탭 구분 표도 됨. `ITEM` 열과 `<이름>_mean` 회차 열은 compare_before_after.py와 같은 방식으로 읽음)에서 verdict가 '차이'·'미결'인 ITEM의 근거를 규칙으로 계산해 `fail_evidence.csv`, `forest.png`, `summary.txt`, `items_index.csv`와 ITEM별 폴더 `items/<유형>_<ITEM>/`를 만듭니다. 폴더에는 항상 `summary.csv`가 있고, 원데이터(`--por`·`--doe`)를 주면 `raw.csv`(die별 원데이터, 행이 없으면 머리줄만)와 `item_view.png`, `evidence.csv`([아래](#item-한-장-보기-item_viewpng-evidencecsv)), status별 `status_<이름>.png`, log 진단 대상이면 `log_diag.png`가 붙습니다(log 진단만 하는 ITEM 폴더는 `summary.csv`·`raw.csv`·`log_diag.png`). `fail_evidence.csv` 첫 열은 실제 `ITEM` 이름이고, 익명 `ID` 열이 있으면 그 옆에 붙습니다. `--items`를 주면 그 ID만 ITEM 그림을 그립니다(CSV·forest는 전체). `--only ID,...`(`--items`와 같이 쓸 수 없음)는 차이·미결 기본 대상 없이 지정 ITEM(실제 이름 또는 익명 ID, 판정 제외 ITEM 포함)만 폴더를 만들고, 원데이터 DCNORMAL 파일도 읽을 때부터 그 ITEM 줄만 파싱하며(`infra_compare.read_dcnormal(..., items=)`, 결과는 전체를 읽고 거른 것과 같음) `fail_evidence.csv`·`forest.png`·`items_index`도 그 ITEM만 담습니다. 이 거르기의 속도는 `python tools/bench_read_only.py [--items 6000 --dies 60 --files 3 --pick 2 --repeat 3 --seed 0]`(합성 파일로 전체 읽기 후 거르기와 비교, 결과 동일 확인)로 잴 수 있습니다.

입력에 items.csv의 `status`, 데이터 상태 지표, 분포 모양 열(`por_doe_compare.py`의 `STATUS_COLS` 순서, `por_gap_over_delta`는 이 도구가 따로 계산해 뺌)과 `sigma_meas`, `meas_precision_pct`, `sigma_meas_over_delta` 열이 있으면 `fail_evidence.csv` 맨 끝에 이 순서로 값을 그대로 옮기고, 없으면 빈 칸 열로 둡니다(판정에는 쓰지 않음).

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

`python compare_before_after.py compare <기존_items.csv> <개선_items.csv> -o <폴더>` — 입력은 `por_doe_compare.py --out 폴더`의 `items.csv` 두 개(기존 실행, 개선 실행)입니다. `ITEM` 열을 비교 키로 읽고(`ITEM` 열이 없는 탭 구분 표는 `ID` 열), 회차 평균 열 `<이름>_mean`은 나온 순서대로 POR1, POR2로 읽습니다. 두 표를 ITEM으로 맞춰 ITEM별 σ_die·σ_run·Δ·CI 폭(|por_median| 대비 %)과 판정 변화를 `compare.csv`(`center_delta_before`·`center_delta_after` 열 포함), `summary.txt`, `stability_overall.csv`(전체 안정성 한 행, group_summary.py 결과의 '전체' 행과 같은 값), `worst_items.csv`(비율 지표별 악화 상위 N ITEM), 지표 그림 6장(`sigma_die_ratio.png`, `sigma_run_ratio.png`, `meas_precision_ratio.png`, `stability_sigma_die_pct.png`, `stability_meas_precision_pct.png`, `verdict_center_delta.png`)으로 냅니다. run_all.py에서는 `--before`만 주면(`--groups` 없이도) `결과/compare/`에 생깁니다. 출력 `compare.csv`와 `evidence.csv`의 첫 열은 실제 `ITEM` 이름이고, 입력에 summarize.py의 익명 `ID` 열이 같이 있으면 그 옆에 `ID` 열로 붙습니다. 비교 키는 항상 실제 ITEM입니다. 한쪽에만 있는 ITEM은 따로 표시하고 σ 집계에서 뺍니다. 정렬 의심 행(같은 ITEM인데 por_median 상대차 > 20%, 내부 기준)은 `misaligned` 열에 표시만 하고 기본으로 σ 집계에 포함합니다. 빼려면 `--exclude-misaligned`를 붙입니다. `compare.csv`에는 측정 정밀도 열 `meas_precision_pct_before`·`meas_precision_pct_after`·`meas_precision_pct_change`(개선−기존)와 `meas_precision_status`(`sigma_die_status`와 같은 규칙: lower/higher/same, 낮을수록 좋음)도 붙습니다. 입력 items.csv에 `meas_precision_pct` 열이 없으면(예전 결과) 100 × √(σ_die² + σ_run²) / |por_median|으로 계산합니다. `evidence <items.csv> -o <폴더>` 모드도 있고, 그 `evidence.csv`에도 같은 방식의 `meas_precision_pct` 열이 붙습니다. `evidence.csv`의 group은 fail_evidence.py와 같이 '차이'/'미결' 둘뿐입니다. `judgment` 바로 앞의 `status` 열에는 items.csv `status` 값을 그대로 옮기고(열이 없는 옛 items.csv면 빈 칸), status가 '정상'이 아니면 `judgment` 끝에 `원인(status): <status>`를 덧붙입니다. `evidence.csv`의 `por_gap_over_delta`(참고용, 판단에 쓰지 않음)도 fail_evidence.py와 같은 규칙입니다. items.csv의 짝지은 회차 차를 쓰고(`por_gap_def` = '짝지은 회차 차'), 열이 없는 옛 items.csv면 회차 평균의 max − min으로 계산하며(`por_gap_def` = '옛 정의(회차 평균 차)'), 그런 행이 있으면 `summary.txt`에 `por_gap: 옛 정의(회차 평균 차) n행 (items.csv에 짝지은 회차 차 열 없음)` 줄이 붙습니다.

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
