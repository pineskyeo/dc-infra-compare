"""explain.py: 숫자 표기, 판정 사유 문장, ITEM 판정 카드, 그림 아래 두 줄. 손으로 만든 items.csv 행."""
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from explain import NOTE_FONTSIZE, add_figure_note, fmt, pct, reason_plain, verdict_card  # noqa: E402
from plot_verdicts import configure_font  # noqa: E402

NAN = math.nan


@pytest.mark.parametrize("args, text", [
    ((0.0000123, "A"), "12.3 µA"),
    ((0.030, "V", True), "+30 mV"),
    ((-2.5e-12, "[A]"), "-2.5 pA"),
    ((999.96e-6, "A"), "1 mA"),
    ((100, "ohm"), "100 Ω"),
    ((0, "V"), "0 V"),
    ((0.45, "u"), "0.45 u"),
    ((1234.5,), "1.23e+03"),
    ((NAN, "A"), "-"),
    ((None,), "-"),
    (("", "V"), "-"),
])
def test_fmt(args, text):
    assert fmt(*args) == text


@pytest.mark.parametrize("part, whole, text", [
    (0.03, 0.45, "+6.7%"), (-0.0011, 0.45, "-0.24%"), (1, -2, "+50.0%"), (0, 1, "0%"),
    (1, 0, "-"), (1, NAN, "-"), (NAN, 1, "-"), ("x", 1, "-"),
])
def test_pct(part, whole, text):
    assert pct(part, whole) == text


@pytest.mark.parametrize("row, text", [
    ({"reason": "90% 신뢰구간이 ±Δ 안"}, "이동량 범위(90% 신뢰구간) 전체가 허용폭 안이라 같다고 본다."),
    ({"reason": "shift +0.02996가 ±Δ(0.02256) 밖"}, "이동량 범위(90% 신뢰구간) 전체가 허용폭 밖이라 달라졌다고 본다."),
    ({"reason": "경계 (신뢰구간이 Δ에 걸침)"}, "이동량 범위가 허용폭 경계에 걸쳐 있다. 같다고도 다르다고도 할 수 없다."),
    ({"reason": "해상도 부족 (신뢰구간 반폭 ≥ Δ)"},
     "측정이 흔들려 이동량 범위가 허용폭보다 넓다. 같은지 다른지 판단할 수 없다."),
    ({"reason": "<LoQ 보고 일치 (이동이 ±Δ 안)"},
     "POR 값이 정량 한계(LoQ) 아래라 둘 다 '<LoQ'로 보고되고, 이동도 허용폭 안이다."),
    ({"reason": "<LoQ 보고 일치 (DOE 중심도 LoQ 미만)"},
     "이동은 허용폭 밖이지만 DOE도 정량 한계(LoQ) 아래에 머물러 둘 다 '<LoQ'로 보고된다."),
    ({"reason": "DOE 중심 2.1e-11가 LoQ(1.652e-11) 이상이고 이동 +2e-11가 ±Δ(4.9e-15) 밖"},
     "POR은 정량 한계(LoQ) 아래인데 DOE가 LoQ 위로 올라가 보고 값이 달라진다."),
    ({"reason": "die 6개 (< 10)"}, "die가 6개뿐이라 판정하기에 부족하다 (10개 이상 필요)."),
    ({"reason": "판정 제외: 회차 0값 (POR2); 모든 값 같음"},
     "판정에서 뺐다. POR2 값만 die 절반 넘게 0이다, POR·DOE 값이 모두 같다."),
    ({"reason": "판정 제외: 중심·신뢰구간 계산 불가 (center, ci_low)"}, "판정에서 뺐다. 이동량이나 신뢰구간을 계산할 수 없다."),
    ({"reason": "판정 제외: die 산포 0 (고정값 80%)"}, "판정에서 뺐다. die 값이 고정되어 있어 흔들림을 잴 수 없다."),
    ({"reason": "판정 제외: 고정값 (중앙값 0·σ_run 0)"}, "판정에서 뺐다. 값이 0에 고정되어 있다."),
    ({"reason": "판정 제외: 최종 Δ가 0 이하이거나 유효하지 않음 (Δ=0, 출처 정책 + 회차)"},
     "판정에서 뺐다. 허용폭이 0 이하라 정할 수 없다."),
    ({"verdict_basis": "log", "reason": "경계 (신뢰구간이 Δ에 걸침)", "log_reason": "90% 신뢰구간이 ±Δ 안"},
     "log 값(배율)으로 보면 이동량 범위(90% 신뢰구간) 전체가 허용폭 안이라 같다고 본다."),
    ({"verdict_basis": "accuracy", "reason": "shift +3.3e-06가 ±Δ(1.6e-06) 밖"},
     "LoQ 근처라 허용폭을 장비 정확도 폭까지 넓히면 이동량 범위 전체가 그 안이라 같다고 본다."),
    ({"reason": "새 사유 문구"}, "새 사유 문구"),
])
def test_reason_plain_every_family(row, text):
    assert reason_plain(row) == text


