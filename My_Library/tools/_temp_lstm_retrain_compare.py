# -*- coding: utf-8
"""20260710 LSTM 재학습 방식 4종 in-memory walk-forward 비교 (READ-ONLY).

A 매회차 재학습 | B 증분 SGD | C IncLSTM 근사(앙상블) | D 슬라이딩 윈도우
DB write 0 · app/lotto 수정 0 · 구간 1131~1231

실행: python tools/_temp_lstm_retrain_compare.py
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "lotto.db"
REPORT_DIR = ROOT.parent / "My_Drive_Sync" / "커서보고서"
REPORT_STEM = "20260710_1군_LSTM재학습방식_inmemory비교실험"
CHECKPOINT_PATH = ROOT / "tools" / "_temp_lstm_retrain_compare_checkpoint.json"

DRAW_FROM = 1131
DRAW_TO = 1231
N_SETS = 5
RANDOM_BASELINE = 6 * 6 / 45  # 0.8
SLIDING_WINDOW = 250
INCR_STEPS = 5
ENSEMBLE_MAX = 3
ENSEMBLE_FINE_WINDOW = 100

from app.lotto.filters import tier1_filter  # noqa: E402
from app.lotto.predict_lstm import (  # noqa: E402
    SEQ_LEN,
    LottoLSTM,
    _build_xy_tensors,
    _fit_model,
    _multihot_from_draw,
    _predict_on_device,
    _softmax_to_dict,
    _sort_by_draw_no,
    _train_on_device,
)

try:
    import torch
    from scipy import stats as scipy_stats

    _TORCH_OK = True
except ImportError as e:
    print(f"DEP MISSING: {e}")
    sys.exit(1)


def _safe_print(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def _load_draws_before(conn: sqlite3.Connection, target: int) -> list[dict]:
    rows = conn.execute(
        """SELECT draw_no, num1, num2, num3, num4, num5, num6, bonus
           FROM lotto_draws WHERE draw_no < ? ORDER BY draw_no""",
        (target,),
    ).fetchall()
    return [dict(r) for r in rows]


def _actual_nums(conn: sqlite3.Connection, target: int) -> set[int]:
    row = conn.execute(
        "SELECT num1,num2,num3,num4,num5,num6 FROM lotto_draws WHERE draw_no=?",
        (target,),
    ).fetchone()
    return {int(row[k]) for k in ("num1", "num2", "num3", "num4", "num5", "num6")}


def _pmf_from_model(model: LottoLSTM, draws: list[dict], device) -> dict[int, float]:
    d_sorted = _sort_by_draw_no(draws)
    if len(d_sorted) < SEQ_LEN:
        return {i: 1 / 45 for i in range(1, 46)}
    win = d_sorted[-SEQ_LEN:]
    seq = [_multihot_from_draw(w) for w in win]
    x1 = torch.tensor([seq], dtype=torch.float32)
    o = _predict_on_device(model, x1, device)
    return _softmax_to_dict(o[0])


def _ensemble_pmf(models: list[LottoLSTM], draws: list[dict], device) -> dict[int, float]:
    if not models:
        return {i: 1 / 45 for i in range(1, 46)}
    acc = {i: 0.0 for i in range(1, 46)}
    for m in models:
        pmf = _pmf_from_model(m, draws, device)
        for k, v in pmf.items():
            acc[k] += v
    s = sum(acc.values())
    return {k: v / s for k, v in acc.items()}


def _sets_from_pmf(pmf: dict[int, float], n_sets: int, seed: int) -> list[list[int]]:
    rng = random.Random(seed)
    results: list[list[int]] = []
    used: set[tuple[int, ...]] = set()
    pool_nums = list(range(1, 46))
    attempts = 0
    while len(results) < n_sets and attempts < 5000:
        attempts += 1
        pool = pool_nums[:]
        w = [pmf.get(n, 1 / 45) for n in pool]
        nums: list[int] = []
        for _ in range(6):
            chosen = rng.choices(pool, weights=w, k=1)[0]
            nums.append(chosen)
            idx = pool.index(chosen)
            pool.pop(idx)
            w.pop(idx)
        nums.sort()
        if not tier1_filter(nums):
            continue
        key = tuple(nums)
        if key in used:
            continue
        used.add(key)
        results.append(nums)
    return results


def _incremental_update(model: LottoLSTM, draws: list[dict], device, steps: int) -> None:
    x_t, y_t, n = _build_xy_tensors(draws, device)
    if n <= 0:
        return
    last_x = x_t[-1:].detach()
    last_y = y_t[-1:].detach()
    opt = torch.optim.Adam(model.parameters(), lr=5e-4)
    crit = torch.nn.BCELoss()
    model.train()
    for _ in range(steps):
        opt.zero_grad()
        out = model(last_x)
        loss = crit(out, last_y)
        loss.backward()
        opt.step()
    model.eval()


@dataclass
class MethodResult:
    name: str
    per_set_hits: list[int] = field(default_factory=list)
    best_of5_hits: list[int] = field(default_factory=list)
    train_secs: list[float] = field(default_factory=list)

    def summarize(self) -> dict:
        ps = self.per_set_hits
        b5 = self.best_of5_hits
        ts = self.train_secs
        mean_ps = statistics.mean(ps) if ps else 0.0
        mean_b5 = statistics.mean(b5) if b5 else 0.0
        mean_t = statistics.mean(ts) if ts else 0.0
        # one-sample t-test vs 0.8 (two-sided: 다를까 / one-sided greater: 0.8보다 높은가)
        t_p_two = float("nan")
        t_p_greater = float("nan")
        w_p_greater = float("nan")
        if len(ps) >= 2:
            t_p_two = float(scipy_stats.ttest_1samp(ps, RANDOM_BASELINE).pvalue)
            t_p_greater = float(
                scipy_stats.ttest_1samp(ps, RANDOM_BASELINE, alternative="greater").pvalue
            )
            diffs = [x - RANDOM_BASELINE for x in ps]
            if any(d != 0 for d in diffs):
                w_p_greater = float(
                    scipy_stats.wilcoxon(diffs, alternative="greater").pvalue
                )
            else:
                w_p_greater = 1.0
        sig = "유의(>0.8)" if t_p_greater < 0.05 and mean_ps > RANDOM_BASELINE else (
            "0.8 수렴(유의↑ 없음)" if t_p_greater >= 0.05 else "0.8 미만/유의↓"
        )
        return {
            "method": self.name,
            "per_set_mean": round(mean_ps, 4),
            "best_of5_mean": round(mean_b5, 4),
            "vs_random_0.8": {
                "baseline": RANDOM_BASELINE,
                "t_test_p_two_sided": round(t_p_two, 6) if t_p_two == t_p_two else None,
                "t_test_p_greater": round(t_p_greater, 6) if t_p_greater == t_p_greater else None,
                "wilcoxon_p_greater": round(w_p_greater, 6) if w_p_greater == w_p_greater else None,
                "significance_label": sig,
            },
            "train_sec_mean": round(mean_t, 2),
            "train_sec_total": round(sum(ts), 1),
            "n_sets": len(ps),
            "n_draws": len(b5),
        }


def run_method_a(conn, device) -> MethodResult:
    res = MethodResult("A_매회차재학습")
    for target in range(DRAW_FROM, DRAW_TO + 1):
        t0 = time.perf_counter()
        draws = _load_draws_before(conn, target)
        model, _ = _fit_model(draws, prefer_cuda=False)
        pmf = _pmf_from_model(model, draws, torch.device("cpu"))
        sets = _sets_from_pmf(pmf, N_SETS, seed=target * 17 + 3)
        actual = _actual_nums(conn, target)
        hits = [len(set(s) & actual) for s in sets]
        res.per_set_hits.extend(hits)
        res.best_of5_hits.append(max(hits) if hits else 0)
        res.train_secs.append(time.perf_counter() - t0)
        if target % 10 == 1 or target == DRAW_TO:
            _safe_print(
                f"  A {target}: hits={hits} avg={statistics.mean(res.per_set_hits):.3f} "
                f"t={res.train_secs[-1]:.1f}s"
            )
    return res


def run_method_b(conn, device) -> MethodResult:
    res = MethodResult("B_증분SGD")
    model: LottoLSTM | None = None
    for target in range(DRAW_FROM, DRAW_TO + 1):
        t0 = time.perf_counter()
        draws = _load_draws_before(conn, target)
        if model is None:
            model, _ = _fit_model(draws, prefer_cuda=False)
        else:
            _incremental_update(model, draws, device, INCR_STEPS)
        pmf = _pmf_from_model(model, draws, torch.device("cpu"))
        sets = _sets_from_pmf(pmf, N_SETS, seed=target * 17 + 3)
        actual = _actual_nums(conn, target)
        hits = [len(set(s) & actual) for s in sets]
        res.per_set_hits.extend(hits)
        res.best_of5_hits.append(max(hits) if hits else 0)
        res.train_secs.append(time.perf_counter() - t0)
        if target % 10 == 1 or target == DRAW_TO:
            _safe_print(
                f"  B {target}: hits={hits} avg={statistics.mean(res.per_set_hits):.3f} "
                f"t={res.train_secs[-1]:.1f}s"
            )
    return res


def run_method_c(conn, device) -> MethodResult:
    """IncLSTM 근사: 앙상블(최대 3) + 주기적 fine-window 재학습 + 증분 업데이트."""
    res = MethodResult("C_IncLSTM근사_앙상블")
    ensemble: list[LottoLSTM] = []
    for target in range(DRAW_FROM, DRAW_TO + 1):
        t0 = time.perf_counter()
        draws = _load_draws_before(conn, target)
        if not ensemble:
            m, _ = _fit_model(draws, prefer_cuda=False)
            ensemble.append(m)
        elif (target - DRAW_FROM) % 15 == 0:
            win_draws = draws[-ENSEMBLE_FINE_WINDOW:] if len(draws) > ENSEMBLE_FINE_WINDOW else draws
            m_new, _ = _fit_model(win_draws, prefer_cuda=False)
            ensemble.append(m_new)
            if len(ensemble) > ENSEMBLE_MAX:
                ensemble.pop(0)
        else:
            _incremental_update(ensemble[-1], draws, device, INCR_STEPS)
        pmf = _ensemble_pmf(ensemble, draws, torch.device("cpu"))
        sets = _sets_from_pmf(pmf, N_SETS, seed=target * 17 + 3)
        actual = _actual_nums(conn, target)
        hits = [len(set(s) & actual) for s in sets]
        res.per_set_hits.extend(hits)
        res.best_of5_hits.append(max(hits) if hits else 0)
        res.train_secs.append(time.perf_counter() - t0)
        if target % 10 == 1 or target == DRAW_TO:
            _safe_print(
                f"  C {target}: hits={hits} ens={len(ensemble)} "
                f"avg={statistics.mean(res.per_set_hits):.3f} t={res.train_secs[-1]:.1f}s"
            )
    return res


def run_method_d(conn, device) -> MethodResult:
    res = MethodResult(f"D_슬라이딩W{SLIDING_WINDOW}")
    for target in range(DRAW_FROM, DRAW_TO + 1):
        t0 = time.perf_counter()
        draws = _load_draws_before(conn, target)
        win = draws[-SLIDING_WINDOW:] if len(draws) > SLIDING_WINDOW else draws
        model, _ = _fit_model(win, prefer_cuda=False)
        pmf = _pmf_from_model(model, draws, torch.device("cpu"))
        sets = _sets_from_pmf(pmf, N_SETS, seed=target * 17 + 3)
        actual = _actual_nums(conn, target)
        hits = [len(set(s) & actual) for s in sets]
        res.per_set_hits.extend(hits)
        res.best_of5_hits.append(max(hits) if hits else 0)
        res.train_secs.append(time.perf_counter() - t0)
        if target % 10 == 1 or target == DRAW_TO:
            _safe_print(
                f"  D {target}: hits={hits} avg={statistics.mean(res.per_set_hits):.3f} "
                f"t={res.train_secs[-1]:.1f}s"
            )
    return res


def _load_checkpoint() -> dict:
    if CHECKPOINT_PATH.is_file():
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    return {"completed": {}}


def _save_checkpoint(completed: dict) -> None:
    CHECKPOINT_PATH.write_text(
        json.dumps({"completed": completed}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _result_from_dict(name: str, d: dict) -> MethodResult:
    r = MethodResult(name)
    r.per_set_hits = list(d["per_set_hits"])
    r.best_of5_hits = list(d["best_of5_hits"])
    r.train_secs = list(d["train_secs"])
    return r


def _finalize(results: list[MethodResult], elapsed: float) -> None:
    summaries = [r.summarize() for r in results]
    _safe_print("\n=== RESULT TABLE ===")
    header = (
        f"{'방식':<22} {'per-set':>8} {'best-of-5':>10} "
        f"{'vs0.8유의성':<18} {'회당sec':>8} {'판정'}"
    )
    _safe_print(header)
    _safe_print("-" * len(header.encode("utf-8", errors="ignore")))
    for s in summaries:
        sig = s["vs_random_0.8"]["significance_label"]
        _safe_print(
            f"{s['method']:<22} {s['per_set_mean']:>8.4f} {s['best_of5_mean']:>10.4f} "
            f"p_greater={s['vs_random_0.8']['t_test_p_greater']:<8} "
            f"{s['train_sec_mean']:>8.2f} {sig}"
        )

    out = {
        "meta": {
            "draw_range": [DRAW_FROM, DRAW_TO],
            "n_sets_per_draw": N_SETS,
            "random_baseline": RANDOM_BASELINE,
            "sliding_window": SLIDING_WINDOW,
            "incr_steps": INCR_STEPS,
            "ensemble_max": ENSEMBLE_MAX,
            "seed_formula": "target*17+3",
            "db_mode": "read-only",
            "total_elapsed_sec": round(elapsed, 1),
            "command": "python tools/_temp_lstm_retrain_compare.py",
        },
        "summaries": summaries,
        "raw_per_method": {
            r.name: {
                "per_set_hits": r.per_set_hits,
                "best_of5_hits": r.best_of5_hits,
                "train_secs": [round(x, 3) for x in r.train_secs],
            }
            for r in results
        },
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / f"{REPORT_STEM}.json"
    txt_path = REPORT_DIR / f"{REPORT_STEM}.txt"
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        REPORT_STEM,
        f"elapsed={elapsed:.1f}s",
        "",
        header,
        "-" * 80,
    ]
    for s in summaries:
        sig = s["vs_random_0.8"]
        lines.append(
            f"{s['method']}|{s['per_set_mean']}|{s['best_of5_mean']}|"
            f"t_p_greater={sig['t_test_p_greater']}|wilcox_p={sig['wilcoxon_p_greater']}|"
            f"{sig['significance_label']}|train_mean={s['train_sec_mean']}s"
        )
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    _safe_print(f"\nWrote {json_path}")
    _safe_print(f"Wrote {txt_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--method",
        choices=["A", "B", "C", "D", "all"],
        default="all",
        help="실행할 방식 (기본 all)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="체크포인트에 완료된 방식 건너뛰기",
    )
    args = parser.parse_args()

    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    device = torch.device("cpu")

    runners = {
        "A": ("A_매회차재학습", run_method_a),
        "B": ("B_증분SGD", run_method_b),
        "C": ("C_IncLSTM근사_앙상블", run_method_c),
        "D": (f"D_슬라이딩W{SLIDING_WINDOW}", run_method_d),
    }
    todo = list("ABCD") if args.method == "all" else [args.method]

    ckpt = _load_checkpoint() if args.resume else {"completed": {}}
    completed = ckpt.get("completed", {})

    _safe_print(
        f"LSTM retrain compare {DRAW_FROM}~{DRAW_TO} READ-ONLY n_sets={N_SETS} "
        f"baseline={RANDOM_BASELINE} method={args.method} resume={args.resume}"
    )
    t_all = time.perf_counter()
    results: list[MethodResult] = []

    for key in "ABCD":
        if args.method != "all" and key != args.method:
            continue
        name, fn = runners[key]
        if args.resume and key in completed:
            _safe_print(f"  SKIP {key} (checkpoint)")
            results.append(_result_from_dict(name, completed[key]))
            continue
        _safe_print(f"\n=== METHOD {key} ===")
        res = fn(conn, device)
        completed[key] = {
            "per_set_hits": res.per_set_hits,
            "best_of5_hits": res.best_of5_hits,
            "train_secs": res.train_secs,
        }
        _save_checkpoint(completed)
        results.append(res)
        _safe_print(f"  CHECKPOINT saved: {key}")

    conn.close()
    elapsed = time.perf_counter() - t_all

    if args.method == "all":
        if len(completed) < 4:
            _safe_print(f"\nPartial ({len(completed)}/4). Re-run: --resume --method all")
            return
        ordered = [_result_from_dict(runners[k][0], completed[k]) for k in "ABCD"]
        _finalize(ordered, elapsed)
    elif results:
        _finalize(results, elapsed)


if __name__ == "__main__":
    main()
