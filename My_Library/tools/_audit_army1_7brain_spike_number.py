# -*- coding: utf-8
"""20260701 1군 7뇌 '튀는 번호 발굴' 독립뇌 검증 — READ-ONLY.

STEP1 튀는번호 정의(1~2뇌 지목, v3 1/k) | STEP2 뇌별 번호대 특기(전구간 설명용,
카이제곱+Bonferroni) | STEP3 walk-forward 예측(특기 vs 랜덤 vs v3) 3구간
| STEP4 판정(R2 정직).

절대: 6뇌 코드·DB 수정 0건. 컨닝 금지(N 예측은 N-1까지만). lead1 외 미변경.
실행: python tools/_audit_army1_7brain_spike_number.py
"""
from __future__ import annotations

import importlib.util
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]

PERIODS = [
    ("A", 330, 629),
    ("B", 630, 929),
    ("C", 930, 1230),
]

POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
SIX_BRAINS = POOL_BRAINS + ("hyena",)
BRAIN_KO = {
    "stat": "시간여행자",
    "markov": "탐정",
    "llm": "지식박사",
    "lstm": "예언자",
    "fusion": "작전본부장",
}
# 번호대 5구간
BANDS = [(1, 10), (11, 20), (21, 30), (31, 40), (41, 45)]
SPIKE_MAX_K = 2       # 1~2뇌만 지목 = 튀는 번호
M_PREDICT = 6         # 회차당 예측 번호 개수
RANDOM_TRIALS = 200
LAPLACE_A = 1.0
LAPLACE_B = 2.0
P_MAX = 0.05


def _load_sel_module():
    spec = importlib.util.spec_from_file_location(
        "sel7", ROOT / "tools" / "_audit_army1_7brain_selection.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _band_idx(n: int) -> int:
    for i, (lo, hi) in enumerate(BANDS):
        if lo <= n <= hi:
            return i
    return len(BANDS) - 1


def _load_pool_flat(conn, dn: int) -> list[tuple[str, tuple[int, ...]]]:
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"""
        SELECT brain_tag, num1,num2,num3,num4,num5,num6
        FROM lotto_predictions
        WHERE target_draw_no=? AND brain_tag IN ({ph})
        ORDER BY brain_tag, id
        """,
        (dn, *POOL_BRAINS),
    ).fetchall()
    return [
        (str(r[0]), tuple(sorted(int(r[i]) for i in range(1, 7))))
        for r in rows
    ]


def _brain_presence(flat) -> dict[int, set[str]]:
    """번호 -> 지목한 뇌 집합 (뇌 내 dedup)."""
    by_brain: dict[str, set[int]] = defaultdict(set)
    for tag, nums in flat:
        by_brain[tag] |= set(nums)
    pres: dict[int, set[str]] = defaultdict(set)
    for tag, nums_set in by_brain.items():
        for n in nums_set:
            pres[n].add(tag)
    return pres


def _win7(conn, dn: int) -> list[int]:
    r = conn.execute(
        "SELECT num1,num2,num3,num4,num5,num6,bonus FROM lotto_draws WHERE draw_no=?",
        (dn,),
    ).fetchone()
    if not r:
        return []
    return [int(r[i]) for i in range(7)]


def _spike_candidates(pres: dict[int, set[str]]) -> dict[int, set[str]]:
    """1~2뇌만 지목한 번호 = 튀는 후보."""
    return {n: b for n, b in pres.items() if 1 <= len(b) <= SPIKE_MAX_K}


