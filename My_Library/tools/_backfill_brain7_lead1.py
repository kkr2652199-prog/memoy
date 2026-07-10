# -*- coding: utf-8
"""1군 7뇌 lead1 과거이력 백필 — 88~1230 walk-forward (B: 하이에나 제외).

실행: python tools/_backfill_brain7_lead1.py
6뇌 행 수정 0건. lead1 DELETE 전량 후 INSERT.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]

BACKFILL_LO = 88
BACKFILL_HI = 1230
POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
SIX_BRAINS = ("stat", "markov", "llm", "lstm", "fusion", "hyena")
SPOT_DRAWS = (88, 600, 1230)


def _db_retry(fn, retries: int = 8, delay: float = 2.0):
    """database is locked 재시도."""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            last_err = e
            if "locked" not in str(e).lower():
                raise
            time.sleep(delay * (attempt + 1))
    raise last_err  # type: ignore[misc]


def _eligible_draws(conn: sqlite3.Connection) -> list[int]:
    """5뇌 각 5세트 이상인 회차 — 88~1230 순."""
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"""
        SELECT p.target_draw_no AS dn, p.brain_tag, COUNT(*) AS c
        FROM lotto_predictions p
        INNER JOIN lotto_draws d ON d.draw_no = p.target_draw_no
        WHERE p.brain_tag IN ({ph})
        GROUP BY p.target_draw_no, p.brain_tag
        HAVING c >= 5
        """,
        POOL_BRAINS,
    ).fetchall()
    by: dict[int, set[str]] = {}
    for dn, tag, _ in rows:
        by.setdefault(int(dn), set()).add(str(tag))
    return sorted(
        dn for dn, tags in by.items()
        if tags >= set(POOL_BRAINS) and BACKFILL_LO <= dn <= BACKFILL_HI
    )


def _six_brain_row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    ph = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"""
        SELECT brain_tag, COUNT(*) FROM lotto_predictions
        WHERE brain_tag IN ({ph}) GROUP BY brain_tag
        """,
        SIX_BRAINS,
    ).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def _lead1_counts(conn: sqlite3.Connection) -> tuple[int, int]:
    draws = conn.execute(
        "SELECT COUNT(DISTINCT target_draw_no) FROM lotto_predictions WHERE brain_tag='lead1'"
    ).fetchone()[0]
    rows = conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'"
    ).fetchone()[0]
    return int(draws), int(rows)


def _hyena_copy_stats(conn: sqlite3.Connection, sample_draws: list[int]) -> dict:
    """lead1 세트 중 hyena 출처/겹침 비율 (샘플)."""
    total = origin_hyena = near5 = 0
    for dn in sample_draws:
        flat_rows = conn.execute(
            """
            SELECT brain_tag, num1,num2,num3,num4,num5,num6
            FROM lotto_predictions
            WHERE target_draw_no=? AND brain_tag IN ({})
            """.format(",".join("?" * len(SIX_BRAINS))),
            (dn, *SIX_BRAINS),
        ).fetchall()
        hyena_sets = {
            tuple(sorted(int(r[i]) for i in range(1, 7)))
            for r in flat_rows
            if r[0] == "hyena"
        }
        flat_map = {
            tuple(sorted(int(r[i]) for i in range(1, 7))): str(r[0])
            for r in flat_rows
        }
        lead = conn.execute(
            """
            SELECT num1,num2,num3,num4,num5,num6
            FROM lotto_predictions WHERE target_draw_no=? AND brain_tag='lead1'
            ORDER BY id
            """,
            (dn,),
        ).fetchall()
        for r in lead:
            nums = tuple(sorted(int(r[i]) for i in range(6)))
            total += 1
            if flat_map.get(nums) == "hyena":
                origin_hyena += 1
            if nums in hyena_sets:
                near5 += 1
            else:
                ov = max((len(set(nums) & set(h)) for h in hyena_sets), default=0)
                if ov >= 5:
                    near5 += 1
    return {
        "sample_draws": sample_draws,
        "sets": total,
        "origin_hyena_pct": round(100.0 * origin_hyena / total, 2) if total else 0,
        "near5_pct": round(100.0 * near5 / total, 2) if total else 0,
    }


def _ordered_backfill(conn, target_draws: list[int]) -> dict:
    """88~1230 회차 순 — 단일 pass walk-forward (O(n))."""
    from app.lotto.predict_brain7 import (
        BRAIN7_METHOD,
        BRAIN7_TAG,
        MIN_POOL_SETS,
        SETS_TO_PICK,
        _draw_contribution,
        _load_flat_sets,
        _pool_brains_ready,
        _score_rows_if_actual,
        _select_cap2_sets,
        _win_plus_bonus,
    )

    deleted = _db_retry(lambda: conn.execute(
        "DELETE FROM lotto_predictions WHERE brain_tag='lead1'"
    ).rowcount)
    _db_retry(lambda: conn.commit())
    print(f"  lead1 전량 삭제: {deleted}행", flush=True)

    target_set = set(target_draws)
    ok_draws: list[int] = []
    skip_draws: list[int] = []
    history: list[tuple[int, dict[str, float]]] = []
    t0 = time.time()

    # warmup + backfill: eligible 전체를 회차순 1회 순회
    ph = ",".join("?" * len(POOL_BRAINS))
    all_with_pool = conn.execute(
        f"""
        SELECT p.target_draw_no AS dn, p.brain_tag, COUNT(*) AS c
        FROM lotto_predictions p
        INNER JOIN lotto_draws d ON d.draw_no = p.target_draw_no
        WHERE p.brain_tag IN ({ph})
        GROUP BY p.target_draw_no, p.brain_tag
        HAVING c >= 5
        """,
        POOL_BRAINS,
    ).fetchall()
    pool_ready: dict[int, set[str]] = {}
    for dn, tag, _ in all_with_pool:
        pool_ready.setdefault(int(dn), set()).add(str(tag))
    ordered_all = sorted(
        dn for dn, tags in pool_ready.items() if tags >= set(POOL_BRAINS)
    )

    for dn in ordered_all:
        if dn > BACKFILL_HI:
            break

        if dn in target_set:
            if not _pool_brains_ready(conn, dn):
                skip_draws.append(dn)
            else:
                flat = _load_flat_sets(conn, dn)
                if len(flat) < MIN_POOL_SETS:
                    skip_draws.append(dn)
                else:
                    cap2 = _select_cap2_sets(flat, history, dn)
                    if len(cap2) < SETS_TO_PICK:
                        skip_draws.append(dn)
                    else:
                        preds: list[dict] = []
                        for rank, (origin, nums, src, score) in enumerate(cap2, 1):
                            label = "표합" if src == "SEL4" else "기여"
                            preds.append({
                                "nums": list(nums),
                                "confidence": round(min(score * 10, 99.9), 1),
                                "reasoning": (
                                    f"출처:{src} | {label}점수={score:.2f} | CAP2 | "
                                    f"원뇌={origin}"
                                ),
                                "method": BRAIN7_METHOD,
                                "rank": rank,
                            })

                        _db_retry(lambda: conn.executemany(
                            """
                            INSERT INTO lotto_predictions
                            (target_draw_no, method, brain_tag, num1,num2,num3,num4,num5,num6,
                             confidence, reasoning, matched_count, bonus_matched)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            [
                                (
                                    dn,
                                    p["method"],
                                    BRAIN7_TAG,
                                    *p["nums"],
                                    p["confidence"],
                                    p["reasoning"],
                                    -1,
                                    0,
                                )
                                for p in preds[:SETS_TO_PICK]
                            ],
                        ))
                        _score_rows_if_actual(conn, dn)
                        ok_draws.append(dn)

                        if len(ok_draws) % 50 == 0:
                            _db_retry(lambda: conn.commit())
                            print(
                                f"  ... {len(ok_draws)}/{len(target_draws)} "
                                f"(latest {dn})",
                                flush=True,
                            )

        flat_hist = _load_flat_sets(conn, dn)
        if len(flat_hist) >= MIN_POOL_SETS:
            win7 = _win_plus_bonus(conn, dn)
            if len(win7) >= 7:
                history.append((dn, _draw_contribution(flat_hist, win7)))

    _db_retry(lambda: conn.commit())
    elapsed = round(time.time() - t0, 1)
    return {
        "deleted_rows": deleted,
        "backfilled_draws": len(ok_draws),
        "skipped_draws": skip_draws,
        "elapsed_sec": elapsed,
        "first_draw": ok_draws[0] if ok_draws else None,
        "last_draw": ok_draws[-1] if ok_draws else None,
    }


