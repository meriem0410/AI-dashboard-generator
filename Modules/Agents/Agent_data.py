from loader import load_data_folder, load_uploaded_files


def data_agent(source, source_type="folder"):
    """
    Data ingestion agent.

    Responsible for:
    - loading the dataset
    - validating the input
    - standardizing the data structure
    - generating ingestion metadata
    """

    print("\n📥 DATA INGESTION")
    print("=" * 60)

    # -------------------------
    # LOAD DATA
    # -------------------------

    if source_type == "folder":

        data = load_data_folder(source)

    elif source_type == "upload":

        data = load_uploaded_files(source)

    else:

        raise ValueError(
            f"Unsupported source type: {source_type}"
        )

    # -------------------------
    # VALIDATION
    # -------------------------

    if not data:

        raise ValueError(
            "No data could be loaded."
        )

    # -------------------------
    # METADATA
    # -------------------------

    metadata = {

        "source_type": source_type,

        "table_count": len(data),

        "tables": list(data.keys()),

        "total_rows": sum(
            len(df)
            for df in data.values()
        ),

        "total_columns": sum(
            len(df.columns)
            for df in data.values()
        )
    }

    # -------------------------
    # SUMMARY
    # -------------------------

    print("\n✅ Data ingestion completed")

    print(
        f"   Tables loaded : "
        f"{metadata['table_count']}"
    )

    print(
        f"   Total rows    : "
        f"{metadata['total_rows']}"
    )

    print(
        f"   Total columns : "
        f"{metadata['total_columns']}"
    )

    return {

        "data": data,

        "metadata": metadata
    }