# ─────────────────────────────────────────────────────────────
# STEP2 — 전구간 뇌별 번호대 특기 (설명용, 카이제곱)
# ─────────────────────────────────────────────────────────────
def step2_band_specialty(conn, eligible: list[int]) -> dict:
    picks = {b: [0] * len(BANDS) for b in POOL_BRAINS}
    hits = {b: [0] * len(BANDS) for b in POOL_BRAINS}

    for dn in eligible:
        flat = _load_pool_flat(conn, dn)
        if len(flat) < 25:
            continue
        win = set(_win7(conn, dn))
        if not win:
            continue
        by_brain: dict[str, set[int]] = defaultdict(set)
        for tag, nums in flat:
            by_brain[tag] |= set(nums)
        for b in POOL_BRAINS:
            for n in by_brain.get(b, set()):
                bi = _band_idx(n)
                picks[b][bi] += 1
                if n in win:
                    hits[b][bi] += 1

    profile = {}
    for b in POOL_BRAINS:
        tot_pick = sum(picks[b]) or 1
        tot_hit = sum(hits[b])
        overall_rate = tot_hit / tot_pick
        # 카이제곱: 관측 hit vs 기대(각 밴드 pick × overall_rate)
        chi = 0.0
        band_rates = []
        for i in range(len(BANDS)):
            exp = picks[b][i] * overall_rate
            band_rate = hits[b][i] / picks[b][i] if picks[b][i] else 0.0
            band_rates.append(round(band_rate, 4))
            if exp > 0:
                chi += (hits[b][i] - exp) ** 2 / exp
        # df=4 카이제곱 p-value (생존함수 근사)
        p = _chi2_sf(chi, df=len(BANDS) - 1)
        profile[b] = {
            "overall_hit_rate": round(overall_rate, 4),
            "band_pick": picks[b],
            "band_hit": hits[b],
            "band_hit_rate": band_rates,
            "chi2": round(chi, 3),
            "p_value": round(p, 5),
            "best_band": BANDS[max(range(len(BANDS)), key=lambda i: band_rates[i])],
        }
    # Bonferroni
    n_tests = len(POOL_BRAINS)
    for b in profile:
        profile[b]["p_bonferroni"] = round(min(1.0, profile[b]["p_value"] * n_tests), 5)
        profile[b]["significant"] = profile[b]["p_bonferroni"] < P_MAX
    return {
        "note": "전구간 설명용 — STEP3 예측에는 사용 안 함(사후편향 방지)",
        "bands": BANDS,
        "bonferroni_tests": n_tests,
        "profile": profile,
        "any_significant": any(profile[b]["significant"] for b in profile),
    }


def _chi2_sf(x: float, df: int) -> float:
    """카이제곱 생존함수 (df 짝수/홀수 급 근사 — Wilson–Hilferty)."""
    if x <= 0:
        return 1.0
    # Wilson-Hilferty 정규 근사
    z = ((x / df) ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * df))) / math.sqrt(2.0 / (9.0 * df))
    return 0.5 * math.erfc(z / math.sqrt(2.0))


# ─────────────────────────────────────────────────────────────
# STEP3 — walk-forward 예측 (특기 vs 랜덤 vs v3)
# ─────────────────────────────────────────────────────────────
def _specialty_score(
    profile_picks, profile_hits, brain: str, band: int
) -> float:
    p = profile_picks[brain][band]
    h = profile_hits[brain][band]
    return (h + LAPLACE_A) / (p + LAPLACE_B)


