# Schema dump: Logistics

### customers  (200 rows, 8 columns)

| column | type | distinct | null % | min | max | examples |
| --- | --- | --- | --- | --- | --- | --- |
| customer_id | str | 200 | 0 |  |  | CUST00001, CUST00002, CUST00003, CUST00004 |
| customer_name | str | 107 | 0 |  |  | Metro Wholesale, National Retail, XYZ Industries, American Corp |
| customer_type | str | 3 | 0 |  |  | Dedicated, Contract, Spot |
| credit_terms_days | int64 | 4 | 0 | 15 | 60 | 60, 30, 15, 45 |
| primary_freight_type | str | 6 | 0 |  |  | General, Retail, Consumer Goods, Food/Beverage |
| account_status | str | 2 | 0 |  |  | Inactive, Active |
| contract_start_date | datetime64[us] | 173 | 0 | 2020-01-07 00:00:00 | 2022-01-01 00:00:00 | 2020-02-20 00:00:00, 2021-06-02 00:00:00, 2020-09-04 00:00:00, 2020-11-29 00:00:00 |
| annual_revenue_potential | int64 | 200 | 0 | 101641 | 4990599 | 985117, 4936566, 3102814, 3948027 |

### delivery_events  (170,820 rows, 11 columns)

| column | type | distinct | null % | min | max | examples |
| --- | --- | --- | --- | --- | --- | --- |
| event_id | str | 170820 | 0 |  |  | EVT00000001, EVT00000002, EVT00000003, EVT00000004 |
| load_id | str | 85410 | 0 |  |  | LOAD00000001, LOAD00000002, LOAD00000003, LOAD00000004 |
| trip_id | str | 85410 | 0 |  |  | TRIP00000001, TRIP00000002, TRIP00000003, TRIP00000004 |
| event_type | str | 2 | 0 |  |  | Pickup, Delivery |
| facility_id | str | 50 | 0 |  |  | FAC00034, FAC00046, FAC00015, FAC00050 |
| scheduled_datetime | datetime64[us] | 99624 | 0 | 2022-01-01 07:00:00 | 2025-01-02 19:21:42 | 2022-01-01 18:00:00, 2022-01-02 23:10:55.9181, 2022-01-02 02:13:26.6084, 2022-01-01 08:00:00 |
| actual_datetime | datetime64[us] | 170820 | 0 | 2022-01-01 06:13:28 | 2025-01-03 00:29:47 | 2022-01-01 20:58:55.9181, 2022-01-02 21:30:22.1420, 2022-01-01 17:37:26.6084, 2022-01-02 05:55:46.2382 |
| detention_minutes | int64 | 240 | 0 | 0 | 239 | 0, 230, 62, 67 |
| on_time_flag | bool | 2 | 0 | False | True | False, True |
| location_city | str | 20 | 0 |  |  | Houston, Detroit, Kansas City, Indianapolis |
| location_state | str | 19 | 0 |  |  | TX, MI, MO, IN |

### drivers  (150 rows, 12 columns)

| column | type | distinct | null % | min | max | examples |
| --- | --- | --- | --- | --- | --- | --- |
| driver_id | str | 150 | 0 |  |  | DRV00001, DRV00002, DRV00003, DRV00004 |
| first_name | str | 20 | 0 |  |  | Jennifer, William, Charles, Barbara |
| last_name | str | 20 | 0 |  |  | Hernandez, Martin, Brown, Martinez |
| hire_date | datetime64[us] | 147 | 0 | 2012-01-28 00:00:00 | 2021-12-06 00:00:00 | 2014-10-31 00:00:00, 2020-10-02 00:00:00, 2021-09-21 00:00:00, 2013-09-08 00:00:00 |
| termination_date | str | 26 | 83 |  |  | 2021-05-17, 2021-01-23, 2021-05-23, 2015-03-16 |
| license_number | str | 150 | 0 |  |  | DL673510887, DL128955006, DL523076025, DL735540030 |
| license_state | str | 23 | 0 |  |  | WA, GA, NC, AZ |
| date_of_birth | datetime64[us] | 148 | 0 | 1960-05-24 00:00:00 | 1995-07-03 00:00:00 | 1973-11-07 00:00:00, 1976-11-03 00:00:00, 1970-04-06 00:00:00, 1995-02-06 00:00:00 |
| home_terminal | str | 25 | 0 |  |  | Denver, Columbus, Salt Lake City, Chicago |
| employment_status | str | 2 | 0 |  |  | Active, Terminated |
| cdl_class | str | 1 | 0 |  |  | A |
| years_experience | int64 | 24 | 0 | 2 | 25 | 3, 20, 19, 12 |

