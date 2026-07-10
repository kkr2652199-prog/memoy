# Dead Zone Filter 정찰 v1 (raw only)

- 작성: 2026-05-01 22:45 KST
- 목적: D그룹 vs 비-D(A) 정답 6번호 통계 raw, Dead Zone Filter 설계 근거 확보
- 선행: `20260501_2030_본질정찰_1·2군분석_보고서.md`
- 선행 `기억16_v1`: 워크스페이스 `My_Library` 기준 파일명 glob `**/*기억16*` 검색 0건 → **raw에 없음**
- DB: `My_Library/data/lotto.db` (SELECT 전용)
- D/A 정의 SQL 범위: `target_draw_no BETWEEN 7 AND 1221` (지시서 그대로)

---

## STEP 1

```
=== 1군 무손상 ===
52AE12EE2980FF0CD549704B1C751655282852EE8718340D22EA0B5C59ECCEF2  app\lotto\predict_statistical.py
9DBCB76E12D2AFD97F28354F71430E7AADA38B1C8277C0285369547E31BBFA00  app\lotto\predict_markov.py
0B9D4189292C7DED7FFE4A3D303EDEA2819A54B052B31003B437AA872A7820C1  app\lotto\predict_lstm.py
3B322A11B50604A5E912757E1478BB1A86082AE9D919FD8102680D5449A8CDEF  app\lotto\fusion.py
90C514A9E8690B154ABA77FEF1F300405798BF64CD64BBCD23EAF0182C23C133  app\lotto\predict_hyena.py
24AE5A0B6232E83BD85CD115716D3DA485FE2525536757B2E1BC94F71411521B  app\lotto\predict_snake.py
F9D65DCFCF04BC0A54D8DEFCFD5BE89D7FEE1E91261487B9541BC6DB4AC572F7  app\lotto\predict_cluster.py
93D8E7715694D2ECC0AEFD7A14A2E23B5A79DF0DAED3417DEE9A31B2A307913D  app\lotto\predict_entropy.py
8A876BBC38A251B7916D397E0DD3C0F467249F06127D162A93AC1271AACA5D9A  app\lotto\engine.py

=== 2군 무손상 ===
5866BB1D852A8A03B061077F15899AD25E6E77F2CC82421A231C3B6BEEBD1855  app\lotto2\v11_engine.py
DD8EA6EF3E217BAC97730EBB8D0E84D1F093C285F2436DB28202613101100066  app\lotto2\v11_models.py
2726CD20EE1A6580FD56D86A89884C7C14D59E0293CC35FD2D0A0FDC1D4CA822  app\lotto2\v11_fusion.py
7C93C38D02B9BB3BEEA73C5105C9ADD217C1EB5658783B6FCACC1D3A4C00B5CA  app\lotto2\v11_fusion_v5.py
2D2BE92FFB073EEE8F4214B1E7026A9C288D85689FB9E52426B15B9116C36CB2  app\lotto2\v11_snake.py
12C538606A6B83A33B12C1751B4927097626DAED2B0DAF425B20A7021B8574E1  app\lotto2\v11_routes.py

=== 3군 baseline v6 검증 ===
[MATCH]  app\lotto3\v12_engine.py
  current=51A4BA330AB19820E6F0BC6E7DD08B8FAD5D1624BC0755B752A6FB610C72242B
  expect =51A4BA330AB19820E6F0BC6E7DD08B8FAD5D1624BC0755B752A6FB610C72242B
[MATCH]  app\lotto3\v12_models.py
  current=801960B54C6CB1A8F892F556EB60631AB72140CA681C77EE82A7735727FE8FBB
  expect =801960B54C6CB1A8F892F556EB60631AB72140CA681C77EE82A7735727FE8FBB
[MATCH]  app\lotto3\v12_routes.py
  current=AC7D1DEA5DAF08F955CEBC56E393E24B6628F7A024373F4BC3088F39C788437A
  expect =AC7D1DEA5DAF08F955CEBC56E393E24B6628F7A024373F4BC3088F39C788437A
[CHANGED]  app\lotto3\predict_run.py
  current=43219CD74D8F1B513A7D630AC8B9312C96ACF1523426A684C18A9BDEE7045161
  expect =EB7F24C4CCE9BC0E9A8C38D5350933C7B2970CC49D4E7EA0C1A83630044AC89B
[MATCH]  app\lotto3\predict_offset.py
  current=13D873CE8FDB67D4841F499639F51016020A00384330E0B62A8A7BF73D999B9C
  expect =13D873CE8FDB67D4841F499639F51016020A00384330E0B62A8A7BF73D999B9C
[MATCH]  app\static\js\lotto3.js
  current=70410C18D763DC45165BFDC736EFBC6391B392C1D8A554FE3673BC94B9D5A89D
  expect =70410C18D763DC45165BFDC736EFBC6391B392C1D8A554FE3673BC94B9D5A89D
```

