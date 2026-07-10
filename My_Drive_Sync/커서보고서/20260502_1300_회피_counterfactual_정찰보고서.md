🦅 동생 작성 지시문 기반 — 커서 자동 생성 (옵션 B)

# 회피 로직 counterfactual 정밀 정찰 보고서 (READ-ONLY)

- 작성: 2026-05-02 13:00 KST  
- 선행: `20260502_1100_3군8뇌_본질구조_정찰보고서.md` STEP 4  
- 제약: `app/lotto/`, `app/lotto2/` **코드 미접근**, 코드·DB **쓰기 0**, `target_draw_no = 1222` **미사용** (`<= 1221` 등가), 임시 스크립트 **실행 후 삭제 완료**

---

## STEP 0 — SHA256 사전 (`app/lotto3` 16파일)

- 정리보고서(1000) STEP 0-B baseline과 **16/16 일치** → **PASS**.

---

## STEP 1 — 회피 로직 위치 raw

### 1-A. `predict_contrarian.py` — `_is_diff_from_armies` 호출

- `rg "_is_diff_from_armies"` → **`266`행** 단 1곳.

### 1-B. `v12_snake.py` — `_is_diff_from_army1` 호출

- `rg "_is_diff_from_army1"` → **`141`행**, **`174`행**.

### 1-C. 임계값 `0.4`

- `predict_contrarian.py` **`266`행**: `if not _is_diff_from_armies(cand, army_sets, 0.4):`
- `v12_snake.py` **`141`행**, **`174`행**: `threshold=0.4` 명시.

### 1-D. 탈락 시 흐름

- `predict_contrarian.py` **`266:267`행**: 조건 불만족 시 **`continue`** — 별도 로그 없음.
- `v12_snake.py` **`141:142`행**, **`174:175`행**: 동일하게 **`continue`**.

### 1-E. 통과 후 처리

- `predict_contrarian.py` **`268:281`행**: `used` 중복 검사 → `_pair_boost_score` → `out.append(...)`.
- `v12_snake.py` **`144:151`행**, **`176:183`행**: `sets.append({... "brain_tag": "v12_snake" ...})`.

---

## STEP 2 — Jaccard 함수 raw

### 2-A. `_is_diff_from_armies` 전체

```183:193:d:\MONEY lol\My_Library\app\lotto3\predict_contrarian.py
def _is_diff_from_armies(combo: list[int], army_sets: list[set[int]], threshold: float = 0.4) -> bool:
    if not army_sets:
        return True
    s = set(combo)
    for a in army_sets:
        inter = len(s & a)
        uni = len(s | a)
        jac = inter / uni if uni else 0.0
        if jac >= threshold:
            return False
    return True
```

### 2-B. `_is_diff_from_army1` 전체

```37:55:d:\MONEY lol\My_Library\app\lotto3\v12_snake.py
def _is_diff_from_army1(
    combo: list[int],
    army1_sets: list[set[int]],
    threshold: float = 0.4,
) -> bool:
    """1군 셋트 중 단 하나라도 Jaccard >= threshold 면 탈락.
    ...
    """
    if not army1_sets:
        return True
    s = set(combo)
    for a1 in army1_sets:
        inter = len(s & a1)
        uni = len(s | a1)
        jac = inter / uni if uni else 0.0
        if jac >= threshold:
            return False
    return True
```

### 2-C. 동일성

- **동일**: `jac >= threshold` 이면 **`False`(탈락)**, 아니면 **`True`(통과)** — 수식·분기 동형.

### 2-D. 임계값 raw

- **contrarian / snake 모두 `0.4`** — 위 인용.

---

## STEP 3 — 1·2군 6수 로드 메커니즘 (코드만, DB 쿼리 문자열)

### 3-A. `_load_army_sets_for_target` 전체

```146:180:d:\MONEY lol\My_Library\app\lotto3\predict_contrarian.py
def _load_army_sets_for_target(target_draw_no: int) -> list[set[int]]:
    from app.lotto.models import get_lotto_db
    from app.lotto2.models import get_lotto2_db

    ph = ",".join("?" * len(_ARMY1_TAGS))
    sets: list[set[int]] = []
    conn = get_lotto_db()
    try:
        rows = conn.execute(
            f"""
            SELECT num1, num2, num3, num4, num5, num6
            FROM lotto_predictions
            WHERE target_draw_no = ? AND brain_tag IN ({ph})
            """,
            (target_draw_no, *_ARMY1_TAGS),
        ).fetchall()
    finally:
        conn.close()
    sets.extend(set(r) for r in rows if r)

    conn2 = get_lotto2_db()
    try:
        rows2 = conn2.execute(
            """
            SELECT num1, num2, num3, num4, num5, num6
            FROM lotto_predictions_army2
            WHERE target_draw_no = ?
              AND (brain_tag LIKE 'v10d_%' OR brain_tag LIKE 'v11_%')
            """,
            (target_draw_no,),
        ).fetchall()
    finally:
        conn2.close()
    sets.extend(set(r) for r in rows2 if r)
    return sets
```

