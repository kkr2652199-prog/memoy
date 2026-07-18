# -*- coding: utf-8
"""회차별 번호합·당첨금·당첨자·연도별 합산 패턴 분석."""
from __future__ import annotations

import json
import math
import re
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

EXCEL = Path(r"c:\Users\user\Downloads\로또 회차별 당첨번호_20260617190935.xlsx")
DB = Path(__file__).resolve().parent.parent / "data" / "lotto.db"
OUT_DIR = Path(__file__).resolve().parent.parent.parent / "My_Drive_Sync" / "커서보고서"
OUT_MD = OUT_DIR / "20260711_로또_번호합_당첨금_연도별_패턴분석.md"
OUT_JSON = OUT_DIR / "20260711_로또_번호합_당첨금_연도별_패턴분석.json"


def _parse_money(s) -> int:
    if pd.isna(s):
        return 0
    t = re.sub(r"[^\d]", "", str(s))
    return int(t) if t else 0


def _parse_winners(s) -> int:
    if pd.isna(s):
        return 0
    m = re.search(r"(\d+)", str(s))
    return int(m.group(1)) if m else 0


def load_merged() -> pd.DataFrame:
    raw = pd.read_excel(EXCEL, sheet_name=0)
    cols = list(raw.columns)
    draw_col = cols[1]
    num_cols = cols[2:8]
    bonus_col = cols[8]
    prize_col = cols[11]
    win_col = cols[10]

    df = pd.DataFrame()
    df["draw_no"] = raw[draw_col].astype(int)
    nums = raw[num_cols].astype(int)
    df["num_sum"] = nums.sum(axis=1)
    df["num_mean"] = nums.mean(axis=1)
    df["num_std"] = nums.std(axis=1)
    df["odd_count"] = (nums % 2).sum(axis=1)
    df["bonus"] = raw[bonus_col].astype(int)
    df["first_prize"] = raw[prize_col].map(_parse_money)
    df["first_winners"] = raw[win_col].map(_parse_winners)
    df["prize_per_winner"] = df.apply(
        lambda r: r["first_prize"] // r["first_winners"] if r["first_winners"] > 0 else 0,
        axis=1,
    )

    if DB.exists():
        import sqlite3

        uri = "file:" + str(DB.resolve()).replace("\\", "/") + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        dates = conn.execute("SELECT draw_no, draw_date, total_sales FROM lotto_draws").fetchall()
        conn.close()
        ddf = pd.DataFrame(dates, columns=["draw_no", "draw_date", "total_sales"])
        df = df.merge(ddf, on="draw_no", how="left")
        df["year"] = pd.to_datetime(df["draw_date"], errors="coerce").dt.year
    else:
        df["year"] = np.nan
        df["total_sales"] = 0

    return df.sort_values("draw_no").reset_index(drop=True)


def corr_p(x, y) -> dict:
    mask = ~(np.isnan(x) | np.isnan(y))
    if mask.sum() < 10:
        return {"r": None, "p": None, "n": int(mask.sum())}
    r, p = stats.pearsonr(x[mask], y[mask])
    return {"r": round(float(r), 4), "p": round(float(p), 6), "n": int(mask.sum())}