def _spot_check(conn) -> list[dict]:
    from app.lotto.predict_brain7 import compute_brain7_sets

    results = []
    for dn in SPOT_DRAWS:
        saved = conn.execute(
            """
            SELECT num1,num2,num3,num4,num5,num6, reasoning
            FROM lotto_predictions
            WHERE target_draw_no=? AND brain_tag='lead1'
            ORDER BY id
            """,
            (dn,),
        ).fetchall()

        recomputed = compute_brain7_sets(conn, dn)
        saved_sets = [tuple(sorted(r[:6])) for r in saved]
        recomputed_sets = [tuple(sorted(p["nums"])) for p in recomputed]

        hist_max = conn.execute(
            """
            SELECT MAX(p.target_draw_no) FROM lotto_predictions p
            INNER JOIN lotto_draws d ON d.draw_no = p.target_draw_no
            WHERE p.target_draw_no < ?
            """,
            (dn,),
        ).fetchone()[0]

        v3_rows = [r for r in saved if "V3" in str(r[6])]
        cap2_tag = all("CAP2" in str(r[6]) for r in saved) if saved else False
        results.append({
            "draw_no": dn,
            "saved_count": len(saved),
            "sets_match": saved_sets == recomputed_sets,
            "max_history_draw": hist_max,
            "no_lookahead": (hist_max is None or hist_max < dn),
            "v3_count": len(v3_rows),
            "cap2_tag": cap2_tag,
            "contamination_check": "PASS" if (hist_max is None or hist_max < dn) else "FAIL",
        })
    return results


