# dc-infra-compare

같은 웨이퍼, 같은 die를 POR(기존 프로그램)로 여러 번, DOE(새 프로그램)로 한 번 잰 DCNORMAL 결과를 ITEM별로 비교해서 **동등 / 차이 / 미결**로 판정합니다.

원칙은 하나입니다. **DOE와 POR의 차이가, POR을 자기 자신과 다시 잰 차이보다 크지 않으면 같다고 본다.**

판정 흐름과 기법별 수식, 시각화는 [`docs/method.html`](docs/method.html)에 있습니다. GitHub 화면에서는 소스만 보이니, 내려받아 브라우저로 여세요.

## 설치

```bash
pip install -r requirements.txt   # Python 3.9+, pandas, numpy, scipy
```

## 실행

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

| 구간 (\|POR 중앙값\|) | 판정 |
|---|---|
| 정량 (≥ LoQ) | 신뢰구간이 ±Δ 안 → **동등**, 통째로 밖 → **차이**, 걸침 → **미결** (반폭 ≥ Δ면 해상도 부족, 아니면 경계) |
| LoQ 미만 | LoQ 미만 값은 "<LoQ"로 보고합니다(IUPAC). 신뢰구간이 통째로 ±Δ 밖이고 **DOE 중심(POR 중앙값 + shift)이 LoQ 이상**이라 보고가 달라질 때만 **차이**, 그 밖은 **동등**("<LoQ 보고 일치") |

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
| `items.csv` | ITEM별 판정. 차이, 미결, 동등 순 |
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

- **요약**은 기본으로 만듭니다. `summary_001.png`부터 장을 나누어 저장하며, 한 장에는 최대 `--per-page`개의 ITEM을 넣습니다(기본 1200). 점은 차이/Δ의 중심이고 가로선은 90% 신뢰구간입니다. LoQ 미만 ITEM을 모은 `summary_loq.png` 패널도 함께 만듭니다.
- **상세**는 `--detail`을 줄 때만 만듭니다. 대상을 정하지 않으면 차이와 미결 ITEM을 그리고, `--items A,B`로 ITEM 코드를 고르거나 `--all`로 전체를 고릅니다. `--jobs N`은 상세 그림을 그리는 작업 프로세스 수입니다(기본 1).
- 그림에는 `item_map.csv`의 실제 항목 이름을 쓰지 않습니다. 상세 파일은 `detail/` 아래에 저장하며, 파일명은 ITEM 코드를 `safe_item_name()`에 통과시켜 만듭니다.

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

`python fail_evidence.py --input <items.csv> --out <폴더> [--items ID,...]` — por_doe_compare.py 결과 표(`--out` 폴더의 `items.csv`, 탭 구분 표도 됨. `ITEM` 열과 `<이름>_mean` 회차 열은 compare_before_after.py와 같은 방식으로 읽음)에서 verdict가 '차이'·'미결'인 ITEM의 근거를 규칙으로 계산해 `fail_evidence.csv`, `forest.png`, `items/<ID>.png`, `summary.txt`를 만듭니다. `fail_evidence.csv` 첫 열은 `ITEM`입니다. `--items`를 주면 그 ID만 ITEM 그림을 그립니다(CSV·forest는 전체).

열은 이름으로 찾습니다(`POR{k}_mean`은 2개 이상, k 가변). 대상 행에서 `por_median DOE_mean center ci_low ci_high delta LoQ` 열이 없거나 값이 빈칸·숫자 아님(엑셀 넘침 `####`, `***` 등)이면, 또는 값이 있는 POR 회차가 2개 미만이면 judgement='계산 불가'로 쓰고 사유를 note에 남깁니다. 빈 `POR{k}_mean`은 그 회차가 없는 것으로 봅니다. 대상이 아닌 행은 '대상 아님'으로 CSV에만 남깁니다.

| 상수 | 값 | 뜻 |
|---|---|---|
| `POR_GAP_OVER_DELTA` | 0.25 | (max POR_mean − min POR_mean)/Δ |
| `MEDIAN_OUT_OVER_DELTA` | 0.10 | por_median이 POR·DOE 평균들의 [min, max] 밖으로 벗어난 거리/Δ |
| `ITEM_AXIS_OVER_DELTA` | 3 | ITEM 그림 x축 범위 ±3·Δ% (밖은 화살표+숫자) |

내부 기준 값이며 비율은 소수 9자리로 반올림한 뒤 비교합니다. 분류(위에서부터 먼저 맞는 것):

1. **차이**: CI 전체가 ±Δ 밖 (ci_high < −Δ 또는 ci_low > Δ)
2. **미결-기준 흔들림**: por_gap/Δ ≥ `POR_GAP_OVER_DELTA` 또는 median_out/Δ ≥ `MEDIAN_OUT_OVER_DELTA`
3. **미결-정상**: 나머지 (POR 일치, CI가 Δ 경계에 걸림)

verdict와 규칙 결과가 어긋나면 note에 'verdict와 다름'을 적습니다.

## 기존·개선 비교 (`compare_before_after.py`)

`python compare_before_after.py compare <기존_items.csv> <개선_items.csv> -o <폴더>` — 입력은 `por_doe_compare.py --out 폴더`의 `items.csv` 두 개(기존 실행, 개선 실행)입니다. 첫 열 `ITEM`은 ID로 읽고(탭 구분 표의 `ID` 열도 됨), 회차 평균 열 `<이름>_mean`은 나온 순서대로 POR1, POR2로 읽습니다. 두 표를 ITEM으로 맞춰 ITEM별 σ_die·σ_run·Δ·CI 폭(|por_median| 대비 %)과 판정 변화를 `compare.csv`, `summary.txt`, σ 짝 비교 그림으로 냅니다. 출력 `compare.csv`와 `evidence.csv`의 첫 열은 `ITEM`입니다. 한쪽에만 있는 ITEM과 정렬 의심 행(같은 ITEM인데 por_median 상대차 > 20%, 내부 기준)은 따로 표시하고 σ 집계에서 뺍니다. `evidence <items.csv> -o <폴더>` 모드도 있습니다.

## 그룹별 요약 (`group_summary.py`)

`python group_summary.py --compare compare.csv --groups 그룹.csv --out group_out` — `compare_before_after.py compare`가 만든 `compare.csv`를 ITEM 그룹별로 요약합니다. 그룹 파일은 첫 열 ITEM, 둘째 열 그룹(쉼표 또는 탭, 헤더는 있어도 없어도 됨)이고, 그룹 파일에 없는 ITEM은 '미지정'으로 묶습니다. presence=matched이고 misaligned=False인 행만 씁니다. 출력은 `group_summary.csv`(맨 위 '전체' 행), `verdict_by_group.csv`(그룹별 판정 변화), `ratio_hist.png`(σ_die 개선/기존 비 히스토그램), `density_die.png`(σ_die 기존 대 개선 산점도), `group_panel.png`(그룹별 비교, 그룹 10~20개 기준)입니다.

## infra_compare.py (이전 방식)

POR 1회(+ 일부 재측정)와 DOE 1회를 비교하던 첫 버전입니다. `python infra_compare.py --ref ref/ --new new/ --blank ... --blank-map ... --out 결과`. 새 분석에는 `por_doe_compare.py`를 쓰세요. `por_doe_compare.py`가 파일 읽기와 blank 읽기 함수를 여기서 가져다 씁니다.
