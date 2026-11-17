# Inspection: hard

Cache information was not recorded in this run.

Outcomes: correct=57, correct_decline=20, failed:generation=14, failed:schema_validation=1, no_answer=10, wrong_decline=3, wrong_result:missing_columns=9

## H05  graph1  run 1  ->  wrong_result:missing_columns

Question: What is our at-fault accident rate per million miles driven?

Reference SQL:
```sql
SELECT 1000000.0 * (SELECT COUNT(*) FROM safety_incidents WHERE incident_type = 'Accident' AND at_fault_flag) / (SELECT SUM(actual_distance_miles) FROM trips) AS accidents_per_million_miles
```
Generated SQL:
```sql
WITH fault AS (
 SELECT COUNT(*) AS fault_count
 FROM safety_incidents
 WHERE at_fault_flag = true
), miles AS (
 SELECT SUM(actual_distance_miles) AS total_miles
 FROM trips
)
SELECT 
 (fault.fault_count / NULLIF(miles.total_miles,0)) * 1000000 AS at_fault_rate_per_million_miles
FROM fault, miles;
```
stage=completed status=ok attempts=1 rows=1 (gold 1) seconds=1.72 replayed=None

## H06  graph1  run 1  ->  wrong_result:missing_columns

Question: For each facility type, what percentage of deliveries had more than 2 hours of detention?

Reference SQL:
```sql
SELECT f.facility_type, 100.0 * AVG(CASE WHEN e.detention_minutes > 120 THEN 1 ELSE 0 END) AS pct_over_2h FROM delivery_events e JOIN facilities f ON e.facility_id = f.facility_id WHERE e.event_type = 'Delivery' GROUP BY f.facility_type
```
Generated SQL:
```sql
WITH total AS (
 SELECT f.facility_type,
 COUNT(*) AS total_deliveries
 FROM delivery_events d
 JOIN facilities f ON d.facility_id = f.facility_id
 GROUP BY f.facility_type
), delayed AS (
 SELECT f.facility_type,
 COUNT(*) AS delayed_deliveries
 FROM delivery_events d
 JOIN facilities f ON d.facility_id = f.facility_id
 WHERE d.detention_minutes > 120
 GROUP BY f.facility_type
)
SELECT t.facility_type,
 (COALESCE(d.delayed_deliveries, 0) * 100.0) / NULLIF(t.total_deliveries, 0) AS detention_percentage
FROM total t
LEFT JOIN delayed d USING (facility_type)
ORDER BY detention_percentage DESC;
```
stage=completed status=ok attempts=1 rows=4 (gold 4) seconds=3.89 replayed=None

## H12  graph1  run 1  ->  wrong_result:missing_columns

Question: Using all maintenance records and all trips, which truck make has the highest maintenance cost per 1,000 miles driven, and what is that cost?

Reference SQL:
```sql
WITH m AS (SELECT truck_id, SUM(total_cost) AS maint FROM maintenance_records GROUP BY truck_id), d AS (SELECT truck_id, SUM(actual_distance_miles) AS miles FROM trips WHERE truck_id IS NOT NULL GROUP BY truck_id) SELECT t.make, 1000.0 * SUM(m.maint) / SUM(d.miles) AS cost_per_1000_miles FROM trucks t LEFT JOIN m ON t.truck_id = m.truck_id LEFT JOIN d ON t.truck_id = d.truck_id GROUP BY t.make ORDER BY cost_per_1000_miles DESC LIMIT 1
```
Generated SQL:
```sql
WITH maint AS (
 SELECT truck_id, SUM(total_cost) AS total_maint_cost
 FROM maintenance_records
 GROUP BY truck_id
), drv AS (
 SELECT truck_id, SUM(actual_distance_miles) AS total_miles
 FROM trips
 GROUP BY truck_id
), truck_stats AS (
 SELECT m.truck_id,
 t.make,
 m.total_maint_cost,
 d.total_miles,
 CASE WHEN d.total_miles > 0 THEN m.total_maint_cost / (d.total_miles / 1000.0) ELSE NULL END AS maint_cost_per_1000_miles
 FROM maint m
 JOIN drv d ON m.truck_id = d.truck_id
 JOIN trucks t ON m.truck_id = t.truck_id
)
SELECT make,
 SUM(total_maint_cost) AS make_total_maint_cost,
 SUM(total_miles) AS make_total_miles,
 SUM(total_maint_cost) / (SUM(total_miles) / 1000.0) AS maint_cost_per_1000_miles
FROM truck_stats
GROUP BY make
ORDER BY maint_cost_per_1000_miles DESC
LIMIT 1;
```
stage=completed status=ok attempts=1 rows=1 (gold 1) seconds=4.16 replayed=None
notes: ['The bar chart has a single bar.']

