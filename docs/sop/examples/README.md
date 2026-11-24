# SOP 예제 ITEM (합성 데이터)

SOP 쪽마다 나오는 예제 숫자는 모두 여기서 만든다. 손으로 친 숫자는 없다.

- `journeys.py`: 유형마다 합성 ITEM 하나를 만들고(정량·선형, 실제 이동, log, LoQ 아래, 0 근처, 계단),
  실제 판정 도구(`por_doe_compare.py`)를 한 번 돌려 items.csv 의 숫자를 옮긴다.
  결과는 `journeys.json` 과 `../assets/journeys.js` (쪽이 file:// 로 열려도 읽히게 JS 로) 두 벌이다.
- `make_example.py`: 정량·선형 예제(EX_ITEM, seed 20263255)의 원데이터를 만든다. `journeys.py` 가 부른다.

다시 만들기 (저장소 루트에서):

    python docs/sop/examples/journeys.py           # 다시 쓴다
    python docs/sop/examples/journeys.py --check   # 커밋된 것과 다르면 실패 (테스트도 이것을 본다)
    python tools/build_sop.py                      # 쪽을 다시 만든다
