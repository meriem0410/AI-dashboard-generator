
"""
Tests for the virtual global dashboard date dimension.

Covers:
    1. Global date dimension discovery.
    2. Primary fact-table date mappings.
    3. Lifecycle date exclusion.
    4. Global date boundaries.
    5. Simultaneous filtering of fact tables.
    6. KPI recalculation.
    7. Fuel cost recalculation.
    8. Joined query recalculation.
    9. Combined date and category filters.
    10. Raw table preservation.
    11. Dimension table preservation.
    12. Invalid mapping rejection.
    13. Filter reset.
    14. Repeated filter stability.
"""

import pandas as pd

from Modules.engine_duckdb import Database
from Modules.dashboard_filters import discover_filter_catalog


# ============================================================
# TEST DATA
# ============================================================

data = {
    "trips": pd.DataFrame({
        "trip_id": ["T1", "T2", "T3", "T4"],
        "dispatch_date": pd.to_datetime([
            "2024-01-01",
            "2024-01-15",
            "2024-02-01",
            "2024-03-01"
        ]),
        "average_mpg": [5.0, 6.0, 7.0, 8.0]
    }),

    "fuel_purchases": pd.DataFrame({
        "purchase_id": ["F1", "F2", "F3", "F4"],
        "trip_id": ["T1", "T2", "T3", "T4"],
        "driver_id": ["D1", "D2", "D1", "D2"],
        "purchase_date": pd.to_datetime([
            "2024-01-02",
            "2024-01-15",
            "2024-02-01",
            "2024-03-01"
        ]),
        "fuel_type": ["Diesel", "Gas", "Diesel", "Diesel"],
        "total_cost": [100, 200, 300, 400]
    }),

    "drivers": pd.DataFrame({
        "driver_id": ["D1", "D2"],
        "hire_date": pd.to_datetime([
            "2018-01-01",
            "2019-01-01"
        ]),
        "first_name": ["Alice", "Bob"]
    })
}


# ============================================================
# PROFILER RELATIONSHIPS
# ============================================================

profile_info = {
    "relationships": [
        {
            "from_table": "fuel_purchases",
            "from_column": "trip_id",
            "to_table": "trips",
            "to_column": "trip_id",
            "confidence": 1.0
        },
        {
            "from_table": "fuel_purchases",
            "from_column": "driver_id",
            "to_table": "drivers",
            "to_column": "driver_id",
            "confidence": 1.0
        },
        {
            "from_table": "trips",
            "from_column": "driver_id",
            "to_table": "drivers",
            "to_column": "driver_id",
            "confidence": 1.0
        }
    ]
}


# ============================================================
# INITIALIZE DATABASE
# ============================================================

db = Database.from_dataframes(data)