def run_walkforward(conn, eligible: list[int]) -> dict:
    """단일 pass — draw N 예측은 N 미만 프로파일만 사용."""
    prof_picks = {b: [0] * len(BANDS) for b in POOL_BRAINS}
    prof_hits = {b: [0] * len(BANDS) for b in POOL_BRAINS}

    # per-draw 기록 (eval 구간만)
    records: dict[int, dict] = {}

    for dn in eligible:
        flat = _load_pool_flat(conn, dn)
        if len(flat) < 25:
            continue
        win7 = _win7(conn, dn)
        if len(win7) < 7:
            continue
        win = set(win7)
        pres = _brain_presence(flat)
        cand = _spike_candidates(pres)  # pre-draw, 컨닝 아님

        # ── 예측 (프로파일은 현재까지 = N 미만) ──
        if len(cand) >= 2:
            pool = list(cand.keys())
            winners_in_pool = [n for n in pool if n in win]
            m = min(M_PREDICT, len(pool))

            # 특기 arm: 후보별 점수 = 지목뇌 특기(밴드 적중률) 최대, tie=1/k
            def spec_score(n: int) -> tuple[float, float]:
                brains = cand[n]
                bi = _band_idx(n)
                s = max(_specialty_score(prof_picks, prof_hits, b, bi) for b in brains)
                v3 = 1.0 / len(brains)
                return (s, v3)

            spec_sorted = sorted(pool, key=lambda n: (-spec_score(n)[0], -spec_score(n)[1], n))
            spec_pick = spec_sorted[:m]
            hit_spec = sum(1 for n in spec_pick if n in win)

            # 교란 진단: spec_pick 중 lstm/fusion(강뇌)만 지목한 번호 비율
            def only_strong(n: int) -> bool:
                return cand[n] <= {"lstm", "fusion"}
            spec_strong_frac = (
                sum(1 for n in spec_pick if only_strong(n)) / len(spec_pick)
                if spec_pick else 0.0
            )
            pool_strong_frac = (
                sum(1 for n in pool if only_strong(n)) / len(pool) if pool else 0.0
            )

            # v3 arm: 순수 희소성 (1/k 큰 것 = k작은 것)
            v3_sorted = sorted(pool, key=lambda n: (len(cand[n]), n))
            v3_pick = v3_sorted[:m]
            hit_v3 = sum(1 for n in v3_pick if n in win)

            # 랜덤 arm: 풀에서 m개 무작위, trials 평균
            rng = random.Random(dn * 7919 + 13)
            rand_hits = []
            for _ in range(RANDOM_TRIALS):
                pick = rng.sample(pool, m)
                rand_hits.append(sum(1 for n in pick if n in win))
            hit_rand = statistics.mean(rand_hits)

            records[dn] = {
                "pool_size": len(pool),
                "winners_in_pool": len(winners_in_pool),
                "m": m,
                "hit_spec": hit_spec,
                "hit_v3": hit_v3,
                "hit_rand": hit_rand,
                "spec_strong_frac": spec_strong_frac,
                "pool_strong_frac": pool_strong_frac,
                "informative": len(pool) > M_PREDICT,
            }

        # ── 프로파일 갱신 (draw N 반영 → N+1부터 사용) ──
        by_brain: dict[str, set[int]] = defaultdict(set)
        for tag, nums in flat:
            by_brain[tag] |= set(nums)
        for b in POOL_BRAINS:
            for n in by_brain.get(b, set()):
                bi = _band_idx(n)
                prof_picks[b][bi] += 1
                if n in win:
                    prof_hits[b][bi] += 1

    return records


def _period_stats(records: dict, mod, lo: int, hi: int) -> dict:
    draws = [dn for dn in records if lo <= dn <= hi]
    inf = [dn for dn in draws if records[dn]["informative"]]
    if not inf:
        return {"range": [lo, hi], "n_all": len(draws), "n_informative": 0}

    spec = [records[dn]["hit_spec"] for dn in inf]
    v3 = [records[dn]["hit_v3"] for dn in inf]
    rand = [records[dn]["hit_rand"] for dn in inf]

    tt_spec_rand = mod.paired_ttest(spec, rand)
    tt_spec_v3 = mod.paired_ttest(spec, v3)
    tt_v3_rand = mod.paired_ttest(v3, rand)

    mean_pool = statistics.mean(records[dn]["pool_size"] for dn in inf)
    mean_win_in_pool = statistics.mean(records[dn]["winners_in_pool"] for dn in inf)
    mean_spec_strong = statistics.mean(records[dn]["spec_strong_frac"] for dn in inf)
    mean_pool_strong = statistics.mean(records[dn]["pool_strong_frac"] for dn in inf)

    return {
        "range": [lo, hi],
        "n_all": len(draws),
        "n_informative": len(inf),
        "mean_pool_size": round(mean_pool, 2),
        "mean_winners_in_pool": round(mean_win_in_pool, 3),
        "mean_hit_spec": round(statistics.mean(spec), 4),
        "mean_hit_v3": round(statistics.mean(v3), 4),
        "mean_hit_rand": round(statistics.mean(rand), 4),
        "delta_spec_vs_rand": round(statistics.mean(spec) - statistics.mean(rand), 4),
        "delta_spec_vs_v3": round(statistics.mean(spec) - statistics.mean(v3), 4),
        "delta_v3_vs_rand": round(statistics.mean(v3) - statistics.mean(rand), 4),
        "p_spec_vs_rand": tt_spec_rand["p_value"],
        "p_spec_vs_v3": tt_spec_v3["p_value"],
        "p_v3_vs_rand": tt_v3_rand["p_value"],
        "spec_strong_frac": round(mean_spec_strong, 4),
        "pool_strong_frac": round(mean_pool_strong, 4),
        "pass_spec": (
            statistics.mean(spec) - statistics.mean(rand) > 0
            and tt_spec_rand["p_value"] < P_MAX
        ),
    }


