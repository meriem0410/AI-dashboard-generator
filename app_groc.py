

# ============================================================
# MAIN
# ============================================================

import json

from loader import load_data_folder

from Modules.profiler import profile_data

from Modules.schema_builder import (
    build_llm_schema,
    save_schema
)

from Modules.Agents.Agent_sql import sql_agent

from Modules.visualisation import (
    choose_visual,
    build_visual_metadata
)

from Modules.benchmark_utils import (
    analyze_sql
)


# ============================================================
# DISPLAY VALIDATION REPORT
# ============================================================

def display_validation_report(result):

    generation_time = result["generation_time"]
    validation_time = result["validation_time"]
    execution_time = result["execution_time"]

    stage = result["stage"]

    print("\n" + "=" * 65)
    print("                 🔍 SQL VALIDATION REPORT")
    print("=" * 65)

    # --------------------------------------------------------
    # GENERATION
    # --------------------------------------------------------

    print("\n🤖 SQL GENERATION")

    if stage == "generation":
        print("   Status        : ❌ FAILED")
        print(f"   Error         : {result['error']}")
    else:
        print("   Status        : ✅ SUCCESS")

    print(f"   Time          : {generation_time:.3f} s")

    # --------------------------------------------------------
    # SCHEMA VALIDATION
    # --------------------------------------------------------

    print("\n📐 SCHEMA COMPATIBILITY")

    validation = result.get("validation")

    if validation is None:

        if stage in ["generation", "extraction"]:
            print("   Status        : ⏭️ NOT REACHED")

        else:
            print("   Status        : ❌ FAILED")

    else:

        schema_valid = validation.get(
            "schema_valid",
            False
        )

        if schema_valid:

            print("   Status        : ✅ PASS")
            print(
                "   Tables/columns referenced by the query "
                "are compatible with the available schema."
            )

        else:

            print("   Status        : ❌ FAIL")

            schema_errors = validation.get(
                "schema_errors",
                []
            )

            for error in schema_errors:
                print(f"      • {error}")

    print(f"   Time          : {validation_time:.3f} s")

    # --------------------------------------------------------
    # SQL EXECUTION
    # --------------------------------------------------------

    print("\n⚙️ SQL EXECUTION")

    if stage == "completed":

        print("   Status        : ✅ PASS")
        print("   SQL executed successfully.")

    elif stage == "execution":

        print("   Status        : ❌ FAIL")
        print(f"   Error         : {result['error']}")

    else:

        print("   Status        : ⏭️ NOT REACHED")
        print("   SQL was not executed.")

    print(f"   Time          : {execution_time:.3f} s")

    # --------------------------------------------------------
    # OVERALL
    # --------------------------------------------------------

    print("\n🏁 OVERALL STATUS")

    if result["success"]:

        print("   ✅ VALID & EXECUTABLE")

    else:

        print("   ❌ QUERY REJECTED")

        if result["error"]:
            print(f"\n   Reason: {result['error']}")

    # --------------------------------------------------------
    # PERFORMANCE
    # --------------------------------------------------------

    print("\n⏱️ PERFORMANCE")
    print(f"   Generation     : {generation_time:.3f} s")
    print(f"   Validation     : {validation_time:.3f} s")
    print(f"   Execution      : {execution_time:.3f} s")

    print("=" * 65)


# ============================================================
# MAIN
# ============================================================

def main():

    # ========================================================
    # 1. LOAD DATA
    # ========================================================

    print("🚀 Loading data...")

    data = load_data_folder("Logistics/")

    # ========================================================
    # 2. PROFILE DATA
    # ========================================================

    print("\n📊 Profiling data...\n")

    profile = profile_data(data)

    with open(
        "profile_output.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            profile,
            f,
            indent=4,
            default=str
        )

    # ========================================================
    # 3. BUILD SCHEMA
    # ========================================================

    print("\n🧠 Building LLM schema...\n")

    schema = build_llm_schema(profile)

    save_schema(schema)

    # ========================================================
    # 4. USER QUESTION
    # ========================================================

    question = input(
        "\n❓ Enter your question: "
    )

    # ========================================================
    # 5. RUN SQL AGENT
    # ========================================================

    print("\n🤖 Running SQL Generation Agent...\n")

    result = sql_agent(
        question,
        schema
    )

    # ========================================================
    # 6. DISPLAY RAW RESPONSE
    # ========================================================

    if result.get("raw_response") is not None:

        print("\n🔍 RAW LLM RESPONSE")
        print("-" * 65)
        print(result["raw_response"])
        print("-" * 65)

    # ========================================================
    # 7. DISPLAY EXTRACTED SQL
    # ========================================================

    if result.get("sql") is not None:

        print("\n📝 EXTRACTED SQL")
        print("-" * 65)
        print(result["sql"])
        print("-" * 65)

    # ========================================================
    # 8. DISPLAY VALIDATION REPORT
    # ========================================================

    display_validation_report(result)

    # ========================================================
    # 9. STOP IF AGENT FAILED
    # ========================================================

    if not result["success"]:

        print("\n❌ Query processing stopped.")
        print("   No SQL execution was performed.")

        return

    # ========================================================
    # 10. RESULT DATA
    # ========================================================

    df = result["result"]

    print("\n📊 RESULT DATA")
    print("-" * 65)

    print(df.head(10))

    print(f"\nRows returned: {len(df)}")

    # ========================================================
    # 11. SQL STRUCTURE
    # ========================================================

    analysis = analyze_sql(
        result["sql"]
    )

    print("\n🧠 SQL STRUCTURE")
    print("-" * 65)

    print(
        json.dumps(
            analysis,
            indent=4
        )
    )

    # ========================================================
    # 12. VISUALIZATION
    # ========================================================

    visual_type = choose_visual(
        question,
        df
    )

    metadata = build_visual_metadata(
        df,
        visual_type
    )

    print("\n📈 VISUALIZATION")
    print("-" * 65)

    print(f"Chart type : {visual_type}")

    print("\nMetadata:")
    print(metadata)

    # ========================================================
    # 13. FINAL SUMMARY
    # ========================================================

    print("\n" + "=" * 65)
    print("                    ✅ QUERY COMPLETED")
    print("=" * 65)

    print(f"Question       : {question}")
    print("Schema         : PASS")
    print("Execution      : PASS")
    print(f"Rows returned  : {len(df)}")
    print(
        f"Generation     : "
        f"{result['generation_time']:.3f}s"
    )
    print(
        f"Validation     : "
        f"{result['validation_time']:.3f}s"
    )
    print(
        f"Execution      : "
        f"{result['execution_time']:.3f}s"
    )
    print(f"Visualization  : {visual_type}")

    print("=" * 65)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()