## H09  graph1  run 1  ->  failed:schema_validation

Question: What percentage of total load revenue comes from our top 10 customers?

Reference SQL:
```sql
WITH r AS (SELECT customer_id, SUM(revenue) AS rev FROM loads GROUP BY customer_id ORDER BY rev DESC LIMIT 10) SELECT 100.0 * SUM(rev) / (SELECT SUM(revenue) FROM loads) AS top10_pct FROM r
```
Generated SQL:
```sql
WITH customer_revenue AS (
 SELECT l.customer_id, SUM(l.revenue) AS total_revenue
 FROM loads l
 GROUP BY l.customer_id
), top_customers AS (
 SELECT cr.customer_id, cr.total_revenue
 FROM customer_revenue cr
 ORDER BY cr.total_revenue DESC
 LIMIT 10
), total_rev AS (
 SELECT SUM(l.revenue) AS overall_revenue
 FROM loads l
)
SELECT SUM(tc.total_revenue) / NULLIF(tr.overall_revenue,0) * 100 AS top_10_customers_percentage
FROM top_customers tc, total_rev tr;
```
stage=schema_validation status=ok attempts=1 rows=None (gold 1) seconds=5.81 replayed=None
error/reason: Query rejected because of schema incompatibility.

## H10  graph1  run 1  ->  wrong_result:missing_columns

Question: Which 3 facilities (by facility ID) have the lowest on-time delivery rate, among facilities with at least 1,000 delivery events, and what is each rate as a percentage?

Reference SQL:
```sql
SELECT facility_id, 100.0 * AVG(CASE WHEN on_time_flag THEN 1 ELSE 0 END) AS on_time_pct FROM delivery_events WHERE event_type = 'Delivery' GROUP BY facility_id HAVING COUNT(*) >= 1000 ORDER BY on_time_pct ASC LIMIT 3
```
Generated SQL:
```sql
SELECT de.facility_id,
 100.0 * SUM(CASE WHEN de.on_time_flag THEN 1 ELSE 0 END) / COUNT(*) AS on_time_rate_percent
FROM delivery_events de
GROUP BY de.facility_id
HAVING COUNT(*) >= 1000
ORDER BY on_time_rate_percent ASC
LIMIT 3;
```
stage=completed status=ok attempts=1 rows=3 (gold 3) seconds=3.71 replayed=None
notes: ['Unresolved: The query ran, but its result does not answer the question properly:']

## H05  graph3  run 1  ->  wrong_result:missing_columns

Question: What is our at-fault accident rate per million miles driven?

Reference SQL:
```sql
SELECT 1000000.0 * (SELECT COUNT(*) FROM safety_incidents WHERE incident_type = 'Accident' AND at_fault_flag) / (SELECT SUM(actual_distance_miles) FROM trips) AS accidents_per_million_miles
```
Generated SQL:
```sql
WITH miles AS (
 SELECT SUM(actual_distance_miles) AS total_miles
 FROM trips
), faults AS (
 SELECT COUNT(*) AS fault_count
 FROM safety_incidents
 WHERE at_fault_flag = true
)
SELECT (faults.fault_count / NULLIF(miles.total_miles,0)) * 1000000 AS at_fault_rate_per_million_miles
FROM faults, miles;
```
stage=completed status=ok attempts=1 rows=1 (gold 1) seconds=2.67 replayed=None

## H06  graph3  run 1  ->  wrong_result:missing_columns

Question: For each facility type, what percentage of deliveries had more than 2 hours of detention?

