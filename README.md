# dc-infra-compare

같은 웨이퍼, 같은 die를 두 테스트 인프라(Ref / New)에서 측정한 DCNORMAL 결과를 ITEM별로 비교해서 **동등 / 차이 / 미결**로 판정합니다.

## 판정 방법

ITEM마다 die별 차이 `d = New − Ref`를 구하고, 공통 shift가 허용폭 안인지 동등성 검정(TOST, 90% 신뢰구간)으로 봅니다.

| 값 | 계산 | 의미 |
|---|---|---|
| m | median(d) | 공통 shift |
| h | 1.645 × 1.2533 × robustσ(d) / √n | m의 90% 신뢰구간 반폭 (판정 해상도) |
| Δ | r × \|median(Ref)\| + 1.645 × σ₀ | 허용폭. r은 상대 허용(기본 1%), σ₀는 blank 노이즈 |

| 판정 | 조건 |
|---|---|
| 동등 | [m−h, m+h]가 ±Δ 안 |
| 차이 | [m−h, m+h]가 통째로 ±Δ 밖 |
| 미결 | 걸침. 사유: 해상도 부족(h ≥ Δ. 괄호에 die 적음 / 부호 섞임 / 계단값 / 흔들림 정보 없음), 경계 shift, die 부족 |

- blank σ₀ = MR̄ / 1.128. 이웃한 두 측정의 차이로 구한 단기 노이즈입니다.
- blank가 없는 ITEM은 Δ = r × \|median(Ref)\|만 씁니다. 0 근처 ITEM은 "해상도 부족 / blank 없음"으로 나옵니다.
- 쌍봉이나 튀는 die가 있어도 중앙값과 robust σ를 쓰기 때문에 판정이 끌려가지 않습니다. 튀는 die는 따로 목록으로 냅니다.

## blank가 있는 ITEM: LoB / LoD / LoQ 구간 (CLSI EP17, IUPAC)

blank 평균 μ와 표준편차 SD로 한계 3개를 구하고, Ref 값의 중앙값(|값|)이 어느 구간인지에 따라 판정 방식을 나눕니다.

| 한계 | 계산 |
|---|---|
| LoB | \|μ\| + 1.645 × SD |
| LoD | \|μ\| + 3.29 × SD |
| LoQ | \|μ\| + 10 × SD |

| 구간 | 판정 |
|---|---|
| 검출한계 이하 (< LoD) | 숫자 비교 안 함. die별 검출 일치로 판정 |
| 검출~정량 (LoD ~ LoQ) | 숫자 비교 안 함. die별 검출 일치로 판정 |
| 정량 (≥ LoQ) | 위 TOST |

LoQ 아래 값은 "<LoQ"로 보고하는 관례(IUPAC, CLSI EP17)대로 숫자를 비교하지 않습니다. die마다 |값| ≥ LoQ인지만 보고, 한쪽만 LoQ 이상인 die가 한 방향으로 치우치고(McNemar 정확 검정 p < 0.05) 그 순차이가 die의 5%를 넘으면 차이, 아니면 동등입니다. 둘 다 LoQ 아래면 둘 다 "<LoQ"이므로 같다고 봅니다. LoD 기준으로 더 엄격하게 보려면 `--strict-low`. 한쪽만 기준을 넘은 die 목록은 `mismatch_dies.csv`에 나옵니다.

허용폭이 해상도보다 작으면(h ≥ Δ) 노이즈 수준의 shift가 차이로 잡히므로 판정하지 않고 미결(해상도 부족)로 둡니다.

### POR 재측정으로 한계 계산 (권장)

같은 웨이퍼, 같은 die를 POR로 한 번 더 잰 파일을 `--ref` 폴더에 같이 넣으면, 그 ITEM은 POR끼리의 1회 측정 흔들림으로 LoB/LoD/LoQ를 정합니다(`limit_source` = POR 재측정). 장비, 컨택, 소자 흔들림이 다 들어 있고 DOE 쪽 흔들림은 섞이지 않습니다. LoQ 아래 항목 목록은 `low_items.csv`에 나옵니다.

### 측정값 자체의 흔들림으로 한계 계산

