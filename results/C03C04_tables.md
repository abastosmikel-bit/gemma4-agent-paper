# C03 probe — tables (data only)

Source: `C03_probe.json + C04 design cells` (`notebooks/C03_probe__L4x4.ipynb`, plan 168d115). Produced by `pilot_c/analyze_c03.py`. Single run. Δ in nats, median over tasks [95% bootstrap CI, 10,000 resamples]. p: two-sided Wilcoxon signed-rank (unadjusted unless marked Holm).

## T0. Coverage

| Size | depth-1 cells ok | depth-2 samples ok | skipped | server start (s) | depth 1 (min) | depth 2 (min) | L0 rerun |Δ| find median / max | use median / max |
|---|---|---|---|---|---|---|---|---|
| 31b | 855 | 762 | — | 343.4 | 53.05 | 29.4 | 0.351 / 1.695 | 0.468 / 2.528 |
| e4b | 855 | 762 | — | 264.3 | 21.87 | 17.91 | 0.245 / 0.67 | 0.213 / 1.231 |
| 12b | 855 | 762 | completed by C04 | 197.3 | 28.96 | — | 0.39 / 0.979 | 0.593 / 5.606 |
| e2b | 0 | 0 | session time guard | — | — | — | — / — | — / — |

Session: 4.323 h; freezes: 0; tasks: 30; excluded before probing: 3.

## T1-find. Depth 1, S-find: Δ vs L0 (and X vs its matched correct rung)

| Condition | e4b Δ [CI] | 12b Δ [CI] | 31b Δ [CI] | e4b n, p | 12b n, p | 31b n, p |
|---|---|---|---|---|---|---|
| L1 − L0 | +6.3 [+3.2, +8.6] | +8.2 [+5.4, +10.7] | +6.9 [+3.6, +14.9] | 30, <0.001 | 30, <0.001 | 30, <0.001 |
| L2 − L0 | +19.4 [+17.5, +24.1] | +25.3 [+21.3, +29.3] | +33.4 [+26.6, +45.6] | 30, <0.001 | 30, <0.001 | 30, <0.001 |
| T − L0 | +1.9 [+0.7, +4.7] | +3.9 [+1.7, +7.4] | +6.3 [+3.2, +11.0] | 30, <0.001 | 30, <0.001 | 30, <0.001 |
| W − L0 | +2.8 [+1.2, +5.5] | +1.9 [+0.7, +4.8] | +1.0 [-0.7, +6.6] | 27, <0.001 | 27, <0.001 | 27, 0.052 |
| G-json − L0 | +11.0 [+9.4, +14.3] | -1.6 [-5.7, +0.0] | +7.4 [+4.7, +12.9] | 30, <0.001 | 30, 0.271 | 30, <0.001 |
| G-edges − L0 | +11.7 [+10.2, +15.1] | -2.3 [-6.5, +0.3] | +7.8 [+5.5, +14.8] | 30, <0.001 | 30, 0.299 | 30, <0.001 |
| G-adj − L0 | +12.0 [+10.2, +15.1] | -2.8 [-6.0, +0.6] | +6.3 [+4.3, +10.7] | 30, <0.001 | 30, 0.184 | 30, <0.001 |
| X-file − L0 | -1.2 [-2.9, +0.4] | -11.5 [-13.4, -0.5] | -5.2 [-7.9, -1.0] | 30, 0.036 | 30, <0.001 | 30, 0.001 |
| X-func − L0 | +7.4 [+5.1, +9.8] | +4.6 [+0.7, +10.0] | +10.6 [+7.5, +20.6] | 30, <0.001 | 30, 0.005 | 30, <0.001 |
| X-graph − L0 | +9.5 [+8.6, +10.9] | -3.5 [-7.3, +1.5] | +5.5 [+1.3, +12.3] | 30, <0.001 | 30, 0.088 | 30, <0.001 |
| X-file − L1 | -9.3 [-10.9, -5.9] | -18.8 [-22.1, -14.6] | -16.0 [-23.0, -13.4] | 30, <0.001 | 30, <0.001 | 30, <0.001 |
| X-func − L2 | -11.4 [-14.3, -8.9] | -18.6 [-23.3, -15.7] | -20.1 [-26.0, -17.6] | 30, <0.001 | 30, <0.001 | 30, <0.001 |
| X-graph − G-json | -1.0 [-1.8, -0.2] | -1.5 [-2.5, +0.2] | -1.2 [-4.0, +0.5] | 30, 0.007 | 30, 0.029 | 30, 0.031 |

