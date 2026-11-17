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