blank가 연결되지 않았거나, 실제 측정 흔들림이 blank보다 큰 ITEM은 측정값 자체를 blank로 봅니다.

- 1회 측정 흔들림 σ = robustσ(New − Ref) / √2. 같은 die끼리 빼서 공정 산포를 없애고, 두 번 측정한 몫(√2)을 나눕니다.
- LoB = 1.645σ, LoD = 3.29σ, LoQ = 10σ. 판정은 blank가 있을 때와 같습니다.
- 값이 흔들림보다 작은 ITEM(바닥 항목)은 검출한계 이하로 분류되어 die별 검출 일치로 판정됩니다. 정규화 단위(`/um`, `/cell`)도 단위 변환 없이 됩니다.
- 화면의 구간 표에 `(blank)` / `(자체 흔들림)`으로 출처가 나옵니다. `items.csv`의 `limit_source` 열에도 남습니다.

## 측정할 때마다의 흔들림 (Ref 재측정)

Ref에 같은 die, 같은 ITEM을 두 번 이상 잰 데이터가 있으면 ITEM별로 1회 측정의 흔들림을 구합니다.

- 회차 순서는 파일·행 순서입니다. 이웃한 회차끼리의 차이(2−1, 3−2, …)를 회차쌍마다 중앙값으로 맞춘 뒤 모아서 `rep_sigma` = robustσ(차이) / √2. POR을 3회 돌리면 3회 모두 씁니다.
- `rep_shift` = 회차쌍 shift 중 절댓값이 가장 큰 것 (회차마다 전체 값이 같이 움직이는 정도)
- 재측정이 없는 ITEM은 같은 항목군(ITEM 이름 앞쪽 영문자, `--family-regex`)의 상대 흔들림 중앙값 × |Ref 값|으로 추정합니다. 항목군에 재측정 ITEM이 3개 이상일 때만 씁니다.
- 허용폭의 노이즈 몫은 blank 노이즈와 재측정 흔들림 중 큰 값을 씁니다.
  Δ = r × |median(Ref)| + 1.645 × max(σ₀, rep_sigma)
- 뜻: 같은 인프라로 다시 재도 생기는 크기의 차이는 인프라 차이로 보지 않습니다.
- 끄려면 `--no-repeat`. 화면에 반영 전(blank만)과 반영 후 판정의 교차표가 나옵니다.

## POR 여러 회 + DOE: 동등 판정 (`por_doe_compare.py`)

POR을 같은 웨이퍼, 같은 die로 여러 번(권장 3회 이상, 매번 재터치다운) 재고 DOE를 1회 잰 데이터로 ITEM마다 동등 / 차이 / 미결을 판정합니다. t-test도 참고로 같이 냅니다.

```bash
python por_doe_compare.py --por run1/ --por run2/ --por run3/ --doe doe/ --out 결과폴더
```

`--por`는 회차마다 따로 씁니다. 하나의 `--por` 뒤에 파일이나 폴더를 여러 개 적으면 그 회차의 파일로 묶입니다. SPECLOW/SPECHIGH는 읽지 않습니다.

**기준은 실행 전에 정하는 값 세 개뿐입니다.** 데이터를 보고 바뀌는 문턱값은 없습니다.

| 값 | 기본 | 뜻 |
|---|---|---|
| `--r` | 0.05 | 정량 구간 허용폭 = r × \|POR 중앙값\| |
| `--det-margin` | 0.05 | LoQ 미만 구간 허용폭 = LoQ 넘는 die 비율 차이 5%p |
| `--estimator` | hl | 신뢰구간 방식. `hl` = Hodges–Lehmann + Wilcoxon 부호순위, `mean` = 평균 + t (NIST 7.3.1.1) |

**흔들림** (POR 회차 반복으로 die·회차 몫을 나눔, NIST e-Handbook 2.4.4. 튀는 die에 끌려가지 않도록 robust 통계 사용)