### facilities  (50 rows, 9 columns)

| column | type | distinct | null % | min | max | examples |
| --- | --- | --- | --- | --- | --- | --- |
| facility_id | str | 50 | 0 |  |  | FAC00001, FAC00002, FAC00003, FAC00004 |
| facility_name | str | 35 | 0 |  |  | Houston Distribution Cen, Kansas City Hub, Charlotte Distribution C, Chicago Distribution Cen |
| facility_type | str | 4 | 0 |  |  | Cross-Dock, Distribution Center, Terminal, Warehouse |
| city | str | 21 | 0 |  |  | Houston, Kansas City, Charlotte, Chicago |
| state | str | 20 | 0 |  |  | TX, MO, NC, IL |
| latitude | float64 | 21 | 0 | 25.7617 | 45.5152 | 29.7604, 39.0997, 35.2271, 41.8781 |
| longitude | float64 | 21 | 0 | -122.6784 | -74.006 | -95.3698, -94.5786, -80.8431, -87.6298 |
| dock_doors | int64 | 40 | 0 | 16 | 150 | 125, 33, 138, 38 |
| operating_hours | str | 4 | 0 |  |  | 24/7, 7AM-7PM, 8AM-5PM, 6AM-10PM |

### fuel_purchases  (196,442 rows, 11 columns)

| column | type | distinct | null % | min | max | examples |
| --- | --- | --- | --- | --- | --- | --- |
| fuel_purchase_id | str | 196442 | 0 |  |  | FUEL00000001, FUEL00000002, FUEL00000003, FUEL00000004 |
| trip_id | str | 76939 | 0 |  |  | TRIP00051284, TRIP00073723, TRIP00018286, TRIP00008465 |
| truck_id | str | 92 | 2 |  |  | TRK00045, TRK00013, TRK00024, TRK00018 |
| driver_id | str | 124 | 2 |  |  | DRV00102, DRV00142, DRV00047, DRV00104 |
| purchase_date | datetime64[us] | 26331 | 0 | 2022-01-01 00:00:00 | 2025-01-02 23:00:00 | 2023-10-22 05:00:00, 2024-08-04 08:00:00, 2022-08-23 13:00:00, 2022-04-20 00:00:00 |
| location_city | str | 25 | 0 |  |  | Columbus, New York, Seattle, Memphis |
| location_state | str | 23 | 0 |  |  | MN, AZ, NE, NY |
| gallons | float64 | 1501 | 0 | 50.0 | 200.0 | 131.6, 139.9, 189.3, 130.7 |
| price_per_gallon | float64 | 1851 | 0 | 3.15 | 5.0 | 3.399, 3.18, 3.804, 3.579 |
| total_cost | float64 | 64113 | 0 | 158.5 | 997.9 | 447.31, 444.88, 720.1, 467.78 |
| fuel_card_number | str | 176645 | 0 |  |  | FC567161, FC717910, FC912816, FC776357 |

### loads  (85,410 rows, 12 columns)

