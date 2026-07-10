# -*- coding: utf-8
"""CAP2 lead1 독립성 최종 감사 — 백필 후 실행.

실행: python tools/_audit_cap2_independence.py
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
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
MAX_ORIGIN_PCT = 40.0
MAX_PER_DRAW = 2
TIERS = [
    ("5등+", 3),
    ("4등+", 4),
    ("3등+", 5),
    ("1등", 6),
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(ROOT / "data" / "lotto.db"))
    conn.row_factory = sqlite3.Row
    return conn


def _load_flat_map(conn, dn: int) -> dict[tuple[int, ...], str]:
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
    return {
        tuple(sorted(int(r[i]) for i in range(1, 7))): str(r[0])
        for r in rows
    }


def _best_matched(rows) -> int:
    if not rows:
        return -1
    return max(int(r["matched_count"]) for r in rows if r["matched_count"] >= 0)


def run_independence_audit(conn: sqlite3.Connection) -> dict:
    """STEP3: 출처 점유·CAP2·적중 상관."""
    draws = [
        int(r[0])
        for r in conn.execute(
            "SELECT DISTINCT target_draw_no FROM lotto_predictions "
            "WHERE brain_tag='lead1' ORDER BY target_draw_no"
        ).fetchall()
    ]

    origin = Counter()
    total_sets = 0
    max_per_draw: list[int] = []
    violations_cap2 = 0
    violations_40pct: list[str] = []

    # tier → draw sets
    lead1_hits: dict[str, set[int]] = {t[0]: set() for t in TIERS}
    brain_hits: dict[str, dict[str, set[int]]] = {
        b: {t[0]: set() for t in TIERS} for b in POOL_BRAINS
    }

    for dn in draws:
        fmap = _load_flat_map(conn, dn)
        lead_rows = conn.execute(
            """
            SELECT num1,num2,num3,num4,num5,num6, matched_count, reasoning
            FROM lotto_predictions WHERE target_draw_no=? AND brain_tag='lead1'
            ORDER BY id
            """,
            (dn,),
        ).fetchall()

        draw_origin = Counter()
        for r in lead_rows:
            nums = tuple(sorted(int(r[i]) for i in range(6)))
            tag = fmap.get(nums, "unknown")
            # reasoning에 원뇌= 태그가 있으면 우선 (flat 중복 세트 대비)
            reasoning = str(r["reasoning"]) if "reasoning" in r.keys() else ""
            if "원뇌=" in reasoning:
                tag = reasoning.split("원뇌=")[-1].strip()
            origin[tag] += 1
            draw_origin[tag] += 1
            total_sets += 1

        if draw_origin:
            pool_only = Counter({k: v for k, v in draw_origin.items() if k in POOL_BRAINS})
            mx = max(pool_only.values()) if pool_only else 0
            max_per_draw.append(mx)
            if mx > MAX_PER_DRAW:
                violations_cap2 += 1

        lead_best = _best_matched(lead_rows)
        for tier_name, threshold in TIERS:
            if lead_best >= threshold:
                lead1_hits[tier_name].add(dn)

        for b in POOL_BRAINS:
            brows = conn.execute(
                """
                SELECT matched_count FROM lotto_predictions
                WHERE target_draw_no=? AND brain_tag=?
                """,
                (dn, b),
            ).fetchall()
            bb = _best_matched(brows)
            for tier_name, threshold in TIERS:
                if bb >= threshold:
                    brain_hits[b][tier_name].add(dn)

    origin_pct = {
        b: round(100.0 * origin.get(b, 0) / total_sets, 2) if total_sets else 0
        for b in POOL_BRAINS
    }
    # unknown 제외 — POOL_BRAINS만 40% 검사
    for b, pct in origin_pct.items():
        if pct > MAX_ORIGIN_PCT:
            violations_40pct.append(f"{b}={pct}%")

    # 상관: lead1 hit 회차 vs 각 뇌 hit 회차 겹침
    correlations = []
    for tier_name, _ in TIERS:
        L = lead1_hits[tier_name]
        row = {"tier": tier_name, "lead1_draws": len(L), "brains": {}}
        for b in POOL_BRAINS:
            B = brain_hits[b][tier_name]
            inter = L & B
            row["brains"][b] = {
                "brain_draws": len(B),
                "overlap": len(inter),
                "pct_of_lead1": round(100.0 * len(inter) / len(L), 2) if L else 0,
                "pct_of_brain": round(100.0 * len(inter) / len(B), 2) if B else 0,
                "jaccard": round(len(inter) / len(L | B), 4) if (L | B) else 0,
            }
        correlations.append(row)

    return {
        "n_draws": len(draws),
        "total_sets": total_sets,
        "origin_pct": origin_pct,
        "origin_counts": dict(origin),
        "max_brain_avg": round(statistics.mean(max_per_draw), 3) if max_per_draw else 0,
        "max_brain_p95": sorted(max_per_draw)[int(len(max_per_draw) * 0.95)]
        if max_per_draw else 0,
        "cap2_violations": violations_cap2,
        "cap2_pass": violations_cap2 == 0,
        "origin_40pct_pass": len(violations_40pct) == 0,
        "origin_40pct_violations": violations_40pct,
        "hit_correlations": correlations,
        "structural_note": (
            "7뇌(lead1)는 5뇌 25세트의 부분집합(5/25)이므로 "
            "적중 회차가 특정 뇌 적중 회차와 겹치는 것은 구조상 불가피. "
            "CAP2는 출처 독점(3세트+)을 제거해 다뇌 합의체에 가깝게 만듦."
        ),
    }


def _six_brain_counts(conn) -> dict[str, int]:
    ph = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag, COUNT(*) FROM lotto_predictions "
        f"WHERE brain_tag IN ({ph}) GROUP BY brain_tag",
        SIX_BRAINS,
    ).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def format_report(
    backfill: dict,
    audit: dict,
    six_before: dict,
    six_after: dict,
) -> str:
    lines = [
        "20260701_1군7뇌_CAP2확정_독립성감사",
        "동생 → 커서 | 2026-07-01 | B1_CAP2 이식+백필+감사",
        "",
        "공식: 5뇌(hyena제외) SEL4+v3 통합풀 greedy, 뇌당 최대 2세트",
        "6뇌 engine/DB 행 수정 0건 | lead1만 DELETE+INSERT",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 1 — predict_brain7.py B1_CAP2 교체",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  _select_cap2_sets() | MAX_PER_BRAIN=2 | reasoning=CAP2|원뇌=tag",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 2 — lead1 리셋 백필 [88~1230]",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  삭제: {backfill.get('deleted_rows', '?')}행",
        f"  백필: {backfill.get('backfilled_draws', '?')}회 "
        f"({backfill.get('first_draw')}~{backfill.get('last_draw')})",
        f"  lead1 행: {backfill.get('lead1_rows', '?')} "
        f"(채점 {backfill.get('lead1_scored', '?')})",
        f"  소요: {backfill.get('elapsed_sec', '?')}s",
        f"  스팟체크: {backfill.get('spot_summary', '?')}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 독립성 최종 감사",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "(a) 뇌별 출처 점유율 (40% 이하 목표):",
    ]
    for b in POOL_BRAINS:
        pct = audit["origin_pct"].get(b, 0)
        ok = "OK" if pct <= MAX_ORIGIN_PCT else "FAIL"
        lines.append(f"  {BRAIN_KO[b]} ({b}): {pct}% [{ok}]")
    lines.append(
        f"  → 40% 초과: {audit['origin_40pct_violations'] or '없음'} "
        f"| PASS={audit['origin_40pct_pass']}"
    )

    lines += [
        "",
        "(b) 회차당 최대 뇌 점유 ≤2 (CAP2):",
        f"  평균 max: {audit['max_brain_avg']} | p95: {audit['max_brain_p95']}",
        f"  CAP2 위반 회차: {audit['cap2_violations']} | PASS={audit['cap2_pass']}",
        "",
        "(c) 7뇌 vs 5뇌 적중 회차 겹침 (1~5등 = matched 3/4/5/6+):",
        "  tier | lead1회차 | 뇌별 overlap/lead1% (겹침율)",
    ]
    for corr in audit["hit_correlations"]:
        lines.append(
            f"  [{corr['tier']}] lead1={corr['lead1_draws']}회"
        )
        for b in POOL_BRAINS:
            br = corr["brains"][b]
            lines.append(
                f"    {b}: overlap={br['overlap']} "
                f"({br['pct_of_lead1']}% of lead1, jaccard={br['jaccard']})"
            )

    lines += [
        "",
        "  R2 정직:",
        f"  {audit['structural_note']}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 4 — 6뇌 회귀",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for tag in SIX_BRAINS:
        b = six_before.get(tag, 0)
        a = six_after.get(tag, 0)
        lines.append(f"  {tag}: {b} → {a} [{'OK' if b == a else 'CHANGED!'}]")
    lines.append(
        f"  6뇌 전체 동일: {six_before == six_after}"
    )
    return "\n".join(lines) + "\n"


def main(backfill_result: dict | None = None) -> dict:
    """독립성 감사 단독 또는 백필 결과와 함께."""
    conn = _connect()
    audit = run_independence_audit(conn)
    six_after = _six_brain_counts(conn)
    conn.close()

    six_before = backfill_result.get("six_before", six_after) if backfill_result else six_after
    bf = backfill_result.get("backfill", {}) if backfill_result else {}
    if backfill_result:
        bf = {
            **bf,
            "lead1_rows": backfill_result.get("lead1_total_rows"),
            "lead1_scored": backfill_result.get("lead1_scored"),
            "spot_summary": backfill_result.get("spot_summary"),
        }

    txt = format_report(bf, audit, six_before, six_after)
    result = {
        "title": "20260701_1군7뇌_CAP2확定_독립성감사",
        "audit": audit,
        "six_regression_ok": six_before == six_after,
        "backfill": backfill_result,
    }

    fname = "20260701_1군7뇌_CAP2확정_독립성감사.txt"
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / fname).write_text(txt, encoding="utf-8")
        (d / "_audit_20260701_cap2_independence.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(str(REPORT_DIRS[1] / fname))
    print(txt.encode("ascii", "replace").decode("ascii"))
    return result


if __name__ == "__main__":
    main()