Scoring mode per condition (PLAN §11 dev. 8): 12b: L0=spliced, L1=spliced, L2=spliced, T=spliced, W=spliced, G-json=direct, G-edges=direct, G-adj=direct, X-file=spliced, X-func=spliced, X-graph=direct; 31b: L0=spliced, L1=spliced, L2=spliced, T=spliced, W=spliced, G-json=direct, G-edges=direct, G-adj=direct, X-file=spliced, X-func=spliced, X-graph=direct

## T1-use. Depth 1, S-use: Δ vs L0 (and X vs its matched correct rung)

| Condition | e4b Δ [CI] | 12b Δ [CI] | 31b Δ [CI] | e4b n, p | 12b n, p | 31b n, p |
|---|---|---|---|---|---|---|
| L1 − L0 | +0.9 [+0.3, +1.5] | -0.4 [-1.2, +1.6] | -1.3 [-1.9, -0.0] | 30, 0.008 | 30, 0.730 | 30, 0.015 |
| L2 − L0 | +1.9 [+1.0, +3.4] | -1.8 [-3.3, +1.9] | -1.5 [-3.0, +0.6] | 30, <0.001 | 30, 0.229 | 30, 0.025 |
| L3 − L0 | +4.9 [+1.8, +6.5] | -0.0 [-1.8, +3.0] | -0.8 [-2.3, +3.7] | 30, <0.001 | 30, 0.516 | 30, 0.598 |
| L4 − L0 | +13.8 [+8.3, +16.9] | +14.1 [+6.9, +18.7] | +11.2 [+5.4, +19.2] | 27, <0.001 | 27, <0.001 | 27, <0.001 |
| L5 − L0 | +29.2 [+22.6, +35.7] | +42.4 [+27.0, +56.2] | +33.8 [+22.6, +48.9] | 27, <0.001 | 27, <0.001 | 27, <0.001 |
| T − L0 | +1.5 [+0.3, +3.5] | +2.2 [-0.3, +4.2] | +0.4 [-0.5, +2.3] | 30, <0.001 | 30, 0.004 | 30, 0.205 |
| W − L0 | +11.4 [+7.2, +15.4] | +14.4 [+6.9, +22.2] | +11.6 [+5.4, +18.5] | 27, <0.001 | 27, <0.001 | 27, <0.001 |
| G-json − L0 | +1.2 [+0.0, +3.8] | +7.5 [+4.6, +9.3] | +5.3 [+1.8, +6.4] | 30, 0.011 | 30, <0.001 | 30, <0.001 |
| G-edges − L0 | +1.2 [-0.1, +3.0] | +7.7 [+5.1, +9.7] | +4.4 [+1.9, +6.5] | 30, 0.021 | 30, <0.001 | 30, <0.001 |
| G-adj − L0 | +1.3 [+0.5, +2.8] | +6.5 [+3.9, +9.8] | +4.8 [+3.0, +6.6] | 30, 0.022 | 30, <0.001 | 30, <0.001 |
| X-file − L0 | -0.3 [-0.9, +0.4] | -1.8 [-2.6, -0.5] | -4.3 [-8.4, -1.0] | 30, 0.299 | 30, 0.002 | 30, <0.001 |
| X-func − L0 | +1.5 [+1.0, +2.2] | -2.4 [-3.9, -0.8] | -1.7 [-5.2, -0.1] | 30, <0.001 | 30, 0.001 | 30, 0.009 |
| X-graph − L0 | +1.2 [+0.1, +2.6] | +7.6 [+6.0, +10.1] | +6.8 [+5.4, +8.6] | 30, 0.004 | 30, <0.001 | 30, <0.001 |
| X-test − L0 | +2.3 [+1.1, +3.2] | +0.3 [-0.9, +1.9] | -1.0 [-2.0, +0.8] | 30, <0.001 | 30, 0.516 | 30, 0.309 |
| X-words − L0 | +1.7 [-0.4, +2.8] | +1.0 [-1.8, +3.7] | -0.2 [-2.7, +4.7] | 27, 0.290 | 27, 0.336 | 27, 0.500 |
| X-file − L1 | -1.3 [-1.6, -0.7] | -1.4 [-2.4, +0.7] | -2.6 [-5.3, -1.8] | 30, <0.001 | 30, 0.158 | 30, <0.001 |
| X-func − L2 | -0.3 [-0.9, +0.6] | -1.7 [-3.3, -0.7] | -1.7 [-3.3, +0.9] | 30, 0.465 | 30, 0.013 | 30, 0.152 |
| X-graph − G-json | -0.3 [-1.1, +0.2] | +0.9 [+0.2, +1.7] | +1.4 [+0.8, +4.3] | 30, 0.556 | 30, 0.105 | 30, 0.015 |
| X-test − L3 | -1.4 [-3.1, -0.0] | -0.8 [-2.3, +1.8] | -0.4 [-4.3, +1.3] | 30, 0.003 | 30, 0.715 | 30, 0.271 |
| X-words − L4 | -12.0 [-17.4, -7.1] | -14.8 [-17.3, -6.4] | -8.4 [-15.2, -6.2] | 27, <0.001 | 27, <0.001 | 27, <0.001 |

