import pandas as pd
import numpy as np
from Modules.role_detector import detect_role

def is_numeric_column(series):

    return (
        pd.api.types.is_numeric_dtype(series)
        and
        not pd.api.types.is_bool_dtype(series)
    )

def is_boolean_column(series):

    return pd.api.types.is_bool_dtype(series)

def is_datetime_column(series):
    return pd.api.types.is_datetime64_any_dtype(series)


def profile_numeric_column(series):

    clean = series.dropna()

    return {

        "min": clean.min() if not clean.empty else None,

        "max": clean.max() if not clean.empty else None,

        "mean": round(clean.mean(), 2) if not clean.empty else None,

        "median": round(clean.median(), 2) if not clean.empty else None,

        "std": round(clean.std(), 2) if not clean.empty else None,

        "q1": round(clean.quantile(0.25), 2) if not clean.empty else None,

        "q3": round(clean.quantile(0.75), 2) if not clean.empty else None

    }


def profile_text_column(series):

    clean = series.dropna().astype(str)

    avg_length = (
        round(clean.str.len().mean(), 2)
        if not clean.empty
        else 0
    )

    return {

        "categories": int(series.nunique(dropna=True)),

        "top_values": series.value_counts(dropna=False).head(10).to_dict(),

        "average_length": avg_length

    }


def profile_datetime_column(series):

    clean = series.dropna()

    return {

        "first_date": str(clean.min()) if not clean.empty else None,

        "last_date": str(clean.max()) if not clean.empty else None

    }


def profile_column(column_name,
                   series):

    column_profile = {

        "dtype": str(series.dtype),

        "role": detect_role(
            column_name,
            series
        ),

        "missing": int(series.isna().sum()),

        "missing_percentage": round(

            series.isna().mean() * 100,

            2

        ),

        "unique": int(series.nunique(dropna=True))

    }

    if is_numeric_column(series):

        column_profile["statistics"] = profile_numeric_column(series)

    elif is_datetime_column(series):

        column_profile["statistics"] = profile_datetime_column(series)

    elif is_boolean_column(series):

        column_profile["statistics"] = {

            "true_count": int((series == True).sum()),

            "false_count": int((series == False).sum())

        }

    else:

        column_profile["statistics"] = profile_text_column(series)

    return column_profile