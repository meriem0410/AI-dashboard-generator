# Evaluation

1. `python -m Evaluation.guard_eval`      safety layers (offline, no data, no model)
2. `python -m Evaluation.dump_schema Logistics`   describe the dataset (to write the gold SQL)
3. write `Evaluation/questions.json` (see questions.template.json), verify each gold result by hand,
   set `"verified": true`
4. `python -m Evaluation.run_eval --dataset Logistics --tag first --runs 2`
5. `python -m Evaluation.report first`