| 값 | 뜻 |
|---|---|
| `sigma_die` | 같은 die를 다시 잰 1회 측정 흔들림. 이웃 회차 차이(2−1, 3−2)를 회차쌍마다 중앙값으로 맞춘 뒤 robust σ(1.4826 × MAD) / √2 |
| `sigma_run` | 회차마다 전체가 같이 움직이는 크기 (컨택, 온도 등). die별 평균을 뺀 값의 회차별 중앙값으로 구함. 자유도 = 회차 수 − 1 |

분산분석(평균·제곱합) 값은 튀는 die 몇 개에도 몇 배로 부풀어서 비교용으로만 `sigma_die_anova`, `sigma_run_anova` 열에 남깁니다. LoQ 미만 구간의 0/1 여부 데이터는 MAD가 0이 되므로 분산분석을 씁니다.

**구간.** σ = max(`sigma_die`, 데이터 분해능 / √12, 장비 분해능 / √12)로 LoD = 3.29σ, LoQ = 10σ를 정합니다(Currie, IUPAC). blank LoQ가 더 크면 blank 쪽을 씁니다. `limit_source` 열에 한계를 정한 쪽(POR 반복 / 데이터 분해능 / 장비 분해능 / blank)이 나옵니다.

- 데이터 분해능: 결과 파일 값 사이의 가장 작은 간격. 계단값 항목은 반복해도 같은 값이 나와 `sigma_die`가 0이 되므로 간격 / √12(GUM F.2.2.1)를 하한으로 씁니다. 가공된 값(CALCVAL)이라도 비교하는 숫자 자체의 눈금이라 그대로 쓸 수 있고, 값이 계단으로 찍히지 않은 ITEM은 간격이 아주 작아 영향이 없습니다.
- 장비 분해능, blank: 아래 `--level`, `--blank`.

**판정.** 두 구간 모두 같은 TOST 규칙이고 비교하는 양만 다릅니다.

| 구간 (\|POR 중앙값\|) | 비교하는 양 (die별) | 허용폭 Δ |
|---|---|---|
| 정량 (≥ LoQ = 10σ) | d = DOE − POR 회차 평균 | r × \|POR\| + t(0.95, J−1) × √(1 + 1/J) × `sigma_run` |
| LoQ 미만 | "\|값\| ≥ LoQ" 여부(0/1)의 DOE − POR 회차 평균 | det_margin + t(0.95, J−1) × √(1 + 1/J) × 여부의 `sigma_run` |

- t(0.95, J−1) × √(1 + 1/J) × `sigma_run`은 같은 프로그램으로 다시 재도 생기는 회차 간 차이입니다. DOE 1회가 POR J회 평균에서 벗어날 수 있는 90% 예측구간의 한쪽 폭이고, `sigma_run`을 회차 J개로만 추정해서 자유도가 J − 1이라 1.645 대신 t를 씁니다(J = 3이면 2.92, 5면 2.13, 10이면 1.83). 회차마다 중심이 크게 움직이는 항목은 이 몫이 커집니다. 그 안의 차이는 프로그램 차이로 보지 않습니다. 회차를 늘리면 t가 작아지고 `sigma_run`도 정확해집니다.
- 90% 신뢰구간이 ±Δ 안이면 동등, 통째로 밖이면 차이, 걸치면 미결(신뢰구간 반폭 ≥ Δ면 해상도 부족, 아니면 경계).
- **LoQ 미만은 "<LoQ 보고 일치".** LoQ 미만 값은 숫자가 아니라 "<LoQ"로 보고하므로(IUPAC), 두 조건이 모두 맞을 때만 차이이고 그 밖은 동등입니다. ① LoQ 넘는 die 비율 차이의 신뢰구간이 통째로 ±Δ 밖. ② die 중심 이동(값 척도 Hodges–Lehmann)의 신뢰구간이 POR 회차 흔들림 예측구간(r × \|POR\| + t × √(1 + 1/J) × `sigma_run`) 밖. 문턱 근처에서는 중심이 조금만 움직여도 넘는 비율이 크게 바뀌어서, 비율만 보면 POR 회차끼리의 이동보다 작은 차이도 크게 보이기 때문입니다. 값 척도 결과는 `value_center`, `value_ci_low`, `value_ci_high`, `value_delta`, `value_beyond_run` 열. die 61개로는 비율 차이 ±5%p 안을 증명하기 어려워서, 차이의 증거가 있을 때만 차이로 봅니다. TOST 그대로의 판정은 `verdict_tost_low`, DOE 비율이 POR 회차 범위 밖인지는 `doe_det_outside_por` 열에 남습니다. TOST 그대로 판정하려면 `--strict-low-tost`.
- Hodges–Lehmann은 die별 차이의 모든 두 개 평균(Walsh 평균)의 중앙값입니다. 분포 가정이 없고 튀는 die에 끌려가지 않아서, 평균과 robust 방식을 데이터로 골라 쓰는 문턱값이 필요 없습니다.
- t-test(`ttest`, `ttest_p`)는 참고용이며 판정에 쓰지 않습니다. `por_ttest_sig`는 POR 회차끼리 t-test를 했을 때 유의차가 나온 쌍의 수입니다.

