# Pipeline reliability report

Generated: 2026-08-11T01:36:53.336427+00:00
Rounds: 5 × 3 jobs

## Average stage timing (ms)

- **select_jobs**: 17365 ms (17.4s)
- **refine**: 452693 ms (452.7s)
- **apply**: 68129 ms (68.1s)
- **open_form**: 26671 ms (26.7s)
- **verify_submit_ui**: 218 ms (0.2s)

## Gate failures (count of rounds failing)

- `A1_ui_opens`: 0/5
- `A2_select`: 0/5
- `A3_refine`: 0/5
- `A4_apply`: 0/5
- `A6_open_form`: 0/5
- `A5_official_ats`: 0/5
- `A7_timing`: 0/5

## Errors

- (none)

## Per-round stage ms

### Round 1
- stages: `{"select_jobs": 15633, "refine": 499651, "apply": 63414, "open_form": 26459, "verify_submit_ui": 94}`
- gates: `{"A1_ui_opens": true, "A2_select": true, "A3_refine": true, "A4_apply": true, "A6_open_form": true, "A5_official_ats": true, "A7_timing": true}`
- errors: `[]`

### Round 2
- stages: `{"select_jobs": 20843, "refine": 424062, "apply": 75343, "open_form": 27196, "verify_submit_ui": 342}`
- gates: `{"A1_ui_opens": true, "A2_select": true, "A3_refine": true, "A4_apply": true, "A6_open_form": true, "A5_official_ats": true, "A7_timing": true}`
- errors: `[]`

### Round 3
- stages: `{"select_jobs": 17683, "refine": 429257, "apply": 72268, "open_form": 26735, "verify_submit_ui": 461}`
- gates: `{"A1_ui_opens": true, "A2_select": true, "A3_refine": true, "A4_apply": true, "A6_open_form": true, "A5_official_ats": true, "A7_timing": true}`
- errors: `[]`

### Round 4
- stages: `{"select_jobs": 17320, "refine": 187109, "apply": 63316, "open_form": 26512, "verify_submit_ui": 106}`
- gates: `{"A1_ui_opens": true, "A2_select": true, "A3_refine": true, "A4_apply": true, "A6_open_form": true, "A5_official_ats": true, "A7_timing": true}`
- errors: `[]`

### Round 5
- stages: `{"select_jobs": 15350, "refine": 723389, "apply": 66308, "open_form": 26456, "verify_submit_ui": 91}`
- gates: `{"A1_ui_opens": true, "A2_select": true, "A3_refine": true, "A4_apply": true, "A6_open_form": true, "A5_official_ats": true, "A7_timing": true}`
- errors: `[]`