| column | type | distinct | null % | min | max | examples |
| --- | --- | --- | --- | --- | --- | --- |
| load_id | str | 85410 | 0 |  |  | LOAD00000001, LOAD00000002, LOAD00000003, LOAD00000004 |
| customer_id | str | 200 | 0 |  |  | CUST00183, CUST00076, CUST00027, CUST00088 |
| route_id | str | 58 | 0 |  |  | RTE00019, RTE00058, RTE00048, RTE00013 |
| load_date | datetime64[us] | 1096 | 0 | 2022-01-01 00:00:00 | 2024-12-31 00:00:00 | 2022-01-01 00:00:00, 2022-01-02 00:00:00, 2022-01-03 00:00:00, 2022-01-04 00:00:00 |
| load_type | str | 2 | 0 |  |  | Dry Van, Refrigerated |
| weight_lbs | int64 | 31927 | 0 | 10000 | 45000 | 19178, 27761, 35594, 33274 |
| pieces | int64 | 28 | 0 | 1 | 28 | 13, 22, 16, 10 |
| revenue | float64 | 79130 | 0 | 125.93 | 8125.22 | 3045.23, 1224.48, 7171.12, 1308.2 |
| fuel_surcharge | float64 | 57 | 0 | 13.8 | 891.82 | 406.72, 98.61, 792.88, 141.33 |
| accessorial_charges | int64 | 6 | 0 | 0 | 200 | 100, 0, 50, 75 |
| load_status | str | 1 | 0 |  |  | Completed |
| booking_type | str | 3 | 0 |  |  | Spot, Dedicated, Contract |

### maintenance_records  (2,920 rows, 12 columns)

| column | type | distinct | null % | min | max | examples |
| --- | --- | --- | --- | --- | --- | --- |
| maintenance_id | str | 2920 | 0 |  |  | MAINT00000001, MAINT00000002, MAINT00000003, MAINT00000004 |
| truck_id | str | 120 | 0 |  |  | TRK00085, TRK00041, TRK00090, TRK00056 |
| maintenance_date | datetime64[us] | 1020 | 0 | 2022-01-01 00:00:00 | 2024-12-31 00:00:00 | 2022-01-01 00:00:00, 2022-01-02 00:00:00, 2022-01-03 00:00:00, 2022-01-04 00:00:00 |
| maintenance_type | str | 7 | 0 |  |  | Inspection, Tire, Preventive, Repair |
| odometer_reading | int64 | 2912 | 0 | 50156 | 749875 | 400255, 268041, 698915, 416522 |
| labor_hours | float64 | 76 | 0 | 0.5 | 8.0 | 7.8, 0.9, 7.2, 2.8 |
| labor_cost | float64 | 2851 | 0 | 43.28 | 976.87 | 781.42, 80.91, 733.18, 298.8 |
| parts_cost | float64 | 2903 | 0 | 0.14 | 3498.61 | 10.41, 3207.16, 1570.57, 67.48 |
| total_cost | float64 | 2914 | 0 | 60.82 | 4426.57 | 791.83, 3288.07, 2303.75, 366.28 |
| facility_location | str | 25 | 0 |  |  | Kansas City, Seattle, Miami, Omaha |
| downtime_hours | float64 | 460 | 0 | 2.0 | 48.0 | 22.2, 8.0, 16.5, 34.6 |
| service_description | str | 21 | 0 |  |  | Emergency Inspection, Scheduled Tire, Routine Preventive, Emergency Repair |

### routes  (58 rows, 9 columns)

| column | type | distinct | null % | min | max | examples |
| --- | --- | --- | --- | --- | --- | --- |
| route_id | str | 58 | 0 |  |  | RTE00001, RTE00002, RTE00003, RTE00004 |
| origin_city | str | 18 | 0 |  |  | Atlanta, Chicago, Dallas, New York |
| origin_state | str | 17 | 0 |  |  | GA, IL, TX, NY |
| destination_city | str | 19 | 0 |  |  | Chicago, Miami, Los Angeles, Portland |
| destination_state | str | 18 | 0 |  |  | IL, FL, CA, OR |
| typical_distance_miles | int64 | 52 | 0 | 92 | 3141 | 677, 697, 2003, 2017 |
| base_rate_per_mile | float64 | 46 | 0 | 1.52 | 2.79 | 1.7, 2.08, 2.55, 1.84 |
| fuel_surcharge_rate | float64 | 20 | 0 | 0.15 | 0.34 | 0.19, 0.22, 0.29, 0.26 |
| typical_transit_days | int64 | 5 | 0 | 1 | 5 | 1, 3, 2, 4 |

