# Patient matching — Fellegi–Sunter

Pairs: 3000 train / 3000 test (synthetic, labelled). Thresholds: file ≥ 4.00, reject ≤ -6.00.

| field | level | m | u | weight (bits) |
|---|---|---|---|---|
| family | agree | 0.983 | 0.270 | +1.87 |
| family | partial | 0.016 | 0.014 | +0.19 |
| family | disagree | 0.000 | 0.716 | -11.07 |
| given | agree | 0.987 | 0.084 | +3.55 |
| given | partial | 0.011 | 0.007 | +0.66 |
| given | disagree | 0.002 | 0.909 | -9.09 |
| dob | exact | 0.927 | 0.028 | +5.07 |
| dob | near | 0.071 | 0.004 | +4.07 |
| dob | disagree | 0.002 | 0.971 | -9.17 |

| metric | value | 95% CI |
|---|---|---|
| false_file | 0.0000 | [0.0000, 0.0000] |
| false_reject | 0.0007 | [0.0000, 0.0021] |
| review | 0.0807 | [0.0713, 0.0907] |
| AUC | 0.9999 | [0.9997, 1.0000] |

## README scenario cases

| requested | document says | W | decision |
|---|---|---|---|
| Maria Beispiel, *1961-03-12 | Maria Beispiel, 12 March 1961 | +10.49 | file |
| Maria Beispiel, *1961-03-12 | Max Beispiel, 1 January 1960 | -16.39 | reject |
| Maria Beispiel, *1961-03-12 | Maria Beispeil, 12.03.1961 | +10.49 | file |
| Maria Beispiel, *1961-03-12 | Maria Beispiel, 03.12.1961 | +9.49 | review |
| Maria Beispiel, *1961-03-12 | Anna Beispiel, 12 March 1961 | -2.15 | review |