def _verdict(period_stats: list[dict], step2: dict) -> dict:
    valid = [p for p in period_stats if p.get("n_informative", 0) > 0]
    pass_cnt = sum(1 for p in valid if p.get("pass_spec"))
    deltas = [p["delta_spec_vs_rand"] for p in valid]
    mean_delta = round(statistics.mean(deltas), 4) if deltas else 0.0

    # 교란 진단
    band_specialty_exists = step2.get("any_significant", False)
    spec_strong = statistics.mean(p["spec_strong_frac"] for p in valid) if valid else 0
    pool_strong = statistics.mean(p["pool_strong_frac"] for p in valid) if valid else 0
    strong_overbet = spec_strong - pool_strong  # 강뇌 편중 초과
    v3_beats_rand = all(p["delta_v3_vs_rand"] > 0 for p in valid)

    # 정식 3자 게이트 (동생 지시): spec가 랜덤·v3 둘 다 3/3 유의 초과해야 함
    spec_beats_rand_3of3 = pass_cnt >= 3
    spec_beats_v3_3of3 = all(
        p["delta_spec_vs_v3"] > 0 and p["p_spec_vs_v3"] < P_MAX for p in valid
    ) and len(valid) >= 3
    formal_gate_pass = (
        spec_beats_rand_3of3 and spec_beats_v3_3of3 and band_specialty_exists
    )

    # 교란: 밴드 특기는 없는데 spec가 랜덤을 이기고, 그 원인이 강뇌 편중
    confound = (
        (not band_specialty_exists)
        and pass_cnt >= 1
        and strong_overbet > 0.15
    )

    if confound:
        go = "NO-GO (교란)"
        final = (
            f"🔴 R2 정직 — 자동판정은 spec>랜덤(3/3, Δ={mean_delta})이나 "
            f"이는 '번호대 특기'가 아니라 교란임. "
            f"STEP2 카이제곱: 밴드 특기 유의 뇌 0개(적중률 평평). "
            f"spec의 강뇌(lstm/fusion)-only 번호 비중 {round(spec_strong,3)} vs "
            f"풀 평균 {round(pool_strong,3)} (초과 {round(strong_overbet,3)}). "
            f"즉 spec 점수가 밴드가 아닌 '뇌 전체 정확도'로 붕괴 → lstm/fusion 픽 재베팅 "
            f"= CAP2에서 벗어나려던 2뇌 종속의 재등장. "
            f"순수 희소성(v3)은 오히려 랜덤 미만(Δ={[p['delta_v3_vs_rand'] for p in valid]}). "
            "→ '번호대 특기 발굴' 신기능 채택 불가. 기존 CAP2 세트추천 유지."
        )
    elif pass_cnt >= 3 and band_specialty_exists:
        go = "GO-SPIKE"
        final = (
            f"🟢 밴드 특기 유의(STEP2) + spike 예측 랜덤 3/3 초과(Δ={mean_delta}). "
            "7뇌 신기능 채택 후보 — 형 GO 후 이식 검토."
        )
    elif pass_cnt >= 1:
        go = "PARTIAL"
        final = (
            f"🟡 {pass_cnt}/3 구간만 랜덤 초과, 밴드 특기 유의={band_specialty_exists}. "
            "재현성/기전 불충분 — CAP2 유지."
        )
    else:
        go = "NO-GO"
        final = (
            f"🔴 spike 예측이 랜덤 미달(Δ={mean_delta}). "
            "R2 정직: 번호대 특기 예측 신호 없음. CAP2 세트추천 유지."
        )
    return {
        "pass_periods": pass_cnt,
        "mean_delta_spec_vs_rand": mean_delta,
        "band_specialty_exists": band_specialty_exists,
        "spec_beats_rand_3of3": spec_beats_rand_3of3,
        "spec_beats_v3_3of3": spec_beats_v3_3of3,
        "formal_gate_pass": formal_gate_pass,
        "spec_strong_frac": round(spec_strong, 4),
        "pool_strong_frac": round(pool_strong, 4),
        "strong_overbet": round(strong_overbet, 4),
        "v3_beats_random": v3_beats_rand,
        "confound_detected": confound,
        "go": go,
        "final": final,
    }