Scoring mode per condition (PLAN §11 dev. 8): 12b: L0=direct, L1=direct, L2=direct, L3=direct, L4=direct, L5=direct, T=direct, W=direct, G-json=direct, G-edges=direct, G-adj=direct, X-file=direct, X-func=direct, X-graph=direct, X-test=direct, X-words=direct; 31b: L0=direct, L1=direct, L2=direct, L3=direct, L4=direct, L5=direct, T=direct, W=direct, G-json=direct, G-edges=direct, G-adj=direct, X-file=direct, X-func=direct, X-graph=direct, X-test=direct, X-words=direct

## T2. Pre-registered hypotheses (PLAN §6), per size

| Hypothesis | Size | Statistic | Value | p (Holm) | Verdict |
|---|---|---|---|---|---|
| H1 location helps find | e4b | Δ_find(L2−L0) | +19.4 [+17.5, +24.1] | <0.001 | supported |
| H1 find > use | e4b | Δ_use(L2−L0); Δ_find−Δ_use | +1.9 [+1.0, +3.4]; +17.2 [+13.7, +19.8] | <0.001 | supported |
| H1 location helps find | 12b | Δ_find(L2−L0) | +25.3 [+21.3, +29.3] | <0.001 | supported |
| H1 find > use | 12b | Δ_use(L2−L0); Δ_find−Δ_use | -1.8 [-3.3, +1.9]; +25.5 [+23.8, +30.7] | <0.001 | supported |
| H1 location helps find | 31b | Δ_find(L2−L0) | +33.4 [+26.6, +45.6] | <0.001 | supported |
| H1 find > use | 31b | Δ_use(L2−L0); Δ_find−Δ_use | -1.5 [-3.0, +0.6]; +37.9 [+27.3, +46.9] | <0.001 | supported |
| H2 Δ_use(L4−L3) increases with size | e4b, 12b, 31b (e2b missing) | Page L (n=27); medians e4b +7.2, 12b +12.4, 31b +9.2 | L=333.0 | 0.221 | not supported |
| H2 Δ_use(L5−L4) decreases with size | e4b, 12b, 31b (e2b missing) | Page L (n=27); medians e4b +15.5, 12b +21.8, 31b +23.4 | L=307.0 | 0.990 | not supported |
| H3 graph < L2 (find) | e4b | G-json − L2 | -7.6 [-10.2, -6.0] | <0.001 | — |
| H3 graph < L2 (find) | e4b | G-edges − L2 | -7.5 [-10.0, -6.2] | <0.001 | — |
| H3 graph < L2 (find) | e4b | G-adj − L2 | -7.2 [-10.2, -5.7] | <0.001 | supported (all three) |
| H3 encodings (find) | e4b | G-edges − G-json | +0.6 [+0.3, +0.9] | <0.001 | — |
| H3 encodings (find) | e4b | G-adj − G-json | +0.8 [+0.5, +1.1] | <0.001 | supported |
| H3 encodings (find) | e4b | G-adj − G-edges | +0.2 [-0.1, +0.5] | 0.140 (unadj.) | — |
| H3 graph < L2 (find) | 12b | G-json − L2 | -24.8 [-29.8, -23.2] | <0.001 | — |
| H3 graph < L2 (find) | 12b | G-edges − L2 | -25.8 [-28.9, -23.6] | <0.001 | — |
| H3 graph < L2 (find) | 12b | G-adj − L2 | -28.5 [-30.2, -24.7] | <0.001 | supported (all three) |
| H3 encodings (find) | 12b | G-edges − G-json | +0.3 [-0.4, +0.9] | 0.570 (unadj.) | exploratory |
| H3 encodings (find) | 12b | G-adj − G-json | -0.2 [-1.2, +0.7] | 0.477 (unadj.) | exploratory |
| H3 encodings (find) | 12b | G-adj − G-edges | -0.4 [-1.1, +0.3] | 0.152 (unadj.) | exploratory |
| H3 graph < L2 (find) | 31b | G-json − L2 | -24.3 [-28.5, -21.5] | <0.001 | — |
| H3 graph < L2 (find) | 31b | G-edges − L2 | -24.5 [-27.5, -19.7] | <0.001 | — |
| H3 graph < L2 (find) | 31b | G-adj − L2 | -25.4 [-29.1, -23.1] | <0.001 | supported (all three) |
| H3 encodings (find) | 31b | G-edges − G-json | +1.4 [+0.8, +2.2] | 0.015 (unadj.) | — |
| H3 encodings (find) | 31b | G-adj − G-json | -0.4 [-1.6, +0.5] | 0.289 (unadj.) | — |
| H3 encodings (find) | 31b | G-adj − G-edges | -1.3 [-2.9, -0.7] | <0.001 (unadj.) | not supported (some |median| ≥ 0.3) |
| H4 wrong hint harms (find) | e4b | X-file − L0 | -1.2 [-2.9, +0.4] | 0.036 | supported |
| H4 wrong hint harms (find) | e4b | X-func − L0 | +7.4 [+5.1, +9.8] | <0.001 | not supported |
| H4 wrong hint harms (find) | e4b | X-graph − L0 | +9.5 [+8.6, +10.9] | <0.001 | not supported |
| H4 wrong hint harms (find) | 12b | X-file − L0 | -11.5 [-13.4, -0.5] | 0.001 | supported |
| H4 wrong hint harms (find) | 12b | X-func − L0 | +4.6 [+0.7, +10.0] | 0.009 | not supported |
| H4 wrong hint harms (find) | 12b | X-graph − L0 | -3.5 [-7.3, +1.5] | 0.088 | not supported |
| H4 wrong hint harms (find) | 31b | X-file − L0 | -5.2 [-7.9, -1.0] | 0.001 | supported |
| H4 wrong hint harms (find) | 31b | X-func − L0 | +10.6 [+7.5, +20.6] | <0.001 | not supported |
| H4 wrong hint harms (find) | 31b | X-graph − L0 | +5.5 [+1.3, +12.3] | <0.001 | not supported |
| H4 harm shrinks with size | e4b, 12b, 31b | Page L (n=30), X-file − L0 | L=343.0 | 1.000 | not supported |
| H4 harm shrinks with size | e4b, 12b, 31b | Page L (n=30), X-func − L0 | L=385.0 | 0.002 | not supported (trend in predicted direction, but Δ > 0 at some size: no harm to shrink) |
| H4 harm shrinks with size | e4b, 12b, 31b | Page L (n=30), X-graph − L0 | L=344.0 | 1.000 | not supported |
| H5 on_target L5 ≥ 50%, L2 ≤ 20% | e4b | tasks with ≥1 of 2 on_target: L2, L5 (samples: L2, L5) | 63%, 74% (55%, 70%) | McNemar 0.754 | not supported (L5≥50%: True, L2≤20%: False) |
| H5 on_target L5 ≥ 50%, L2 ≤ 20% (exploratory: H5 is about e4b) | 12b | tasks with ≥1 of 2 on_target: L2, L5 (samples: L2, L5) | 0%, 30% (0%, 24%) | McNemar 0.008 | not supported (L5≥50%: False, L2≤20%: True) |
| H5 on_target L5 ≥ 50%, L2 ≤ 20% (exploratory: H5 is about e4b) | 31b | tasks with ≥1 of 2 on_target: L2, L5 (samples: L2, L5) | 3%, 48% (2%, 41%) | McNemar <0.001 | not supported (L5≥50%: False, L2≤20%: True) |
| H6 probe predicts rollout flips | 12b | AUC | — | — | not testable (validation not run) |

