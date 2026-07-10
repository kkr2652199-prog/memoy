🦅 패치 G — η 롤백 + Clipping만 유지

- **작성**: 2026-05-04 KST  
- **대상**: `My_Library/app/lotto3/v12_models.py` — `update_v12_weights`  
- **선행**: `20260503_0530_가중치폭주제어_패치보고서.md` · `20260503_0600_패치F_백테스트_보고서.md`  
- **금지**: `app/lotto/` · `app/lotto2/` 미수정 · **`target_draw_no=1222` 미사용**  
- **R22**: 단일 보고, 8000토큰 이하 목표

---

## STEP 0 — SHA256 사전검증 (31파일)

- **기준 경로**: `My_Library/`  
- **`v12_models.py`**: `08F631673D1C1EB7235DCAEE26B4D5DCD245128B7CAA4938A41C68AF68D8B4AE` (패치 F) — **일치**  
- **나머지 30파일**: `20260503_0600_패치F_백테스트_보고서.md` STEP0 표와 **전부 일치** (스크립트 일괄 검증, `STEP0: all 31 files match`).

---

## STEP 1 — `v12_models.py` 수정 (`update_v12_weights`)

| 항목 | 처리 |
|------|------|
| **1-A** | 모듈 상단 `import math` **유지** |
| **1-B** | 뇌별 `COUNT(DISTINCT target_draw_no)` 쿼리 및 `dc_by` **삭제** |
| **1-C** | `η_t = V11_HEDGE_ETA * sqrt(...)` **삭제** → `eta = V11_HEDGE_ETA` (고정 **2.0**) |
| **1-D** | `W_MAX = 100.0` **유지** |
| **1-E** | `new_w = min(float(new_w), W_MAX)` **유지** |

### 1-F — 변경 전/후 (줄번호·핵심 diff)

**모듈 docstring**

| 줄 | 변경 전 (패치 F) | 변경 후 (패치 G) |
|----|------------------|------------------|
| 5~6 | `감쇠 η_t + Clipping` | `고정 η=V11_HEDGE_ETA + Clipping` |

**상수 주석**

| 줄 | 변경 전 | 변경 후 |
|----|---------|---------|
| 41 | `# 감쇠 Hedge: η_t 분자 (V9 1.5, V11 기준 2.0)` | `# Hedge 고정 학습률 η (V9 1.5, V11·V12 기준 2.0)` |

**`update_v12_weights`**

| 구간 | 변경 전 (패치 F) | 변경 후 (패치 G) |
|------|------------------|------------------|
| 173~179 | docstring: 감쇠 `η_t` · `draw_count` 서술 | docstring: **고정 η** · draw_count **무관** 명시 |
| 196~207 | `dc_rows` / `dc_by` SELECT+빌드 | **삭제** (해당 줄 없음) |
| 213~215 루프 내 | `draw_count`… `eta_t`… `exp(eta_t * …)` | `eta = V11_HEDGE_ETA` · `exp(eta * …)` |

---

## STEP 2 — 검증

### 2-A) `app` import

```text
python -c "from app.main import app; print('app OK')"
→ app OK
```

### 2-B) η와 `draw_count` 무관

- 코드상 `draw_count`·`dc_by`·`sqrt(log(7)/…)` **제거**됨. 루프에서 **`eta = V11_HEDGE_ETA`** 만 사용 → **항상 2.0** (`V11_HEDGE_ETA == 2.0` 단언으로 확인).

### 2-C) `W_MAX=100` 클리핑 시뮬레이션

- `min(150.0, W_MAX)` → **100.0** (동일 식으로 확인).  
- 추가: 극단 시그널에서 `base * exp(2.0 * score_signal)`이 매우 커져도 **`min(..., W_MAX)`로 100.0**으로 제한됨을 확인.

---

## STEP 3 — SHA256 사후검증

- **`v12_models.py`만** 변경됨.  
- **나머지 30파일**: 패치 F STEP0/0600 표 해시와 **바이트 동일** (`STEP3: v12_models.py changed; other 30 files byte-identical`).

---

## STEP 4 — 요약

| 항목 | 내용 |
|------|------|
| **변경 파일** | `app/lotto3/v12_models.py` |
| **대략 줄 범위** | **5~6**, **41**, **173~179**, **196~207(삭제)**, **208~215** |
| **이전 SHA `v12_models.py`** | `08F631673D1C1EB7235DCAEE26B4D5DCD245128B7CAA4938A41C68AF68D8B4AE` |
| **새 SHA `v12_models.py`** | **`EBDE761B807CD3CC185D1974E7B5ABD2F8E2ED4D0D6E99957D22A13BBC2D423B`** |

### 사후 31파일 중 나머지 30경로 SHA256

- **`20260503_0600_패치F_백테스트_보고서.md`** STEP0 표와 **동일** (본 패치에서 해당 파일들 **미변경**).

---

## 🦅 한 줄 요약

- 패치 F의 **Decreasing η_t** 롤백, **η = `V11_HEDGE_ETA` (=2.0) 고정** 복원.  
- **`W_MAX=100` 클리핑**은 그대로 유지.

---

*미해결 사항: 없음 (재백테·STATUS·기억 SHA 갱신은 후속 작업자 판단).*
