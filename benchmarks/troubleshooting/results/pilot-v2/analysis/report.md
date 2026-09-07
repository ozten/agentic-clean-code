# Analysis: pilot-v2 (pilot-v2)

## Trials attempted

| model | case | arm | planned | completed | needs_review | pending | correct | telemetry incomplete | stop reasons |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| gpt-5.6-luna | S1 | clean | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-luna | S1 | clean-no-traces | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-luna | S1 | simple | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-luna | S2 | clean | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-luna | S2 | clean-no-traces | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-luna | S2 | simple | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-luna | S3 | clean | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-luna | S3 | clean-no-traces | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-luna | S3 | simple | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-luna | S4 | clean | 1 | 1 | 0 | 0 | 0 | 0 | {'token_limit': 1} |
| gpt-5.6-luna | S4 | clean-no-traces | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-luna | S4 | simple | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-luna | S5 | clean | 1 | 1 | 0 | 0 | 0 | 0 | {'token_limit': 1} |
| gpt-5.6-luna | S5 | clean-no-traces | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-luna | S5 | simple | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-terra | S1 | clean | 1 | 1 | 0 | 0 | 0 | 0 | {'token_limit': 1} |
| gpt-5.6-terra | S1 | clean-no-traces | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-terra | S1 | simple | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-terra | S2 | clean | 1 | 1 | 0 | 0 | 0 | 0 | {'token_limit': 1} |
| gpt-5.6-terra | S2 | clean-no-traces | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-terra | S2 | simple | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-terra | S3 | clean | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-terra | S3 | clean-no-traces | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-terra | S3 | simple | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-terra | S4 | clean | 1 | 1 | 0 | 0 | 0 | 0 | {'token_limit': 1} |
| gpt-5.6-terra | S4 | clean-no-traces | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-terra | S4 | simple | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-terra | S5 | clean | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-terra | S5 | clean-no-traces | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |
| gpt-5.6-terra | S5 | simple | 1 | 1 | 0 | 0 | 1 | 0 | {'submitted': 1} |

## Consumption among correct trials (complete telemetry only)

| model | case | arm | n correct | median total tokens | min | max | median input | median output | median cached | median reasoning | median seconds | median tool calls |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gpt-5.6-luna | S1 | clean | 1 | 268901 | 268901 | 268901 | 265339 | 3562 | 241452 | 1327 | 68.57 | 16 |
| gpt-5.6-luna | S1 | clean-no-traces | 1 | 125876 | 125876 | 125876 | 123179 | 2697 | 100737 | 951 | 54.86 | 16 |
| gpt-5.6-luna | S1 | simple | 1 | 88526 | 88526 | 88526 | 85401 | 3125 | 73183 | 1241 | 54.41 | 13 |
| gpt-5.6-luna | S2 | clean | 1 | 293072 | 293072 | 293072 | 290375 | 2697 | 244337 | 586 | 58.47 | 18 |
| gpt-5.6-luna | S2 | clean-no-traces | 1 | 132204 | 132204 | 132204 | 128852 | 3352 | 101600 | 1278 | 61.04 | 16 |
| gpt-5.6-luna | S2 | simple | 1 | 90861 | 90861 | 90861 | 88088 | 2773 | 77006 | 1009 | 55.13 | 14 |
| gpt-5.6-luna | S3 | clean | 1 | 243099 | 243099 | 243099 | 240649 | 2450 | 217210 | 413 | 47.75 | 15 |
| gpt-5.6-luna | S3 | clean-no-traces | 1 | 88237 | 88237 | 88237 | 86102 | 2135 | 74372 | 424 | 43.55 | 13 |
| gpt-5.6-luna | S3 | simple | 1 | 61460 | 61460 | 61460 | 59413 | 2047 | 48931 | 500 | 45.21 | 11 |
| gpt-5.6-luna | S4 | clean | 0 | null | null | null | null | null | null | null | null | null |
| gpt-5.6-luna | S4 | clean-no-traces | 1 | 126695 | 126695 | 126695 | 123992 | 2703 | 92374 | 834 | 55.91 | 15 |
| gpt-5.6-luna | S4 | simple | 1 | 75424 | 75424 | 75424 | 72514 | 2910 | 59359 | 1196 | 57.43 | 11 |
| gpt-5.6-luna | S5 | clean | 0 | null | null | null | null | null | null | null | null | null |
| gpt-5.6-luna | S5 | clean-no-traces | 1 | 138946 | 138946 | 138946 | 135858 | 3088 | 106507 | 1074 | 57.92 | 16 |
| gpt-5.6-luna | S5 | simple | 1 | 89123 | 89123 | 89123 | 86479 | 2644 | 70574 | 961 | 49.53 | 12 |
| gpt-5.6-terra | S1 | clean | 0 | null | null | null | null | null | null | null | null | null |
| gpt-5.6-terra | S1 | clean-no-traces | 1 | 138038 | 138038 | 138038 | 133894 | 4144 | 119733 | 1408 | 83.94 | 16 |
| gpt-5.6-terra | S1 | simple | 1 | 112605 | 112605 | 112605 | 107722 | 4883 | 94810 | 2038 | 79.44 | 14 |
| gpt-5.6-terra | S2 | clean | 0 | null | null | null | null | null | null | null | null | null |
| gpt-5.6-terra | S2 | clean-no-traces | 1 | 100357 | 100357 | 100357 | 96806 | 3551 | 82144 | 1203 | 60.64 | 13 |
| gpt-5.6-terra | S2 | simple | 1 | 70838 | 70838 | 70838 | 66753 | 4085 | 54159 | 1843 | 70.83 | 11 |
| gpt-5.6-terra | S3 | clean | 1 | 285460 | 285460 | 285460 | 282583 | 2877 | 259844 | 618 | 61.63 | 17 |
| gpt-5.6-terra | S3 | clean-no-traces | 1 | 86931 | 86931 | 86931 | 83997 | 2934 | 71552 | 805 | 49.72 | 13 |
| gpt-5.6-terra | S3 | simple | 1 | 81994 | 81994 | 81994 | 79193 | 2801 | 68831 | 641 | 48.95 | 12 |
| gpt-5.6-terra | S4 | clean | 0 | null | null | null | null | null | null | null | null | null |
| gpt-5.6-terra | S4 | clean-no-traces | 1 | 114434 | 114434 | 114434 | 111221 | 3213 | 97382 | 1042 | 70.73 | 14 |
| gpt-5.6-terra | S4 | simple | 1 | 80516 | 80516 | 80516 | 76567 | 3949 | 65524 | 1583 | 65.41 | 12 |
| gpt-5.6-terra | S5 | clean | 1 | 263953 | 263953 | 263953 | 260711 | 3242 | 216074 | 898 | 64.42 | 16 |
| gpt-5.6-terra | S5 | clean-no-traces | 1 | 82253 | 82253 | 82253 | 79098 | 3155 | 67358 | 763 | 49.53 | 12 |
| gpt-5.6-terra | S5 | simple | 1 | 73269 | 73269 | 73269 | 70133 | 3136 | 59343 | 1043 | 53.54 | 11 |