## T3. Depth 2, S-find (1 sample per task): share of tasks

| Size | Condition | n | hit_file | hit_func | McNemar vs L0 (file; func) | tools |
|---|---|---|---|---|---|---|
| e4b | L0 | 30 | 37% | 13% | — | read_file 20, run_command 4, search_similar_code 6 |
| e4b | L1 | 30 | 100% | 33% | <0.001; 0.031 | read_file 30 |
| e4b | L2 | 30 | 100% | 97% | <0.001; <0.001 | read_file 30 |
| e4b | G-edges | 30 | 83% | 30% | <0.001; 0.062 | read_file 27, search_similar_code 2, run_command 1 |
| e4b | G-json | 30 | 83% | 33% | <0.001; 0.031 | read_file 29, run_command 1 |
| e4b | X-func | 30 | 100% | 23% | <0.001; 0.508 | read_file 30 |
| 12b | L0 | 30 | 20% | 3% | — | run_command 21, read_file 8, code_analyzer_agent 1 |
| 12b | L1 | 30 | 93% | 30% | <0.001; 0.008 | read_file 25, run_command 5 |
| 12b | L2 | 30 | 100% | 93% | <0.001; <0.001 | read_file 30 |
| 12b | G-edges | 30 | 80% | 23% | <0.001; 0.070 | read_file 23, run_command 7 |
| 12b | G-json | 30 | 70% | 23% | <0.001; 0.070 | read_file 22, run_command 8 |
| 12b | X-func | 30 | 97% | 43% | <0.001; <0.001 | read_file 29, run_command 1 |
| 31b | L0 | 30 | 43% | 10% | — | read_file 11, run_command 18, write_file 1 |
| 31b | L1 | 30 | 87% | 33% | <0.001; 0.016 | read_file 26, write_file 3, run_command 1 |
| 31b | L2 | 30 | 93% | 93% | <0.001; <0.001 | read_file 28, write_file 2 |
| 31b | G-edges | 30 | 70% | 23% | 0.008; 0.125 | read_file 21, run_command 9 |
| 31b | G-json | 30 | 70% | 20% | 0.008; 0.250 | read_file 23, run_command 6, write_file 1 |
| 31b | X-func | 30 | 93% | 27% | <0.001; 0.125 | read_file 27, run_command 1, write_file 2 |

