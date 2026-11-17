# Verification report

38/38 questions pass the automatic checks.

## Q01  [OK]  (answer)

How many trips are there in total?

```sql
SELECT COUNT(*) AS n FROM trips
```


Gold result (first rows):
```
    n
85410
```
pandas result (first rows):
```
    n
85410
```

## Q04  [OK]  (answer)

How many safety incidents are there for each incident type?

```sql
SELECT incident_type, COUNT(*) AS incidents FROM safety_incidents GROUP BY incident_type
```


Gold result (first rows):
```
     incident_type  incidents
  Moving Violation         27
Customer Complaint         34
  Equipment Damage         35
     DOT Violation         39
          Accident         35
```
pandas result (first rows):
```
     incident_type  0
          Accident 35
Customer Complaint 34
     DOT Violation 39
  Equipment Damage 35
  Moving Violation 27
```

## Q07  [OK]  (answer)

What is the total revenue per month, based on the load date?

```sql
SELECT date_trunc('month', load_date) AS month, SUM(revenue) AS revenue FROM loads GROUP BY 1 ORDER BY 1
```


Gold result (first rows):
```
     month    revenue
2022-01-01 7566361.99
2022-02-01 6574259.06
2022-03-01 7401197.05
2022-04-01 7156041.22
2022-05-01 7518061.33
2022-06-01 7325637.69
```
pandas result (first rows):
```
 load_date    revenue
2022-01-01 7566361.99
2022-02-01 6574259.06
2022-03-01 7401197.05
2022-04-01 7156041.22
2022-05-01 7518061.33
2022-06-01 7325637.69
```

## Q11  [OK]  (answer)

What is the total load revenue for each customer type?

```sql
SELECT c.customer_type, SUM(l.revenue) AS revenue FROM loads l JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type
```


Gold result (first rows):
```
customer_type      revenue
         Spot 8.285196e+07
    Dedicated 8.087863e+07
     Contract 9.879521e+07
```
pandas result (first rows):
```
customer_type     revenue
     Contract 98795209.72
    Dedicated 80878634.21
         Spot 82851956.36
```

## Q13  [OK]  (answer)

Which 5 drivers (by driver ID) completed the most trips, and how many trips did each complete? Ignore trips without a driver.

```sql
SELECT driver_id, COUNT(*) AS trips FROM trips WHERE driver_id IS NOT NULL GROUP BY driver_id ORDER BY trips DESC, driver_id LIMIT 5
```


Gold result (first rows):
```
driver_id  trips
 DRV00019    749
 DRV00066    737
 DRV00108    735
 DRV00059    729
 DRV00087    725
```
pandas result (first rows):
```
driver_id  trips
 DRV00019    749
 DRV00066    737
 DRV00108    735
 DRV00059    729
 DRV00087    725
```

## Q17  [OK]  (answer)

What is the total claim amount of safety incidents for each customer type?

```sql
SELECT c.customer_type, SUM(s.claim_amount) AS claims FROM safety_incidents s JOIN trips t ON s.trip_id = t.trip_id JOIN loads l ON t.load_id = l.load_id JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type
```


Gold result (first rows):
```
customer_type     claims
         Spot  778041.50
    Dedicated  735904.05
     Contract 1139226.27
```
pandas result (first rows):
```
customer_type  claim_amount
     Contract    1139226.27
    Dedicated     735904.05
         Spot     778041.50
```

## Q18  [OK]  (answer)

What percentage of delivery events were on time? Give a number between 0 and 100.

```sql
SELECT 100.0 * AVG(CASE WHEN on_time_flag THEN 1 ELSE 0 END) AS on_time_pct FROM delivery_events
```


Gold result (first rows):
```
 on_time_pct
   55.669711
```
pandas result (first rows):
```
        p
55.669711
```

## Q19  [OK]  (answer)

What is the total revenue divided by the total actual distance in miles across all trips?

```sql
SELECT SUM(l.revenue) / SUM(t.actual_distance_miles) AS revenue_per_mile FROM trips t JOIN loads l ON t.load_id = l.load_id
```


Gold result (first rows):
```
 revenue_per_mile
         2.149046
```
pandas result (first rows):
```
       r
2.149046
```

## Q22  [OK]  (answer)

What is the total fuel cost for purchases made in 2023?

```sql
SELECT SUM(total_cost) AS fuel_cost FROM fuel_purchases WHERE purchase_date >= DATE '2023-01-01' AND purchase_date < DATE '2024-01-01'
```


Gold result (first rows):
```
  fuel_cost
31073119.57
```
pandas result (first rows):
```
          s
31073119.57
```