Reference SQL:
```sql
SELECT f.facility_type, 100.0 * AVG(CASE WHEN e.detention_minutes > 120 THEN 1 ELSE 0 END) AS pct_over_2h FROM delivery_events e JOIN facilities f ON e.facility_id = f.facility_id WHERE e.event_type = 'Delivery' GROUP BY f.facility_type
```
Generated SQL:
```sql
WITH total AS (
 SELECT f.facility_type,
 COUNT(*) AS total_deliveries
 FROM delivery_events d
 JOIN facilities f ON d.facility_id = f.facility_id
 GROUP BY f.facility_type
), delayed AS (
 SELECT f.facility_type,
 COUNT(*) AS delayed_deliveries
 FROM delivery_events d
 JOIN facilities f ON d.facility_id = f.facility_id
 WHERE d.detention_minutes > 120
 GROUP BY f.facility_type
)
SELECT t.facility_type,
 (COALESCE(d.delayed_deliveries, 0) * 100.0) / NULLIF(t.total_deliveries, 0) AS detention_percentage
FROM total t
LEFT JOIN delayed d USING (facility_type)
ORDER BY detention_percentage DESC;
```
stage=completed status=ok attempts=1 rows=4 (gold 4) seconds=3.85 replayed=None

## H12  graph3  run 1  ->  wrong_result:missing_columns

Question: Using all maintenance records and all trips, which truck make has the highest maintenance cost per 1,000 miles driven, and what is that cost?

Reference SQL:
```sql
WITH m AS (SELECT truck_id, SUM(total_cost) AS maint FROM maintenance_records GROUP BY truck_id), d AS (SELECT truck_id, SUM(actual_distance_miles) AS miles FROM trips WHERE truck_id IS NOT NULL GROUP BY truck_id) SELECT t.make, 1000.0 * SUM(m.maint) / SUM(d.miles) AS cost_per_1000_miles FROM trucks t LEFT JOIN m ON t.truck_id = m.truck_id LEFT JOIN d ON t.truck_id = d.truck_id GROUP BY t.make ORDER BY cost_per_1000_miles DESC LIMIT 1
```
Generated SQL:
```sql
WITH maint AS (
 SELECT truck_id, SUM(total_cost) AS total_maint_cost
 FROM maintenance_records
 GROUP BY truck_id
), drv AS (
 SELECT truck_id, SUM(actual_distance_miles) AS total_miles
 FROM trips
 GROUP BY truck_id
), truck_stats AS (
 SELECT m.truck_id,
 t.make,
 m.total_maint_cost,
 d.total_miles,
 CASE WHEN d.total_miles > 0 THEN m.total_maint_cost / (d.total_miles / 1000.0) ELSE NULL END AS maint_cost_per_1000_miles
 FROM maint m
 JOIN drv d ON m.truck_id = d.truck_id
 JOIN trucks t ON m.truck_id = t.truck_id
)
SELECT make,
 SUM(total_maint_cost) AS make_total_maint_cost,
 SUM(total_miles) AS make_total_miles,
 SUM(total_maint_cost) / (SUM(total_miles) / 1000.0) AS maint_cost_per_1000_miles
FROM truck_stats
GROUP BY make
ORDER BY maint_cost_per_1000_miles DESC
LIMIT 1;
```
stage=completed status=ok attempts=1 rows=1 (gold 1) seconds=3.11 replayed=None
notes: ['The bar chart has a single bar.']

## H10  graph3  run 1  ->  wrong_result:missing_columns

Question: Which 3 facilities (by facility ID) have the lowest on-time delivery rate, among facilities with at least 1,000 delivery events, and what is each rate as a percentage?

