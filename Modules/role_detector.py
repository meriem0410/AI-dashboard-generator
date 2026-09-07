import pandas as pd


def is_identifier(column_name: str) -> bool:
    """
    Detect identifier columns using their names.
    """

    column_name = column_name.lower()

    keywords = [
        "id",
        "_id",
        "code",
        "key",
        "number",
        "num"
    ]

    return any(keyword in column_name for keyword in keywords)


def is_primary_key_candidate(series: pd.Series) -> bool:
    """
    A primary key candidate must:

    - contain no missing values
    - contain unique values
    """

    return (

        series.isna().sum() == 0

        and

        series.nunique(dropna=False) == len(series)

    )


def is_foreign_key_candidate(column_name: str) -> bool:
    """
    Detect FK candidates only from their names.
    """

    column_name = column_name.lower()

    return (

        column_name.endswith("_id")

        or

        column_name.endswith("id")

    )


def detect_role(column_name: str,
                series: pd.Series):

    dtype = str(series.dtype)

    role = "attribute"

    if is_primary_key_candidate(series):

        role = "primary_key_candidate"

    elif is_foreign_key_candidate(column_name):

        role = "foreign_key_candidate"

    elif pd.api.types.is_bool_dtype(series):

        role = "boolean"

    elif pd.api.types.is_datetime64_any_dtype(series):

        role = "datetime"

    elif pd.api.types.is_numeric_dtype(series):

        if is_identifier(column_name):

            role = "identifier"

        else:

            role = "measure"

    else:

        unique_ratio = (

            series.nunique(dropna=True)

            /

            max(len(series), 1)

        )

        if unique_ratio < 0.20:

            role = "category"

    return role