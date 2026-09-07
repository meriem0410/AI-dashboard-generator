import time
import pandas as pd

from loader import load_data_folder

from Modules.profiler import profile_data

from Modules.schema_builder import build_llm_schema

from Modules.sql_generator import (
    generate_sql,
    safe_generate_sql)

MODELS = {
    "llama": "llama-3.3-70b-versatile",
    "qwen": "qwen/qwen3-32b"
}

def compare_models():

    print("Loading data...")

    data = load_data_folder("Logistics/")
    profile = profile_data(data)
    schema = build_llm_schema(profile)

    questions = [
        "top 5 customers by revenue",
        "total revenue by customer_id",
        "average mpg by driver_id",
        "top 10 drivers by trips_completed",
        "fuel_gallons_used by month",
        "total cost by truck_id",
        "revenue by month",
        "revenue by year",
        "top 5 routes by revenue",
        "average detention_minutes by driver_id"
    ]

    results = []

    for question in questions:


        row = {"question": question}

        generated_sql = {}

        for model_name, model_id in MODELS.items():

            start = time.time()

            sql = safe_generate_sql(
                question,
                schema,
                model=model_id
            )

            elapsed = round(time.time() - start, 3)

            row[f"{model_name}_sql"] = sql
            row[f"{model_name}_time"] = elapsed

            generated_sql[model_name] = sql

        results.append(row)

    df = pd.DataFrame(results)

    df.to_csv(
        "benchmark_results.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("\nBenchmark saved to benchmark_results.csv")

    print("\nSUMMARY")
    print("=" * 40)

    for model in MODELS:

        print(
            f"Average {model} time: "
            f"{df[f'{model}_time'].mean():.3f}s"
        )


if __name__ == "__main__":
    compare_models()