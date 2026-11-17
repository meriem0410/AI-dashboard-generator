# Evaluation report: final

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
| graph1 | 9 | 100.0% [70.1, 100.0] (9/9) | 88.9% [56.5, 98.0] (8/9) | 1.000 | 1.000 | 1.000 | 100.0% [70.1, 100.0] (9/9) | 0 | 1.00 | 11.1 |

## Accuracy by question category

| Category | graph1 |
| --- | --- |
| aggregation | 1/1 |
| filter | 1/1 |
| grouping | 1/1 |
| join | 1/1 |
| multi_join | 1/1 |
| ranking | 1/1 |
| ratio | 2/2 |
| time | 1/1 |

## What went wrong (answerable questions that were not correct)

| Outcome | graph1 |
| --- | --- |
| (none) | |

## Per question (run 1)

| Question | Category | graph1 |
| --- | --- | --- |
| Q01 | aggregation | correct |
| Q04 | grouping | correct |
| Q07 | time | correct |
| Q11 | join | correct |
| Q13 | ranking | correct |
| Q17 | multi_join | correct |
| Q18 | ratio | correct |
| Q19 | ratio | correct |
| Q22 | filter | correct |