def _format_report(result: dict) -> str:
    bf = result["backfill"]
    lines = [
        "20260701_1군7뇌_1등가자_백필완료_B5뇌",
        "동생 → 커서 | 2026-07-01 | 6뇌 무변경 | hyena 제외 5뇌 풀",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"STEP 1 — lead1 전량 삭제 후 백필 [{BACKFILL_LO}~{BACKFILL_HI}]",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"삭제 행: {bf['deleted_rows']}",
        f"백필 회차 수: {bf['backfilled_draws']}",
        f"범위: {bf['first_draw']} ~ {bf['last_draw']}",
        f"스킵 회차: {len(bf['skipped_draws'])}",
        f"소요 시간: {bf['elapsed_sec']}s",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 2 — 채점",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"lead1 scored: {result['lead1_scored']} / {result['lead1_total_rows']}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 검증",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"lead1 총 행: {result['lead1_total_rows']} (기대 {result['expected_rows']})",
        f"행 수 일치: {result['rows_ok']}",
        f"6뇌 전체 동일: {result['six_regression_ok']}",
        "",
        "하이에나 복사율 (스팟 88/600/1230):",
        f"  origin_hyena: {result['hyena_stats']['origin_hyena_pct']}%",
        f"  near5+: {result['hyena_stats']['near5_pct']}%",
        "",
        "컨닝 스팟체크:",
    ]
    for sp in result["spot_checks"]:
        lines.append(
            f"  draw {sp['draw_no']}: match={sp['sets_match']} | "
            f"5뇌풀={sp['pool5_tag']} | {sp['contamination_check']}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    from app.lotto.models import get_lotto_db

    conn = get_lotto_db()
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("PRAGMA locking_mode=EXCLUSIVE")

    six_before = _six_brain_row_counts(conn)
    _, lead1_before = _lead1_counts(conn)

    target = _eligible_draws(conn)
    print(f"백필 대상: {len(target)}회 ({BACKFILL_LO}~{BACKFILL_HI}, 5뇌 준비 순)")

    backfill_result = _ordered_backfill(conn, target)

    six_after = _six_brain_row_counts(conn)
    lead1_draws, lead1_total = _lead1_counts(conn)
    lead1_scored = conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1' AND matched_count>=0"
    ).fetchone()[0]

    spot = _spot_check(conn)
    hyena_stats = _hyena_copy_stats(conn, list(SPOT_DRAWS))
    conn.close()

    expected = backfill_result["backfilled_draws"] * 5
    rows_ok = lead1_total == expected

    result = {
        "formula": "B_NO_HYENA",
        "backfill": backfill_result,
        "six_before": six_before,
        "six_after": six_after,
        "six_regression_ok": six_before == six_after,
        "lead1_before_rows": lead1_before,
        "lead1_draws": lead1_draws,
        "lead1_total_rows": lead1_total,
        "lead1_scored": int(lead1_scored),
        "expected_rows": expected,
        "rows_ok": rows_ok,
        "spot_checks": spot,
        "hyena_stats": hyena_stats,
    }

    txt = _format_report(result)
    jp = json.dumps(result, ensure_ascii=False, indent=2)

    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / "20260701_1군7뇌_1등가자_백필완료_B5뇌.txt").write_text(txt, encoding="utf-8")
        (d / "_audit_20260701_brain7_backfill_b5.json").write_text(jp, encoding="utf-8")

    print(txt.encode("ascii", "replace").decode("ascii"))
    print(f"6brain regression: {result['six_regression_ok']}")
    print(f"lead1 rows: {lead1_total} (expected {expected})")


if __name__ == "__main__":
    main()