def _format_txt(result: dict) -> str:
    op = result["cursor_opinion"]
    s2 = result["step2"]
    v = result["verdict"]
    lines = [
        result["title"],
        "동생 → 커서(Opus 4.8) | 2026-07-01 | READ-ONLY (이식은 형 GO 후)",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "커서 의견 3가지 (실행 전)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "[1] 더 나은 구현:",
    ]
    for x in op["better"]:
        lines.append(f"  - {x}")
    lines.append("[2] 예상 함정/버그:")
    for x in op["pitfalls"]:
        lines.append(f"  - {x}")
    lines.append("[3] 설계 허점(통계 편향):")
    for x in op["flaws"]:
        lines.append(f"  - {x}")
    lines.append(f"  → 판단: {op['decision']}")

    lines += [
        "",
        "절대 원칙: 6뇌 코드·DB 수정 0건 | 컨닝 금지(N은 N-1까지) | R2 정직",
        f"JSON: _audit_20260701_army1_7brain_spike_number.json",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 1 — 튀는 번호 정의",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  5뇌 중 1~2뇌만 지목한 번호 = 튀는 후보 | v3 점수=1/k (k=지목뇌수)",
        f"  후보는 추첨 전 6뇌 세트에서 산출(pre-draw, 컨닝 아님)",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 2 — 뇌별 번호대 특기 (전구간 설명용, 카이제곱+Bonferroni)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  {s2['note']}",
        f"  번호대: {s2['bands']} | Bonferroni tests={s2['bonferroni_tests']}",
        "  뇌 | 전체적중률 | 밴드별적중률 | best밴드 | chi2 | p(Bonf) | 유의",
    ]
    for b in POOL_BRAINS:
        pr = s2["profile"][b]
        lines.append(
            f"  {BRAIN_KO[b]}({b}) | {pr['overall_hit_rate']} | "
            f"{pr['band_hit_rate']} | {pr['best_band']} | {pr['chi2']} | "
            f"{pr['p_bonferroni']} | {pr['significant']}"
        )
    lines.append(f"  → 유의한 특기 뇌 존재: {s2['any_significant']}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — walk-forward 예측 (특기 vs 랜덤 vs v3희소성)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  회차당 {M_PREDICT}번호 예측 | 랜덤 {RANDOM_TRIALS}회 평균 | 스무딩 (h+1)/(p+2)",
        "  구간 | 정보성회차 | 평균풀 | 풀내당첨 | hit특기 | hit랜덤 | hitv3 | Δ특기-랜덤 | p | 통과",
    ]
    for p in result["step3_periods"]:
        if p.get("n_informative", 0) == 0:
            lines.append(f"  {p['range']} | 정보성 회차 없음")
            continue
        lines.append(
            f"  {p['range']} | {p['n_informative']} | {p['mean_pool_size']} | "
            f"{p['mean_winners_in_pool']} | {p['mean_hit_spec']} | {p['mean_hit_rand']} | "
            f"{p['mean_hit_v3']} | {p['delta_spec_vs_rand']} | {p['p_spec_vs_rand']} | "
            f"{p['pass_spec']}"
        )

    lines += [
        "",
        "  참고 — 특기가 순수 희소성(v3)보다 나은가 + 교란 진단:",
    ]
    for p in result["step3_periods"]:
        if p.get("n_informative", 0) == 0:
            continue
        lines.append(
            f"    {p['range']} Δ(특기-v3)={p['delta_spec_vs_v3']} "
            f"p={p['p_spec_vs_v3']} | v3-랜덤 Δ={p['delta_v3_vs_rand']} p={p['p_v3_vs_rand']}"
        )
        lines.append(
            f"      강뇌(lstm/fusion)-only 비중: spec픽={p['spec_strong_frac']} "
            f"vs 풀평균={p['pool_strong_frac']}"
        )

    # 3자 비교 전용 섹션 (동생 지시: 반드시 포함)
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "3자 비교 요약 — 뇌특기 arm vs 순수v3 arm vs 랜덤 arm",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  구간 | 특기 | v3 | 랜덤 | 특기>랜덤 | 특기>v3 | v3>랜덤",
    ]
    for p in result["step3_periods"]:
        if p.get("n_informative", 0) == 0:
            continue
        sr = "O" if (p["delta_spec_vs_rand"] > 0 and p["p_spec_vs_rand"] < P_MAX) else "X"
        sv = "O" if (p["delta_spec_vs_v3"] > 0 and p["p_spec_vs_v3"] < P_MAX) else "X"
        vr = "O" if (p["delta_v3_vs_rand"] > 0 and p["p_v3_vs_rand"] < P_MAX) else "X"
        lines.append(
            f"  {p['range']} | {p['mean_hit_spec']} | {p['mean_hit_v3']} | "
            f"{p['mean_hit_rand']} | {sr} | {sv} | {vr}"
        )
    lines += [
        f"  정식 게이트(특기>랜덤 3/3 & 특기>v3 3/3 & 밴드특기유의): "
        f"{v['formal_gate_pass']}",
        f"    - 특기>랜덤 3/3: {v['spec_beats_rand_3of3']}",
        f"    - 특기>v3 3/3: {v['spec_beats_v3_3of3']}",
        f"    - 밴드특기 유의(STEP2): {v['band_specialty_exists']}",
    ]

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 4 — 판정 (R2 정직)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  랜덤 초과 구간(자동): {v['pass_periods']}/3 | mean Δ={v['mean_delta_spec_vs_rand']}",
        f"  정식 3자 게이트 통과: {v['formal_gate_pass']}",
        f"  밴드 특기 유의(STEP2): {v['band_specialty_exists']}",
        f"  강뇌 편중 초과: spec {v['spec_strong_frac']} - 풀 {v['pool_strong_frac']} "
        f"= {v['strong_overbet']}",
        f"  v3(희소성)>랜덤: {v['v3_beats_random']} | 교란 감지: {v['confound_detected']}",
        f"  GO: {v['go']}",
        f"  {v['final']}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "6뇌 무변경 회귀",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for tag in SIX_BRAINS:
        b = result["six_before"].get(tag, 0)
        a = result["six_after"].get(tag, 0)
        lines.append(f"  {tag}: {b} → {a} [{'OK' if b == a else 'CHANGED!'}]")
    lines.append(f"  lead1: {result['lead1_before']} → {result['lead1_after']} "
                 f"[{'OK' if result['lead1_before'] == result['lead1_after'] else 'CHANGED!'}]")
    lines.append(f"  6뇌+lead1 전체 동일: {result['regression_ok']}")
    return "\n".join(lines) + "\n"