VT_SHIFT = {"ITEM": "VT_SHIFT", "UNIT": "V", "verdict_final": "차이", "verdict_basis": "linear", "verdict": "차이",
            "zone": "정량", "reason": "shift +0.02996가 ±Δ(0.02256) 밖", "n_die": 61, "center": 0.02995881,
            "ci_low": 0.02976098, "ci_high": 0.03037213, "delta": 0.02256272, "policy_margin": 0.02256272,
            "run_margin": 0.0, "por_median": 0.4512543, "LoQ": 0.01109464, "sigma_meas": 0.001109464,
            "meas_precision_pct": 0.245862}


def test_card_quantified_difference():
    assert verdict_card(VT_SHIFT, dies_up=61, dies_down=0) == [
        "VT_SHIFT · 차이 (기본 판정)",
        "DOE가 POR보다 +30 mV (+6.6%) 높다. die 61개 중 61개에서 DOE가 높고 0개에서 낮다.",
        "실제 이동량은 +29.8 mV ~ +30.4 mV 사이로 본다 (90% 신뢰구간).",
        "같다고 보는 범위는 ±22.6 mV다 = 값의 5% 22.6 mV + 회차 흔들림 0 V.",
        "→ 이동량 범위(90% 신뢰구간) 전체가 허용폭 밖이라 달라졌다고 본다.",
        "같은 die를 다시 재면 ±1.11 mV (0.246%) 흔들린다. 정량 한계 11.1 mV의 40.7배 위에서 잰 값이다.",
    ]


def test_card_loq_zone_has_no_percent_and_explains_loq():
    row = {"ITEM": "IOFF_LEAK", "UNIT": "A", "verdict_final": "동등", "verdict_basis": "linear", "verdict": "동등",
           "zone": "검출한계 이하", "reason": "<LoQ 보고 일치 (DOE 중심도 LoQ 미만)", "n_die": 61,
           "center": 5.858201e-13, "ci_low": 2.354243e-13, "ci_high": 1.556112e-12, "delta": 4.894006e-15,
           "policy_margin": 4.894006e-15, "run_margin": 0.0, "por_median": -9.788012e-14, "LoQ": 1.652256e-11}
    assert verdict_card(row) == [
        "IOFF_LEAK · 동등 (기본 판정)",
        "DOE가 POR보다 +586 fA 높다.",
        "실제 이동량은 +235 fA ~ +1.56 pA 사이로 본다 (90% 신뢰구간).",
        "같다고 보는 범위는 ±4.89 fA다 = 값의 5% 4.89 fA + 회차 흔들림 0 A.",
        "→ 이동은 허용폭 밖이지만 DOE도 정량 한계(LoQ) 아래에 머물러 둘 다 '<LoQ'로 보고된다.",
        "POR 값은 -97.9 fA, 정량 한계는 16.5 pA다 (LoQ의 0.00592배). "
        "값이 LoQ 아래라 숫자 대신 '<LoQ' 보고가 같은지로 판정했다.",
    ]


def test_card_excluded_is_head_and_reason_only():
    row = {"ITEM": "STEP", "verdict_final": "판정 제외", "verdict_basis": "linear", "verdict": "판정 제외",
           "zone": "판정 제외", "reason": "판정 제외: die 산포 0 (σ_die=0)", "center": 0.0, "ci_low": 0.0,
           "ci_high": 0.0, "delta": 0.003}
    assert verdict_card(row) == ["STEP · 판정 제외 (기본 판정)", "→ 판정에서 뺐다. die 값이 고정되어 있어 흔들림을 잴 수 없다."]


def test_card_accuracy_basis_shows_equipment_term():
    row = {"ITEM": "VOS_OFFSET", "UNIT": "V", "verdict_final": "동등", "verdict_basis": "accuracy", "verdict": "차이",
           "zone": "정량", "reason": "shift +3.333e-06가 ±Δ(1.567e-06) 밖", "n_die": 61, "center": 3.333333e-06,
           "ci_low": 2e-06, "ci_high": 4e-06, "delta": 1.566667e-06, "policy_margin": 1.566667e-06, "run_margin": 0.0,
           "por_median": 3.133333e-05, "LoQ": 2.096713e-05, "sigma_meas": 2.096713e-06, "meas_precision_pct": 6.691637,
           "accuracy_margin": 1.074527e-03}
    lines = verdict_card(row)
    assert lines[0] == "VOS_OFFSET · 동등 (장비 정확도 옵션) · 기본 판정은 차이"
    assert lines[3] == "같다고 보는 범위는 ±1.07 mV다 = max(값의 5% 1.57 µV + 회차 흔들림 0 V, 장비 정확도 폭 1.07 mV)."
    assert lines[4].startswith("→ LoQ 근처라 허용폭을 장비 정확도 폭까지 넓히면")