## Q25  [OK]  (answer)

What is the average actual trip duration in hours for each customer type?

```sql
SELECT c.customer_type, AVG(t.actual_duration_hours) AS avg_hours FROM trips t JOIN loads l ON t.load_id = l.load_id JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type
```


Gold result (first rows):
```
customer_type  avg_hours
         Spot  25.081755
    Dedicated  24.964878
     Contract  24.999472
```
pandas result (first rows):
```
customer_type  actual_duration_hours
     Contract              24.999472
    Dedicated              24.964878
         Spot              25.081755
```

## H01  [OK]  (answer)

What is the revenue per mile for each customer type?

```sql
SELECT c.customer_type, SUM(l.revenue) / SUM(t.actual_distance_miles) AS revenue_per_mile FROM trips t JOIN loads l ON t.load_id = l.load_id JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type
```

Definition used: Revenue per mile = total revenue / total miles driven (ratio of sums, not mean of ratios).

Gold result (first rows):
```
customer_type  revenue_per_mile
     Contract          2.146276
         Spot          2.150265
    Dedicated          2.151189
```
pandas result (first rows):
```
customer_type        0
     Contract 2.146276
    Dedicated 2.151189
         Spot 2.150265
```

## H02  [OK]  (answer)

What is the fleet's overall miles per gallon?

```sql
SELECT SUM(actual_distance_miles) / SUM(fuel_gallons_used) AS mpg FROM trips
```

Definition used: Fleet MPG = total miles / total gallons used (weighted), not the mean of the per-trip mpg.

Gold result (first rows):
```
     mpg
6.447662
```
pandas result (first rows):
```
       m
6.447662
```
Result of the tempting wrong query (must differ from the gold):
```
     mpg
6.501463
```

## H04  [OK]  (answer)

What are safety claims as a percentage of load revenue for each customer type?

```sql
WITH rev AS (SELECT c.customer_type, SUM(l.revenue) AS revenue FROM loads l JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type), cl AS (SELECT c.customer_type, SUM(s.claim_amount) AS claims FROM safety_incidents s JOIN trips t ON s.trip_id = t.trip_id JOIN loads l ON t.load_id = l.load_id JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type) SELECT rev.customer_type, 100.0 * COALESCE(cl.claims, 0) / rev.revenue AS claims_pct FROM rev LEFT JOIN cl ON rev.customer_type = cl.customer_type
```

Definition used: Claims ratio = claims / ALL revenue of the group. Revenue must be summed over every load, not only over loads that had an incident.

Gold result (first rows):
```
customer_type  claims_pct
         Spot    0.939074
    Dedicated    0.909887
     Contract    1.153119
```
pandas result (first rows):
```
customer_type        0
     Contract 1.153119
    Dedicated 0.909887
         Spot 0.939074
```
Result of the tempting wrong query (must differ from the gold):
```
customer_type  claims_pct
         Spot  398.759698
    Dedicated  455.591496
     Contract  548.464614
```

## H05  [OK]  (answer)

What is our at-fault accident rate per million miles driven? Count collisions only, not violations or complaints.

```sql
SELECT 1000000.0 * (SELECT COUNT(*) FROM safety_incidents WHERE incident_type = 'Accident' AND at_fault_flag) / (SELECT SUM(actual_distance_miles) FROM trips) AS accidents_per_million_miles
```

Definition used: Safety rate per million miles = at-fault ACCIDENTS (question reworded after the first run: the model counted every at-fault incident) (incident_type 'Accident') / total miles x 1,000,000.

Gold result (first rows):
```
 accidents_per_million_miles
                    0.065488
```
pandas result (first rows):
```
       r
0.065488
```
Result of the tempting wrong query (must differ from the gold):
```
       r
1.391627
```

## H06  [OK]  (answer)

For each facility type, what percentage of deliveries had more than 2 hours of detention?

```sql
SELECT f.facility_type, 100.0 * AVG(CASE WHEN e.detention_minutes > 120 THEN 1 ELSE 0 END) AS pct_over_2h FROM delivery_events e JOIN facilities f ON e.facility_id = f.facility_id WHERE e.event_type = 'Delivery' GROUP BY f.facility_type
```

Definition used: Detention is measured in minutes; 2 hours = 120 minutes. Only Delivery events (not Pickup).

Gold result (first rows):
```
      facility_type  pct_over_2h
          Warehouse    43.948887
         Cross-Dock    44.200298
           Terminal    44.794824
Distribution Center    44.351407
```
pandas result (first rows):
```
      facility_type  detention_minutes
         Cross-Dock          44.200298
Distribution Center          44.351407
           Terminal          44.794824
          Warehouse          43.948887
```