---

## STEP 2

```
D그룹 회차 수: 1202
첫 10: [(7, 3, 2), (8, 2, 2), (9, 3, 2), (10, 3, 3), (11, 2, 2), (12, 3, 2), (13, 2, 3), (14, 2, 2), (15, 3, 3), (16, 4, 2)]
마지막 10: [(1212, 3, 2), (1213, 3, 5), (1214, 4, 4), (1215, 3, 4), (1216, 5, 4), (1217, 3, 3), (1218, 4, 4), (1219, 5, 4), (1220, 3, 3), (1221, 2, 3)]
D1 (max=5): 191회
D2 (max=4): 602회
D3 (max<=3): 409회
```

---

## STEP 3

```
=== D그룹 (n=1202) ===
sum  mean=138.11  stdev=30.88
var  mean=142.08 stdev=59.00
min  mean=6.73  max  mean=39.41
range mean=32.68
zones mean per draw: z1=1.303 z2=1.391 z3=1.291 z4=1.364 z5=0.651
even mean=2.925  consec mean=0.663
prime mean=1.863  last_unique mean=4.880

=== A그룹 (1·2군 1등) (n=13) ===
sum  mean=138.62  stdev=18.43
var  mean=189.84 stdev=66.39
min  mean=4.54  max  mean=41.62
range mean=37.08
zones mean per draw: z1=1.462 z2=1.308 z3=1.077 z4=1.231 z5=0.923
even mean=3.077  consec mean=0.385
prime mean=1.538  last_unique mean=5.077
```

---

## STEP 4