| 옵션 | 내용 |
|---|---|
| `--blank`, `--blank-map` | blank 데이터와 연결표. 형식은 아래 "blank 넣기"와 같음 |

**blank.** blank는 원측정값(A, V 기본 단위)이고 결과 값은 가공됐을 수 있습니다. 그래서 `--level` 표에서 **변형이 아니고 CALCVAL이 있는 ITEM에만** blank 한계(LoD = \|μ\| + 3.29 SD, LoQ = \|μ\| + 10 SD)에 CALCVAL을 곱해 ITEM 단위로 바꿔 씁니다. 나머지는 쓰지 않습니다(`blank_status`: 변형 / CALCVAL 없음 / level.csv 없음). 바꾼 한계(`blank_LoQ_item`)가 POR 반복으로 구한 한계보다 크면 blank 쪽을 씁니다.

**UNIT은 판정에 쓰지 않습니다.** DCNORMAL의 UNIT 값이 잘못 들어간 경우가 많아서, 판정은 값과 POR 반복 흔들림만으로 합니다. 판정이 모두 비율 기준(허용폭은 POR 값의 r배, LoQ는 그 ITEM 흔들림의 10배)이라 값의 단위나 정규화 계수가 무엇이든 결과가 같습니다. UNIT 열은 결과 표시용으로만 옮깁니다.

**ITEM 정보 표 (`--level`, 선택).** ITEM마다 원측정값의 크기와 가공 방식을 주면 장비 사양(Keysight P9001A Per-pin SMU)과 blank를 정확하게 씁니다. UNIT은 여전히 보지 않습니다.

```
ITEM,LEVEL,CALCVAL,DERIVED
IOFF_N1,10fA,1e12,N     ← 원측정값 10~100 fA, 파일 값 = 원측정값 × 1e12 (pA로 찍힘)
ION_N1,100nA,,N         ← CALCVAL 모름
VT_N1,,,Y               ← 변형 값 (여러 측정 조합·추출, 예: Vt 추출, 저항 = V / I, 비율)
```

| 열 | 뜻 |
|---|---|
| LEVEL | 원측정값 \|값\|의 자릿수 아래 끝. 10fA = 10~100 fA, 1nA = 1~10 nA. 표기 1fA … 100mA, 1uV … 1V (A, V는 사양 적용), 100fF … 100pF, 10kHz … 1MHz (기록만) |
| CALCVAL | 파일 값 = 원측정값 × CALCVAL (단위 환산, 정규화 포함). 모르면 비움 |
| DERIVED | Y = 변형 값. 원측정값의 배율이 아니라서 장비 사양과 blank를 쓰지 않음 (LEVEL 비워도 됨) |

| 경우 | 장비 분해능·정확도 | blank |
|---|---|---|
| 변형 (DERIVED = Y) | 안 씀 | 안 씀 |
| 변형 아님 + CALCVAL 있음 | 실제 값 = \|POR 중앙값\| / CALCVAL로 정확히 환산 | × CALCVAL 해서 씀 |
| 변형 아님 + CALCVAL 없음 | 실제 값을 자릿수 상한 10L로 보수적으로 환산 (장비 분해능·정확도를 실제보다 작게 잡는 쪽) | 안 씀 |
| 표에 없음 | 안 씀 | 안 씀 |

