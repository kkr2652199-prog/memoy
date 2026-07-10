# 1군 lead1 overlap grid + 다차원(Pareto) 탐색 (in-memory 최종)

- **일자**: 2026-07-10 KST  
- **모드**: in-memory A/B · lotto.db·predict_brain7 READ-ONLY  
- **전문**: [`20260710_1군7뇌_overlap균등_grid_및_다차원탐색.txt`](./20260710_1군7뇌_overlap균등_grid_및_다차원탐색.txt) · [JSON](./20260710_1군7뇌_overlap균등_grid_및_다차원탐색.json)

## 최종 결론

| 판정 | 결과 |
|------|------|
| ADOPT | **없음** (hit4p/best5 2구간+ p<0.05 유의 개선 0건) |
| RECONSIDER | OB_v4_L/H, OB_v8_L/H 등 (Pareto 우위·pack_gap 개선) |
| 프로덕션 | **F1_V2_STRICT 유지** |

- n_draws=898, contamination=0, copy0=전 arm 5시드 0.0  
- Pareto front: OB_v4_L, OB_v4_H, OB_v8_H, BRAIN_DIV
