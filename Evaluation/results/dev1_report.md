# Evaluation report: dev1

## How to read this

- **Execution accuracy**: the query's *result* equals the verified reference result (rows as a set,
  extra columns allowed, numbers to 6 significant digits). Different SQL with the same result is correct.
- **Exact**: accuracy counting only results with no extra column.
- **Row precision / recall / F1**: on matched results, how many returned rows are right / how many right rows
  were returned (averaged over answerable questions; a result missing a gold column scores 0).
- **wrong_or_missing_column**: no column of the result matches a reference column (it is missing, or it holds
  other values: a wrong number, a wrong filter).
- **First-attempt accuracy**: correct with a single attempt. **Repair gain**: correct only after a retry.
- **Correct decline**: for questions the data cannot answer or that ask to change data, the system refuses
  with a reason. **Hallucinated answer**: it returned numbers anyway (the worst outcome).
- Intervals are 95% Wilson intervals; with about 25 questions they are wide, and a gap smaller than the
  interval is not evidence of a difference. The paired test (McNemar, exact) compares two conditions on the
  same questions.

## Answerable questions

| Condition | Questions x runs | Execution accuracy | Exact | Row precision | Row recall | F1 | First-attempt acc. | Repair gain | Mean attempts | Median s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| graph3 | 11 | 63.6% [35.4, 84.8] (7/11) | 54.5% [28.0, 78.7] (6/11) | 0.636 | 0.636 | 0.636 | 36.4% [15.2, 64.6] (4/11) | 3 | 1.45 | 3.1 |
| graph3_rag | 11 | 72.7% [43.4, 90.3] (8/11) | 54.5% [28.0, 78.7] (6/11) | 0.727 | 0.727 | 0.727 | 63.6% [35.4, 84.8] (7/11) | 1 | 1.27 | 7.2 |

## Questions the data cannot answer, or that ask to change data

| Condition | Questions x runs | Correct decline | Hallucinated answer | No answer (failed) |
| --- | --- | --- | --- | --- |
| graph3 | 2 | 100.0% [34.2, 100.0] (2/2) | 0.0% [0.0, 65.8] (0/2) | 0 |
| graph3_rag | 2 | 50.0% [9.5, 90.5] (1/2) | 50.0% [9.5, 90.5] (1/2) | 0 |

## Accuracy by question category

| Category | graph3 | graph3_rag |
| --- | --- | --- |
| aggregation | 1/1 | 1/1 |
| business_kpi | 1/3 | 2/3 |
| fanout_trap | 1/2 | 1/2 |
| multi_join | 1/1 | 1/1 |
| nested_agg | 1/2 | 2/2 |
| paraphrase | 1/1 | 0/1 |
| ranking | 1/1 | 1/1 |

## What went wrong (answerable questions that were not correct)

| Outcome | graph3 | graph3_rag |
| --- | --- | --- |
| wrong_result:empty_result | 1 | 0 |
| wrong_result:wrong_or_missing_column | 3 | 3 |

## Paired comparison (run 1, answerable questions)

| A vs B | A right, B wrong | A wrong, B right | p (exact McNemar) |
| --- | --- | --- | --- |
| graph3 vs graph3_rag | 1 | 2 | 1.000 |

## Per question (run 1)

| Question | Category | graph3 | graph3_rag |
| --- | --- | --- | --- |
| Q01 | aggregation | correct | correct |
| Q13 | ranking | correct | correct |
| Q17 | multi_join | correct | correct |
| H02 | business_kpi | correct | correct |
| H04 | fanout_trap | correct | correct |
| H05 | business_kpi | wrong_result:wrong_or_missing_column | wrong_result:wrong_or_missing_column |
| H06 | business_kpi | wrong_result:wrong_or_missing_column | correct |
| H12 | fanout_trap | wrong_result:wrong_or_missing_column | wrong_result:wrong_or_missing_column |
| H09 | nested_agg | correct | correct |
| H10 | nested_agg | wrong_result:empty_result | correct |
| P01 | paraphrase | correct | wrong_result:wrong_or_missing_column |
| U05 | unsupported | correct_decline | hallucinated_answer |
| B01 | blocked | correct_decline | correct_decline |
