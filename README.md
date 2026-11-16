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
| 미결 | 걸침. 사유: 해상도 부족(h ≥ Δ), 경계 shift, die 부족 |

- blank σ₀ = MR̄ / 1.128. 이웃한 두 측정의 차이로 구한 단기 노이즈입니다.
- blank가 없는 ITEM은 Δ = r × \|median(Ref)\|만 씁니다. 0 근처 ITEM은 "해상도 부족 / blank 없음"으로 나옵니다.
- 쌍봉이나 튀는 die가 있어도 중앙값과 robust σ를 쓰기 때문에 판정이 끌려가지 않습니다. 튀는 die는 따로 목록으로 냅니다.

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
| `items.csv` | ITEM별 판정. 차이, 미결, 동등 순. `verdict`, `reason`, `shift_m`, `h`, `delta`, `sigma0`, `n_outlier_die` 등 |
| `outlier_dies.csv` | 공통 shift에서 robust σ의 5배 넘게 벗어난 die |
| `blank_sigma.csv` | blank 조건별 σ₀. `blank_drift_ratio`가 1보다 확연히 크면 blank에 드리프트가 있음 |

## 예제 데이터로 확인

```bash
python examples/make_test_data.py td
python infra_compare.py --ref td/ref --new td/new --blank td/blank td/blank_summary.csv --blank-map td/blank_map.csv --out td/out
```

합성 데이터의 9개 ITEM(정상, shift, 경계, 바닥 노이즈, blank 없음, offset, 쌍봉, 튀는 die)에 대해 기대 판정이 함께 출력됩니다.

## 근거

- 동등성 판정: TOST (Schuirmann 1987), ASTM E2935
- 차이 기반 비교: Bland & Altman 1986
- blank 기반 노이즈 한계: ISO 11843, IUPAC (Currie)
- 단기 노이즈 MR̄/1.128: NIST/SEMATECH e-Handbook of Statistical Methods (관리도)

상대 허용폭 r은 표준이 정하지 않는 사내 정책 값입니다.
