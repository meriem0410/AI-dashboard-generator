# Devoboard — pipeline evaluation evidence (`final`)
_Generated 2026-11-16T01:08:22._

## Summary

| Stage | Step | Result |
|---|---|---|
| Unit suite | `unit` | FAILED |
| Safety | `guard` | passed |
| Schema retrieval (RAG) | `retrieval` | passed |
| SQL accuracy | `main` | passed |
| Accuracy report | `report` | passed |

Artifacts in `Evaluation/results/`: `final.jsonl` (raw per-question records), `final_report.md` (accuracy tables), `guard_eval.md` (safety).

## `unit` — Unit suite — deterministic components (ingest, profiling, schema, filters, KPI trends, ops, semantic checks, insights, export, overview)

Command: `C:\Users\emmaw\Downloads\PFE\.venv\Scripts\python.exe C:\Users\emmaw\Downloads\PFE\Modules\Scripts\run_all_tests.py`
Status: exit 1  ·  132s

```
OK   test_migration.py              63 checks passed, 0 failed
OK   test_tools_and_schemas.py      46 checks passed, 0 failed
OK   test_graph_panel.py            37 checks passed, 0 failed
OK   test_llm_cache.py              19 checks passed, 0 failed
OK   test_semantic_checks.py        27 checks passed, 0 failed
OK   test_day2.py                   44 checks passed, 0 failed
OK   test_composition.py            19 checks passed, 0 failed
OK   test_knowledge_base.py         42 checks passed, 0 failed
OK   test_data_agent.py             30 checks passed, 0 failed
OK   test_rag_context.py            21 checks passed, 0 failed
OK   test_library.py                68 checks passed, 0 failed
OK   test_app_services.py           23 checks passed, 0 failed
OK   test_eval_metrics.py           32 checks passed, 0 failed
OK   test_guard_eval.py             6 checks passed, 0 failed
FAIL test_eval_runner.py            38 checks passed, 1 failed
       FAIL  the run stops cleanly at the budget | 5
       last output: ['PASS  classify: gold column missing is not a match', '', '==== 1 TEST(S) FAILED ====']
OK   test_gold_logistics.py         66 checks passed, 0 failed
OK   test_retrieval_eval.py         13 checks passed, 0 failed
OK   test_engine_filters.py         16 checks passed, 0 failed
OK   test_dashboard_filters_scope.py 19 checks passed, 0 failed
OK   test_kpi_headline.py           10 checks passed, 0 failed
OK   test_kpi_trends.py             38 checks passed, 0 failed
OK   test_dashboard_ops.py          31 checks passed, 0 failed
OK   test_followup.py               21 checks passed, 0 failed
OK   test_schema_values.py          12 checks passed, 0 failed
OK   test_insights.py               14 checks passed, 0 failed
OK   test_export_html.py            12 checks passed, 0 failed
OK   test_dataset_overview.py       8 checks passed, 0 failed
OK   test_eval_harness.py           18 checks passed, 0 failed

==== 1 SCRIPT(S) FAILED ====
```

## `guard` — Safety — SQL guard + locked engine (attack block rate, benign pass rate)

Command: `C:\Users\emmaw\Downloads\PFE\.venv\Scripts\python.exe -m Evaluation.guard_eval`
Status: OK  ·  9s

```
# Safety layers: evaluation

- Attacks tested: 57; refused by the guard: **57/57** (100.0%)
- Benign queries tested: 32; allowed by the guard: **32/32** (100.0%); executed successfully: 32/32

## Attacks by category

| Category | Attacks | Guard refuses | Engine alone refuses |
| --- | --- | --- | --- |
| write | 13 | 13/13 | 10/13 |
| cte-write | 3 | 3/3 | 3/3 |
| stacked | 4 | 4/4 | 3/4 |
| obfuscated | 4 | 4/4 | 4/4 |
| file-read | 10 | 10/10 | 10/10 |
| file-write | 3 | 3/3 | 3/3 |
| engine | 20 | 20/20 | 10/20 |

## Attacks the guard let through

None.

## Benign queries wrongly refused or failing

None.

## Defence in depth

43/57 attacks would also fail on the locked engine alone. 14 are stopped ONLY by the guard (mostly writes on the in-memory copy, which the engine permits); the guard is therefore necessary, and the engine lock covers file and configuration access independently.

Written to C:\Users\emmaw\Downloads\PFE\Evaluation\results\guard_eval.md

[stderr]
'LOAD httpfs' contains unsupported syntax. Falling back to parsing as a 'Command'.
'RESET enable_external_access' contains unsupported syntax. Falling back to parsing as a 'Command'.
'CALL pragma_database_size()' contains unsupported syntax. Falling back to parsing as a 'Command'.
'EXECUTE foo' contains unsupported syntax. Falling back to parsing as a 'Command'.
```

