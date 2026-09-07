import pandas as pd


def get_table_statistics(df: pd.DataFrame) -> dict:
    """
    Compute global statistics for a table.
    """

    rows = len(df)
    columns = len(df.columns)

    memory_mb = round(
        df.memory_usage(deep=True).sum() / (1024 ** 2),
        2
    )

    duplicate_rows = int(df.duplicated().sum())

    missing_cells = int(df.isna().sum().sum())

    total_cells = rows * columns

    missing_percentage = round(
        (missing_cells / total_cells) * 100,
        2
    ) if total_cells > 0 else 0

    return {
        "rows": rows,
        "columns": columns,
        "memory_mb": memory_mb,
        "duplicate_rows": duplicate_rows,
        "missing_cells": missing_cells,
        "missing_percentage": missing_percentage
    }


def detect_constant_columns(df: pd.DataFrame):
    """
    Detect columns containing a single unique value.
    """

    constant_columns = []

    for column in df.columns:

        if df[column].nunique(dropna=False) == 1:
            constant_columns.append(column)

    return constant_columns


def detect_near_constant_columns(df: pd.DataFrame,
                                 threshold: float = 0.95):
    """
    Detect columns where one value represents more than threshold
    of the observations.
    """

    near_constant_columns = []

    for column in df.columns:

        if len(df) == 0:
            continue

        frequencies = df[column].value_counts(
            normalize=True,
            dropna=False
        )

        if len(frequencies) == 0:
            continue

        if frequencies.iloc[0] >= threshold:
            near_constant_columns.append(column)

    return near_constant_columns


def profile_table(df: pd.DataFrame):
    """
    Generate V1 profile for one table.
    """

    stats = get_table_statistics(df)

    profile = {

        **stats,

        "quality": {

            "constant_columns":
                detect_constant_columns(df),

            "near_constant_columns":
                detect_near_constant_columns(df)

        }

    }

    return profile