def test_card_log_basis_reads_in_ratio():
    row = {"ITEM": "I00013", "UNIT": "u", "verdict_final": "차이", "verdict_basis": "log", "verdict": "미결",
           "zone": "정량", "reason": "경계 (신뢰구간이 Δ에 걸침)", "log_reason": "shift +0.04가 ±Δ(0.029) 밖",
           "n_die": 61, "center": 0.0987, "por_median": 0.987, "center_log": 0.04139, "ci_low_log": 0.0414,
           "ci_high_log": 0.0453, "delta_log": 0.0293, "sigma_rep_log": 0.00807, "LoQ": 0.146, "sigma_meas": 0.0146,
           "meas_precision_pct": 1.48}
    assert verdict_card(row) == [
        "I00013 · 차이 (log 판정) · 기본 판정은 미결",
        "DOE가 POR보다 +0.0987 u (+10.0%) 높다.",
        "log 값으로 보면 DOE가 POR의 1.1배다 (+10.0%).",
        "실제 배율은 1.1 ~ 1.11배 사이로 본다 (90% 신뢰구간).",
        "같다고 보는 범위는 log 값으로 ±0.0293 (배율 0.935 ~ 1.07배)다 = 정책 log10(1 + r) 0.0212 + 회차 흔들림 0.00807.",
        "→ log 값(배율)으로 보면 이동량 범위(90% 신뢰구간) 전체가 허용폭 밖이라 달라졌다고 본다.",
        "같은 die를 다시 재면 ±0.0146 u (1.48%) 흔들린다. 정량 한계 0.146 u의 6.76배 위에서 잰 값이다.",
    ]


def test_card_few_dies():
    row = {**VT_SHIFT, "verdict_final": "미결", "verdict": "미결", "zone": "die 부족", "reason": "die 6개 (< 10)",
           "n_die": 6}
    assert "→ die가 6개뿐이라 판정하기에 부족하다 (10개 이상 필요)." in verdict_card(row)


def _overlaps(a, b) -> bool:
    return a.x0 < b.x1 and b.x0 < a.x1 and a.y0 < b.y1 and b.y0 < a.y1


@pytest.mark.parametrize("layout", [None, "constrained", "tight"])
def test_figure_note_is_one_this_run_line_below_axes_at_fixed_place(layout):
    configure_font()      # 한글 글꼴 폭으로 재야 겹침 검사가 실제 그림과 같다
    long = "점이 가운데 아래에 모일수록 DOE가 POR과 같다. 위쪽 점은 측정이 흔들려 판단을 못 한 ITEM이다. " * 3
    placed = []
    for size in ((6, 4), (10, 7)):
        fig, axes = plt.subplots(2, 1, figsize=size, layout=layout)
        fig.suptitle("제목")
        for ax in axes:
            ax.plot([0, 1], [0, 1])
            ax.set_xlabel("x 축 이름")
        run = add_figure_note(fig, long, "차이 40개 중 32개가 + 방향")
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        note = run.get_window_extent(renderer)
        for ax in axes:
            assert not _overlaps(ax.get_tightbbox(renderer), note)
        page = fig.bbox
        assert note.x0 >= page.x0 and note.x1 <= page.x1 and note.y0 >= page.y0
        assert run.get_text() == "이번 결과: 차이 40개 중 32개가 + 방향"
        assert not any("읽는 법" in t.get_text() or "점이 가운데" in t.get_text() for t in fig.texts), \
            "읽는 법은 리포트 마우스오버로 옮겨 그림에 그리지 않는다"
        assert run.get_fontsize() == NOTE_FONTSIZE and run.get_transform() == fig.dpi_scale_trans
        placed.append(run.get_position())
        plt.close(fig)
    assert placed[0] == placed[1], "이번 결과 줄은 그림 크기와 상관없이 왼쪽 아래 같은 인치 위치"


@pytest.mark.parametrize("dpi", [72, 100, 110, 130, 150, 200])
def test_figure_note_lines_fit_the_page_at_the_save_dpi(dpi, tmp_path):
    configure_font()
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot([0, 1], [0, 1])
    run = add_figure_note(fig, "읽는 법", "차이 40개 중 32개가 + 방향 (한쪽으로 몰림, p < 0.05). VT_LONG_ITEM_NAME_0001 " * 3,
                          dpi=dpi)
    fig.savefig(tmp_path / "note.png", dpi=dpi)
    fig.set_dpi(dpi)
    renderer = fig.canvas.get_renderer()
    right = (fig.get_size_inches()[0] - 0.15) * dpi
    assert run.get_text().count("\n") >= 1
    assert run.get_window_extent(renderer).x1 <= right + 1, run.get_text()
    plt.close(fig)