## `retrieval` — Schema retrieval (RAG) — table recall, precision, prompt-size sweep

Command: `C:\Users\emmaw\Downloads\PFE\.venv\Scripts\python.exe -m Evaluation.retrieval_eval Logistics`
Status: OK  ·  62s

```

📥 DATA INGESTION
============================================================
   ✓ customers (200 rows, 8 columns)
   ✓ delivery_events (170820 rows, 11 columns)
   ✓ drivers (150 rows, 12 columns)
   ✓ facilities (50 rows, 9 columns)
   ✓ fuel_purchases (196442 rows, 11 columns)
   ✓ loads (85410 rows, 12 columns)
   ✓ maintenance_records (2920 rows, 12 columns)
   ✓ routes (58 rows, 9 columns)
   ✓ safety_incidents (170 rows, 15 columns)
   ✓ trailers (180 rows, 9 columns)
   ✓ trips (85410 rows, 12 columns)
   ✓ trucks (120 rows, 11 columns)

✅ Data ingestion completed
   Tables loaded : 12
   Total rows    : 541930
   Total columns : 131
# Schema retrieval: evaluation (no language model)

For each verified question: the tables its reference SQL needs against the tables retrieval handed to the model. A missing table makes the question unanswerable for the model.

| Setting | Questions | Table recall | All needed tables retrieved | Precision | Prompt size vs full schema |
| --- | --- | --- | --- | --- | --- |
| k2_max4 (default) | 28 | 0.798 | 71.4% | 0.446 | 23.7% |
| k3_max6 | 28 | 0.917 | 85.7% | 0.352 | 34.7% |
| k4_max8 | 28 | 0.929 | 89.3% | 0.299 | 44.7% |

## Questions that lost a table: k2_max4 (default) (8)

| Question | Category | Needed | Retrieved | Missing |
| --- | --- | --- | --- | --- |
| Q17 | multi_join | customers, loads, safety_incidents, trips | drivers, safety_incidents | **customers, loads, trips** |
| H01 | business_kpi | customers, loads, trips | customers, loads, routes | **trips** |
| H02 | business_kpi | trips | drivers, fuel_purchases, trucks | **trips** |
| H05 | business_kpi | safety_incidents, trips | drivers, routes, safety_incidents | **trips** |
| H03 | fanout_trap | customers, fuel_purchases, loads, trips | drivers, fuel_purchases, routes | **customers, loads, trips** |
| H12 | fanout_trap | maintenance_records, trips, trucks | maintenance_records, trucks | **trips** |
| P01 | paraphrase | loads | customers, trucks | **loads** |
| P03 | paraphrase | loads | customers, drivers, fuel_purchases | **loads** |

## Questions that lost a table: k3_max6 (4)

| Question | Category | Needed | Retrieved | Missing |
| --- | --- | --- | --- | --- |
| Q17 | multi_join | customers, loads, safety_incidents, trips | drivers, safety_incidents | **customers, loads, trips** |
| H01 | business_kpi | customers, loads, trips | customers, loads, routes | **trips** |
| H03 | fanout_trap | customers, fuel_purchases, loads, trips | drivers, fuel_purchases, loads, routes, trips | **customers** |
| P01 | paraphrase | loads | customers, trailers, trips, trucks | **loads** |

## Questions that lost a table: k4_max8 (3)

| Question | Category | Needed | Retrieved | Missing |
| --- | --- | --- | --- | --- |
| Q17 | multi_join | customers, loads, safety_incidents, trips | drivers, safety_incidents | **customers, loads, trips** |
| H03 | fanout_trap | customers, fuel_purchases, loads, trips | drivers, fuel_purchases, loads, routes, trips | **customers** |
| P01 | paraphrase | loads | customers, facilities, trailers, trips, trucks | **loads** |

Written to C:\Users\emmaw\Downloads\PFE\Evaluation\results\retrieval_eval.md
```

## `main` — SQL accuracy — generation + repair vs verified gold (execution accuracy, precision/recall/F1)

