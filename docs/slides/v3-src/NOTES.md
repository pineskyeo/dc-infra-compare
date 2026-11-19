# NOTES — dc-equiv-criteria-v3 (2 slides)
- workflow: edit; last phase: finish (deck done). v2 data (old_fail_detail / improved_pass_detail) declared invalid by 정훈님; all derived content removed. v2 deck kept as dc-equiv-criteria-v2.pptx; v2 generator kept as build/deck.v2.js.
- source: build/deck.js (reads ../numbers.json, ../charts/*.png) -> build/post.sh (renders to renders/v3-N) ; final: office pptx clean + pack --original start.pptx -> dc-equiv-criteria-v3.pptx ; render renders/finish-v3/
- charts.py: reads /workspace/real_fail_11.tsv -> charts/s1_forest.png, charts/s2_axis.png, charts/s2_row_<ID>.png, numbers.json
- storyboard: 1 (slide1.xml) summary: left unchanged; 03 table = 신규 기준 판정 차이 2 / 미결 9, ITEM 수·동등 '정훈님 데이터 확인 후 입력'; forest chart center/Δ + CI for 11; 04 = 4 logic points; 결론 updated, 동등률 '확인 필요'. 2 (slide2.xml) '실제 Fail 11건 검토': 3 groups, per-ITEM mini strip (POR1/POR2/DOE % vs por_median, ±Δ band), 근거, 판단; 다음 조치 bar.
- groups (hard-coded in charts.py from Sec's reading, verified): 차이 F31_I3475,F65_I6106; 미결-정상 F54_I5492,F54_I5493,F61_I6003,F59_I5574; 미결-기준 F15_I1403,F23_I2064,F14_I1231,F31_I3583,F31_I3870
- design: LAYOUT_WIDE, Pretendard, NAVY 3D4C61, TINT EEF1F5
- left: none on render