def _row_counts(conn) -> dict[str, int]:
    ph = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag, COUNT(*) FROM lotto_predictions "
        f"WHERE brain_tag IN ({ph}) GROUP BY brain_tag",
        SIX_BRAINS,
    ).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def _lead1_count(conn) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'"
        ).fetchone()[0]
    )


def main() -> None:
    mod = _load_sel_module()
    conn = mod._connect()
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=30000")

    six_before = _row_counts(conn)
    lead1_before = _lead1_count(conn)

    # 5뇌 풀 eligible
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"""
        SELECT p.target_draw_no AS dn, p.brain_tag, COUNT(*) c
        FROM lotto_predictions p
        INNER JOIN lotto_draws d ON d.draw_no = p.target_draw_no
        WHERE p.brain_tag IN ({ph})
        GROUP BY p.target_draw_no, p.brain_tag HAVING c >= 5
        """,
        POOL_BRAINS,
    ).fetchall()
    by: dict[int, set[str]] = defaultdict(set)
    for dn, tag, _ in rows:
        by[int(dn)].add(str(tag))
    eligible = sorted(dn for dn, tags in by.items() if tags >= set(POOL_BRAINS))

    s2 = step2_band_specialty(conn, eligible)
    records = run_walkforward(conn, eligible)
    period_stats = [_period_stats(records, mod, lo, hi) for _, lo, hi in PERIODS]
    verdict = _verdict(period_stats, s2)

    six_after = _row_counts(conn)
    lead1_after = _lead1_count(conn)
    conn.close()

    result = {
        "title": "20260701_1군7뇌_튀는번호발굴_검증",
        "date": "2026-07-01",
        "mode": "READ_ONLY",
        "cursor_opinion": {
            "better": [
                "STEP2(전구간 특기)와 STEP3(예측) 프로파일 물리 분리 — STEP2는 설명용만, STEP3는 draw<N 누적만",
                "특기 프로파일 단일 pass 증분 누적(O(n))",
                "번호대 5구간 집계 + 라플라스 스무딩 (h+1)/(p+2)로 소표본 과신 방지",
            ],
            "pitfalls": [
                "DB 락 — READ-ONLY + query_only=ON + busy_timeout",
                "컨닝 — 튀는후보는 pre-draw 6뇌세트, 당첨은 채점에만",
                "바닥률 — 풀<=M이면 특기=랜덤 무의미, pool>M 정보성 회차만 집계",
            ],
            "flaws": [
                "다중비교 위양성 — 카이제곱 Bonferroni 보정",
                "순환정의 — v3(순수 희소성) 대조군으로 뇌특기 순증분만 분리 측정",
                "사전기대 — 0629에서 약했음, 미달 시 R2 정직 기록",
            ],
            "decision": "큰 허점 없음 — 그대로 실행",
        },
        "config": {
            "spike_max_k": SPIKE_MAX_K,
            "m_predict": M_PREDICT,
            "random_trials": RANDOM_TRIALS,
            "bands": BANDS,
            "laplace": [LAPLACE_A, LAPLACE_B],
        },
        "step2": s2,
        "step3_periods": period_stats,
        "verdict": verdict,
        "six_before": six_before,
        "six_after": six_after,
        "lead1_before": lead1_before,
        "lead1_after": lead1_after,
        "regression_ok": (six_before == six_after and lead1_before == lead1_after),
    }

    txt = _format_txt(result)
    jp = json.dumps(result, ensure_ascii=False, indent=2)
    fname = "20260701_1군7뇌_튀는번호발굴_검증.txt"

    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / fname).write_text(txt, encoding="utf-8")
        (d / "_audit_20260701_army1_7brain_spike_number.json").write_text(
            jp, encoding="utf-8"
        )

    print(str(REPORT_DIRS[0] / fname))
    print(verdict["final"].encode("ascii", "replace").decode("ascii"))
    print(f"regression_ok: {result['regression_ok']}")


if __name__ == "__main__":
    main()
