"""판정 결과를 사람이 읽는 한국어 문장으로 바꾸는 순수 함수. 판정을 바꾸지 않고 items.csv 한 행을 읽기만 한다.

  fmt(x, unit)        숫자를 유효숫자 3자리로 (A·V·Ω 같은 단위는 SI 접두어: 0.0000123 A → 12.3 µA)
  pct(part, whole)    part / |whole| 을 부호 있는 % 로 ("+6.6%")
  reason_plain(row)   최종 판정 사유 한 문장
  verdict_card(row)   ITEM 판정 카드 (판정과 근거, 이동량, 신뢰구간, 허용폭 구성, 사유, 정밀도와 LoQ 배수)
  add_figure_note(fig, how_to_read, this_run)   그림 아래 "읽는 법" / "이번 결과" 두 줄
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping

SI_UNITS = {"A": "A", "V": "V", "Ω": "Ω", "ohm": "Ω", "OHM": "Ω", "Ohm": "Ω", "F": "F", "Hz": "Hz", "HZ": "Hz",
            "W": "W", "s": "s"}
SI_PREFIXES = {-15: "f", -12: "p", -9: "n", -6: "µ", -3: "m", 0: "", 3: "k", 6: "M", 9: "G"}
V_EXCLUDED = "판정 제외"
LOQ_ZONES = ("검출한계 이하", "검출~정량")
BASIS_NAMES = {"linear": "기본 판정", "log": "log 판정", "accuracy": "장비 정확도 옵션", "log_physics": "물리 log 판정"}


def _num(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


def _text(x) -> str:
    return "" if x is None or (isinstance(x, float) and math.isnan(x)) else str(x).strip()


def _sig3(v: float) -> str:
    return f"{v:.3g}"


def _times(v: float) -> str:
    """배수. 1000 이상은 지수 대신 자릿수 쉼표 (3.65e+03 → 3,650)."""
    return f"{v:,.0f}" if abs(v) >= 1000 else _sig3(v)


def fmt(x, unit: str = "", signed: bool = False) -> str:
    """유효숫자 3자리. SI_UNITS 단위는 접두어를 붙인다. NaN·빈 값은 "-"."""
    v = _num(x)
    if not math.isfinite(v):
        return "-"
    sign = "+" if signed and v > 0 else ""
    si = SI_UNITS.get(_text(unit).strip("[]"))
    if si is None:
        return f"{sign}{_sig3(v)}{' ' + _text(unit) if _text(unit) else ''}"
    if v == 0:
        return f"0 {si}"
    exp = min(max(3 * math.floor(math.log10(abs(v)) / 3), -15), 9)
    mant = float(_sig3(v / 10 ** exp))
    if abs(mant) >= 1000 and exp < 9:
        exp, mant = exp + 3, mant / 1000
    return f"{sign}{_sig3(mant)} {SI_PREFIXES[exp]}{si}"


def pct(part, whole) -> str:
    """100 × part / |whole| 을 부호와 함께. |값| ≥ 1 이면 소수 한 자리, 그 아래는 유효숫자 2자리. whole 이 0·NaN 이면 "-"."""
    p, w = _num(part), _num(whole)
    if not (math.isfinite(p) and math.isfinite(w)) or w == 0:
        return "-"
    v = 100 * p / abs(w)
    if v == 0:
        return "0%"
    return f"{v:+.1f}%" if abs(v) >= 1 else f"{v:+.2g}%"


Rule = tuple[str, "str | Callable[[re.Match], str]"]

# 판정 제외 원인 (por_doe_compare.EXCLUSION_CAUSES 와 Δ 검사). reason 에 '; ' 로 이어 적힌다
EXCLUSION_RULES: tuple[Rule, ...] = (
    (r"중심·신뢰구간 계산 불가", "이동량이나 신뢰구간을 계산할 수 없다"),
    (r"회차 0값 \((.+)\)", lambda m: f"{m[1]} 값만 die 절반 넘게 0이다"),
    (r"모든 값 같음", "POR·DOE 값이 모두 같다"),
    (r"die 산포 0", "die 값이 고정되어 있어 흔들림을 잴 수 없다"),
    (r"고정값 \(중앙값 0·σ_run 0\)", "값이 0에 고정되어 있다"),
    (r"최종 Δ가 0 이하", "허용폭이 0 이하라 정할 수 없다"),
)


def _match(rules: tuple[Rule, ...], text: str) -> str | None:
    for pattern, render in rules:
        m = re.match(pattern, text)
        if m:
            return render if isinstance(render, str) else render(m)
    return None


def _excluded(m: re.Match) -> str:
    causes = [_match(EXCLUSION_RULES, c.strip()) or c.strip() for c in m[1].split(";")]
    return f"판정에서 뺐다. {', '.join(causes)}."


# por_doe_compare 의 reason·log_reason 이 만드는 사유 종류 (tost, judge 의 LoQ 판정, die 부족, 판정 제외)
REASON_RULES: tuple[Rule, ...] = (
    (r"90% 신뢰구간이 ±Δ 안$", "이동량 범위(90% 신뢰구간) 전체가 허용폭 안이라 같다고 본다."),
    (r"shift .*밖$", "이동량 범위(90% 신뢰구간) 전체가 허용폭 밖이라 달라졌다고 본다."),
    (r"해상도 부족", "측정이 흔들려 이동량 범위가 허용폭보다 넓다. 같은지 다른지 판단할 수 없다."),
    (r"경계", "이동량 범위가 허용폭 경계에 걸쳐 있다. 같다고도 다르다고도 할 수 없다."),
    (r"<LoQ 보고 일치 \(이동이 ±Δ 안\)", "POR 값이 정량 한계(LoQ) 아래라 둘 다 '<LoQ'로 보고되고, 이동도 허용폭 안이다."),
    (r"<LoQ 보고 일치 \(DOE 중심도 LoQ 미만\)",
     "이동은 허용폭 밖이지만 DOE도 정량 한계(LoQ) 아래에 머물러 둘 다 '<LoQ'로 보고된다."),
    (r"DOE 중심 .* 이상이고 이동 .*밖$", "POR은 정량 한계(LoQ) 아래인데 DOE가 LoQ 위로 올라가 보고 값이 달라진다."),
    (r"die (\d+)개 \(< (\d+)\)$", lambda m: f"die가 {m[1]}개뿐이라 판정하기에 부족하다 ({m[2]}개 이상 필요)."),
    (rf"{V_EXCLUDED}: (.*)$", _excluded),
)


def reason_plain(row: Mapping) -> str:
    """최종 판정(verdict_final)을 정한 사유를 한 문장으로. 모르는 사유는 원문 그대로."""
    basis = _text(row.get("verdict_basis")) or "linear"
    if basis == "accuracy":
        return "LoQ 근처라 허용폭을 장비 정확도 폭까지 넓히면 이동량 범위 전체가 그 안이라 같다고 본다."
    raw = _text(row.get("log_reason" if basis in ("log", "log_physics") else "reason"))
    plain = _match(REASON_RULES, raw) or raw
    return f"log 값(배율)으로 보면 {plain}" if basis in ("log", "log_physics") else plain


def _sentence(*parts: str) -> str:
    return " ".join(p for p in parts if p)


def _shift_lines(row: Mapping, unit: str, dies_up, dies_down) -> tuple[str, str]:
    """(이동량 문장, 신뢰구간 문장). 값이 없으면 빈 문자열."""
    center, lo, hi, por = (_num(row.get(k)) for k in ("center", "ci_low", "ci_high", "por_median"))
    moved = ci = ""
    if math.isfinite(center):
        if center == 0:
            moved = "DOE와 POR의 die별 차이 중앙값이 0이다."
        else:
            share = "" if _text(row.get("zone")) in LOQ_ZONES else f" ({pct(center, por)})"
            moved = f"DOE가 POR보다 {fmt(center, unit, signed=True)}{share} {'높다' if center > 0 else '낮다'}."
        n = int(_num(row.get("n_die"))) if math.isfinite(_num(row.get("n_die"))) else None
        dies = (f"die {n}개 중 {dies_up}개에서 DOE가 높고 {dies_down}개에서 낮다."
                if n is not None and dies_up is not None and dies_down is not None else "")
        moved = _sentence(moved, dies)
    if math.isfinite(lo) and math.isfinite(hi):
        ci = f"실제 이동량은 {fmt(lo, unit, signed=True)} ~ {fmt(hi, unit, signed=True)} 사이로 본다 (90% 신뢰구간)."
    return moved, ci


def _delta_line(row: Mapping, unit: str, basis: str) -> str:
    delta, policy, run, por, acc = (_num(row.get(k)) for k in
                                    ("delta", "policy_margin", "run_margin", "por_median", "accuracy_margin"))
    if not math.isfinite(delta):
        return ""
    r = f"값의 {_sig3(100 * policy / abs(por))}% " if math.isfinite(policy) and math.isfinite(por) and por else ""
    parts = f"{r}{fmt(policy, unit)} + 회차 흔들림 {fmt(run, unit)}"
    if basis == "accuracy" and math.isfinite(acc):
        return f"같다고 보는 범위는 ±{fmt(max(delta, acc), unit)}다 = max({parts}, 장비 정확도 폭 {fmt(acc, unit)})."
    return f"같다고 보는 범위는 ±{fmt(delta, unit)}다 = {parts}."


def _log_lines(row: Mapping) -> list[str]:
    c, lo, hi, d, rep = (_num(row.get(k)) for k in ("center_log", "ci_low_log", "ci_high_log", "delta_log",
                                                    "sigma_rep_log"))
    lines = []
    if math.isfinite(c):
        lines.append(f"log 값으로 보면 DOE가 POR의 {_times(10 ** c)}배다 ({pct(10 ** c - 1, 1)}).")
    if math.isfinite(lo) and math.isfinite(hi):
        lines.append(f"실제 배율은 {_times(10 ** lo)} ~ {_times(10 ** hi)}배 사이로 본다 (90% 신뢰구간).")
    if math.isfinite(d):
        tail = (f" = 정책 log10(1 + r) {_sig3(d - rep)} + 회차 흔들림 {_sig3(rep)}" if math.isfinite(rep) else "")
        lines.append(f"같다고 보는 범위는 log 값으로 ±{_sig3(d)} (배율 {_times(10 ** -d)} ~ {_times(10 ** d)}배)다{tail}.")
    return lines


def _precision_line(row: Mapping, unit: str) -> str:
    zone = _text(row.get("zone"))
    por, loq, s, p = (_num(row.get(k)) for k in ("por_median", "LoQ", "sigma_meas", "meas_precision_pct"))
    ratio = abs(por) / loq if math.isfinite(por) and math.isfinite(loq) and loq > 0 else math.nan
    if zone in LOQ_ZONES:
        times = f" (LoQ의 {_times(ratio)}배)" if math.isfinite(ratio) else ""
        return (f"POR 값은 {fmt(por, unit)}, 정량 한계는 {fmt(loq, unit)}다{times}. "
                "값이 LoQ 아래라 숫자 대신 '<LoQ' 보고가 같은지로 판정했다.")
    shake = (f"같은 die를 다시 재면 ±{fmt(s, unit)}"
             + (f" ({_sig3(p)}%)" if math.isfinite(p) else "") + " 흔들린다.") if math.isfinite(s) else ""
    above = f"정량 한계 {fmt(loq, unit)}의 {_times(ratio)}배 위에서 잰 값이다." if math.isfinite(ratio) else ""
    return _sentence(shake, above)


def verdict_card(row: Mapping, dies_up: int | None = None, dies_down: int | None = None) -> list[str]:
    """ITEM 판정 카드 (설계 1-6). row 는 items.csv 한 행. dies_up·dies_down 은 DOE가 높은·낮은 die 수 (원데이터에서)."""
    unit = _text(row.get("UNIT"))
    basis = _text(row.get("verdict_basis")) or "linear"
    final, verdict = _text(row.get("verdict_final")) or _text(row.get("verdict")), _text(row.get("verdict"))
    head = f"{_text(row.get('ITEM'))} · {final} ({BASIS_NAMES.get(basis, basis)})"
    if verdict and verdict != final:
        head += f" · 기본 판정은 {verdict}"
    if final == V_EXCLUDED:
        return [head, f"→ {reason_plain(row)}"]
    moved, ci = _shift_lines(row, unit, dies_up, dies_down)
    if basis in ("log", "log_physics"):
        lines = [head, moved, *_log_lines(row)]
    else:
        lines = [head, moved, ci, _delta_line(row, unit, basis)]
    lines += [f"→ {reason_plain(row)}", _precision_line(row, unit)]
    return [line for line in lines if line]


NOTE_FONTSIZE = 9
NOTE_LEFT_IN = 0.15          # 그림 왼쪽 끝에서
NOTE_PAD_IN = 0.1            # 주석 위·아래 여백, 두 줄 사이 간격


def _wrap_measured(text: str, probe, renderer, width_px: float) -> str:
    """probe(Text) 로 실제 글꼴 폭을 재며 낱말 단위로 줄을 나눈다. 한 낱말이 너무 길면 그 줄에 그대로 둔다."""
    def fits(s: str) -> bool:
        probe.set_text(s)
        return probe.get_window_extent(renderer).width <= width_px

    lines, cur = [], ""
    for word in text.split():
        cand = f"{cur} {word}" if cur else word
        if cur and not fits(cand):
            lines.append(cur)
            cand = word
        cur = cand
    return "\n".join([*lines, cur])


def add_figure_note(fig, how_to_read: str, this_run: str):
    """그림 아래에 "읽는 법: ..." 과 "이번 결과: ..." 를 단다. 모든 그림에서 같은 글자 크기, 왼쪽 아래 같은 인치 위치
    ("이번 결과" 가 맨 아래, 그 위에 "읽는 법"). 글을 실제 글꼴로 재서 줄을 나누고, 그림 높이를 그만큼 늘리고
    기존 축·글자를 그만큼 위로 옮겨 겹치지 않게 한다. (읽는 법, 이번 결과) Text 를 돌려준다."""
    width, height = fig.get_size_inches()
    renderer = fig.canvas.get_renderer()
    style = dict(transform=fig.dpi_scale_trans, ha="left", va="bottom", fontsize=NOTE_FONTSIZE)
    how, run = (fig.text(NOTE_LEFT_IN, 0, "", **style) for _ in range(2))
    width_px = (width - 2 * NOTE_LEFT_IN) * fig.dpi
    how.set_text(_wrap_measured(f"읽는 법: {how_to_read}", how, renderer, width_px))
    run.set_text(_wrap_measured(f"이번 결과: {this_run}", run, renderer, width_px))
    h_run, h_how = (t.get_window_extent(renderer).height / fig.dpi for t in (run, how))
    footer = 3 * NOTE_PAD_IN + h_run + h_how
    new_height = height + footer
    fig.set_size_inches(width, new_height, forward=True)
    engine = fig.get_layout_engine() if hasattr(fig, "get_layout_engine") else None
    if engine is not None and "rect" in engine.get():
        engine.set(rect=(0, footer / new_height, 1, height / new_height))
    else:
        for ax in fig.axes:
            pos = ax.get_position()
            ax.set_position([pos.x0, (pos.y0 * height + footer) / new_height, pos.width, pos.height * height / new_height])
    for t in {id(t): t for t in [*fig.texts, getattr(fig, "_suptitle", None)] if t is not None}.values():
        if t.get_transform() == fig.transFigure:
            x, y = t.get_position()
            t.set_position((x, (y * height + footer) / new_height))
    run.set_position((NOTE_LEFT_IN, NOTE_PAD_IN))
    how.set_position((NOTE_LEFT_IN, 2 * NOTE_PAD_IN + h_run))
    return how, run
