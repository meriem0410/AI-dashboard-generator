import re
import pandas as pd


# ============================================================
# 1. NAME NORMALIZATION
# ============================================================

def normalize_name(name: str) -> str:
    """
    Normalize names for comparison.
    """
    name = str(name).strip().lower()

    # camelCase -> camel_Case
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)

    name = re.sub(r"[\s\-]+", "_", name)
    name = re.sub(r"_+", "_", name)

    return name


def tokens(name: str) -> list[str]:
    name = normalize_name(name)

    return [
        token
        for token in re.split(r"[_\W]+", name)
        if token
    ]


# ============================================================
# 2. FOREIGN-KEY NAME SIGNAL
# ============================================================

def is_fk_like_name(column_name: str) -> bool:
    """
    Detect strong FK naming patterns.

    IMPORTANT:
    This is only a candidate-generation signal.
    It does NOT prove that a relationship exists.
    """

    column_tokens = tokens(column_name)

    # Strongest common pattern:
    #
    # customer_id
    # truck_id
    # employee_id
    #
    if len(column_tokens) >= 2 and column_tokens[-1] == "id":
        return True

    # Other strong relational conventions:
    #
    # customer_key
    # account_code
    #
    # These are weaker than *_id and therefore are handled
    # conservatively.
    if len(column_tokens) >= 2 and column_tokens[-1] in {
        "key",
        "ref",
        "reference",
    }:
        return True

    return False


# ============================================================
# 3. CANDIDATE KEY DETECTION
# ============================================================

def is_candidate_key(series: pd.Series) -> bool:
    """
    A candidate key must be:
        - non-null
        - unique

    This is only a profiling candidate.
    It does not prove that the database defines it as PK.
    """

    clean = series.dropna()

    if clean.empty:
        return False

    return clean.nunique() == len(clean)


def candidate_keys(data: dict, profile: dict):
    """
    Identify candidate key columns for each table.

    We use the role assigned by role_detector when possible,
    but also verify uniqueness directly.
    """

    keys = []

    for table_name, table_profile in profile.items():

        # Skip global relationship entry
        if table_name == "relationships":
            continue

        if "columns" not in table_profile:
            continue

        for column_name, column_profile in table_profile["columns"].items():

            role = column_profile.get("role")

            if role not in {
                "identifier",
                "primary_key_candidate",
            }:
                continue

            series = data[table_name][column_name]

            if is_candidate_key(series):

                keys.append({
                    "table": table_name,
                    "column": column_name,
                    "unique_ratio": 1.0,
                })

    return keys


# ============================================================
# 4. SOURCE FK CANDIDATES
# ============================================================

def foreign_key_candidates(data: dict, profile: dict):
    """
    Find columns that look like possible foreign keys.

    We DO NOT classify them as FKs yet.

    They must later be validated against another table.
    """

    candidates = []

    for table_name, table_profile in profile.items():

        if table_name == "relationships":
            continue

        if "columns" not in table_profile:
            continue

        for column_name, column_profile in table_profile["columns"].items():

            if is_fk_like_name(column_name):

                candidates.append({
                    "table": table_name,
                    "column": column_name,
                })

    return candidates


# ============================================================
# 5. VALUE OVERLAP
# ============================================================

def calculate_overlap(
    source_series: pd.Series,
    target_series: pd.Series
) -> float:
    """
    Calculate the proportion of non-null source values that
    exist in the target column.
    """

    source_values = set(
        source_series.dropna().unique()
    )

    target_values = set(
        target_series.dropna().unique()
    )

    if not source_values:
        return 0.0

    common = source_values.intersection(target_values)

    return len(common) / len(source_values)


# ============================================================
# 6. TYPE COMPATIBILITY
# ============================================================

def compatible_types(
    source_series: pd.Series,
    target_series: pd.Series
) -> bool:
    """
    Basic type compatibility check.

    We intentionally don't require exact pandas dtype equality
    because CSV/Excel/database imports can represent the same
    identifier differently.
    """

    source_numeric = pd.api.types.is_numeric_dtype(source_series)
    target_numeric = pd.api.types.is_numeric_dtype(target_series)

    source_string = (
        pd.api.types.is_object_dtype(source_series)
        or pd.api.types.is_string_dtype(source_series)
    )

    target_string = (
        pd.api.types.is_object_dtype(target_series)
        or pd.api.types.is_string_dtype(target_series)
    )

    if source_numeric and target_numeric:
        return True

    if source_string and target_string:
        return True

    return False


# ============================================================
# 7. NAME SIMILARITY
# ============================================================

def column_name_similarity(
    source_column: str,
    target_column: str
) -> float:
    """
    Compare normalized column names.

    Exact name match is a strong signal.
    """

    source = normalize_name(source_column)
    target = normalize_name(target_column)

    if source == target:
        return 1.0

    source_tokens = set(tokens(source))
    target_tokens = set(tokens(target))

    if not source_tokens or not target_tokens:
        return 0.0

    intersection = source_tokens.intersection(target_tokens)

    return len(intersection) / len(source_tokens.union(target_tokens))