Reference SQL:
```sql
SELECT facility_id, 100.0 * AVG(CASE WHEN on_time_flag THEN 1 ELSE 0 END) AS on_time_pct FROM delivery_events WHERE event_type = 'Delivery' GROUP BY facility_id HAVING COUNT(*) >= 1000 ORDER BY on_time_pct ASC LIMIT 3
```
Generated SQL:
```sql
SELECT de.facility_id,
 f.facility_name,
 100.0 * SUM(CASE WHEN de.on_time_flag THEN 1 ELSE 0 END) / COUNT(*) AS on_time_rate_percent
FROM delivery_events de
JOIN facilities f ON de.facility_id = f.facility_id
GROUP BY de.facility_id, f.facility_name
HAVING COUNT(*) >= 1000
ORDER BY on_time_rate_percent ASC
LIMIT 3;
```
stage=completed status=ok attempts=2 rows=3 (gold 3) seconds=10.4 replayed=None

## Q17  graph3_rag  run 1  ->  wrong_decline

Question: What is the total claim amount of safety incidents for each customer type?

Reference SQL:
```sql
SELECT c.customer_type, SUM(s.claim_amount) AS claims FROM safety_incidents s JOIN trips t ON s.trip_id = t.trip_id JOIN loads l ON t.load_id = l.load_id JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type
```
Generated SQL:
```sql
None
```
stage=unsupported status=unsupported attempts=1 rows=None (gold 3) seconds=14.85 replayed=None
error/reason: the schema has no customer or customer type information

## H01  graph3_rag  run 1  ->  wrong_result:missing_columns

Question: What is the revenue per mile for each customer type?

Reference SQL:
```sql
SELECT c.customer_type, SUM(l.revenue) / SUM(t.actual_distance_miles) AS revenue_per_mile FROM trips t JOIN loads l ON t.load_id = l.load_id JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type
```
Generated SQL:
```sql
SELECT c.customer_type,
 SUM(l.revenue) AS total_revenue,
 SUM(r.typical_distance_miles) AS total_miles,
 SUM(l.revenue) / NULLIF(SUM(r.typical_distance_miles), 0) AS revenue_per_mile
FROM loads l
JOIN routes r ON l.route_id = r.route_id
JOIN customers c ON l.customer_id = c.customer_id
GROUP BY c.customer_type
ORDER BY revenue_per_mile DESC;
```
stage=completed status=ok attempts=1 rows=3 (gold 3) seconds=8.23 replayed=None

## H02  graph3_rag  run 1  ->  wrong_decline

Question: What is the fleet's overall miles per gallon?

Reference SQL:
```sql
SELECT SUM(actual_distance_miles) / SUM(fuel_gallons_used) AS mpg FROM trips
```
Generated SQL:
```sql
None
```
stage=unsupported status=unsupported attempts=1 rows=None (gold 1) seconds=9.85 replayed=None
error/reason: the schema has no mileage or miles driven data to calculate miles per gallon

## H05  graph3_rag  run 1  ->  wrong_decline

Question: What is our at-fault accident rate per million miles driven?

Reference SQL:
```sql
SELECT 1000000.0 * (SELECT COUNT(*) FROM safety_incidents WHERE incident_type = 'Accident' AND at_fault_flag) / (SELECT SUM(actual_distance_miles) FROM trips) AS accidents_per_million_miles
```
Generated SQL:
```sql
None
```
stage=unsupported status=unsupported attempts=1 rows=None (gold 1) seconds=86.18 replayed=None
error/reason: the schema does not contain total miles driven data to calculate rate per million miles

## H06  graph3_rag  run 1  ->  failed:generation

Question: For each facility type, what percentage of deliveries had more than 2 hours of detention?

Reference SQL:
```sql
SELECT f.facility_type, 100.0 * AVG(CASE WHEN e.detention_minutes > 120 THEN 1 ELSE 0 END) AS pct_over_2h FROM delivery_events e JOIN facilities f ON e.facility_id = f.facility_id WHERE e.event_type = 'Delivery' GROUP BY f.facility_type
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 4) seconds=0.3 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198406, Requested 3051. Please try again in 10m29.424s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## H07  graph3_rag  run 1  ->  failed:generation

Question: What is our driver turnover rate, as a percentage?

Reference SQL:
```sql
SELECT 100.0 * AVG(CASE WHEN employment_status = 'Terminated' THEN 1 ELSE 0 END) AS turnover_pct FROM drivers
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 1) seconds=0.23 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198405, Requested 2372. Please try again in 5m35.664s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## H08  graph3_rag  run 1  ->  failed:generation

