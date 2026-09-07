import pandas as pd


def detect_relationships(data, profile):
    """
    Detect relationships between tables using primary key candidates
    and foreign key candidates.
    """

    relationships = []

    # -------------------------
    # Collect PK candidates
    # -------------------------

    primary_keys = []

    for table_name, table_profile in profile.items():

        for column_name, column in table_profile["columns"].items():

            if column["role"] == "primary_key_candidate":

                primary_keys.append(

                    (table_name, column_name)

                )

    # -------------------------
    # Compare with FK candidates
    # -------------------------

    for source_table, source_df in data.items():

        for source_column in source_df.columns:

            source_role = profile[source_table]["columns"][source_column]["role"]

            if source_role != "foreign_key_candidate":
                continue

            fk_values = set(

                source_df[source_column]

                .dropna()

                .unique()

            )

            if len(fk_values) == 0:
                continue

            for target_table, target_column in primary_keys:

                if source_table == target_table:
                    continue

                pk_values = set(

                    data[target_table][target_column]

                    .dropna()

                    .unique()

                )

                common = fk_values.intersection(pk_values)

                confidence = len(common) / len(fk_values)

                if confidence >= 0.80:

                    relationships.append({

                        "from_table": source_table,

                        "from_column": source_column,

                        "to_table": target_table,

                        "to_column": target_column,

                        "confidence": round(confidence, 2)

                    })

    return relationships