```
샘플 D1 회차 5개: [53, 56, 74, 89, 93]

=== 회차 53 정답: (7, 8, 14, 32, 33, 39) ===
  1군 hyena                m=5 (7, 8, 32, 33, 36, 39)
  1군 hyena                m=4 (7, 8, 29, 32, 36, 39)
  1군 lstm                 m=4 (8, 29, 32, 33, 36, 39)
  1군 fusion               m=3 (7, 28, 32, 36, 39, 43)
  1군 hyena                m=3 (7, 8, 11, 29, 32, 36)
  2군 v11_fusion           m=3 (2, 8, 16, 26, 32, 39)
  2군 v11_lstm             m=3 (7, 27, 31, 32, 33, 36)
  2군 v11_markov           m=3 (4, 7, 17, 29, 32, 39)
  2군 v11_combo            m=2 (8, 14, 20, 31, 36, 42)
  2군 v11_combo            m=2 (7, 13, 21, 27, 33, 38)
  3군 v12_fusion           m=3 (2, 8, 16, 26, 32, 39)
  3군 v12_lstm             m=3 (8, 10, 20, 25, 32, 39)
  3군 v12_fusion           m=2 (7, 8, 9, 16, 18, 30)
  3군 v12_hyena            m=2 (11, 16, 25, 32, 35, 39)
  3군 v12_hyena            m=2 (16, 25, 26, 32, 35, 39)

=== 회차 56 정답: (10, 14, 30, 31, 33, 37) ===
  1군 lstm                 m=5 (10, 30, 31, 33, 37, 40)
  1군 hyena                m=4 (10, 31, 33, 35, 37, 38)
  1군 hyena                m=4 (10, 30, 31, 35, 37, 38)
  1군 hyena                m=4 (8, 10, 30, 31, 35, 37)
  1군 hyena                m=3 (10, 13, 31, 35, 37, 38)
  2군 v11_fusion           m=4 (10, 31, 33, 37, 40, 44)
  2군 v11_hyena            m=4 (10, 16, 26, 30, 33, 37)
  2군 v11_hyena            m=4 (10, 16, 25, 30, 33, 37)
  2군 v11_lstm             m=4 (10, 16, 31, 33, 37, 44)
  2군 v11_hyena            m=3 (1, 10, 16, 33, 37, 44)
  3군 v12_fusion           m=4 (10, 31, 33, 37, 40, 44)
  3군 v12_lstm             m=4 (16, 30, 31, 33, 37, 44)
  3군 v12_hyena            m=3 (16, 17, 30, 31, 33, 44)
  3군 v12_hyena            m=3 (5, 16, 30, 31, 33, 44)
  3군 v12_hyena            m=3 (17, 30, 31, 33, 42, 44)

=== 회차 74 정답: (6, 15, 17, 18, 35, 40) ===
  1군 hyena                m=5 (15, 17, 18, 35, 40, 44)
  1군 hyena                m=5 (15, 17, 18, 34, 35, 40)
  1군 lstm                 m=4 (15, 16, 18, 35, 40, 43)
  1군 lstm                 m=4 (15, 18, 32, 35, 40, 44)
  1군 miss_analysis        m=4 (17, 18, 26, 35, 39, 40)
  2군 v11_fusion           m=4 (15, 17, 18, 32, 40, 43)
  2군 v11_hyena            m=3 (15, 18, 27, 31, 32, 40)
  2군 v11_hyena            m=3 (8, 15, 18, 27, 32, 40)
  2군 v11_hyena            m=3 (10, 17, 18, 27, 32, 40)
  2군 v11_lstm             m=3 (3, 5, 15, 18, 34, 40)
  3군 v12_hyena            m=5 (6, 15, 16, 17, 35, 40)
  3군 v12_fusion           m=4 (15, 17, 18, 32, 40, 43)
  3군 v12_hyena            m=4 (2, 6, 15, 16, 17, 40)
  3군 v12_hyena            m=4 (2, 6, 15, 17, 24, 35)
  3군 v12_hyena            m=4 (2, 6, 15, 17, 40, 44)

=== 회차 89 정답: (4, 26, 28, 29, 33, 40) ===
  1군 hyena                m=5 (17, 26, 28, 29, 33, 40)
  1군 hyena                m=4 (17, 26, 28, 33, 40, 41)
  1군 lstm                 m=4 (1, 26, 28, 29, 30, 40)
  1군 lstm                 m=3 (17, 20, 28, 29, 33, 41)
  1군 lstm                 m=3 (7, 17, 26, 28, 33, 34)
  2군 v11_fusion           m=3 (17, 20, 26, 29, 33, 35)
  2군 v11_hyena            m=3 (17, 20, 25, 26, 28, 29)
  2군 v11_hyena            m=3 (14, 17, 25, 26, 28, 29)
  2군 v11_combo            m=2 (7, 14, 25, 28, 33, 37)
  2군 v11_combo            m=2 (6, 11, 29, 30, 37, 40)
  3군 v12_fusion           m=3 (17, 20, 26, 29, 33, 35)
  3군 v12_hyena            m=3 (17, 18, 26, 29, 33, 35)
  3군 v12_hyena            m=3 (15, 17, 26, 29, 33, 35)
  3군 v12_lstm             m=3 (1, 17, 29, 33, 40, 42)
  3군 v12_stat             m=3 (4, 23, 29, 31, 33, 42)

=== 회차 93 정답: (6, 22, 24, 36, 38, 44) ===
  1군 lstm                 m=5 (6, 22, 24, 25, 36, 44)
  1군 hyena                m=4 (6, 21, 22, 24, 33, 36)
  1군 hyena                m=4 (6, 21, 22, 24, 25, 36)
  1군 hyena                m=4 (6, 21, 22, 24, 33, 44)
  1군 hyena                m=3 (6, 21, 22, 24, 25, 31)
  2군 v11_fusion           m=4 (6, 17, 24, 33, 36, 44)
  2군 v11_hyena            m=4 (6, 24, 25, 26, 36, 44)
  2군 v11_hyena            m=4 (6, 24, 25, 36, 40, 44)
  2군 v11_hyena            m=3 (1, 6, 24, 25, 33, 36)
  2군 v11_hyena            m=3 (1, 6, 24, 33, 34, 36)
  3군 v12_fusion           m=4 (6, 17, 24, 33, 36, 44)
  3군 v12_hyena            m=3 (6, 15, 22, 24, 27, 33)
  3군 v12_hyena            m=3 (6, 14, 15, 22, 24, 39)
  3군 v12_hyena            m=3 (6, 14, 15, 17, 22, 24)
  3군 v12_hyena            m=3 (6, 15, 22, 24, 27, 34)
```

---

## STEP 5

```
n_D=1202  n_A=13

sum           D mean=138.106  A mean=138.615  Cohen_d=-0.017
var           D mean=142.078  A mean=189.838  Cohen_d=-0.808
even          D mean=  2.925  A mean=  3.077  Cohen_d=-0.132
prime         D mean=  1.863  A mean=  1.538  Cohen_d=+0.312
z3(21~30)     D mean=  1.291  A mean=  1.077  Cohen_d=+0.229
```

