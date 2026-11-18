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

## 근거

- 반복 측정으로 흔들림 구하기: NIST/SEMATECH e-Handbook 2.4 (Gauge R&R), 2.6.1 (반도체 사례)
- MAD, robust σ: NIST e-Handbook 1.3.5.6
- LoD / LoQ: Currie 1968, IUPAC
- 분해능, 균일분포 불확도: GUM (JCGM 100) F.2.2.1, 4.3.7
- 동등성 검정: TOST (Schuirmann 1987), ASTM E2935
- 중앙값 부호검정 신뢰구간: Hollander & Wolfe, Nonparametric Statistical Methods
- t-test: NIST e-Handbook 7.3.1.1

허용폭의 정책 몫 r(기본 5%)은 표준이 정하지 않는 사내 정책 값입니다.

## infra_compare.py (이전 방식)

POR 1회(+ 일부 재측정)와 DOE 1회를 비교하던 첫 버전입니다. `python infra_compare.py --ref ref/ --new new/ --blank ... --blank-map ... --out 결과`. 새 분석에는 `por_doe_compare.py`를 쓰세요. `por_doe_compare.py`가 파일 읽기와 blank 읽기 함수를 여기서 가져다 씁니다.
