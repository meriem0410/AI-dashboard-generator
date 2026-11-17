# Evaluation report: hard

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
| graph1 | 28 | 82.1% [64.4, 92.1] (23/28) | 82.1% [64.4, 92.1] (23/28) | 0.821 | 0.821 | 0.821 | 82.1% [64.4, 92.1] (23/28) | 0 | 1.00 | 3.5 |
| graph3 | 28 | 85.7% [68.5, 94.3] (24/28) | 82.1% [64.4, 92.1] (23/28) | 0.857 | 0.857 | 0.857 | 78.6% [60.5, 89.8] (22/28) | 2 | 1.14 | 3.4 |
| graph3_rag | 28 | 35.7% [20.7, 54.2] (10/28) | 32.1% [17.9, 50.7] (9/28) | 0.357 | 0.357 | 0.357 | 35.7% [20.7, 54.2] (10/28) | 0 | 1.00 | 0.4 |

## Questions the data cannot answer, or that ask to change data

| Condition | Questions x runs | Correct decline | Hallucinated answer | No answer (failed) |
| --- | --- | --- | --- | --- |
| graph1 | 10 | 100.0% [72.2, 100.0] (10/10) | 0.0% [0.0, 27.8] (0/10) | 0 |
| graph3 | 10 | 100.0% [72.2, 100.0] (10/10) | 0.0% [0.0, 27.8] (0/10) | 0 |
| graph3_rag | 10 | 0.0% [0.0, 27.8] (0/10) | 0.0% [0.0, 27.8] (0/10) | 10 |

## Accuracy by question category

| Category | graph1 | graph3 | graph3_rag |
| --- | --- | --- | --- |
| aggregation | 1/1 | 1/1 | 1/1 |
| business_kpi | 5/7 | 5/7 | 0/7 |
| fanout_trap | 2/3 | 2/3 | 1/3 |
| filter | 1/1 | 1/1 | 1/1 |
| grouping | 1/1 | 1/1 | 1/1 |
| join | 1/1 | 1/1 | 1/1 |
| multi_join | 2/2 | 2/2 | 1/2 |
| nested_agg | 3/5 | 4/5 | 0/5 |
| paraphrase | 3/3 | 3/3 | 0/3 |
| ranking | 1/1 | 1/1 | 1/1 |
| ratio | 2/2 | 2/2 | 2/2 |
| time | 1/1 | 1/1 | 1/1 |

## What went wrong (answerable questions that were not correct)

| Outcome | graph1 | graph3 | graph3_rag |
| --- | --- | --- | --- |
| failed:generation | 0 | 0 | 14 |
| failed:schema_validation | 1 | 0 | 0 |
| wrong_decline | 0 | 0 | 3 |
| wrong_result:missing_columns | 4 | 4 | 1 |

## Paired comparison (run 1, answerable questions)

| A vs B | A right, B wrong | A wrong, B right | p (exact McNemar) |
| --- | --- | --- | --- |
| graph1 vs graph3 | 0 | 1 | 1.000 |
| graph1 vs graph3_rag | 13 | 0 | 0.000 |
| graph3 vs graph3_rag | 14 | 0 | 0.000 |

## Per question (run 1)

| Question | Category | graph1 | graph3 | graph3_rag |
| --- | --- | --- | --- | --- |
| Q01 | aggregation | correct | correct | correct |
| Q04 | grouping | correct | correct | correct |
| Q07 | time | correct | correct | correct |
| Q11 | join | correct | correct | correct |
| Q13 | ranking | correct | correct | correct |
| Q17 | multi_join | correct | correct | wrong_decline |
| Q18 | ratio | correct | correct | correct |
| Q19 | ratio | correct | correct | correct |
| Q22 | filter | correct | correct | correct |
| Q25 | multi_join | correct | correct | correct |
| H01 | business_kpi | correct | correct | wrong_result:missing_columns |
| H02 | business_kpi | correct | correct | wrong_decline |
| H04 | fanout_trap | correct | correct | correct |
| H05 | business_kpi | wrong_result:missing_columns | wrong_result:missing_columns | wrong_decline |
| H06 | business_kpi | wrong_result:missing_columns | wrong_result:missing_columns | failed:generation |
| H07 | business_kpi | correct | correct | failed:generation |
| H08 | business_kpi | correct | correct | failed:generation |
| H13 | business_kpi | correct | correct | failed:generation |
| H03 | fanout_trap | correct | correct | failed:generation |
| H12 | fanout_trap | wrong_result:missing_columns | wrong_result:missing_columns | failed:generation |
| H09 | nested_agg | failed:schema_validation | correct | failed:generation |
| H10 | nested_agg | wrong_result:missing_columns | wrong_result:missing_columns | failed:generation |
| H11 | nested_agg | correct | correct | failed:generation |
| H14 | nested_agg | correct | correct | failed:generation |
| H15 | nested_agg | correct | correct | failed:generation |
| P01 | paraphrase | correct | correct | failed:generation |
| P02 | paraphrase | correct | correct | failed:generation |
| P03 | paraphrase | correct | correct | failed:generation |
| U01 | unsupported | correct_decline | correct_decline | no_answer |
| U02 | unsupported | correct_decline | correct_decline | no_answer |
| U03 | unsupported | correct_decline | correct_decline | no_answer |
| U04 | unsupported | correct_decline | correct_decline | no_answer |
| U05 | unsupported | correct_decline | correct_decline | no_answer |
| U06 | unsupported | correct_decline | correct_decline | no_answer |
| B01 | blocked | correct_decline | correct_decline | no_answer |
| B02 | blocked | correct_decline | correct_decline | no_answer |
| B03 | blocked | correct_decline | correct_decline | no_answer |
| B04 | blocked | correct_decline | correct_decline | no_answer |