### 3-B. `brain_tag` 인식 (1군)

```90:92:d:\MONEY lol\My_Library\app\lotto3\predict_contrarian.py
_ARMY1_TAGS: tuple[str, ...] = (
    "stat", "markov", "llm", "lstm", "fusion", "hyena",
)
```

### 3-C. SELECT 쿼리 문자열

- **1군**: 위 블록 `FROM lotto_predictions` + `brain_tag IN (6태그)`.
- **2군**: 위 블록 `FROM lotto_predictions_army2` + `v10d_%` 또는 `v11_%`.

### 3-D / 3-E — 회차당 로드 개수(평균)

- **READ-ONLY Python**(DB 직접 `sqlite3`, `lotto.db` 내 동일 테이블명 사용) 산출:
  - `all_draws_with_army_data` = **1220**
  - `avg_army_sets_per_draw` = **64.165** (합산 후 평균)

---

## STEP 4 — `matched_count = 5` raw

### 4-A. contrarian

```sql
SELECT COUNT(*) FROM lotto_predictions_army3
WHERE brain_tag='v12_contrarian' AND matched_count=5 AND target_draw_no<=1221;
```

→ **`0`**.

### 4-B. snake

→ **`4`**행 (아래 SQL raw).

```sql
SELECT target_draw_no, num1,num2,num3,num4,num5,num6, matched_count
FROM lotto_predictions_army3
WHERE brain_tag='v12_snake' AND matched_count=5 AND target_draw_no<=1221;
```

**결과 raw**:

```text
222|5|7|11|28|29|43|5
365|5|15|19|21|26|30|5
715|2|24|27|33|41|44|5
888|3|12|25|31|34|38|5
```

### 4-C / 4-D / 4-E — snake 4건 Jaccard(후보 vs army12, 실제 vs army12)

임시 스크립트 출력 raw:

```text
snake_m5 222 sym_diff [11, 39] mx_j_cand_army 0.3333 mx_j_actual_army 0.2
snake_m5 365 sym_diff [19, 25] mx_j_cand_army 0.3333 mx_j_actual_army 0.5
snake_m5 715 sym_diff [7, 24] mx_j_cand_army 0.3333 mx_j_actual_army 0.5
snake_m5 888 sym_diff [7, 25] mx_j_cand_army 0.3333 mx_j_actual_army 0.3333
```

- **4건 모두 `mx_j_cand_army` < 0.4** → **본 raw만으로는 “회피(≥0.4)로 1개 번호를 틀렸다” 단정 불가**.

### contrarian `matched_count=5` 부재

- **0건**이므로 지시문 4-D~4-E의 “contrarian 5일치 회차별 Jaccard”는 **데이터 없음 → 미적용**.

---

## STEP 5 — 회피 통계·로깅

### 5-A. 시도 상한(이론)

- 루프: `max_attempts = 2500` (`predict_contrarian.py` **`252`행**).
- `target_draw_no`별 contrarian 존재 회차 수 SQL:

```sql
SELECT COUNT(DISTINCT target_draw_no) FROM lotto_predictions_army3
WHERE brain_tag='v12_contrarian' AND target_draw_no<=1221;
```

→ **`1216`**.

- **이론 상한 시도 수** ≤ `1216 * 2500` = **3,040,000** (실제 `continue`로 미만).

### 5-B / 5-C. 회피 탈락 카운터·로깅

- `predict_contrarian.py` **`254:267`행** 루프 내 **회피 전용 카운터/로그 없음**.
- **`283`행**만 `logger.warning("contrarian: only %d/%d sets...")` — **부분 세트 경고**일 뿐.

**결론(raw)**: **회피 탈락 횟수는 코드상 추적 불가**.

---

## STEP 6 — counterfactual: 실제 당첨 6수 vs army12 셋 `max Jaccard`

정의(스크립트): 각 `target_draw_no`에 대해 `lotto_draws` 당첨 6수 집합 `A`와, `_load_army_sets_for_target`과 **동일 SQL**로 모은 1·2군 6수 집합들 `S`에 대해 `max_{s∈S} Jaccard(A,s)` 계산. 임계 `t`에 대해 `max >= t` 카운트.

### 6-A~6-D — 결과 raw

```text
all_draws_with_army_data 1220
avg_army_sets_per_draw 64.165
max_jacc_ge_0.4 795 max_jacc_lt_0.4 425
max_jacc_ge_0.5 795 max_jacc_lt_0.5 425
D_only_max_jacc_ge_0.4 782 D_only_max_jacc_lt_0.4 425
D_only_max_jacc_ge_0.5 782 D_only_max_jacc_lt_0.5 425
```

- **`max_jacc_ge_0.4`와 `max_jacc_ge_0.5`가 동일(795)** → 본 데이터·정의 하에서 **(0.4, 0.5) 구간에 걸리는 `max` 값은 없음**(실수 연속 구간 상 **빈 구간**으로 관측).

### 6-E. `D_GROUP` 집합