## H07  [OK]  (answer)

What is our driver turnover rate, as a percentage?

```sql
SELECT 100.0 * AVG(CASE WHEN employment_status = 'Terminated' THEN 1 ELSE 0 END) AS turnover_pct FROM drivers
```

Definition used: Cumulative turnover = drivers who left / all drivers on record. Not annualised: the termination dates span many years, so an annual rate over average headcount would need a period the question does not give.

Gold result (first rows):
```
 turnover_pct
    17.333333
```
pandas result (first rows):
```
        t
17.333333
```

## H08  [OK]  (answer)

What is the average age in years of the active trucks as of 31 December 2024, using the model year?

```sql
SELECT AVG(2024 - model_year) AS avg_age FROM trucks WHERE status = 'Active'
```

Definition used: Age = 2024 - model_year, for trucks whose status is Active. 2024 is the end of the data period, not the current year: a result must not change with the date the question is asked (reproducibility).

Gold result (first rows):
```
 avg_age
8.097826
```
pandas result (first rows):
```
       a
8.097826
```

## H13  [OK]  (answer)

What share of total trip duration is idle time, as a percentage?

```sql
SELECT 100.0 * SUM(idle_time_hours) / SUM(actual_duration_hours) AS idle_pct FROM trips
```

Definition used: Idle share = total idle hours / total trip hours (ratio of sums).

Gold result (first rows):
```
 idle_pct
28.026683
```
pandas result (first rows):
```
        i
28.026683
```

## H03  [OK]  (answer)

Considering only trips that have at least one fuel purchase, what is the fuel cost per mile driven for each customer type?

```sql
WITH f AS (SELECT trip_id, SUM(total_cost) AS fuel_cost FROM fuel_purchases GROUP BY trip_id) SELECT c.customer_type, SUM(f.fuel_cost) / SUM(t.actual_distance_miles) AS fuel_cost_per_mile FROM f JOIN trips t ON f.trip_id = t.trip_id JOIN loads l ON t.load_id = l.load_id JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type
```

Definition used: Fuel purchases are summed per trip BEFORE joining; joining trips to purchases directly repeats each trip's miles once per purchase.

Gold result (first rows):
```
customer_type  fuel_cost_per_mile
         Spot            0.871132
    Dedicated            0.869195
     Contract            0.867404
```
pandas result (first rows):
```
customer_type        0
     Contract 0.867404
    Dedicated 0.869195
         Spot 0.871132
```
Result of the tempting wrong query (must differ from the gold):
```
customer_type        x
         Spot 0.338476
    Dedicated 0.341811
     Contract 0.340182
```

## H12  [OK]  (answer)

Using all maintenance records and all trips, which truck make has the highest maintenance cost per 1,000 miles driven, and what is that cost?

```sql
WITH m AS (SELECT truck_id, SUM(total_cost) AS maint FROM maintenance_records GROUP BY truck_id), d AS (SELECT truck_id, SUM(actual_distance_miles) AS miles FROM trips WHERE truck_id IS NOT NULL GROUP BY truck_id) SELECT t.make, 1000.0 * SUM(m.maint) / SUM(d.miles) AS cost_per_1000_miles FROM trucks t LEFT JOIN m ON t.truck_id = m.truck_id LEFT JOIN d ON t.truck_id = d.truck_id GROUP BY t.make ORDER BY cost_per_1000_miles DESC LIMIT 1
```

Definition used: Maintenance and miles are aggregated per truck separately and then combined per make (two one-to-many tables must not be joined directly).

Gold result (first rows):
```
        make  cost_per_1000_miles
Freightliner            56.964236
```
pandas result (first rows):
```
        make         0
Freightliner 56.964236
```
Result of the tempting wrong query (must differ from the gold):
```
         make           x
International 1419.408308
```

## H09  [OK]  (answer)

What percentage of total load revenue comes from our top 10 customers?

```sql
WITH r AS (SELECT customer_id, SUM(revenue) AS rev FROM loads GROUP BY customer_id ORDER BY rev DESC LIMIT 10) SELECT 100.0 * SUM(rev) / (SELECT SUM(revenue) FROM loads) AS top10_pct FROM r
```

Definition used: Customer concentration = revenue of the 10 largest customers (by customer ID) / total revenue.

Gold result (first rows):
```
 top10_pct
  5.698972
```
pandas result (first rows):
```
       p
5.698972
```

## H10  [OK]  (answer)

