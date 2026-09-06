# Analysis: pilot-v1 (pilot-v1)

## Trials attempted

| model | case | arm | planned | completed | needs_review | pending | correct | telemetry incomplete | stop reasons |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| gpt-5.6-luna | S2 | clean | 3 | 3 | 0 | 0 | 0 | 0 | {'token_limit': 3} |
| gpt-5.6-luna | S2 | clean-no-traces | 3 | 3 | 0 | 0 | 2 | 0 | {'token_limit': 1, 'submitted': 2} |
| gpt-5.6-luna | S2 | simple | 3 | 3 | 0 | 0 | 3 | 0 | {'submitted': 3} |
| gpt-5.6-terra | S2 | clean | 3 | 3 | 0 | 0 | 0 | 0 | {'token_limit': 3} |
| gpt-5.6-terra | S2 | clean-no-traces | 3 | 3 | 0 | 0 | 2 | 0 | {'submitted': 2, 'token_limit': 1} |
| gpt-5.6-terra | S2 | simple | 3 | 3 | 0 | 0 | 3 | 0 | {'submitted': 3} |

## Consumption among correct trials (complete telemetry only)

| model | case | arm | n correct | median total tokens | min | max | median input | median output | median cached | median reasoning | median seconds | median tool calls |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gpt-5.6-luna | S2 | clean | 0 | null | null | null | null | null | null | null | null | null |
| gpt-5.6-luna | S2 | clean-no-traces | 2 | 91626 | 84665 | 98586 | 88948 | 2678 | 76884 | 889 | 54.76 | 15.00 |
| gpt-5.6-luna | S2 | simple | 3 | 66295 | 58825 | 67844 | 63446 | 2635 | 57143 | 794 | 47.47 | 13 |
| gpt-5.6-terra | S2 | clean | 0 | null | null | null | null | null | null | null | null | null |
| gpt-5.6-terra | S2 | clean-no-traces | 2 | 73670 | 73284 | 74057 | 70258 | 3412 | 59978 | 1234 | 59.65 | 13.00 |
| gpt-5.6-terra | S2 | simple | 3 | 77355 | 67902 | 77726 | 73181 | 3954 | 65969 | 1490 | 64.92 | 15 |

## Unsuccessful or incomplete trials (consumption kept visible)

| model | case | arm | trial | verdict | stop reason | exact tokens | known lower bound | telemetry |
|---|---|---|---|---|---|---:|---:|---|
| gpt-5.6-terra | S2 | clean | 73d39b6c | no_submission | token_limit | 94754 | 94754 | complete (completed) |
| gpt-5.6-terra | S2 | clean | 561ef3b9 | no_submission | token_limit | 94488 | 94488 | complete (completed) |
| gpt-5.6-luna | S2 | clean-no-traces | 3657819c | no_submission | token_limit | 93428 | 93428 | complete (completed) |
| gpt-5.6-luna | S2 | clean | ead8c1e6 | no_submission | token_limit | 89836 | 89836 | complete (completed) |
| gpt-5.6-terra | S2 | clean | 52c0417b | no_submission | token_limit | 94751 | 94751 | complete (completed) |
| gpt-5.6-terra | S2 | clean-no-traces | 0be6f48e | no_submission | token_limit | 88647 | 88647 | complete (completed) |
| gpt-5.6-luna | S2 | clean | 96b5724c | no_submission | token_limit | 91806 | 91806 | complete (completed) |
| gpt-5.6-luna | S2 | clean | 702517bb | no_submission | token_limit | 90524 | 90524 | complete (completed) |

## Total tokens consumed per correct completion (all attempts, descriptive)

| model | case | arm | attempts | correct | known tokens consumed | tokens per correct completion |
|---|---|---|---:|---:|---:|---:|
| gpt-5.6-luna | S2 | clean | 3 | 0 | 272166 | undefined |
| gpt-5.6-luna | S2 | clean-no-traces | 3 | 2 | 276679 | 138340 |
| gpt-5.6-luna | S2 | simple | 3 | 3 | 192964 | 64321 |
| gpt-5.6-terra | S2 | clean | 3 | 0 | 283993 | undefined |
| gpt-5.6-terra | S2 | clean-no-traces | 3 | 2 | 235988 | 117994 |
| gpt-5.6-terra | S2 | simple | 3 | 3 | 222983 | 74328 |

## Paired differences (blocks where both arms are correct with complete telemetry)

| model | case | comparison | qualifying pairs | of blocks | median difference (tokens) | median ratio |
|---|---|---|---:|---:|---:|---:|
| gpt-5.6-luna | S2 | clean minus simple | 0 | 3 | null | null |
| gpt-5.6-luna | S2 | clean minus clean-no-traces | 0 | 3 | null | null |
| gpt-5.6-luna | S2 | clean-no-traces minus simple | 2 | 3 | 24556 | 1.37 |
| gpt-5.6-terra | S2 | clean minus simple | 0 | 3 | null | null |
| gpt-5.6-terra | S2 | clean minus clean-no-traces | 0 | 3 | null | null |
| gpt-5.6-terra | S2 | clean-no-traces minus simple | 2 | 3 | 856 | 1.02 |

## Spend (rate-card estimates, not invoices)

- known solving cost: $0.67923179
- budget file: committed $0.67923179 / cap $15.00; unresolved $0
