# Inspection: dev1

Answers replayed from the LLM cache: 11/26 (a replayed answer was not generated again: timings and run-to-run stability are then not measurements)

Outcomes: correct=15, correct_decline=3, hallucinated_answer=1, wrong_result:empty_result=1, wrong_result:wrong_or_missing_column=6

## H05  graph3  run 1  ->  wrong_result:wrong_or_missing_column

Question: What is our at-fault accident rate per million miles driven? Count collisions only, not violations or complaints.

Reference SQL:
```sql
SELECT 1000000.0 * (SELECT COUNT(*) FROM safety_incidents WHERE incident_type = 'Accident' AND at_fault_flag) / (SELECT SUM(actual_distance_miles) FROM trips) AS accidents_per_million_miles
```
Generated SQL:
```sql
SELECT (COUNT(*)::DOUBLE / NULLIF(SUM(t.actual_distance_miles),0)) * 1000000 AS at_fault_accident_rate_per_million_miles
FROM safety_incidents si
JOIN trips t ON si.trip_id = t.trip_id
WHERE si.at_fault_flag = TRUE;
```
stage=completed status=ok attempts=1 rows=1 (gold 1) seconds=189.81 replayed=False

## H06  graph3  run 1  ->  wrong_result:wrong_or_missing_column

Question: For each facility type, what percentage of deliveries had more than 2 hours of detention?

Reference SQL:
```sql
SELECT f.facility_type, 100.0 * AVG(CASE WHEN e.detention_minutes > 120 THEN 1 ELSE 0 END) AS pct_over_2h FROM delivery_events e JOIN facilities f ON e.facility_id = f.facility_id WHERE e.event_type = 'Delivery' GROUP BY f.facility_type
```
Generated SQL:
```sql
SELECT f.facility_type,
 100.0 * SUM(CASE WHEN de.detention_minutes > 120 THEN 1 ELSE 0 END) / COUNT(*) AS pct_detention_over_2h
FROM delivery_events de
JOIN facilities f ON de.facility_id = f.facility_id
GROUP BY f.facility_type
ORDER BY pct_detention_over_2h DESC;
```
stage=completed status=ok attempts=1 rows=4 (gold 4) seconds=4.39 replayed=False

## H12  graph3  run 1  ->  wrong_result:wrong_or_missing_column

Question: Using all maintenance records and all trips, which truck make has the highest maintenance cost per 1,000 miles driven, and what is that cost?

Reference SQL:
```sql
WITH m AS (SELECT truck_id, SUM(total_cost) AS maint FROM maintenance_records GROUP BY truck_id), d AS (SELECT truck_id, SUM(actual_distance_miles) AS miles FROM trips WHERE truck_id IS NOT NULL GROUP BY truck_id) SELECT t.make, 1000.0 * SUM(m.maint) / SUM(d.miles) AS cost_per_1000_miles FROM trucks t LEFT JOIN m ON t.truck_id = m.truck_id LEFT JOIN d ON t.truck_id = d.truck_id GROUP BY t.make ORDER BY cost_per_1000_miles DESC LIMIT 1
```
Generated SQL:
```sql
WITH maint AS (
 SELECT truck_id,
 SUM(total_cost) AS total_maint_cost
 FROM maintenance_records
 GROUP BY truck_id
), drv AS (
 SELECT truck_id,
 SUM(actual_distance_miles) AS total_miles
 FROM trips
 GROUP BY truck_id
), combined AS (
 SELECT m.truck_id,
 m.total_maint_cost,
 d.total_miles
 FROM maint m
 JOIN drv d USING (truck_id)
), make_agg AS (
 SELECT t.make,
 SUM(c.total_maint_cost) AS make_maint_cost,
 SUM(c.total_miles) AS make_miles
 FROM combined c
 JOIN trucks t ON c.truck_id = t.truck_id
 GROUP BY t.make
)
SELECT make,
 (make_maint_cost / NULLIF(make_miles,0) * 1000) AS maintenance_cost_per_1000_miles
FROM make_agg
ORDER BY maintenance_cost_per_1000_miles DESC
LIMIT 1;
```
stage=completed status=ok attempts=1 rows=1 (gold 1) seconds=1.25 replayed=False
notes: ['The bar chart has a single bar.']

## H10  graph3  run 1  ->  wrong_result:empty_result

Question: Considering deliveries only (not pickups), which 3 facilities (by facility ID) have the lowest on-time rate among facilities with at least 1,000 deliveries, and what is each rate as a percentage?