- CALCVAL로 환산한 실제 값이 LEVEL 자릿수와 다르면 `level_check` 열과 화면에 경고가 나옵니다. CALCVAL이나 LEVEL 입력 실수를 잡는 용도입니다.
- auto range: `measure_i`/`measure_v`에 range 0을 주면 값이 들어가는 가장 작은 range를 씁니다(Programming Reference Table 2-19, 2-22). `range_por`, `range_doe`, `range_changed` 열. 바닥(LoQ 미만) ITEM은 DOE range를 정하지 않습니다.
- 분해능 하한: σ ≥ range 측정 분해능 / √12 (GUM F.2.2.1). `limit_source` = 장비 분해능.
- `--accuracy`: 두 측정이 각자 사양 정확도 ±(a × |값| + b × range + c) 안에 있을 때 생길 수 있는 차이 1.645 × √((U_POR² + U_DOE²) / 3) (균일분포, GUM 4.3.7)를 정량 구간 허용폭 하한으로 씁니다. 사양의 Vo, Rres × Io 항은 0으로 둡니다. 정확도 없이 낸 판정은 `verdict_no_accuracy`, 허용폭을 정한 쪽은 `delta_source`.
- 사양 값은 `por_doe_compare.py`의 `I_RANGES`, `V_RANGES` 표 (P9001 Data sheet p.6-7). 원본과 대조해서 쓰세요.

**결과 파일**

| 파일 | 내용 |
|---|---|
| `items.csv` | ITEM별 판정, 신뢰구간, 허용폭 구성(`policy_margin`, `run_margin`), 회차별 평균(`POR1_mean` … `DOE_mean`), LoQ 미만은 회차별 LoQ 넘는 die 비율(`POR1_det` … `DOE_det`) |
| `outlier_dies.csv` | ITEM마다 \|d − 중앙값\| > 5 robust σ인 die (확인용. 판정에는 쓰지 않음) |

예제: `python examples/make_por3_data.py p3` 후 `python por_doe_compare.py --por p3/por_run1 --por p3/por_run2 --por p3/por_run3 --doe p3/doe --blank p3/blank --blank-map p3/blank_map.csv --level p3/level.csv --out p3/out`

### 결과 요약 (공유용, ITEM 이름 익명화)

```bash
python summarize.py 결과폴더/items.csv
```

- `summary.txt`: 판정 표, t-test x TOST, POR끼리 t-test, 흔들림 비율, 허용폭 구성, 이상 신호, 항목군별 판정, 차이·미결 ITEM의 회차별 평균(DOE가 POR 회차들의 퍼짐 밖인지), 여러 ITEM에서 반복해서 튀는 die, 차이·미결 목록. ITEM 이름 대신 `F03_I0123` 같은 익명 번호가 나옵니다.
- `item_map.csv`: 익명 번호와 실제 ITEM의 대응표. 공유하지 말고 로컬에서 찾아볼 때만 씁니다.
- `items.csv`에도 ITEM 바로 옆에 같은 익명 번호가 `ID` 열로 들어갑니다(다시 실행해도 같은 번호).
- 항목군 이름(VT, ION 등)도 기본으로 `F01`처럼 바꿉니다. 그대로 두려면 `--keep-family`.

## 패턴 리포트

동등이 아닌 ITEM이 어디에 몰리는지 봅니다. `흔들림_중앙값`은 die별 차이의 흔들림 ÷ |Ref 값|입니다.

| 파일 | 묶는 기준 |
|---|---|
| `patterns_family.csv` | 항목군 |
| `patterns_level.csv` | 단위와 값의 자릿수 (예: `A 1e-12`) |

## 설치

```bash
pip install -r requirements.txt   # Python 3.9+
```

## 실행

```bash
python infra_compare.py --ref ref폴더/ --new new폴더/ --blank blank.csv --blank-map map.csv --out 결과폴더
```