## Unsuccessful or incomplete trials (consumption kept visible)

| model | case | arm | trial | verdict | stop reason | exact tokens | known lower bound | telemetry |
|---|---|---|---|---|---|---:|---:|---|
| gpt-5.6-luna | S4 | clean | 7658ea3d | no_submission | token_limit | 279461 | 279461 | complete (completed) |
| gpt-5.6-terra | S2 | clean | dc196eab | no_submission | token_limit | 284918 | 284918 | complete (completed) |
| gpt-5.6-terra | S1 | clean | f24f07a6 | no_submission | token_limit | 289651 | 289651 | complete (completed) |
| gpt-5.6-luna | S5 | clean | 73c6c89f | no_submission | token_limit | 296414 | 296414 | complete (completed) |
| gpt-5.6-terra | S4 | clean | 96f75320 | no_submission | token_limit | 284693 | 284693 | complete (completed) |

## Total tokens consumed per correct completion (all attempts, descriptive)

| model | case | arm | attempts | correct | known tokens consumed | tokens per correct completion |
|---|---|---|---:|---:|---:|---:|
| gpt-5.6-luna | S1 | clean | 1 | 1 | 268901 | 268901 |
| gpt-5.6-luna | S1 | clean-no-traces | 1 | 1 | 125876 | 125876 |
| gpt-5.6-luna | S1 | simple | 1 | 1 | 88526 | 88526 |
| gpt-5.6-luna | S2 | clean | 1 | 1 | 293072 | 293072 |
| gpt-5.6-luna | S2 | clean-no-traces | 1 | 1 | 132204 | 132204 |
| gpt-5.6-luna | S2 | simple | 1 | 1 | 90861 | 90861 |
| gpt-5.6-luna | S3 | clean | 1 | 1 | 243099 | 243099 |
| gpt-5.6-luna | S3 | clean-no-traces | 1 | 1 | 88237 | 88237 |
| gpt-5.6-luna | S3 | simple | 1 | 1 | 61460 | 61460 |
| gpt-5.6-luna | S4 | clean | 1 | 0 | 279461 | undefined |
| gpt-5.6-luna | S4 | clean-no-traces | 1 | 1 | 126695 | 126695 |
| gpt-5.6-luna | S4 | simple | 1 | 1 | 75424 | 75424 |
| gpt-5.6-luna | S5 | clean | 1 | 0 | 296414 | undefined |
| gpt-5.6-luna | S5 | clean-no-traces | 1 | 1 | 138946 | 138946 |
| gpt-5.6-luna | S5 | simple | 1 | 1 | 89123 | 89123 |
| gpt-5.6-terra | S1 | clean | 1 | 0 | 289651 | undefined |
| gpt-5.6-terra | S1 | clean-no-traces | 1 | 1 | 138038 | 138038 |
| gpt-5.6-terra | S1 | simple | 1 | 1 | 112605 | 112605 |
| gpt-5.6-terra | S2 | clean | 1 | 0 | 284918 | undefined |
| gpt-5.6-terra | S2 | clean-no-traces | 1 | 1 | 100357 | 100357 |
| gpt-5.6-terra | S2 | simple | 1 | 1 | 70838 | 70838 |
| gpt-5.6-terra | S3 | clean | 1 | 1 | 285460 | 285460 |
| gpt-5.6-terra | S3 | clean-no-traces | 1 | 1 | 86931 | 86931 |
| gpt-5.6-terra | S3 | simple | 1 | 1 | 81994 | 81994 |
| gpt-5.6-terra | S4 | clean | 1 | 0 | 284693 | undefined |
| gpt-5.6-terra | S4 | clean-no-traces | 1 | 1 | 114434 | 114434 |
| gpt-5.6-terra | S4 | simple | 1 | 1 | 80516 | 80516 |
| gpt-5.6-terra | S5 | clean | 1 | 1 | 263953 | 263953 |
| gpt-5.6-terra | S5 | clean-no-traces | 1 | 1 | 82253 | 82253 |
| gpt-5.6-terra | S5 | simple | 1 | 1 | 73269 | 73269 |