## T4. Depth 2, S-use (2 samples per task)

| Size | Condition | tasks / samples | tasks ≥1 on_target | tasks ≥1 exact | McNemar vs L0 (on_target; exact) | samples: edit_file on gold file [CI] | on_target given edit [CI] | exact given edit [CI] |
|---|---|---|---|---|---|---|---|---|
| e4b | L0 | 30 / 60 | 37% | 3% | — | 58% [42%, 75%] | 46% [26%, 68%] (n=35) | 3% [0%, 9%] |
| e4b | L2 | 30 / 60 | 63% | 7% | 0.008; 1.000 | 88% [77%, 97%] | 62% [45%, 78%] (n=53) | 4% [0%, 9%] |
| e4b | L3 | 30 / 60 | 70% | 7% | 0.002; 1.000 | 83% [72%, 93%] | 66% [50%, 81%] (n=50) | 4% [0%, 10%] |
| e4b | L4 | 27 / 54 | 70% | 15% | 0.039; 0.250 | 82% [67%, 96%] | 80% [64%, 93%] (n=44) | 14% [2%, 28%] |
| e4b | L5 | 27 / 54 | 74% | 52% | 0.049; <0.001 | 85% [72%, 96%] | 83% [68%, 95%] (n=46) | 54% [35%, 72%] |
| e4b | G-json | 30 / 60 | 57% | 0% | 0.109; 1.000 | 65% [50%, 80%] | 64% [46%, 82%] (n=39) | 0% [0%, 0%] |
| e4b | T | 30 / 60 | 37% | 3% | 1.000; 1.000 | 57% [42%, 72%] | 50% [29%, 71%] (n=34) | 6% [0%, 19%] |
| e4b | W | 27 / 54 | 63% | 11% | 0.146; 0.500 | 74% [59%, 89%] | 82% [65%, 97%] (n=40) | 12% [0%, 28%] |
| e4b | X-func | 30 / 60 | 30% | 7% | 0.754; 1.000 | 33% [18%, 48%] | 65% [43%, 84%] (n=20) | 10% [0%, 23%] |
| e4b | X-test | 30 / 60 | 60% | 0% | 0.092; 1.000 | 82% [68%, 93%] | 59% [42%, 76%] (n=49) | 0% [0%, 0%] |
| 12b | L0 | 30 / 60 | 0% | 0% | — | 3% [0%, 10%] | 0% [0%, 0%] (n=2) | 0% [0%, 0%] |
| 12b | L2 | 30 / 60 | 0% | 0% | —; — | 2% [0%, 5%] | 0% [0%, 0%] (n=1) | 0% [0%, 0%] |
| 12b | L3 | 30 / 60 | 7% | 3% | 0.500; 1.000 | 3% [0%, 8%] | 100% [100%, 100%] (n=2) | 50% [0%, 100%] |
| 12b | L4 | 27 / 54 | 7% | 7% | 0.500; 0.500 | 4% [0%, 9%] | 100% [100%, 100%] (n=2) | 100% [100%, 100%] |
| 12b | L5 | 27 / 54 | 30% | 26% | 0.008; 0.016 | 30% [15%, 46%] | 81% [57%, 100%] (n=16) | 62% [33%, 88%] |
| 12b | G-json | 30 / 60 | 3% | 0% | 1.000; — | 5% [0%, 13%] | 33% [0%, 100%] (n=3) | 0% [0%, 0%] |
| 12b | T | 30 / 60 | 0% | 0% | —; — | 0% [0%, 0%] | — — (n=0) | — — |
| 12b | W | 27 / 54 | 7% | 7% | 0.500; 0.500 | 6% [0%, 13%] | 67% [0%, 100%] (n=3) | 67% [0%, 100%] |
| 12b | X-func | 30 / 60 | 0% | 0% | —; — | 0% [0%, 0%] | — — (n=0) | — — |
| 12b | X-test | 30 / 60 | 0% | 0% | —; — | 0% [0%, 0%] | — — (n=0) | — — |
| 31b | L0 | 30 / 60 | 0% | 0% | — | 0% [0%, 0%] | — — (n=0) | — — |
| 31b | L2 | 30 / 60 | 3% | 0% | 1.000; — | 2% [0%, 5%] | 100% [100%, 100%] (n=1) | 0% [0%, 0%] |
| 31b | L3 | 30 / 60 | 3% | 3% | 1.000; 1.000 | 3% [0%, 10%] | 50% [50%, 50%] (n=2) | 50% [50%, 50%] |
| 31b | L4 | 27 / 54 | 7% | 4% | 0.500; 1.000 | 6% [0%, 15%] | 100% [100%, 100%] (n=3) | 33% [0%, 100%] |
| 31b | L5 | 27 / 54 | 48% | 41% | <0.001; <0.001 | 46% [30%, 63%] | 88% [68%, 100%] (n=25) | 68% [43%, 91%] |
| 31b | G-json | 30 / 60 | 0% | 0% | —; — | 0% [0%, 0%] | — — (n=0) | — — |
| 31b | T | 30 / 60 | 0% | 0% | —; — | 0% [0%, 0%] | — — (n=0) | — — |
| 31b | W | 27 / 54 | 26% | 11% | 0.016; 0.250 | 20% [7%, 35%] | 100% [100%, 100%] (n=11) | 36% [0%, 80%] |
| 31b | X-func | 30 / 60 | 0% | 0% | —; — | 0% [0%, 0%] | — — (n=0) | — — |
| 31b | X-test | 30 / 60 | 0% | 0% | —; — | 2% [0%, 5%] | 0% [0%, 0%] (n=1) | 0% [0%, 0%] |

