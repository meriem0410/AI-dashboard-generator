import re
import pandas as pd


# ============================================================
# 1. NAME NORMALIZATION
# ============================================================

def normalize_name(column_name: str) -> str:
    """
    Normalize a column name so semantic rules work across
    snake_case, camelCase, kebab-case, etc.
    """
    name = str(column_name).strip().lower()

    # camelCase -> camel_Case
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)

    # Replace separators with _
    name = re.sub(r"[\s\-]+", "_", name)

    # Remove repeated underscores
    name = re.sub(r"_+", "_", name)

    return name


def name_tokens(column_name: str) -> list[str]:
    """
    Split a column name into semantic tokens.
    """
    name = normalize_name(column_name)

    return [
        token
        for token in re.split(r"[_\W]+", name)
        if token
    ]


# ============================================================
# 2. SEMANTIC VOCABULARIES
# ============================================================

IDENTIFIER_TOKENS = {
    "id",
    "identifier",
    "uuid",
    "guid",
    "code",
    "key",
    "serial",
    "reference",
    "ref",
}

DATETIME_TOKENS = {
    "date",
    "datetime",
    "timestamp",
    "time",
    "created",
    "updated",
    "modified",
    "occurred",
    "scheduled",
    "effective",
    "expiry",
    "expiration",
    "terminated",
    "acquisition",
    "hire",
    "birth",
    "start",
    "end",
}

YEAR_TOKENS = {
    "year",
    "yr",
}

MEASURE_TOKENS = {
    "amount",
    "revenue",
    "income",
    "cost",
    "price",
    "profit",
    "salary",
    "fee",
    "charge",
    "expense",
    "distance",
    "mileage",
    "weight",
    "height",
    "width",
    "length",
    "volume",
    "capacity",
    "quantity",
    "qty",
    "count",
    "number_of",
    "total",
    "average",
    "avg",
    "rate",
    "ratio",
    "percentage",
    "percent",
    "duration",
    "hours",
    "minutes",
    "days",
    "speed",
    "temperature",
    "score",
    "rating",
}

DESCRIPTIVE_TOKENS = {
    "name",
    "description",
    "comment",
    "notes",
    "address",
    "text",
    "label",
    "title",
}


# ============================================================
# 3. BASIC TYPE DETECTION
# ============================================================

def is_numeric_column(series: pd.Series) -> bool:
    return (
        pd.api.types.is_numeric_dtype(series)
        and not pd.api.types.is_bool_dtype(series)
    )


def is_boolean_column(series: pd.Series) -> bool:
    return pd.api.types.is_bool_dtype(series)


def is_datetime_column(series: pd.Series) -> bool:
    return pd.api.types.is_datetime64_any_dtype(series)


# ============================================================
# 4. NAME-BASED SEMANTIC SIGNALS
# ============================================================
def contains_number_identifier_token(column_name: str) -> bool:
    tokens = name_tokens(column_name)

    if len(tokens) < 2:
        return False

    # number_of_orders, number_of_trips, etc. are measures
    if "number" in tokens and "of" in tokens:
        return False

    return tokens[-1] in {"number", "num", "no"}


def contains_identifier_token(column_name: str) -> bool:
    tokens = name_tokens(column_name)

    if any(token in IDENTIFIER_TOKENS for token in tokens):
        return True

    return contains_number_identifier_token(column_name)


def contains_datetime_token(column_name: str) -> bool:
    tokens = name_tokens(column_name)
    return any(token in DATETIME_TOKENS for token in tokens)


def contains_year_token(column_name: str) -> bool:
    tokens = name_tokens(column_name)
    return any(token in YEAR_TOKENS for token in tokens)


def contains_measure_token(column_name: str) -> bool:
    tokens = name_tokens(column_name)

    # Direct token match
    if any(token in MEASURE_TOKENS for token in tokens):
        return True

    # Handle patterns such as:
    # number_of_orders
    # total_revenue
    # average_cost
    for i in range(len(tokens) - 1):
        if tokens[i] in {"number", "total", "average", "avg"}:
            if tokens[i + 1] in {
                "of",
                "amount",
                "cost",
                "revenue",
                "orders",
                "items",
                "units",
                "customers",
                "records",
            }:
                return True

    return False


def contains_descriptive_token(column_name: str) -> bool:
    tokens = name_tokens(column_name)
    return any(token in DESCRIPTIVE_TOKENS for token in tokens)


# ============================================================
# 5. STATISTICAL SIGNALS
# ============================================================

def uniqueness_ratio(series: pd.Series) -> float:
    """
    Ratio of distinct non-null values to total rows.
    """
    if len(series) == 0:
        return 0.0

    return series.nunique(dropna=True) / len(series)


def is_unique(series: pd.Series) -> bool:
    """
    Check uniqueness among non-null values.
    """
    clean = series.dropna()

    if clean.empty:
        return False

    return clean.nunique() == len(clean)


def is_non_null(series: pd.Series) -> bool:
    return series.isna().sum() == 0


# ============================================================
# 6. DATETIME DETECTION
# ============================================================
DATETIME_SAMPLE_SIZE = 1000