Reference SQL:
```sql
SELECT facility_id, 100.0 * AVG(CASE WHEN on_time_flag THEN 1 ELSE 0 END) AS on_time_pct FROM delivery_events WHERE event_type = 'Delivery' GROUP BY facility_id HAVING COUNT(*) >= 1000 ORDER BY on_time_pct ASC LIMIT 3
```
Generated SQL:
```sql
SELECT de.facility_id,
 (SUM(CASE WHEN de.on_time_flag THEN 1 ELSE 0 END)::FLOAT / COUNT(*)) * 100 AS on_time_rate_percentage
FROM delivery_events de
WHERE de.event_type = 'delivery'
GROUP BY de.facility_id
HAVING COUNT(*) >= 1000
ORDER BY on_time_rate_percentage ASC
LIMIT 3;
```
stage=completed status=ok attempts=2 rows=0 (gold 3) seconds=7.98 replayed=False

## H05  graph3_rag  run 1  ->  wrong_result:wrong_or_missing_column

Question: What is our at-fault accident rate per million miles driven? Count collisions only, not violations or complaints.

Reference SQL:
```sql
SELECT 1000000.0 * (SELECT COUNT(*) FROM safety_incidents WHERE incident_type = 'Accident' AND at_fault_flag) / (SELECT SUM(actual_distance_miles) FROM trips) AS accidents_per_million_miles
```
Generated SQL:
```sql
SELECT (COUNT(*)::DOUBLE / NULLIF(SUM(t.actual_distance_miles),0)) * 1000000 AS at_fault_accident_rate_per_million_miles
FROM safety_incidents si
JOIN trips t ON si.trip_id = t.trip_id
WHERE si.at_fault_flag = TRUE;
```
stage=completed status=ok attempts=1 rows=1 (gold 1) seconds=6.33 replayed=True
notes: ['Retrieval may have hidden a table: asked again with the full schema.']

## H12  graph3_rag  run 1  ->  wrong_result:wrong_or_missing_column

Question: Using all maintenance records and all trips, which truck make has the highest maintenance cost per 1,000 miles driven, and what is that cost?

Reference SQL:
```sql
WITH m AS (SELECT truck_id, SUM(total_cost) AS maint FROM maintenance_records GROUP BY truck_id), d AS (SELECT truck_id, SUM(actual_distance_miles) AS miles FROM trips WHERE truck_id IS NOT NULL GROUP BY truck_id) SELECT t.make, 1000.0 * SUM(m.maint) / SUM(d.miles) AS cost_per_1000_miles FROM trucks t LEFT JOIN m ON t.truck_id = m.truck_id LEFT JOIN d ON t.truck_id = d.truck_id GROUP BY t.make ORDER BY cost_per_1000_miles DESC LIMIT 1
```
Generated SQL:
```sql
WITH maint AS (
 SELECT truck_id,
 SUM(total_cost) AS total_maint_cost
 FROM maintenance_records
 GROUP BY truck_id
), drv AS (
 SELECT truck_id,
 SUM(actual_distance_miles) AS total_miles
 FROM trips
 GROUP BY truck_id
), combined AS (
 SELECT m.truck_id,
 m.total_maint_cost,
 d.total_miles
 FROM maint m
 JOIN drv d USING (truck_id)
), make_agg AS (
 SELECT t.make,
 SUM(c.total_maint_cost) AS make_maint_cost,
 SUM(c.total_miles) AS make_miles
 FROM combined c
 JOIN trucks t ON c.truck_id = t.truck_id
 GROUP BY t.make
)
SELECT make,
 (make_maint_cost / NULLIF(make_miles,0) * 1000) AS maintenance_cost_per_1000_miles
FROM make_agg
ORDER BY maintenance_cost_per_1000_miles DESC
LIMIT 1;
```
stage=completed status=ok attempts=1 rows=1 (gold 1) seconds=7.19 replayed=True
notes: ['Retrieval may have hidden a table: asked again with the full schema.', 'The bar chart has a single bar.']

## P01  graph3_rag  run 1  ->  wrong_result:wrong_or_missing_column

Question: What's our top line?

Reference SQL:
```sql
SELECT SUM(revenue) AS revenue FROM loads
```
Generated SQL:
```sql
SELECT SUM(annual_revenue_potential) AS total_annual_revenue_potential FROM customers;
```
stage=completed status=ok attempts=3 rows=1 (gold 1) seconds=38.37 replayed=False
notes: ['Unresolved: The query ran, but its result does not answer the question properly:']

## U05  graph3_rag  run 1  ->  hallucinated_answer

Question: What percentage of our miles are driven empty (deadhead)?

Generated SQL:
```sql
SELECT (SUM(CASE WHEN load_id IS NULL THEN actual_distance_miles ELSE 0 END) * 100.0) / NULLIF(SUM(actual_distance_miles),0) AS deadhead_miles_percentage FROM trips;
```
stage=completed status=ok attempts=1 rows=1 (gold None) seconds=6.91 replayed=False