Cochran's Q across L0, L2, L3, L4, L5 (tasks with all five cells): e4b/any_on_target: Q=13.3, p=0.010, n=27; e4b/any_exact: Q=36.0, p=<0.001, n=27; 12b/any_on_target: Q=22.7, p=<0.001, n=27; 12b/any_exact: Q=21.2, p=<0.001, n=27; 31b/any_on_target: Q=40.4, p=<0.001, n=27; 31b/any_exact: Q=38.8, p=<0.001, n=27

## T5. Information threshold per task (lowest S-use rung with ≥1 of 2 samples `exact`; `solves` pending `notebooks/C03v_test_verify__CPU.ipynb`)

| Size | L0 | L2 | L3 | L4 | L5 | >L5 | none (L4/L5 missing) |
|---|---|---|---|---|---|---|---|
| e4b | 1 | 1 | 1 | 2 | 9 | 13 | 3 |
| 12b | 0 | 0 | 1 | 1 | 5 | 20 | 3 |
| 31b | 0 | 0 | 1 | 0 | 10 | 16 | 3 |

## T6. Exploratory: graph rung vs text location (coordinator's question a)

| Size / state | L1 − L0 | L2 − L1 | X-func − L0 | L2 − X-func | G-json − L0 | X-graph − L0 | G-json − X-graph | X-graph − L1 | G-json − L2 | scoring mode L0 / G-json |
|---|---|---|---|---|---|---|---|---|---|---|
| e4b/find | +6.3 [+3.2, +8.6] | +13.4 [+9.7, +15.0] | +7.4 [+5.1, +9.8] | +11.4 [+8.9, +14.3] | +11.0 [+9.4, +14.3] | +9.5 [+8.6, +10.9] | +1.0 [+0.2, +1.8] | +3.7 [+2.1, +5.4] | -7.6 [-10.2, -6.0] | direct / direct |
| e4b/use | +0.9 [+0.3, +1.5] | +0.9 [+0.7, +1.6] | +1.5 [+1.0, +2.2] | +0.3 [-0.6, +0.9] | +1.2 [+0.0, +3.8] | +1.2 [+0.1, +2.6] | +0.3 [-0.2, +1.1] | +0.2 [-0.3, +1.5] | -0.9 [-1.9, +0.0] | direct / direct |
| 12b/find | +8.2 [+5.4, +10.7] | +15.8 [+13.1, +19.5] | +4.6 [+0.7, +10.0] | +18.6 [+15.7, +23.3] | -1.6 [-5.7, +0.0] | -3.5 [-7.3, +1.5] | +1.5 [-0.2, +2.5] | -11.0 [-12.9, -10.1] | -24.8 [-29.8, -23.2] | spliced / direct |
| 12b/use | -0.4 [-1.2, +1.6] | -0.1 [-3.0, +1.2] | -2.4 [-3.9, -0.8] | +1.7 [+0.7, +3.3] | +7.5 [+4.6, +9.3] | +7.6 [+6.0, +10.1] | -0.9 [-1.7, -0.2] | +7.7 [+6.4, +10.1] | +6.6 [+5.1, +9.0] | direct / direct |
| 31b/find | +6.9 [+3.6, +14.9] | +24.8 [+21.9, +29.6] | +10.6 [+7.5, +20.6] | +20.1 [+17.6, +26.0] | +7.4 [+4.7, +12.9] | +5.5 [+1.3, +12.3] | +1.2 [-0.5, +4.0] | -1.7 [-5.9, +0.7] | -24.3 [-28.5, -21.5] | spliced / direct |
| 31b/use | -1.3 [-1.9, -0.0] | -1.1 [-1.8, +0.3] | -1.7 [-5.2, -0.1] | +1.7 [-0.9, +3.3] | +5.3 [+1.8, +6.4] | +6.8 [+5.4, +8.6] | -1.4 [-4.3, -0.8] | +7.5 [+5.0, +10.4] | +5.6 [+2.5, +8.1] | direct / direct |

