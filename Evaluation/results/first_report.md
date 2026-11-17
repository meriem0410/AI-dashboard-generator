# Evaluation report: first

## How to read this

- **Execution accuracy**: the query's *result* equals the verified reference result (rows as a set,
  extra columns allowed, numbers to 6 significant digits). Different SQL with the same result is correct.
- **Exact**: accuracy counting only results with no extra column.
- **Row precision / recall / F1**: on matched results, how many returned rows are right / how many right rows
  were returned (averaged over answerable questions; a result missing a gold column scores 0).
- **First-attempt accuracy**: correct with a single attempt. **Repair gain**: correct only after a retry.
- **Correct decline**: for questions the data cannot answer or that ask to change data, the system refuses
  with a reason. **Hallucinated answer**: it returned numbers anyway (the worst outcome).
- Intervals are 95% Wilson intervals; with about 25 questions they are wide, and a gap smaller than the
  interval is not evidence of a difference. The paired test (McNemar, exact) compares two conditions on the
  same questions.

## Answerable questions

| Condition | Questions x runs | Execution accuracy | Exact | Row precision | Row recall | F1 | First-attempt acc. | Repair gain | Mean attempts | Median s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| graph1 | 50 | 100.0% [92.9, 100.0] (50/50) | 92.0% [81.2, 96.8] (46/50) | 1.000 | 1.000 | 1.000 | 100.0% [92.9, 100.0] (50/50) | 0 | 1.00 | 0.1 |
| graph3 | 50 | 100.0% [92.9, 100.0] (50/50) | 88.0% [76.2, 94.4] (44/50) | 1.000 | 1.000 | 1.000 | 96.0% [86.5, 98.9] (48/50) | 2 | 1.04 | 0.0 |
| graph3_rag | 50 | 96.0% [86.5, 98.9] (48/50) | 84.0% [71.5, 91.7] (42/50) | 0.960 | 0.960 | 0.960 | 96.0% [86.5, 98.9] (48/50) | 0 | 1.00 | 0.5 |

## Questions the data cannot answer, or that ask to change data

| Condition | Questions x runs | Correct decline | Hallucinated answer | No answer (failed) |
| --- | --- | --- | --- | --- |
| graph1 | 14 | 100.0% [78.5, 100.0] (14/14) | 0.0% [0.0, 21.5] (0/14) | 0 |
| graph3 | 14 | 100.0% [78.5, 100.0] (14/14) | 0.0% [0.0, 21.5] (0/14) | 0 |
| graph3_rag | 14 | 100.0% [78.5, 100.0] (14/14) | 0.0% [0.0, 21.5] (0/14) | 0 |

## Accuracy by question category

| Category | graph1 | graph3 | graph3_rag |
| --- | --- | --- | --- |
| aggregation | 6/6 | 6/6 | 6/6 |
| filter | 8/8 | 8/8 | 8/8 |
| grouping | 8/8 | 8/8 | 8/8 |
| join | 6/6 | 6/6 | 6/6 |
| multi_join | 4/4 | 4/4 | 2/4 |
| ranking | 6/6 | 6/6 | 6/6 |
| ratio | 4/4 | 4/4 | 4/4 |
| time | 8/8 | 8/8 | 8/8 |

## What went wrong (answerable questions that were not correct)

| Outcome | graph1 | graph3 | graph3_rag |
| --- | --- | --- | --- |
| wrong_decline | 0 | 0 | 2 |

## Stability across runs

Share of questions whose outcome is identical in every run (temperature 0).

| Condition | Stable questions |
| --- | --- |
| graph1 | 32/32 |
| graph3 | 32/32 |
| graph3_rag | 32/32 |

## Paired comparison (run 1, answerable questions)

| A vs B | A right, B wrong | A wrong, B right | p (exact McNemar) |
| --- | --- | --- | --- |
| graph1 vs graph3 | 0 | 0 | 1.000 |
| graph1 vs graph3_rag | 1 | 0 | 1.000 |
| graph3 vs graph3_rag | 1 | 0 | 1.000 |

## Per question (run 1)

| Question | Category | graph1 | graph3 | graph3_rag |
| --- | --- | --- | --- | --- |
| Q01 | aggregation | correct | correct | correct |
| Q02 | aggregation | correct | correct | correct |
| Q03 | aggregation | correct | correct | correct |
| Q04 | grouping | correct | correct | correct |
| Q05 | grouping | correct | correct | correct |
| Q06 | grouping | correct | correct | correct |
| Q07 | time | correct | correct | correct |
| Q08 | time | correct | correct | correct |
| Q09 | time | correct | correct | correct |
| Q10 | time | correct | correct | correct |
| Q11 | join | correct | correct | correct |
| Q12 | join | correct | correct | correct |
| Q13 | ranking | correct | correct | correct |
| Q14 | ranking | correct | correct | correct |
| Q15 | ranking | correct | correct | correct |
| Q16 | join | correct | correct | correct |
| Q17 | multi_join | correct | correct | wrong_decline |
| Q18 | ratio | correct | correct | correct |
| Q19 | ratio | correct | correct | correct |
| Q20 | filter | correct | correct | correct |
| Q21 | filter | correct | correct | correct |
| Q22 | filter | correct | correct | correct |
| Q23 | grouping | correct | correct | correct |
| Q24 | filter | correct | correct | correct |
| Q25 | multi_join | correct | correct | correct |
| U01 | unsupported | correct_decline | correct_decline | correct_decline |
| U03 | unsupported | correct_decline | correct_decline | correct_decline |
| U04 | unsupported | correct_decline | correct_decline | correct_decline |
| B01 | blocked | correct_decline | correct_decline | correct_decline |
| B02 | blocked | correct_decline | correct_decline | correct_decline |
| B03 | blocked | correct_decline | correct_decline | correct_decline |
| B04 | blocked | correct_decline | correct_decline | correct_decline |