### safety_incidents  (170 rows, 15 columns)

| column | type | distinct | null % | min | max | examples |
| --- | --- | --- | --- | --- | --- | --- |
| incident_id | str | 170 | 0 |  |  | INC00000001, INC00000002, INC00000003, INC00000004 |
| trip_id | str | 170 | 0 |  |  | TRIP00036079, TRIP00032462, TRIP00067583, TRIP00049128 |
| truck_id | str | 80 | 1 |  |  | TRK00006, TRK00084, TRK00106, TRK00085 |
| driver_id | str | 92 | 1 |  |  | DRV00006, DRV00119, DRV00134, DRV00133 |
| incident_date | datetime64[us] | 169 | 0 | 2022-01-05 02:00:00 | 2024-12-24 09:00:00 | 2023-04-09 14:00:00, 2023-02-19 11:00:00, 2024-05-20 01:00:00, 2023-09-26 03:00:00 |
| incident_type | str | 5 | 0 |  |  | Moving Violation, Customer Complaint, Equipment Damage, DOT Violation |
| location_city | str | 25 | 0 |  |  | Columbus, Seattle, Kansas City, Las Vegas |
| location_state | str | 23 | 0 |  |  | PA, NC, OK, TN |
| at_fault_flag | bool | 2 | 0 | False | True | True, False |
| injury_flag | bool | 2 | 0 | False | True | False, True |
| vehicle_damage_cost | float64 | 119 | 0 | 0.0 | 24614.16 | 12629.26, 2700.7, 24302.32, 4879.13 |
| cargo_damage_cost | float64 | 49 | 0 | 0.0 | 49744.07 | 0.0, 14284.24, 28315.16, 379.1 |
| claim_amount | float64 | 132 | 0 | 0.0 | 64245.72 | 12629.26, 16984.94, 24302.32, 4879.13 |
| preventable_flag | bool | 2 | 0 | False | True | True, False |
| description | str | 12 | 0 |  |  | Severe incident involvin, Severe incident involvin, Minor incident involving, Moderate incident involv |

### trailers  (180 rows, 9 columns)

| column | type | distinct | null % | min | max | examples |
| --- | --- | --- | --- | --- | --- | --- |
| trailer_id | str | 180 | 0 |  |  | TRL00001, TRL00002, TRL00003, TRL00004 |
| trailer_number | int64 | 176 | 0 | 1072 | 9939 | 4290, 8848, 6147, 3910 |
| trailer_type | str | 2 | 0 |  |  | Refrigerated, Dry Van |
| length_feet | int64 | 1 | 0 | 53 | 53 | 53 |
| model_year | int64 | 10 | 0 | 2015 | 2024 | 2016, 2018, 2022, 2024 |
| vin | str | 180 | 0 |  |  | 1AV889081755621178, 1BU942062588832828, 1AV669057807416326, 1AV544000060905105 |
| acquisition_date | datetime64[us] | 173 | 0 | 2015-01-06 00:00:00 | 2021-12-16 00:00:00 | 2018-05-11 00:00:00, 2018-11-24 00:00:00, 2019-01-28 00:00:00, 2018-08-27 00:00:00 |
| status | str | 1 | 0 |  |  | Active |
| current_location | str | 25 | 0 |  |  | Kansas City, Milwaukee, New York, Las Vegas |

### trips  (85,410 rows, 12 columns)

