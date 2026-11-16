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