| 옵션 | 내용 |
|---|---|
| `--ref`, `--new` | DCNORMAL 파일이나 폴더 (여러 개 가능, 확장자 없는 파일도 인식) |
| `--key` | 짝짓기 키. 기본 `WAFERID,COORD_X_Y,ITEM` (다른 좌표를 쓰면 `FLAT_X_Y`, `DIE_X_Y`로 변경) |
| `--blank` | blank 데이터 (아래 형식) |
| `--blank-map` | 제품 ITEM과 blank 이름 연결표 |
| `--r` | 상대 허용폭. 기본 0.01 (1%) |
| `--strict-low` | LoQ 아래 항목을 LoD 기준으로 비교 (바닥 offset 차이까지 잡음) |
| `--verbose` | 입력 요약, 재측정 반영 전후, 항목군·값 구간 표까지 화면에 출력. 기본은 판정 표와 사유만 |
| `--no-repeat` | Ref 재측정 흔들림을 허용폭에 넣지 않음 |
| `--family-regex` | 항목군을 뽑는 정규식. 기본 `^[A-Za-z]+` |
| `--encoding` | 기본 `auto`: UTF-8로 읽고 안 되면 CP949. 다른 인코딩은 직접 지정 (예: `euc-kr`) |

같은 키가 여러 번 나오면 중앙값을 쓰고 개수를 결과에 남깁니다.

## blank 넣기

가장 쉬운 형식은 **가로형 CSV**입니다. 맨 윗줄에 blank 조건 이름을 쓰고, 그 아래에 측정값을 측정 순서대로 붙입니다. 단위는 DCNORMAL과 같게 맞춥니다(A, V, F).

```
OPEN_I_1PA,OPEN_I_10PA,SHORT_V
1.2e-12,3.1e-12,0.00012
-0.8e-12,-1.5e-12,-0.00008
...
```

제품 ITEM 이름과 다르면 연결표를 만듭니다. 같은 측정 종류, 같은 range끼리 연결합니다.

```
ITEM,BLANK_ITEM
IOFF_N1,OPEN_I_1PA
VT_N1,SHORT_V
```

그 밖에 읽을 수 있는 형식은 다음과 같습니다.
- DCNORMAL blank 결과 파일이나 폴더
- CSV `ITEM,VALUE` (세로형 원측정값)
- CSV `ITEM,SIGMA0` (σ₀를 이미 계산한 경우)

blank 측정 구성은 전류와 용량은 open, 전압은 short입니다.

## 결과

| 파일 | 내용 |
|---|---|
| `items.csv` | ITEM별 판정. 차이, 미결, 동등 순. `zone`, `verdict`, `reason`, `LoB`, `LoD`, `LoQ`, `n_mismatch_die`, `shift_m`, `h`, `delta`, `sigma0`, `n_outlier_die` 등 |
| `mismatch_dies.csv` | 검출 불일치 die (검출한계 이하, 검출~정량 구간) |
| `outlier_dies.csv` | 공통 shift에서 robust σ의 5배 넘게 벗어난 die |
| `blank_sigma.csv` | blank 조건별 σ₀. `blank_drift_ratio`가 1보다 확연히 크면 blank에 드리프트가 있음 |

## 예제 데이터로 확인

```bash
python examples/make_test_data.py td
python examples/add_hard_cases.py td   # 선택: 부호 섞임, 계단값, blank보다 큰 흔들림
python infra_compare.py --ref td/ref --new td/new --blank td/blank td/blank_summary.csv --blank-map td/blank_map.csv --out td/out
```

합성 데이터의 10개 ITEM(정상, shift, 경계, 바닥 노이즈, blank 없음, offset, 검출~정량, 쌍봉, 튀는 die)에 대해 기대 판정이 함께 출력됩니다.

## 근거

- 동등성 판정: TOST (Schuirmann 1987), ASTM E2935
- 차이 기반 비교: Bland & Altman 1986
- blank 기반 노이즈 한계: ISO 11843, IUPAC (Currie)
- LoB / LoD / LoQ: CLSI EP17, IUPAC
- 단기 노이즈 MR̄/1.128: NIST/SEMATECH e-Handbook of Statistical Methods (관리도)

상대 허용폭 r은 표준이 정하지 않는 사내 정책 값입니다.