try:

    # --------------------------------------------------------
    # TEST 1: GLOBAL DATE DIMENSION DISCOVERY
    # --------------------------------------------------------

    catalog = discover_filter_catalog(
        data,
        profile_info
    )

    date_dimension = catalog["date_dimension"]

    assert date_dimension is not None

    print("PASS: Global date dimension discovered")


    # --------------------------------------------------------
    # TEST 2: PRIMARY DATE MAPPINGS
    # --------------------------------------------------------

    mapping_lookup = {
        item["table"]: item["column"]
        for item in date_dimension["mappings"]
    }

    assert mapping_lookup["trips"] == "dispatch_date"
    assert mapping_lookup["fuel_purchases"] == "purchase_date"

    print("PASS: Primary fact-table dates detected")


    # --------------------------------------------------------
    # TEST 3: EXCLUDE LIFECYCLE DATES
    # --------------------------------------------------------

    assert "drivers" not in mapping_lookup

    print("PASS: Driver hire dates excluded")


    # --------------------------------------------------------
    # TEST 4: GLOBAL DATE BOUNDARIES
    # --------------------------------------------------------

    assert date_dimension["min_date"] == "2024-01-01"
    assert date_dimension["max_date"] == "2024-03-01"

    print("PASS: Global date boundaries calculated")


    # --------------------------------------------------------
    # TEST 5: FILTER ALL FACT TABLES
    # --------------------------------------------------------

    filters = {
        "date": {
            "start": "2024-01-01",
            "end": "2024-01-31",
            "mappings": [
                {
                    "table": item["table"],
                    "column": item["column"]
                }
                for item in date_dimension["mappings"]
            ]
        }
    }

    summary = db.set_filters(filters)

    trip_count = db.run(
        "SELECT COUNT(*) AS n FROM trips"
    )

    fuel_count = db.run(
        "SELECT COUNT(*) AS n FROM fuel_purchases"
    )

    assert trip_count["n"].iloc[0] == 2
    assert fuel_count["n"].iloc[0] == 2

    assert summary["trips"]["after"] == 2
    assert summary["fuel_purchases"]["after"] == 2

    print("PASS: Global date filter affects both fact tables")


    # --------------------------------------------------------
    # TEST 6: AVERAGE MPG RECALCULATION
    # --------------------------------------------------------

    result = db.run(
        "SELECT AVG(average_mpg) AS avg_mpg FROM trips"
    )

    assert result["avg_mpg"].iloc[0] == 5.5

    print("PASS: Trip KPI recalculated")


    # --------------------------------------------------------
    # TEST 7: FUEL COST RECALCULATION
    # --------------------------------------------------------

    result = db.run(
        "SELECT SUM(total_cost) AS total_cost "
        "FROM fuel_purchases"
    )

    assert result["total_cost"].iloc[0] == 300

    print("PASS: Fuel cost recalculated")


    # --------------------------------------------------------
    # TEST 8: JOINED QUERY RECALCULATION
    # --------------------------------------------------------

    result = db.run(
        """
        SELECT
            d.driver_id,
            SUM(fp.total_cost) AS total_cost
        FROM drivers d
        JOIN fuel_purchases fp
            ON d.driver_id = fp.driver_id
        GROUP BY d.driver_id
        """
    )

    assert result["total_cost"].sum() == 300

    print("PASS: Joined dimension/fact query recalculated")


    # --------------------------------------------------------
    # TEST 9: COMBINED DATE AND CATEGORY FILTERS
    # --------------------------------------------------------

    combined = {
        **filters,
        "category": {
            "table": "fuel_purchases",
            "column": "fuel_type",
            "values": ["Diesel"]
        }
    }

    db.set_filters(combined)

    result = db.run(
        "SELECT SUM(total_cost) AS total_cost "
        "FROM fuel_purchases"
    )

    assert result["total_cost"].iloc[0] == 100

    print("PASS: Global date and category filters combined")


    # --------------------------------------------------------
    # TEST 10: RAW TABLES PRESERVED
    # --------------------------------------------------------

    result = db.run(
        "SELECT COUNT(*) AS n FROM raw_trips"
    )

    assert result["n"].iloc[0] == 4

    result = db.run(
        "SELECT COUNT(*) AS n FROM raw_fuel_purchases"
    )

    assert result["n"].iloc[0] == 4

    print("PASS: Original raw tables preserved")


    # --------------------------------------------------------
    # TEST 11: DIMENSION TABLE PRESERVED
    # --------------------------------------------------------

    result = db.run(
        "SELECT COUNT(*) AS n FROM drivers"
    )

    assert result["n"].iloc[0] == 2

    print("PASS: Driver dimension table unchanged")


    # --------------------------------------------------------
    # TEST 12: INVALID MAPPING REJECTED
    # --------------------------------------------------------

    try:

        db.set_filters({
            "date": {
                "start": "2024-01-01",
                "end": "2024-01-31",
                "mappings": [
                    {
                        "table": "unknown_table",
                        "column": "unknown_date"
                    }
                ]
            }
        })

        raise AssertionError(
            "Unknown date mapping should have been rejected."
        )

    except ValueError:

        print("PASS: Invalid mapping rejected")


    # --------------------------------------------------------
    # TEST 13: CLEAR FILTERS
    # --------------------------------------------------------

    db.set_filters({})

    result = db.run(
        "SELECT COUNT(*) AS n FROM trips"
    )

    assert result["n"].iloc[0] == 4

    result = db.run(
        "SELECT SUM(total_cost) AS total_cost "
        "FROM fuel_purchases"
    )

    assert result["total_cost"].iloc[0] == 1000

    print("PASS: Clearing filters restores original records")


    # --------------------------------------------------------
    # TEST 14: REPEATED FILTER STABILITY
    # --------------------------------------------------------

    first = db.set_filters(filters)
    second = db.set_filters(filters)

    assert first == second

    print("PASS: Repeated filter configuration is stable")


    print("\nALL GLOBAL DATE FILTER TESTS PASSED")


finally:

    db.close()
