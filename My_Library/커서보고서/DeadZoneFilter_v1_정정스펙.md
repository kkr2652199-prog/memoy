# Dead Zone Filter v1 — 코드베이스 정정 스펙 (실행용)

원 지시문 대비 아래만 따르면 STEP 4·7·8·10이 코드와 일치한다.

## 1. 세트 키

- `v12_engine` INSERT 루프는 **`nums` 리스트**만 사용한다 (`num1`~`num6` 직접 조회 금지).

## 2. 점수 vs 신뢰도

- `fresh` dict에 **`score` 없음**. 보정은 **`confidence`에 `dz_delta_conf` 가산 후 0.01~0.99 클램프**.
- `_score_v12_predictions`는 당첨 번호와의 **교집합만** 사용하므로 **avg_match·등수는 confidence 변경만으로는 불변**일 수 있음(의도된 한계).

## 3. STEP 7 검증

- `POST /api/lotto3/v12/predict/{n}` 응답에 **`all_predictions`(샘플/전체 + `dz_*`)** 포함.
- DB `GET /predictions`는 `dz_*` 컬럼 없음 → **즉시 검증은 POST JSON**, 목록 재조회 시에는 DZ 뱃지 없을 수 있음.

## 4. STEP 10 보호 파일 SHA

- PowerShell `Get-FileHash -Algorithm SHA256`의 **64자 대문자 HEX 전체**와 비교한다 (접두 8자만 사용 금지).

## 5. DZ 임계·의미

- `DZ_VAR_THRESHOLD=130`: 원 지시값 유지. 주석에 **정찰 D 평균 분산(~142)보다 낮은 분산을 패널티**한다고 명시 (142−1σ≈83은 더 공격적이며 본 배포에서는 미사용).

## 6. `dz_filter_passed`

- **저분산·z3≥3·소수≥4** 중 하나라면 `false` (데드존 플래그). 그 외 `true`.

## 7. UI·CSS

- `.dz-flag`는 **기존 CSS 변수**(`--text-secondary`, `--accent-soft` 등)만 사용. `index.html`의 `lotto3.js` 캐시버스트 갱신 필수.