Question: What is the average age in years of the active trucks as of 31 December 2024, using the model year?

Reference SQL:
```sql
SELECT AVG(2024 - model_year) AS avg_age FROM trucks WHERE status = 'Active'
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 1) seconds=0.21 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198405, Requested 2796. Please try again in 8m38.832s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## H13  graph3_rag  run 1  ->  failed:generation

Question: What share of total trip duration is idle time, as a percentage?

Reference SQL:
```sql
SELECT 100.0 * SUM(idle_time_hours) / SUM(actual_duration_hours) AS idle_pct FROM trips
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 1) seconds=0.36 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198404, Requested 3016. Please try again in 10m13.44s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## H03  graph3_rag  run 1  ->  failed:generation

Question: Considering only trips that have at least one fuel purchase, what is the fuel cost per mile driven for each customer type?

Reference SQL:
```sql
WITH f AS (SELECT trip_id, SUM(total_cost) AS fuel_cost FROM fuel_purchases GROUP BY trip_id) SELECT c.customer_type, SUM(f.fuel_cost) / SUM(t.actual_distance_miles) AS fuel_cost_per_mile FROM f JOIN trips t ON f.trip_id = t.trip_id JOIN loads l ON t.load_id = l.load_id JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 3) seconds=0.27 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198403, Requested 2636. Please try again in 7m28.848s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## H12  graph3_rag  run 1  ->  failed:generation

Question: Using all maintenance records and all trips, which truck make has the highest maintenance cost per 1,000 miles driven, and what is that cost?

Reference SQL:
```sql
WITH m AS (SELECT truck_id, SUM(total_cost) AS maint FROM maintenance_records GROUP BY truck_id), d AS (SELECT truck_id, SUM(actual_distance_miles) AS miles FROM trips WHERE truck_id IS NOT NULL GROUP BY truck_id) SELECT t.make, 1000.0 * SUM(m.maint) / SUM(d.miles) AS cost_per_1000_miles FROM trucks t LEFT JOIN m ON t.truck_id = m.truck_id LEFT JOIN d ON t.truck_id = d.truck_id GROUP BY t.make ORDER BY cost_per_1000_miles DESC LIMIT 1
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 1) seconds=0.4 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198402, Requested 2476. Please try again in 6m19.296s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## H09  graph3_rag  run 1  ->  failed:generation

Question: What percentage of total load revenue comes from our top 10 customers?

Reference SQL:
```sql
WITH r AS (SELECT customer_id, SUM(revenue) AS rev FROM loads GROUP BY customer_id ORDER BY rev DESC LIMIT 10) SELECT 100.0 * SUM(rev) / (SELECT SUM(revenue) FROM loads) AS top10_pct FROM r
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 1) seconds=0.22 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198402, Requested 2217. Please try again in 4m27.408s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## H10  graph3_rag  run 1  ->  failed:generation

Question: Which 3 facilities (by facility ID) have the lowest on-time delivery rate, among facilities with at least 1,000 delivery events, and what is each rate as a percentage?

Reference SQL:
```sql
SELECT facility_id, 100.0 * AVG(CASE WHEN on_time_flag THEN 1 ELSE 0 END) AS on_time_pct FROM delivery_events WHERE event_type = 'Delivery' GROUP BY facility_id HAVING COUNT(*) >= 1000 ORDER BY on_time_pct ASC LIMIT 3
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 3) seconds=0.2 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198401, Requested 2256. Please try again in 4m43.824s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## H11  graph3_rag  run 1  ->  failed:generation

Question: What was the year-over-year revenue growth, as a percentage, for 2023 and for 2024, based on the load date?

