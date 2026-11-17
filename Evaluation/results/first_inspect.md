# Inspection: first

Cache information was not recorded in this run.

Outcomes: correct=148, correct_decline=42, wrong_decline=2

## Q17  graph1  run 1  ->  correct

Question: What is the total claim amount of safety incidents for each customer type?

Reference SQL:
```sql
SELECT c.customer_type, SUM(s.claim_amount) AS claims FROM safety_incidents s JOIN trips t ON s.trip_id = t.trip_id JOIN loads l ON t.load_id = l.load_id JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type
```
Generated SQL:
```sql
SELECT c.customer_type,
 SUM(si.claim_amount) AS total_claim_amount
FROM safety_incidents si
JOIN trips t ON si.trip_id = t.trip_id
JOIN loads l ON t.load_id = l.load_id
JOIN customers c ON l.customer_id = c.customer_id
GROUP BY c.customer_type
ORDER BY total_claim_amount DESC;
```
stage=completed status=ok attempts=1 rows=3 (gold 3) seconds=12.91 replayed=None

## Q17  graph1  run 2  ->  correct

Question: What is the total claim amount of safety incidents for each customer type?

Reference SQL:
```sql
SELECT c.customer_type, SUM(s.claim_amount) AS claims FROM safety_incidents s JOIN trips t ON s.trip_id = t.trip_id JOIN loads l ON t.load_id = l.load_id JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type
```
Generated SQL:
```sql
SELECT c.customer_type,
 SUM(si.claim_amount) AS total_claim_amount
FROM safety_incidents si
JOIN trips t ON si.trip_id = t.trip_id
JOIN loads l ON t.load_id = l.load_id
JOIN customers c ON l.customer_id = c.customer_id
GROUP BY c.customer_type
ORDER BY total_claim_amount DESC;
```
stage=completed status=ok attempts=1 rows=3 (gold 3) seconds=0.08 replayed=None

## Q17  graph3  run 1  ->  correct

Question: What is the total claim amount of safety incidents for each customer type?

Reference SQL:
```sql
SELECT c.customer_type, SUM(s.claim_amount) AS claims FROM safety_incidents s JOIN trips t ON s.trip_id = t.trip_id JOIN loads l ON t.load_id = l.load_id JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type
```
Generated SQL:
```sql
SELECT c.customer_type,
 SUM(si.claim_amount) AS total_claim_amount
FROM safety_incidents si
JOIN trips t ON si.trip_id = t.trip_id
JOIN loads l ON t.load_id = l.load_id
JOIN customers c ON l.customer_id = c.customer_id
GROUP BY c.customer_type
ORDER BY total_claim_amount DESC;
```
stage=completed status=ok attempts=1 rows=3 (gold 3) seconds=0.06 replayed=None

## Q17  graph3  run 2  ->  correct

Question: What is the total claim amount of safety incidents for each customer type?

Reference SQL:
```sql
SELECT c.customer_type, SUM(s.claim_amount) AS claims FROM safety_incidents s JOIN trips t ON s.trip_id = t.trip_id JOIN loads l ON t.load_id = l.load_id JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type
```
Generated SQL:
```sql
SELECT c.customer_type,
 SUM(si.claim_amount) AS total_claim_amount
FROM safety_incidents si
JOIN trips t ON si.trip_id = t.trip_id
JOIN loads l ON t.load_id = l.load_id
JOIN customers c ON l.customer_id = c.customer_id
GROUP BY c.customer_type
ORDER BY total_claim_amount DESC;
```
stage=completed status=ok attempts=1 rows=3 (gold 3) seconds=0.06 replayed=None

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
stage=unsupported status=unsupported attempts=1 rows=None (gold 3) seconds=9.23 replayed=None
error/reason: the schema has no customer or customer type information

## Q17  graph3_rag  run 2  ->  wrong_decline

Question: What is the total claim amount of safety incidents for each customer type?

Reference SQL:
```sql
SELECT c.customer_type, SUM(s.claim_amount) AS claims FROM safety_incidents s JOIN trips t ON s.trip_id = t.trip_id JOIN loads l ON t.load_id = l.load_id JOIN customers c ON l.customer_id = c.customer_id GROUP BY c.customer_type
```
Generated SQL:
```sql
None
```
stage=unsupported status=unsupported attempts=1 rows=None (gold 3) seconds=0.09 replayed=None
error/reason: the schema has no customer or customer type information
