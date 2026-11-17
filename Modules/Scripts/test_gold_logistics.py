"""
Tests for Evaluation/gold_logistics.py and verify_gold.py on a SYNTHETIC dataset
with the same schema as the Logistics data (the real data is not needed).

    python -m Modules.Scripts.test_gold_logistics
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from Evaluation import gold_logistics as G
from Evaluation.verify_gold import verify_questions, tie_at_cutoff
from Modules.engine_duckdb import Database

failures = 0


def check(name, condition, detail=""):
    global failures
    if condition:
        print("PASS ", name)
    else:
        failures += 1
        print("FAIL ", name, "|", detail)


def synthetic(seed=1):
    r = np.random.default_rng(seed)
    nC, nL, nD, nT = 40, 3000, 30, 20
    ids = lambda p, n, w=5: [f"{p}{i:0{w}d}" for i in range(1, n + 1)]
    customers = pd.DataFrame({"customer_id": ids("CUST", nC),
                              "customer_name": [f"Name{i % 25}" for i in range(nC)],
                              "customer_type": r.choice(["Dedicated", "Contract", "Spot"], nC)})
    routes = pd.DataFrame({"route_id": ids("RTE", 12)})
    loads = pd.DataFrame({
        "load_id": ids("LOAD", nL, 8),
        "customer_id": r.choice(customers.customer_id, nL),
        "route_id": r.choice(routes.route_id, nL, p=np.arange(1, 13) / 78),
        "load_date": pd.to_datetime("2022-01-01") + pd.to_timedelta(r.integers(0, 1096, nL), unit="D"),
        "load_type": r.choice(["Dry Van", "Refrigerated"], nL),
        "revenue": r.uniform(100, 8000, nL).round(2),
        "booking_type": r.choice(["Spot", "Dedicated", "Contract"], nL)})
    trucks = pd.DataFrame({
        "truck_id": ids("TRK", 30), "make": r.choice(["Peterbilt", "Kenworth", "Volvo", "Mack"], 30),
        "model_year": r.integers(2015, 2022, 30), "status": r.choice(["Active", "Maintenance", "Inactive"], 30)})
    drivers = pd.DataFrame({
        "driver_id": ids("DRV", nD), "hire_date": pd.to_datetime("2012-01-01") + pd.to_timedelta(r.integers(0, 3500, nD), unit="D")})
    gone = r.random(nD) < 0.2
    drivers["employment_status"] = np.where(gone, "Terminated", "Active")
    drivers["termination_date"] = [
        (h + pd.Timedelta(days=int(r.integers(200, 3000)))).strftime("%Y-%m-%d") if g else None
        for h, g in zip(drivers.hire_date, gone)]
    drv = r.choice(drivers.driver_id, nL).astype(object)
    drv[r.random(nL) < 0.02] = None
    trk = r.choice(trucks.truck_id[:24], nL).astype(object)       # a few trucks never drive
    trk[r.random(nL) < 0.02] = None
    miles = r.integers(90, 3000, nL)
    trips = pd.DataFrame({
        "trip_id": ids("TRIP", nL, 8), "load_id": loads.load_id, "driver_id": drv, "truck_id": trk,
        "dispatch_date": loads.load_date, "actual_distance_miles": miles,
        "actual_duration_hours": r.uniform(1.4, 60, nL).round(1),
        "fuel_gallons_used": (miles / r.uniform(5.5, 7.5, nL)).round(1),
        "average_mpg": r.uniform(5.5, 7.5, nL).round(2),
        "idle_time_hours": r.uniform(2, 12, nL).round(1)})
    nF = 6000
    fdrv = r.choice(drivers.driver_id, nF).astype(object)
    fdrv[r.random(nF) < 0.02] = None
    fuel = pd.DataFrame({
        "fuel_purchase_id": ids("FUEL", nF, 8), "trip_id": r.choice(trips.trip_id[:2500], nF),
        "driver_id": fdrv,
        "purchase_date": pd.to_datetime("2022-01-01") + pd.to_timedelta(r.integers(0, 1100 * 24, nF), unit="h"),
        "gallons": r.uniform(50, 200, nF).round(1),
        "total_cost": r.uniform(158, 997, nF).round(2)})
    facilities = pd.DataFrame({"facility_id": ids("FAC", 6),
                               "facility_type": ["Terminal", "Warehouse", "Cross-Dock", "Terminal", "Warehouse", "Cross-Dock"]})
    nE = 20000
    events = pd.DataFrame({
        "event_id": ids("EVT", nE, 8), "load_id": r.choice(loads.load_id, nE),
        "facility_id": r.choice(facilities.facility_id, nE, p=[.25, .2, .2, .15, .1, .1]),
        "event_type": r.choice(["Pickup", "Delivery"], nE),
        "detention_minutes": r.integers(0, 240, nE),
        "on_time_flag": r.random(nE) < r.choice([.5, .6, .7, .8, .9, .55], nE)})
    nI = 170
    inc = pd.DataFrame({
        "incident_id": ids("INC", nI, 8), "trip_id": r.choice(trips.trip_id, nI, replace=False),
        "driver_id": r.choice(drivers.driver_id[:20], nI).astype(object),
        "incident_type": r.choice(["Accident", "DOT Violation", "Moving Violation", "Equipment Damage", "Customer Complaint"], nI),
        "at_fault_flag": r.random(nI) < 0.5, "preventable_flag": r.random(nI) < 0.5,
        "claim_amount": r.uniform(0, 60000, nI).round(2)})
    inc.loc[r.random(nI) < 0.01, "driver_id"] = None
    maint = pd.DataFrame({
        "maintenance_id": ids("MAINT", 500, 8), "truck_id": r.choice(trucks.truck_id, 500),
        "maintenance_type": r.choice(["Inspection", "Tire", "Preventive", "Repair"], 500),
        "total_cost": r.uniform(60, 4400, 500).round(2)})
    return {"customers": customers, "routes": routes, "loads": loads, "trips": trips,
            "fuel_purchases": fuel, "delivery_events": events, "safety_incidents": inc,
            "trucks": trucks, "maintenance_records": maint, "drivers": drivers, "facilities": facilities}


data = synthetic()
db = Database.from_dataframes(data)
res = verify_questions(data, db, G.Q, G.PANDAS)
by = {r["id"]: r for r in res}

answerable = [q for q in G.Q if q["expected"] == "answer"]
check("28 answerable, 6 unsupported, 4 blocked",
      (len(answerable), sum(q["expected"] == "unsupported" for q in G.Q),
       sum(q["expected"] == "blocked" for q in G.Q)) == (28, 6, 4))
check("the set has anchors, business, trap, nested and paraphrase questions",
      {q["category"] for q in answerable} >= {"business_kpi", "fanout_trap", "nested_agg", "paraphrase", "ratio"})
check("ids are unique", len({q["id"] for q in G.Q}) == len(G.Q))
check("every answerable question has a pandas derivation", all(q["id"] in G.PANDAS for q in answerable))
for q in answerable:
    r = by[q["id"]]
    tie_only = r["problems"] and all("tie at" in p for p in r["problems"])
    check(f"{q['id']} gold SQL agrees with pandas", r["status"] == "ok" or tie_only, r["problems"])
    if q.get("alt_sql"):
        check(f"{q['id']} the tempting wrong query gives a different result", not r["warnings"], r["warnings"])
    if q["category"] in ("business_kpi", "fanout_trap", "nested_agg"):
        check(f"{q['id']} has a written definition", bool(q.get("definition")))
for q in G.Q:
    if q["expected"] == "unsupported":
        check(f"{q['id']} unsupported: no column supports it", by[q["id"]]["status"] == "ok", by[q["id"]]["problems"])

# the checks themselves must be able to fail
BASE = next(q for q in G.Q if q["id"] == "P01")
bad = [dict(BASE, id="X1", gold_sql="SELECT SUM(revenue) * 2 AS t FROM loads")]
r = verify_questions(data, db, bad, {"X1": G.PANDAS["P01"]})[0]
check("a wrong gold SQL is caught", r["status"] == "problem" and "disagree" in r["problems"][0])
bad = [dict(BASE, id="X2", gold_sql="SELECT nope FROM loads")]
r = verify_questions(data, db, bad, {"X2": G.PANDAS["P01"]})[0]
check("a failing gold SQL is caught", r["status"] == "problem" and "failed" in r["problems"][0])
bad = [dict(BASE, id="X3")]
r = verify_questions(data, db, bad, {})[0]
check("a missing pandas derivation is caught", r["status"] == "problem")
u = [dict(BASE, id="X4", expected="unsupported", probe_terms=["revenue"])]
r = verify_questions(data, db, u, {})[0]
check("an 'unsupported' question that the data supports is caught", r["status"] == "problem")

nd = [dict(BASE, id="X5", alt_sql="SELECT SUM(revenue) AS r FROM loads")]
r = verify_questions(data, db, nd, {"X5": G.PANDAS["P01"]})[0]
check("a trap that gives the same result is flagged as non-discriminating",
      r["status"] == "ok" and any("does not discriminate" in w for w in r["warnings"]), r["warnings"])

# tie detection
tie = Database.from_dataframes({"t": pd.DataFrame({"k": ["a", "b", "c", "d"], "v": [9, 5, 5, 1]})})
check("tie at the cut-off detected",
      tie_at_cutoff(tie, "SELECT k, v FROM t ORDER BY v DESC LIMIT 2"))
check("no tie when the cut-off is clean",
      not tie_at_cutoff(tie, "SELECT k, v FROM t ORDER BY v DESC LIMIT 1"))
check("no tie on non-limit queries", not tie_at_cutoff(tie, "SELECT k, v FROM t"))

db.close()
tie.close()
print("\n%s" % ("ALL PASSED" if not failures else f"{failures} FAILED"))
sys.exit(1 if failures else 0)