---

## STEP 6

```
[OK] 임시 정찰 스크립트 삭제 완료
```

---

## STEP 7

```
=== 1군 무손상 ===
52AE12EE2980FF0CD549704B1C751655282852EE8718340D22EA0B5C59ECCEF2  app\lotto\predict_statistical.py
9DBCB76E12D2AFD97F28354F71430E7AADA38B1C8277C0285369547E31BBFA00  app\lotto\predict_markov.py
0B9D4189292C7DED7FFE4A3D303EDEA2819A54B052B31003B437AA872A7820C1  app\lotto\predict_lstm.py
3B322A11B50604A5E912757E1478BB1A86082AE9D919FD8102680D5449A8CDEF  app\lotto\fusion.py
90C514A9E8690B154ABA77FEF1F300405798BF64CD64BBCD23EAF0182C23C133  app\lotto\predict_hyena.py
24AE5A0B6232E83BD85CD115716D3DA485FE2525536757B2E1BC94F71411521B  app\lotto\predict_snake.py
F9D65DCFCF04BC0A54D8DEFCFD5BE89D7FEE1E91261487B9541BC6DB4AC572F7  app\lotto\predict_cluster.py
93D8E7715694D2ECC0AEFD7A14A2E23B5A79DF0DAED3417DEE9A31B2A307913D  app\lotto\predict_entropy.py
8A876BBC38A251B7916D397E0DD3C0F467249F06127D162A93AC1271AACA5D9A  app\lotto\engine.py

=== 2군 무손상 ===
5866BB1D852A8A03B061077F15899AD25E6E77F2CC82421A231C3B6BEEBD1855  app\lotto2\v11_engine.py
DD8EA6EF3E217BAC97730EBB8D0E84D1F093C285F2436DB28202613101100066  app\lotto2\v11_models.py
2726CD20EE1A6580FD56D86A89884C7C14D59E0293CC35FD2D0A0FDC1D4CA822  app\lotto2\v11_fusion.py
7C93C38D02B9BB3BEEA73C5105C9ADD217C1EB5658783B6FCACC1D3A4C00B5CA  app\lotto2\v11_fusion_v5.py
2D2BE92FFB073EEE8F4214B1E7026A9C288D85689FB9E52426B15B9116C36CB2  app\lotto2\v11_snake.py
12C538606A6B83A33B12C1751B4927097626DAED2B0DAF425B20A7021B8574E1  app\lotto2\v11_routes.py

=== 3군 baseline v6 검증 ===
[MATCH]  app\lotto3\v12_engine.py
  current=51A4BA330AB19820E6F0BC6E7DD08B8FAD5D1624BC0755B752A6FB610C72242B
  expect =51A4BA330AB19820E6F0BC6E7DD08B8FAD5D1624BC0755B752A6FB610C72242B
[MATCH]  app\lotto3\v12_models.py
  current=801960B54C6CB1A8F892F556EB60631AB72140CA681C77EE82A7735727FE8FBB
  expect =801960B54C6CB1A8F892F556EB60631AB72140CA681C77EE82A7735727FE8FBB
[MATCH]  app\lotto3\v12_routes.py
  current=AC7D1DEA5DAF08F955CEBC56E393E24B6628F7A024373F4BC3088F39C788437A
  expect =AC7D1DEA5DAF08F955CEBC56E393E24B6628F7A024373F4BC3088F39C788437A
[CHANGED]  app\lotto3\predict_run.py
  current=43219CD74D8F1B513A7D630AC8B9312C96ACF1523426A684C18A9BDEE7045161
  expect =EB7F24C4CCE9BC0E9A8C38D5350933C7B2970CC49D4E7EA0C1A83630044AC89B
[MATCH]  app\lotto3\predict_offset.py
  current=13D873CE8FDB67D4841F499639F51016020A00384330E0B62A8A7BF73D999B9C
  expect =13D873CE8FDB67D4841F499639F51016020A00384330E0B62A8A7BF73D999B9C
[MATCH]  app\static\js\lotto3.js
  current=70410C18D763DC45165BFDC736EFBC6391B392C1D8A554FE3673BC94B9D5A89D
  expect =70410C18D763DC45165BFDC736EFBC6391B392C1D8A554FE3673BC94B9D5A89D
```