def datetime_parse_ratio(series: pd.Series, sample_size: int = DATETIME_SAMPLE_SIZE) -> float:
    """
    Estimate datetime parseability using a sample instead of
    parsing the entire column.
    """

    clean = series.dropna()

    if clean.empty:
        return 0.0

    # Already small enough: parse everything.
    if len(clean) <= sample_size:
        sample = clean
    else:
        # Fixed deterministic sample for reproducibility.
        sample = clean.sample(
            n=sample_size,
            random_state=42
        )

    parsed = pd.to_datetime(
        sample,
        errors="coerce",
        utc=True,
        format="mixed"
    )

    return parsed.notna().mean()


def looks_like_datetime(column_name: str, series: pd.Series) -> bool:
    """
    Detect datetime columns efficiently.

    Strategy:
    1. Real pandas datetime dtype -> datetime.
    2. Strong date-related column name -> sample values.
    3. Otherwise only sample values to detect unnamed dates.
    """

    # --------------------------------------------------------
    # Already a real datetime dtype
    # --------------------------------------------------------

    if is_datetime_column(series):
        return True

    # --------------------------------------------------------
    # Only object/string columns need parsing
    # --------------------------------------------------------

    if not (
        pd.api.types.is_object_dtype(series)
        or pd.api.types.is_string_dtype(series)
    ):
        return False

    if series.dropna().empty:
        return False

    has_datetime_name = contains_datetime_token(column_name)

    # --------------------------------------------------------
    # Sample instead of parsing the whole column
    # --------------------------------------------------------

    parse_ratio = datetime_parse_ratio(series)

    # Strong date name + highly parseable values
    if has_datetime_name and parse_ratio >= 0.95:
        return True

    # No obvious date name:
    # require extremely strong evidence.
    if not has_datetime_name and parse_ratio >= 0.99:
        return True

    return False


# ============================================================
# 7. IDENTIFIER DETECTION
# ============================================================

def is_identifier_like(column_name: str, series: pd.Series) -> bool:
    """
    Detect columns that behave like identifiers.

    IMPORTANT:
    This does NOT mean the column is a primary key or foreign key.
    Those are relationship-level concepts handled elsewhere.
    """

    if contains_identifier_token(column_name):
        return True

    # A highly unique string column can be an identifier even
    # when its name doesn't explicitly contain "id".
    if (
        (pd.api.types.is_object_dtype(series)
         or pd.api.types.is_string_dtype(series))
        and uniqueness_ratio(series) >= 0.95
    ):
        return True

    return False


# ============================================================
# 8. NUMERIC SEMANTICS
# ============================================================

def looks_like_year(series: pd.Series) -> bool:
    """
    Detect numeric year-like values.

    This is intentionally based on value range rather than
    dataset-specific column names.
    """
    if not is_numeric_column(series):
        return False

    clean = series.dropna()

    if clean.empty:
        return False

    # Typical year range.
    # Broad enough for historical and modern datasets.
    return (
        clean.min() >= 1000
        and clean.max() <= 3000
        and clean.nunique() <= max(300, len(clean) * 0.5)
    )


def is_discrete_numeric(series: pd.Series) -> bool:
    """
    Detect numeric columns that behave more like discrete
    attributes/counts than continuous measures.
    """
    if not is_numeric_column(series):
        return False

    clean = series.dropna()

    if clean.empty:
        return False

    unique_ratio = clean.nunique() / len(clean)

    # Very low-cardinality numeric variables are often
    # categorical/discrete values.
    return (
        clean.nunique() <= 20
        or unique_ratio <= 0.01
    )


# ============================================================
# 9. TEXT SEMANTICS
# ============================================================

def classify_text_column(column_name: str, series: pd.Series) -> str:
    """
    Distinguish category from general descriptive attribute.
    """

    clean = series.dropna()

    if clean.empty:
        return "attribute"

    unique_ratio = uniqueness_ratio(series)

    # Explicit descriptive semantics should override
    # pure cardinality.
    if contains_descriptive_token(column_name):
        return "attribute"

    # Low-cardinality text is useful as a category.
    if unique_ratio <= 0.20:
        return "category"

    return "attribute"


# ============================================================
# 10. MAIN ROLE DETECTOR
# ============================================================

def detect_role(column_name: str, series: pd.Series) -> str:

    # --------------------------------------------------------
    # 1. Boolean
    # --------------------------------------------------------

    if is_boolean_column(series):
        return "boolean"

    # --------------------------------------------------------
    # 2. Strong identifier semantics
    # --------------------------------------------------------
    #
    # IMPORTANT:
    # Check this BEFORE datetime detection.
    #
    # event_id
    # load_id
    # trip_id
    # fuel_purchase_id
    # fuel_card_number
    #
    # should never go through expensive datetime parsing.
    # --------------------------------------------------------

    if contains_identifier_token(column_name):
        return "identifier"

    # --------------------------------------------------------
    # 3. Datetime
    # --------------------------------------------------------

    if looks_like_datetime(column_name, series):
        return "datetime"

    # --------------------------------------------------------
    # 4. Numeric semantics
    # --------------------------------------------------------

    if is_numeric_column(series):

        if contains_year_token(column_name):
            return "attribute"

        if looks_like_year(series):
            return "attribute"

        if contains_measure_token(column_name):
            return "measure"

        return "measure"

    # --------------------------------------------------------
    # 5. Text
    # --------------------------------------------------------

    return classify_text_column(column_name, series)