| column | type | distinct | null % | min | max | examples |
| --- | --- | --- | --- | --- | --- | --- |
| trip_id | str | 85410 | 0 |  |  | TRIP00000001, TRIP00000002, TRIP00000003, TRIP00000004 |
| load_id | str | 85410 | 0 |  |  | LOAD00000001, LOAD00000002, LOAD00000003, LOAD00000004 |
| driver_id | str | 124 | 2 |  |  | DRV00117, DRV00141, DRV00032, DRV00083 |
| truck_id | str | 92 | 2 |  |  | TRK00035, TRK00108, TRK00031, TRK00105 |
| trailer_id | str | 180 | 2 |  |  | TRL00167, TRL00082, TRL00138, TRL00018 |
| dispatch_date | datetime64[us] | 1096 | 0 | 2022-01-01 00:00:00 | 2024-12-31 00:00:00 | 2022-01-01 00:00:00, 2022-01-02 00:00:00, 2022-01-03 00:00:00, 2022-01-04 00:00:00 |
| actual_distance_miles | int64 | 2818 | 0 | 90 | 3391 | 1314, 515, 2509, 717 |
| actual_duration_hours | float64 | 632 | 0 | 1.4 | 67.8 | 26.2, 8.6, 45.0, 11.1 |
| fuel_gallons_used | float64 | 5247 | 0 | 12.0 | 611.9 | 183.8, 93.6, 339.1, 110.3 |
| average_mpg | float64 | 201 | 0 | 5.5 | 7.5 | 7.15, 5.5, 7.4, 6.5 |
| idle_time_hours | float64 | 101 | 0 | 2.0 | 12.0 | 3.5, 8.3, 12.0, 9.6 |
| trip_status | str | 1 | 0 |  |  | Completed |

### trucks  (120 rows, 11 columns)

| column | type | distinct | null % | min | max | examples |
| --- | --- | --- | --- | --- | --- | --- |
| truck_id | str | 120 | 0 |  |  | TRK00001, TRK00002, TRK00003, TRK00004 |
| unit_number | int64 | 120 | 0 | 1086 | 9991 | 3463, 6461, 2335, 3317 |
| make | str | 6 | 0 |  |  | Peterbilt, Kenworth, Freightliner, Volvo |
| model_year | int64 | 7 | 0 | 2015 | 2021 | 2016, 2015, 2018, 2017 |
| vin | str | 120 | 0 |  |  | 1VV205190335317039, 1NV753749606229960, 1NT803101860493229, 1VV131945381692351 |
| acquisition_date | datetime64[us] | 119 | 0 | 2015-01-27 00:00:00 | 2021-10-08 00:00:00 | 2017-04-27 00:00:00, 2018-10-04 00:00:00, 2020-09-17 00:00:00, 2017-06-17 00:00:00 |
| acquisition_mileage | int64 | 120 | 0 | 227 | 49556 | 18814, 26795, 11795, 8875 |
| fuel_type | str | 1 | 0 |  |  | Diesel |
| tank_capacity_gallons | int64 | 3 | 0 | 150 | 250 | 200, 150, 250 |
| status | str | 3 | 0 |  |  | Active, Maintenance, Inactive |
| home_terminal | str | 24 | 0 |  |  | Omaha, Seattle, Atlanta, Salt Lake City |

## Detected relationships

- customers.customer_id (one) -> loads.customer_id (one-to-many)
- loads.load_id (one) -> delivery_events.load_id (one-to-many)
- loads.load_id (one) -> trips.load_id (one-to-one)
- trips.load_id (one) -> delivery_events.load_id (one-to-many)
- trips.trip_id (one) -> delivery_events.trip_id (one-to-many)
- trips.trip_id (one) -> fuel_purchases.trip_id (one-to-many)
- trips.trip_id (one) -> safety_incidents.trip_id (one-to-one)
- facilities.facility_id (one) -> delivery_events.facility_id (one-to-many)
- drivers.driver_id (one) -> fuel_purchases.driver_id (one-to-many)
- drivers.driver_id (one) -> safety_incidents.driver_id (one-to-many)
- drivers.driver_id (one) -> trips.driver_id (one-to-many)
- trucks.truck_id (one) -> fuel_purchases.truck_id (one-to-many)
- trucks.truck_id (one) -> maintenance_records.truck_id (one-to-many)
- trucks.truck_id (one) -> safety_incidents.truck_id (one-to-many)
- trucks.truck_id (one) -> trips.truck_id (one-to-many)
- routes.route_id (one) -> loads.route_id (one-to-many)
- trailers.trailer_id (one) -> trips.trailer_id (one-to-many)