# ============================================================
# 8. TABLE/COLUMN ENTITY MATCH
# ============================================================

def table_column_match(
    source_table: str,
    source_column: str,
    target_table: str,
    target_column: str
) -> float:
    """
    Additional semantic signal used to distinguish multiple
    possible targets.

    Example:

        trips.load_id
            -> loads.load_id

    should score better than an unrelated table containing
    a load_id column.
    """

    source_tokens = set(tokens(source_column))
    target_table_tokens = set(tokens(target_table))
    target_column_tokens = set(tokens(target_column))

    score = 0.0

    # Target table name appears in source column
    if source_tokens.intersection(target_table_tokens):
        score += 0.5

    # Exact column name
    if normalize_name(source_column) == normalize_name(target_column):
        score += 0.5

    return min(score, 1.0)


# ============================================================
# 9. RELATIONSHIP SCORING
# ============================================================

def relationship_score(
    source_table: str,
    source_column: str,
    target_table: str,
    target_column: str,
    source_series: pd.Series,
    target_series: pd.Series
):
    """
    Calculate a confidence score from multiple independent
    signals.

    Signals:
        - value overlap
        - type compatibility
        - column name similarity
        - table/column semantic match
        - target uniqueness
    """

    overlap = calculate_overlap(
        source_series,
        target_series
    )

    type_match = compatible_types(
        source_series,
        target_series
    )

    name_score = column_name_similarity(
        source_column,
        target_column
    )

    semantic_match = table_column_match(
        source_table,
        source_column,
        target_table,
        target_column
    )

    target_unique = is_candidate_key(target_series)

    # --------------------------------------------------------
    # Weighted confidence
    # --------------------------------------------------------

    score = 0.0

    # Value overlap is the strongest empirical signal
    score += overlap * 0.55

    # Compatible types
    if type_match:
        score += 0.10

    # Column naming
    score += name_score * 0.15

    # Table/column semantic relationship
    score += semantic_match * 0.10

    # Target uniqueness
    if target_unique:
        score += 0.10

    return {
        "confidence": round(min(score, 1.0), 2),
        "overlap": round(overlap, 2),
        "name_similarity": round(name_score, 2),
        "type_match": type_match,
        "target_unique": target_unique,
    }


# ============================================================
# 10. MAIN RELATIONSHIP DETECTOR
# ============================================================

def detect_relationships(data: dict, profile: dict):
    """
    Detect cross-table foreign-key relationships.

    Process:

        1. Find candidate key columns.
        2. Find FK-like source columns.
        3. Compare source values against candidate keys.
        4. Validate datatype compatibility.
        5. Score semantic/name compatibility.
        6. Keep sufficiently strong relationships.
    """

    keys = candidate_keys(data, profile)

    fk_candidates = foreign_key_candidates(
        data,
        profile
    )

    relationships = []

    # --------------------------------------------------------
    # Compare every FK candidate with every candidate key
    # --------------------------------------------------------

    for fk in fk_candidates:

        source_table = fk["table"]
        source_column = fk["column"]

        source_series = data[source_table][source_column]

        # Don't compare a column against itself
        for key in keys:

            target_table = key["table"]
            target_column = key["column"]

            if source_table == target_table:
                continue

            target_series = data[target_table][target_column]

            # ------------------------------------------------
            # Basic type validation
            # ------------------------------------------------

            if not compatible_types(
                source_series,
                target_series
            ):
                continue

            # ------------------------------------------------
            # Calculate relationship confidence
            # ------------------------------------------------

            result = relationship_score(
                source_table,
                source_column,
                target_table,
                target_column,
                source_series,
                target_series
            )

            # ------------------------------------------------
            # Strong empirical relationship
            # ------------------------------------------------

            if result["overlap"] >= 0.80:

                relationships.append({
                    "from_table": source_table,
                    "from_column": source_column,
                    "to_table": target_table,
                    "to_column": target_column,
                    "confidence": result["confidence"],
                    "overlap": result["overlap"],
                    "name_similarity": result["name_similarity"],
                })

    # ========================================================
    # 11. REMOVE DUPLICATE / WEAKER RELATIONSHIPS
    # ========================================================

    final_relationships = []

    grouped = {}

    for relationship in relationships:

        source_key = (
            relationship["from_table"],
            relationship["from_column"]
        )

        grouped.setdefault(
            source_key,
            []
        ).append(relationship)

    for source_key, candidates in grouped.items():

        # Sort strongest first
        candidates.sort(
            key=lambda x: (
                x["confidence"],
                x["overlap"],
                x["name_similarity"]
            ),
            reverse=True
        )

        # Keep all very strong matches.
        # If several targets are possible, keep those that
        # are nearly as strong instead of arbitrarily deleting
        # legitimate relationships.
        best = candidates[0]

        for candidate in candidates:

            if (
                candidate["confidence"] >= 0.80
                or
                candidate["confidence"] >= best["confidence"] - 0.10
            ):
                final_relationships.append(candidate)

    return final_relationships