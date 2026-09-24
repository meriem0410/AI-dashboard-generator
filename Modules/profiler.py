import time

from Modules.quality import profile_table
from Modules.Column_profiler import profile_column
from Modules.relationship_detector import detect_relationships


def profile_data(data):
    profile = {}

    total_start = time.perf_counter()

    print("\n" + "=" * 65)
    print("📊 DATA PROFILING")
    print("=" * 65)

    # ---------------------------------------------------------
    # TABLE + COLUMN PROFILING
    # ---------------------------------------------------------

    profiling_start = time.perf_counter()

    for table_name, df in data.items():

        table_start = time.perf_counter()

        print(
            f"\n🔎 {table_name} "
            f"({len(df):,} rows × {len(df.columns)} columns)"
        )

        table_info_start = time.perf_counter()
        table_info = profile_table(df)
        table_info_time = time.perf_counter() - table_info_start

        columns = {}

        columns_start = time.perf_counter()

        for column in df.columns:
            column_start = time.perf_counter()

            columns[column] = profile_column(
                column,
                df[column]
            )

            column_time = time.perf_counter() - column_start

            if column_time > 0.5:
                print(
                    f"   ⚠ {column}: {column_time:.3f}s"
                )

        columns_time = time.perf_counter() - columns_start

        profile[table_name] = {
            "table_info": table_info,
            "columns": columns
        }

        table_time = time.perf_counter() - table_start

        print(
            f"   table_info : {table_info_time:.3f}s"
        )
        print(
            f"   columns    : {columns_time:.3f}s"
        )
        print(
            f"   total      : {table_time:.3f}s"
        )

    profiling_time = time.perf_counter() - profiling_start

    # ---------------------------------------------------------
    # RELATIONSHIPS
    # ---------------------------------------------------------

    print("\n🔗 Detecting relationships...")

    relationship_start = time.perf_counter()

    profile["relationships"] = detect_relationships(
        data,
        profile
    )

    relationship_time = time.perf_counter() - relationship_start

    # ---------------------------------------------------------
    # TOTAL
    # ---------------------------------------------------------

    total_time = time.perf_counter() - total_start

    print("\n" + "=" * 65)
    print("⏱️ PROFILING PERFORMANCE")
    print("=" * 65)

    print(
        f"Column/table profiling : {profiling_time:.3f}s"
    )

    print(
        f"Relationship detection  : {relationship_time:.3f}s"
    )

    print(
        f"TOTAL                   : {total_time:.3f}s"
    )

    print("=" * 65)

    return profile