Command: `C:\Users\emmaw\Downloads\PFE\.venv\Scripts\python.exe -m Evaluation.run_eval --dataset Logistics --tag final --conditions graph1,graph3,graph3_rag --runs 1 --max-wait 60 --resume --budget 180000 --pace 20.0`  (env: LLM_CACHE=on)
Status: OK  ·  286s

```
38 questions (0 skipped as unverified)

📥 DATA INGESTION
============================================================
   ✓ customers (200 rows, 8 columns)
   ✓ delivery_events (170820 rows, 11 columns)
   ✓ drivers (150 rows, 12 columns)
   ✓ facilities (50 rows, 9 columns)
   ✓ fuel_purchases (196442 rows, 11 columns)
   ✓ loads (85410 rows, 12 columns)
   ✓ maintenance_records (2920 rows, 12 columns)
   ✓ routes (58 rows, 9 columns)
   ✓ safety_incidents (170 rows, 15 columns)
   ✓ trailers (180 rows, 9 columns)
   ✓ trips (85410 rows, 12 columns)
   ✓ trucks (120 rows, 11 columns)

✅ Data ingestion completed
   Tables loaded : 12
   Total rows    : 541930
   Total columns : 131

=================================================================
📊 DATA PROFILING
=================================================================

🔎 customers (200 rows × 8 columns)
   table_info : 0.030s
   columns    : 0.081s
   total      : 0.111s

🔎 delivery_events (170,820 rows × 11 columns)
   table_info : 0.673s
   columns    : 0.628s
   total      : 1.301s

🔎 drivers (150 rows × 12 columns)
   table_info : 0.032s
   columns    : 0.095s
   total      : 0.127s

🔎 facilities (50 rows × 9 columns)
   table_info : 0.023s
   columns    : 0.153s
   total      : 0.176s

🔎 fuel_purchases (196,442 rows × 11 columns)
   table_info : 1.023s
   columns    : 0.818s
   total      : 1.841s

🔎 loads (85,410 rows × 12 columns)
   table_info : 0.288s
   columns    : 0.295s
   total      : 0.584s

🔎 maintenance_records (2,920 rows × 12 columns)
   table_info : 0.031s
   columns    : 0.071s
   total      : 0.103s

🔎 routes (58 rows × 9 columns)
   table_info : 0.015s
   columns    : 0.054s
   total      : 0.070s

🔎 safety_incidents (170 rows × 15 columns)
   table_info : 0.026s
   columns    : 0.075s
   total      : 0.101s

🔎 trailers (180 rows × 9 columns)
   table_info : 0.021s
   columns    : 0.063s
   total      : 0.084s

🔎 trips (85,410 rows × 12 columns)
   table_info : 0.309s
   columns    : 0.316s
   total      : 0.626s

🔎 trucks (120 rows × 11 columns)
   table_info : 0.020s
   columns    : 0.077s
   total      : 0.097s

🔗 Detecting relationships...

=================================================================
⏱️ PROFILING PERFORMANCE
=================================================================
Column/table profiling : 5.221s
Relationship detection  : 6.834s
TOTAL                   : 12.055s
=================================================================
Schema saved to schema.txt
About 3,223 tokens per model call; at most ~367,422 tokens if nothing is replayed (cache: on, budget 180,000).
graph1      run1 Q01    correct                      tries=1   4.4s
graph1      run1 Q04    correct                      tries=1   0.7s
graph1      run1 Q07    correct                      tries=1   0.7s
graph1      run1 Q11    correct                      tries=1  10.1s
graph1      run1 Q13    correct                      tries=1  11.1s
graph1      run1 Q17    correct                      tries=1  14.7s
graph1      run1 Q18    correct                      tries=1  13.1s
graph1      run1 Q19    correct                      tries=1  13.2s
graph1      run1 Q22    correct                      tries=1  13.1s
graph1      run1 Q25    the model service asks to wait 900s (more than --max-wait 60s): quota reached. Stopped cleanly, nothing lost: run the same command with --resume later.
Real model calls in this file: 9 (39,411 tokens measured); replayed cases: 0.

Results: C:\Users\emmaw\Downloads\PFE\Evaluation\results\final.jsonl
Next: python -m Evaluation.report final
```

## `report` — Accuracy report — tables with 95% CIs, repair/RAG effect, failure taxonomy, significance tests

Command: `C:\Users\emmaw\Downloads\PFE\.venv\Scripts\python.exe -m Evaluation.report final`
Status: OK  ·  7s

```
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


Written to C:\Users\emmaw\Downloads\PFE\Evaluation\results\final_report.md
```
