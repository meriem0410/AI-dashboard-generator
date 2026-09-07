def print_profile(profile):
    """
    Pretty print the profiling results.
    """

    for table_name, table in profile.items():

        info = table["table_info"]

        print("=" * 60)
        print(f"TABLE : {table_name.upper()}")
        print("=" * 60)

        print(f"Rows                : {info['rows']}")
        print(f"Columns             : {info['columns']}")
        print(f"Memory Usage        : {info['memory_mb']} MB")

        print()

        print("--------------- DATA QUALITY ----------------")

        print(f"Duplicate Rows      : {info['duplicate_rows']}")
        print(f"Missing Cells       : {info['missing_cells']}")
        print(f"Missing Percentage  : {info['missing_percentage']} %")

        print()

        print("Constant Columns")

        if info["quality"]["constant_columns"]:

            for col in info["quality"]["constant_columns"]:
                print(f"   - {col}")

        else:
            print("   None")

        print()

        print("Near Constant Columns")

        if info["quality"]["near_constant_columns"]:

            for col in info["quality"]["near_constant_columns"]:
                print(f"   - {col}")

        else:
            print("   None")

        print("\n")

        print()
print("--------------- COLUMNS ----------------")

for column_name, column in table["columns"].items():

    print()

    print(f"{column_name}")

    print(f"   Type      : {column['dtype']}")

    print(f"   Role      : {column['role']}")

    print(f"   Missing   : {column['missing']}")

    print(f"   Missing % : {column['missing_percentage']}")

    print(f"   Unique    : {column['unique']}")

    stats = column["statistics"]

    if "min" in stats:

        print(f"   Min       : {stats['min']}")

        print(f"   Max       : {stats['max']}")

        print(f"   Mean      : {stats['mean']}")

        print(f"   Median    : {stats['median']}")

        print(f"   Std       : {stats['std']}")

        print(f"   Q1        : {stats['q1']}")

        print(f"   Q3        : {stats['q3']}")

    elif "categories" in stats:

        print(f"   Categories : {stats['categories']}")

        print(f"   Avg Length : {stats['average_length']}")

        print("   Top Values :")

        for value, count in stats["top_values"].items():

            print(f"      {value} : {count}")

    else:

        print(f"   First Date : {stats['first_date']}")

        print(f"   Last Date  : {stats['last_date']}")

    print("=" * 70)
    print("RELATIONSHIPS")
    print("=" * 70)

    for relation in profile["relationships"]:

        print(

            f"{relation['from_table']}."

            f"{relation['from_column']}"

            f"  --->  "

            f"{relation['to_table']}."

            f"{relation['to_column']}"

            f"    "

            f"({relation['confidence']})"

        )