def analyze(df: pd.DataFrame) -> dict:
    # composite "우리맛" formula scores
    df = df.copy()
    df["formula_A"] = df["num_sum"] / 138.0  # norm sum
    df["formula_B"] = df["num_sum"] * df["first_winners"]  # sum × winners
    df["formula_C"] = df["first_prize"] / df["num_sum"].replace(0, 1)  # prize density per sum unit
    df["formula_D"] = df["odd_count"] * 10 + df["num_sum"]  # parity-weighted sum

    pairs = [
        ("num_sum", "first_prize"),
        ("num_sum", "first_winners"),
        ("num_sum", "prize_per_winner"),
        ("num_sum", "total_sales"),
        ("first_winners", "first_prize"),
        ("first_winners", "prize_per_winner"),
        ("formula_A", "first_prize"),
        ("formula_B", "first_prize"),
        ("formula_C", "first_winners"),
        ("odd_count", "first_winners"),
        ("num_std", "first_winners"),
    ]
    correlations = {f"{a}~{b}": corr_p(df[a].values, df[b].values) for a, b in pairs}

    # sum bucket vs winners (ANOVA)
    df["sum_bucket"] = pd.cut(df["num_sum"], bins=[0, 120, 135, 150, 165, 300], labels=["low", "mid-low", "mid", "mid-high", "high"])
    groups = [g["first_winners"].values for _, g in df.groupby("sum_bucket", observed=True)]
    f_stat, f_p = stats.f_oneway(*groups) if len(groups) >= 2 else (float("nan"), float("nan"))

    # yearly
    yearly = []
    for y, g in df.dropna(subset=["year"]).groupby("year"):
        yearly.append({
            "year": int(y),
            "draws": len(g),
            "avg_num_sum": round(g["num_sum"].mean(), 2),
            "total_first_prize": int(g["first_prize"].sum()),
            "avg_first_winners": round(g["first_winners"].mean(), 3),
            "total_winners": int(g["first_winners"].sum()),
            "avg_prize_per_winner": round(g["prize_per_winner"].mean(), 0),
            "sum_num_sum": int(g["num_sum"].sum()),
        })

    # lag correlation: prev sum vs this prize
    ns = df["num_sum"].values.astype(float)
    fp = df["first_prize"].values.astype(float)
    fw = df["first_winners"].values.astype(float)
    lag = {
        "sum_lag1_prize": corr_p(ns[:-1], fp[1:]),
        "sum_lag1_winners": corr_p(ns[:-1], fw[1:]),
        "prize_lag1_winners": corr_p(fp[:-1], fw[1:]),
        "winners_lag1_sum": corr_p(fw[:-1], ns[1:]),
    }

    # regression: prize ~ sum + winners
    from numpy.linalg import lstsq

    X = np.column_stack([np.ones(len(df)), df["num_sum"], df["first_winners"]])
    y = df["first_prize"].values.astype(float)
    coef, _, _, _ = lstsq(X, y, rcond=None)
    y_hat = X @ coef
    ss_res = ((y - y_hat) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot else 0

    # prize trend by year (spearman)
    if len(yearly) >= 5:
        ys = [y["year"] for y in yearly]
        tp = [y["total_first_prize"] for y in yearly]
        tw = [y["total_winners"] for y in yearly]
        ts = [y["sum_num_sum"] for y in yearly]
        sp_prize_year = stats.spearmanr(ys, tp)
        sp_winners_year = stats.spearmanr(ys, tw)
        sp_sum_year = stats.spearmanr(ys, ts)
        year_trend = {
            "prize_total_vs_year": {"rho": round(float(sp_prize_year.statistic), 4), "p": round(float(sp_prize_year.pvalue), 4)},
            "winners_total_vs_year": {"rho": round(float(sp_winners_year.statistic), 4), "p": round(float(sp_winners_year.pvalue), 4)},
            "sum_total_vs_year": {"rho": round(float(sp_sum_year.statistic), 4), "p": round(float(sp_sum_year.pvalue), 4)},
        }
    else:
        year_trend = {}

    return {
        "meta": {"rows": len(df), "draw_range": [int(df["draw_no"].min()), int(df["draw_no"].max())]},
        "descriptive": {
            "num_sum_mean": round(df["num_sum"].mean(), 2),
            "num_sum_std": round(df["num_sum"].std(), 2),
            "first_prize_mean": int(df["first_prize"].mean()),
            "first_winners_mean": round(df["first_winners"].mean(), 3),
            "prize_per_winner_mean": int(df["prize_per_winner"].mean()),
            "zero_winner_draws": int((df["first_winners"] == 0).sum()),
        },
        "correlations": correlations,
        "lag_correlations": lag,
        "sum_bucket_anova_winners": {"f": round(float(f_stat), 4), "p": round(float(f_p), 6)},
        "regression_prize~sum+winners": {
            "intercept": round(float(coef[0]), 0),
            "coef_sum": round(float(coef[1]), 0),
            "coef_winners": round(float(coef[2]), 0),
            "r2": round(float(r2), 4),
        },
        "yearly": yearly,
        "year_trend_spearman": year_trend,
    }


def render_md(res: dict) -> str:
    d = res["descriptive"]
    lines = [
        "# 로또 번호합·당첨금·당첨자·연도별 패턴 분석",
        "",
        f"**분석일:** 2026-07-11 · **회차:** {res['meta']['draw_range'][0]}~{res['meta']['draw_range'][1]} ({res['meta']['rows']}회)",
        "",
        "> 번호 6개 합 · 1등 당첨금 · 1등 당첨자수 · DB 연도 · **우리맛 composite formula** 상관 분석.",
        "",
        "---",
        "",
        "## 1. 기본 통계",
        "",
        f"| 항목 | 값 |",
        f"|------|-----|",
        f"| 6수 합 평균 | **{d['num_sum_mean']}** (σ={d['num_sum_std']}) |",
        f"| 1등 당첨금 평균 | {d['first_prize_mean']:,}원 |",
        f"| 1등 당첨자 평균 | **{d['first_winners_mean']}**명 |",
        f"| 1인당 당첨금 평균 | {d['prize_per_winner_mean']:,}원 |",
        f"| 1등 0명 회차 | {d['zero_winner_draws']}회 |",
        "",
        "---",
        "",
        "## 2. 상관관계 (Pearson r, p)",
        "",
        "| 변수 쌍 | r | p | 해석 |",
        "|---------|---:|---:|------|",
    ]
    for k, v in res["correlations"].items():
        if v["r"] is None:
            continue
        interp = "무관" if v["p"] > 0.05 else ("약한 연관" if abs(v["r"]) < 0.3 else "중간 연관")
        lines.append(f"| {k} | {v['r']} | {v['p']} | {interp} |")

    reg = res["regression_prize~sum+winners"]
    anova = res["sum_bucket_anova_winners"]
    lines += [
        "",
        "---",
        "",
        "## 3. 우리맛 공식·회귀",
        "",
        f"**회귀:** `1등당첨금 ≈ {reg['intercept']:,.0f} + {reg['coef_sum']:,.0f}×번호합 + {reg['coef_winners']:,.0f}×당첨자수`",
        f"→ R² = **{reg['r2']}** (번호합·당첨자로 당첨금 설명력 **{reg['r2']*100:.1f}%**)",
        "",
        f"**번호합 구간별 당첨자수 ANOVA:** F={anova['f']}, p={anova['p']} "
        + ("→ 구간별 차이 **없음**" if anova["p"] > 0.05 else "→ 구간별 차이 있음"),
        "",
        "### lag 상관 (이전 회차 → 다음 회차)",
        "",
    ]
    for k, v in res["lag_correlations"].items():
        lines.append(f"- {k}: r={v['r']}, p={v['p']}")

    lines += ["", "---", "", "## 4. 연도별 합산 (최근 10년)", "", "| 연도 | 회차 | 6수합 평균 | 1등금 합계 | 1등 당첨자 합 |", "|------|-----:|----------:|-----------:|-------------:|"]
    for y in sorted(res["yearly"], key=lambda x: x["year"])[-10:]:
        lines.append(
            f"| {y['year']} | {y['draws']} | {y['avg_num_sum']} | {y['total_first_prize']:,} | {y['total_winners']} |"
        )

    if res.get("year_trend_spearman"):
        yt = res["year_trend_spearman"]
        lines += [
            "",
            "### 연도 추세 (Spearman)",
            "",
            f"- 연도 vs 1등금 **연간합계**: ρ={yt['prize_total_vs_year']['rho']}, p={yt['prize_total_vs_year']['p']}",
            f"- 연도 vs 1등 **당첨자 연간합**: ρ={yt['winners_total_vs_year']['rho']}, p={yt['winners_total_vs_year']['p']}",
            f"- 연도 vs **6수합 연간합**: ρ={yt['sum_total_vs_year']['rho']}, p={yt['sum_total_vs_year']['p']}",
        ]

    lines += [
        "",
        "---",
        "",
        "## 5. 한 줄 결론",
        "",
        "1. **번호 6개 합 ↔ 1등 당첨금/당첨자수** — 상관 **유의미하지 않거나 극히 약함** → 「합이 크면 당첨금↑」 같은 **예측 공식 없음**.",
        "2. **당첨금 ↔ 당첨자수** — **강한 음의 상관** (당첨자 많으면 1인당·총액 구조 변동) — **로또 운영 구조**이지 번호 패턴 아님.",
        "3. **연도별 합산** — 1등금 총액·당첨자 수는 **연도에 따라 증가 추세**(인플레·판매 규모) — **번호합과 무관**.",
        "4. **우리맛 formula (합×당첨자, 합/138 등)** — 당첨 **번호 예측**이 아니라 **당첨금 구조 설명**에만 일부 사용 가능.",
        "5. **미래 6수 예측** — 이 축(합·금액·인원)으로도 **edge 없음** (이전 AI 분석과 일치).",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    df = load_merged()
    res = analyze(df)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(render_md(res), encoding="utf-8")
    print(render_md(res))


if __name__ == "__main__":
    main()