## T7. Exploratory: first action at S-use (coordinator's question b), share of samples

| Size | Condition | n | edit_file | read_file | run_command | write_file(other) | get_code_neighbors | search_similar_code |
|---|---|---|---|---|---|---|---|---|
| e4b | L0 | 60 | 58% | 33% | 8% | 0% | 0% | 0% |
| e4b | L2 | 60 | 88% | 12% | 0% | 0% | 0% | 0% |
| e4b | L3 | 60 | 83% | 17% | 0% | 0% | 0% | 0% |
| e4b | L4 | 54 | 82% | 18% | 0% | 0% | 0% | 0% |
| e4b | L5 | 54 | 85% | 15% | 0% | 0% | 0% | 0% |
| e4b | G-json | 60 | 65% | 33% | 2% | 0% | 0% | 0% |
| e4b | T | 60 | 57% | 40% | 2% | 0% | 0% | 2% |
| e4b | W | 54 | 74% | 22% | 2% | 0% | 0% | 2% |
| e4b | X-func | 60 | 33% | 63% | 3% | 0% | 0% | 0% |
| e4b | X-test | 60 | 82% | 17% | 0% | 0% | 0% | 2% |
| 12b | L0 | 60 | 3% | 55% | 30% | 0% | 7% | 0% |
| 12b | L2 | 60 | 2% | 57% | 40% | 0% | 2% | 0% |
| 12b | L3 | 60 | 3% | 53% | 33% | 7% | 3% | 0% |
| 12b | L4 | 54 | 4% | 50% | 30% | 13% | 0% | 0% |
| 12b | L5 | 54 | 30% | 46% | 9% | 9% | 0% | 0% |
| 12b | G-json | 60 | 5% | 53% | 28% | 3% | 10% | 0% |
| 12b | T | 60 | 0% | 62% | 25% | 3% | 7% | 0% |
| 12b | W | 54 | 6% | 61% | 20% | 4% | 0% | 0% |
| 12b | X-func | 60 | 0% | 77% | 10% | 2% | 2% | 0% |
| 12b | X-test | 60 | 0% | 58% | 35% | 0% | 5% | 0% |
| 31b | L0 | 60 | 0% | 53% | 35% | 8% | 0% | 3% |
| 31b | L2 | 60 | 2% | 47% | 30% | 18% | 3% | 0% |
| 31b | L3 | 60 | 3% | 48% | 20% | 28% | 0% | 0% |
| 31b | L4 | 54 | 6% | 46% | 30% | 18% | 0% | 0% |
| 31b | L5 | 54 | 46% | 33% | 11% | 9% | 0% | 0% |
| 31b | G-json | 60 | 0% | 60% | 25% | 8% | 5% | 2% |
| 31b | T | 60 | 0% | 50% | 23% | 23% | 0% | 3% |
| 31b | W | 54 | 20% | 48% | 30% | 2% | 0% | 0% |
| 31b | X-func | 60 | 0% | 88% | 3% | 8% | 0% | 0% |
| 31b | X-test | 60 | 2% | 53% | 32% | 12% | 2% | 0% |