## Paired differences (blocks where both arms are correct with complete telemetry)

| model | case | comparison | qualifying pairs | of blocks | median difference (tokens) | median ratio |
|---|---|---|---:|---:|---:|---:|
| gpt-5.6-luna | S1 | clean minus simple | 1 | 1 | 180375 | 3.04 |
| gpt-5.6-luna | S1 | clean minus clean-no-traces | 1 | 1 | 143025 | 2.14 |
| gpt-5.6-luna | S1 | clean-no-traces minus simple | 1 | 1 | 37350 | 1.42 |
| gpt-5.6-luna | S2 | clean minus simple | 1 | 1 | 202211 | 3.23 |
| gpt-5.6-luna | S2 | clean minus clean-no-traces | 1 | 1 | 160868 | 2.22 |
| gpt-5.6-luna | S2 | clean-no-traces minus simple | 1 | 1 | 41343 | 1.46 |
| gpt-5.6-luna | S3 | clean minus simple | 1 | 1 | 181639 | 3.96 |
| gpt-5.6-luna | S3 | clean minus clean-no-traces | 1 | 1 | 154862 | 2.76 |
| gpt-5.6-luna | S3 | clean-no-traces minus simple | 1 | 1 | 26777 | 1.44 |
| gpt-5.6-luna | S4 | clean minus simple | 0 | 1 | null | null |
| gpt-5.6-luna | S4 | clean minus clean-no-traces | 0 | 1 | null | null |
| gpt-5.6-luna | S4 | clean-no-traces minus simple | 1 | 1 | 51271 | 1.68 |
| gpt-5.6-luna | S5 | clean minus simple | 0 | 1 | null | null |
| gpt-5.6-luna | S5 | clean minus clean-no-traces | 0 | 1 | null | null |
| gpt-5.6-luna | S5 | clean-no-traces minus simple | 1 | 1 | 49823 | 1.56 |
| gpt-5.6-terra | S1 | clean minus simple | 0 | 1 | null | null |
| gpt-5.6-terra | S1 | clean minus clean-no-traces | 0 | 1 | null | null |
| gpt-5.6-terra | S1 | clean-no-traces minus simple | 1 | 1 | 25433 | 1.23 |
| gpt-5.6-terra | S2 | clean minus simple | 0 | 1 | null | null |
| gpt-5.6-terra | S2 | clean minus clean-no-traces | 0 | 1 | null | null |
| gpt-5.6-terra | S2 | clean-no-traces minus simple | 1 | 1 | 29519 | 1.42 |
| gpt-5.6-terra | S3 | clean minus simple | 1 | 1 | 203466 | 3.48 |
| gpt-5.6-terra | S3 | clean minus clean-no-traces | 1 | 1 | 198529 | 3.28 |
| gpt-5.6-terra | S3 | clean-no-traces minus simple | 1 | 1 | 4937 | 1.06 |
| gpt-5.6-terra | S4 | clean minus simple | 0 | 1 | null | null |
| gpt-5.6-terra | S4 | clean minus clean-no-traces | 0 | 1 | null | null |
| gpt-5.6-terra | S4 | clean-no-traces minus simple | 1 | 1 | 33918 | 1.42 |
| gpt-5.6-terra | S5 | clean minus simple | 1 | 1 | 190684 | 3.60 |
| gpt-5.6-terra | S5 | clean minus clean-no-traces | 1 | 1 | 181700 | 3.21 |
| gpt-5.6-terra | S5 | clean-no-traces minus simple | 1 | 1 | 8984 | 1.12 |

## Spend (rate-card estimates, not invoices)

- known solving cost: $1.91897502
- budget file: committed $1.91897502 / cap $65.00; unresolved $0