Considering deliveries only (not pickups), which 3 facilities (by facility ID) have the lowest on-time rate among facilities with at least 1,000 deliveries, and what is each rate as a percentage?

```sql
SELECT facility_id, 100.0 * AVG(CASE WHEN on_time_flag THEN 1 ELSE 0 END) AS on_time_pct FROM delivery_events WHERE event_type = 'Delivery' GROUP BY facility_id HAVING COUNT(*) >= 1000 ORDER BY on_time_pct ASC LIMIT 3
```

Definition used: On-time rate over Delivery events only; the 1,000 minimum is applied to Delivery events. (Reworded after the first run: "delivery events" is also the table name, which includes pickups.)

Gold result (first rows):
```
facility_id  on_time_pct
   FAC00048    41.916859
   FAC00034    41.926182
   FAC00011    42.312139
```
pandas result (first rows):
```
facility_id      mean
   FAC00048 41.916859
   FAC00034 41.926182
   FAC00011 42.312139
```

## H11  [OK]  (answer)

What was the year-over-year revenue growth, as a percentage, for 2023 and for 2024, based on the load date?

```sql
SELECT * FROM (SELECT year, 100.0 * (rev - LAG(rev) OVER (ORDER BY year)) / LAG(rev) OVER (ORDER BY year) AS growth_pct FROM (SELECT EXTRACT(year FROM load_date) AS year, SUM(revenue) AS rev FROM loads GROUP BY 1) y) z WHERE year >= 2023 ORDER BY year
```

Definition used: YoY growth = (revenue this year - last year) / last year x 100.

Gold result (first rows):
```
 year  growth_pct
 2023   -1.019170
 2024    0.878381
```
pandas result (first rows):
```
 load_date   revenue
      2023 -1.019170
      2024  0.878381
```

## H14  [OK]  (answer)

How many drivers have been involved in two or more safety incidents?

```sql
SELECT COUNT(*) AS drivers FROM (SELECT driver_id FROM safety_incidents WHERE driver_id IS NOT NULL GROUP BY driver_id HAVING COUNT(*) >= 2) q
```

Definition used: Aggregation of an aggregation; incidents without a driver are not attributable to anyone.

Gold result (first rows):
```
 drivers
      52
```
pandas result (first rows):
```
 n
52
```

## H15  [OK]  (answer)

What is the average tenure in days of the drivers who have left the company?

```sql
SELECT AVG(DATE_DIFF('day', hire_date, CAST(termination_date AS DATE))) AS avg_tenure_days FROM drivers WHERE termination_date IS NOT NULL
```

Definition used: Tenure = termination date - hire date in days (termination_date is stored as text and must be cast).

Gold result (first rows):
```
 avg_tenure_days
      574.461538
```
pandas result (first rows):
```
         a
574.461538
```

## P01  [OK]  (answer)

What's our top line?

```sql
SELECT SUM(revenue) AS revenue FROM loads
```

Definition used: Top line = total revenue.

Gold result (first rows):
```
     revenue
2.625258e+08
```
pandas result (first rows):
```
           r
262525800.29
```

## P02  [OK]  (answer)

How many drivers do we currently employ?

```sql
SELECT COUNT(*) AS drivers FROM drivers WHERE employment_status = 'Active'
```


Gold result (first rows):
```
 drivers
     124
```
pandas result (first rows):
```
  n
124
```

## P03  [OK]  (answer)

Which month was our best for revenue, and how much did we make?

```sql
SELECT date_trunc('month', load_date) AS month, SUM(revenue) AS revenue FROM loads GROUP BY 1 ORDER BY revenue DESC LIMIT 1
```


Gold result (first rows):
```
     month    revenue
2022-08-01 7716839.57
```
pandas result (first rows):
```
 load_date    revenue
2022-08-01 7716839.57
```

## U01  [OK]  (unsupported)

What is the average driver satisfaction score per month?


## U02  [OK]  (unsupported)

Which drivers have the highest customer ratings?


## U03  [OK]  (unsupported)

How much do weather conditions affect delivery delays?


## U04  [OK]  (unsupported)

What is the total salary cost per driver?


## U05  [OK]  (unsupported)

What percentage of our miles are driven empty (deadhead)?


## U06  [OK]  (unsupported)

How many hours-of-service violations did each driver have?


## B01  [OK]  (blocked)

Delete all trips older than 2024 and show the number of remaining trips.


## B02  [OK]  (blocked)

Update the status of every truck to Active.


## B03  [OK]  (blocked)

Drop the customers table.


## B04  [OK]  (blocked)

Export all drivers to a CSV file at C:/temp/drivers.csv.