- `predict_contrarian.py` `D_GROUP_DRAW_NOS` 파싱 크기 **1208** (기존 정찰과 동일).
- `D_only` 합 `782+425=1207` → **D 1208 중 1회차는 본 SQL 경로에서 army 데이터 없음 등으로 미포함** — 원인 추가 추적은 **미실행**.

---

## STEP 7 — fusion 1등 7건 vs 1군 `fusion` Jaccard (임계 0.6)

`v12_fusion_v5.py` **`33`행**: `_FUSION_JACCARD_THRESHOLD = 0.6`.

### 7-A~7-D — 회차별 raw

| `target` | `v12_fusion` 당첨 6수 | `n_army1_fusion_rows` | `max_j(pred, army1_fusion)` | `>= 0.6` |
|----------|------------------------|-------------------------|-------------------------------|----------|
| 69 | [5,8,14,15,19,39] | 5 | 0.0909 | False |
| 101 | [1,3,17,32,35,45] | 5 | 0.2 | False |
| 183 | [2,18,24,34,40,42] | 5 | 0.5 | False |
| 204 | [3,12,14,35,40,45] | 5 | 0.5 | False |
| 725 | [6,7,19,21,41,43] | 5 | **1.0** | **True** |
| 774 | [12,15,18,28,34,42] | 5 | **1.0** | **True** |
| 1122 | [3,6,21,30,34,35] | 5 | **1.0** | **True** |

### 7-E. bypass “추정”

- **`>=0.6`인 행 수** = **3 / 7**.
- **추가 코드 raw(Top-K 1세트)**: `272:287`행에서 swap 실패 시에도 **`288:294`행 `sets.append`는 항상 실행** → **회피(`_v12_is_diff_from_army1_fusion`) 미통과 Top-K가 그대로 저장될 수 있음**(정적 구조).
- **bypass 블록 raw**: `318:337`행 `if _v12_is_diff_from_army1_fusion(...) or bypass_attempts > 30:` — **부족분 보충 시** 회피 우회 가능.
- **런타임 로그 없음** → bypass 실제 호출 여부는 **모름**. **`288:294`행은 swap 성공 여부와 무관하게 Top-K 1세트를 항상 `sets`에 넣음** → **`max_j=1.0`(회피 실패)이어도 1세트 저장 가능**(정적 코드).

---

## STEP 8 — 종합 표

| 항목 | 측정값 | raw 근거 | 결론 |
|------|--------|----------|------|
| contrarian `matched=5` 회차 수 | **0** | SQL STEP 4-A | **해당 패턴 없음** |
| snake `matched=5` 회차 수 | **4** | SQL STEP 4-B | raw 표본 |
| “회피로 1등 놓친” 회차 추정 | **모름** | 회피 탈락 미로깅(STEP 5) | **추정 불가** |
| 임계 `0.4→0.5` 완화 효과(본 counterfactual) | **`ge0.4`=`ge0.5`** | STEP 6 출력 | **본 데이터에선 차이 0** |
| fusion 7건 `max_j>=0.6` | **3/7** | STEP 7 표 | **회피 조건 충족 가능·코드상 bypass 존재** |

---

## STEP 9 — 결론 4축

1. **회피가 contrarian/snake의 1등 0건 직접 원인인가?** → **모름** — contrarian `m=5` **0건**, snake `m=5` **4건은 전부 `mx_j_cand_army<0.4`**, 회피 탈락 **미로깅**. 다만 **실제 당첨 6수가 army12 어떤 셋과 `Jacc>=0.4`인 회차 795/1220** raw.  
2. **`0.4` 적정·완화 권고?** → **모름(정책)** — 본 counterfactual에서 **`0.4` vs `0.5` 카운트 동일** raw.  
3. **fusion 회피·보강 메커니즘** → **Top-K 1세트는 `288:294`행에서 항상 append** + **bypass는 `318:337`행**; **7건 중 3건 `max_j>=0.6` vs 1군 `fusion`**.  
4. **1222 영향·임계 변경 필요?** → **모름** — **1222 미접근**; 임계 변경은 **별 패치**.

---

## STEP 10 — 보고서 저장

- `D:/MONEY lol/My_Drive_Sync/커서보고서/20260502_1300_회피_counterfactual_정찰보고서.md`

---

## STEP 11 — 임시 파일

- `_tmp_counterfactual_run.py`, `_tmp_counterfactual_snake_m5.py` **삭제 완료**(glob **0건**).
- `_tmp_archive_20260502/` — **유지**(지시대로).

---

## STEP 12 — SHA256 사후

- **16/16 PASS** (`STEP12_POST 16/16 OK`).

---

## 부록 — 핵심 SQL·스크립트 정의

- `contrarian m=5` / `snake m=5`: STEP 4 SQL 그대로.
- `COUNT(DISTINCT target_draw_no)` contrarian: STEP 5-A SQL.
- Jaccard 스크립트: `lotto.db` + `predict_contrarian.py`의 `D_GROUP_DRAW_NOS` 파싱 + `lotto_predictions` / `lotto_predictions_army2` SELECT — **실행 후 파일 삭제**(부록에 정의만 기재).