Reference SQL:
```sql
SELECT * FROM (SELECT year, 100.0 * (rev - LAG(rev) OVER (ORDER BY year)) / LAG(rev) OVER (ORDER BY year) AS growth_pct FROM (SELECT EXTRACT(year FROM load_date) AS year, SUM(revenue) AS rev FROM loads GROUP BY 1) y) z WHERE year >= 2023 ORDER BY year
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 2) seconds=0.19 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198401, Requested 2232. Please try again in 4m33.455999999s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## H14  graph3_rag  run 1  ->  failed:generation

Question: How many drivers have been involved in two or more safety incidents?

Reference SQL:
```sql
SELECT COUNT(*) AS drivers FROM (SELECT driver_id FROM safety_incidents WHERE driver_id IS NOT NULL GROUP BY driver_id HAVING COUNT(*) >= 2) q
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 1) seconds=0.16 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198400, Requested 2591. Please try again in 7m8.112s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## H15  graph3_rag  run 1  ->  failed:generation

Question: What is the average tenure in days of the drivers who have left the company?

Reference SQL:
```sql
SELECT AVG(DATE_DIFF('day', hire_date, CAST(termination_date AS DATE))) AS avg_tenure_days FROM drivers WHERE termination_date IS NOT NULL
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 1) seconds=0.16 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198400, Requested 2483. Please try again in 6m21.455999999s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## P01  graph3_rag  run 1  ->  failed:generation

Question: What's our top line?

Reference SQL:
```sql
SELECT SUM(revenue) AS revenue FROM loads
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 1) seconds=0.18 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198400, Requested 2183. Please try again in 4m11.856s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## P02  graph3_rag  run 1  ->  failed:generation

Question: How many drivers do we currently employ?

Reference SQL:
```sql
SELECT COUNT(*) AS drivers FROM drivers WHERE employment_status = 'Active'
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 1) seconds=0.19 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198399, Requested 2386. Please try again in 5m39.119999999s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## P03  graph3_rag  run 1  ->  failed:generation

Question: Which month was our best for revenue, and how much did we make?

Reference SQL:
```sql
SELECT date_trunc('month', load_date) AS month, SUM(revenue) AS revenue FROM loads GROUP BY 1 ORDER BY revenue DESC LIMIT 1
```
Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold 1) seconds=0.24 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198398, Requested 2760. Please try again in 8m20.256s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## U01  graph3_rag  run 1  ->  no_answer

Question: What is the average driver satisfaction score per month?

Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold None) seconds=0.2 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198398, Requested 2235. Please try again in 4m33.455999999s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## U02  graph3_rag  run 1  ->  no_answer

Question: Which drivers have the highest customer ratings?

Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold None) seconds=0.21 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198397, Requested 2386. Please try again in 5m38.256s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## U03  graph3_rag  run 1  ->  no_answer

Question: How much do weather conditions affect delivery delays?

Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold None) seconds=0.17 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198397, Requested 3041. Please try again in 10m21.216s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## U04  graph3_rag  run 1  ->  no_answer

Question: What is the total salary cost per driver?

Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold None) seconds=0.27 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198396, Requested 2504. Please try again in 6m28.799999999s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## U05  graph3_rag  run 1  ->  no_answer

Question: What percentage of our miles are driven empty (deadhead)?

Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold None) seconds=0.21 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198396, Requested 3149. Please try again in 11m7.44s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## U06  graph3_rag  run 1  ->  no_answer

Question: How many hours-of-service violations did each driver have?

Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold None) seconds=0.22 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198395, Requested 2453. Please try again in 6m6.336s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## B01  graph3_rag  run 1  ->  no_answer

Question: Delete all trips older than 2024 and show the number of remaining trips.

Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold None) seconds=0.21 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198395, Requested 3048. Please try again in 10m23.376s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## B02  graph3_rag  run 1  ->  no_answer

Question: Update the status of every truck to Active.

Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold None) seconds=0.19 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198394, Requested 2319. Please try again in 5m8.016s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## B03  graph3_rag  run 1  ->  no_answer

Question: Drop the customers table.

Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold None) seconds=0.21 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198394, Requested 2844. Please try again in 8m54.816s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}

## B04  graph3_rag  run 1  ->  no_answer

Question: Export all drivers to a CSV file at C:/temp/drivers.csv.

Generated SQL:
```sql
None
```
stage=generation status=ok attempts=1 rows=None (gold None) seconds=0.21 replayed=None
error/reason: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kt2m3bpees2a48713bc38gxb` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198393, Requested 2529. Please try again in 6m38.304s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}
