import re
import pandas as pd


# ============================================================
# 1. NAME NORMALIZATION
# ============================================================

def normalize_name(name: str) -> str:
    name = str(name).strip().lower()

    name = re.sub(
        r"([a-z0-9])([A-Z])",
        r"\1_\2",
        name
    )

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

    column_tokens = tokens(column_name)

    if (
        len(column_tokens) >= 2
        and column_tokens[-1] == "id"
    ):
        return True

    if (
        len(column_tokens) >= 2
        and column_tokens[-1] in {
            "key",
            "ref",
            "reference",
        }
    ):
        return True

    return False


# ============================================================
# 3. BASIC SERIES STATISTICS
# ============================================================

def build_series_stats(series: pd.Series) -> dict:
    """
    Compute expensive statistics ONCE per column.

    These values are reused during relationship detection.
    """

    clean = series.dropna()

    if clean.empty:
        return {
            "empty": True,
            "unique_count": 0,
            "non_null_count": 0,
            "is_unique": False,
            "unique_values": set(),
        }

    unique_values = set(clean.unique())

    unique_count = len(unique_values)
    non_null_count = len(clean)

    return {
        "empty": False,
        "unique_count": unique_count,
        "non_null_count": non_null_count,
        "is_unique": unique_count == non_null_count,
        "unique_values": unique_values,
    }


# ============================================================
# 4. TYPE COMPATIBILITY
# ============================================================

def series_type(series: pd.Series) -> str:
    """
    Convert pandas dtype into a simple compatibility category.
    """

    if pd.api.types.is_numeric_dtype(series):
        return "numeric"

    if (
        pd.api.types.is_object_dtype(series)
        or pd.api.types.is_string_dtype(series)
    ):
        return "string"

    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"

    if pd.api.types.is_bool_dtype(series):
        return "boolean"

    return "other"


def compatible_types(
    source_series: pd.Series,
    target_series: pd.Series
) -> bool:

    source_type = series_type(source_series)
    target_type = series_type(target_series)

    if source_type == target_type:
        return source_type in {
            "numeric",
            "string",
            "datetime",
            "boolean",
        }

    return False


# ============================================================
# 5. NAME SIMILARITY
# ============================================================

def column_name_similarity(
    source_column: str,
    target_column: str
) -> float:

    source = normalize_name(source_column)
    target = normalize_name(target_column)

    if source == target:
        return 1.0

    source_tokens = set(tokens(source))
    target_tokens = set(tokens(target))

    if not source_tokens or not target_tokens:
        return 0.0

    intersection = source_tokens.intersection(
        target_tokens
    )

    return len(intersection) / len(
        source_tokens.union(target_tokens)
    )


# ============================================================
# 6. TABLE/COLUMN ENTITY MATCH
# ============================================================

def table_column_match(
    source_table: str,
    source_column: str,
    target_table: str,
    target_column: str
) -> float:

    source_tokens = set(tokens(source_column))
    target_table_tokens = set(tokens(target_table))

    score = 0.0

    if source_tokens.intersection(
        target_table_tokens
    ):
        score += 0.5

    if normalize_name(source_column) == normalize_name(
        target_column
    ):
        score += 0.5

    return min(score, 1.0)


# ============================================================
# 7. CANDIDATE KEYS
# ============================================================

def candidate_keys(
    data: dict,
    profile: dict,
    stats: dict
):
    """
    Identify candidate keys using statistics already computed.
    """

    keys = []

    for table_name, table_profile in profile.items():

        if table_name == "relationships":
            continue

        if "columns" not in table_profile:
            continue

        for column_name, column_profile in (
            table_profile["columns"].items()
        ):

            role = column_profile.get("role")

            if role not in {
                "identifier",
                "primary_key_candidate",
            }:
                continue

            column_stats = stats[
                table_name
            ][column_name]

            if column_stats["is_unique"]:

                keys.append({
                    "table": table_name,
                    "column": column_name,
                    "unique_ratio": 1.0,
                    "values": column_stats[
                        "unique_values"
                    ],
                    "type": column_stats["type"],
                })

    return keys


# ============================================================
# 8. FOREIGN KEY CANDIDATES
# ============================================================

def foreign_key_candidates(
    data: dict,
    profile: dict
):

    candidates = []

    for table_name, table_profile in profile.items():

        if table_name == "relationships":
            continue

        if "columns" not in table_profile:
            continue

        for column_name in table_profile["columns"]:

            if is_fk_like_name(column_name):

                candidates.append({
                    "table": table_name,
                    "column": column_name,
                })

    return candidates


# ============================================================
# 9. VALUE OVERLAP
# ============================================================

def calculate_overlap_from_sets(
    source_values: set,
    target_values: set
) -> float:

    if not source_values:
        return 0.0

    common = source_values.intersection(
        target_values
    )

    return len(common) / len(source_values)


# ============================================================
# 10. RELATIONSHIP SCORE
# ============================================================

def relationship_score(
    source_table: str,
    source_column: str,
    target_table: str,
    target_column: str,
    source_stats: dict,
    target_stats: dict,
    type_match: bool
):

    overlap = calculate_overlap_from_sets(
        source_stats["unique_values"],
        target_stats["unique_values"]
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

    target_unique = target_stats["is_unique"]

    score = 0.0

    score += overlap * 0.55

    if type_match:
        score += 0.10

    score += name_score * 0.15

    score += semantic_match * 0.10

    if target_unique:
        score += 0.10

    return {
        "confidence": round(
            min(score, 1.0),
            2
        ),
        "overlap": round(
            overlap,
            2
        ),
        "name_similarity": round(
            name_score,
            2
        ),
        "type_match": type_match,
        "target_unique": target_unique,
    }


# ============================================================
# 11. MAIN RELATIONSHIP DETECTOR
# ============================================================

def detect_relationships(
    data: dict,
    profile: dict
):

    # --------------------------------------------------------
    # PRECOMPUTE STATISTICS ONCE
    # --------------------------------------------------------

    stats = {}

    for table_name, df in data.items():

        stats[table_name] = {}

        for column_name in df.columns:

            column_stats = build_series_stats(
                df[column_name]
            )

            column_stats["type"] = series_type(
                df[column_name]
            )

            stats[table_name][column_name] = (
                column_stats
            )

    # --------------------------------------------------------
    # CANDIDATES
    # --------------------------------------------------------

    keys = candidate_keys(
        data,
        profile,
        stats
    )

    fk_candidates = foreign_key_candidates(
        data,
        profile
    )

    relationships = []

    # --------------------------------------------------------
    # RELATIONSHIP SEARCH
    # --------------------------------------------------------

    for fk in fk_candidates:

        source_table = fk["table"]
        source_column = fk["column"]

        source_stats = stats[
            source_table
        ][source_column]

        source_type = source_stats["type"]

        if source_stats["empty"]:
            continue

        for key in keys:

            target_table = key["table"]
            target_column = key["column"]

            if source_table == target_table:
                continue

            target_stats = stats[
                target_table
            ][target_column]

            # ------------------------------------------------
            # TYPE FILTER
            # ------------------------------------------------

            if source_type != target_stats["type"]:
                continue

            # ------------------------------------------------
            # NAME FILTER
            # ------------------------------------------------
            #
            # Strong name mismatch + no shared entity
            # = unlikely relationship.
            #
            # We still allow exact column matches and
            # table/column semantic matches.
            # ------------------------------------------------

            name_score = column_name_similarity(
                source_column,
                target_column
            )

            semantic_score = table_column_match(
                source_table,
                source_column,
                target_table,
                target_column
            )

            if (
                name_score == 0
                and semantic_score == 0
            ):
                continue

            # ------------------------------------------------
            # OVERLAP
            # ------------------------------------------------

            result = relationship_score(
                source_table,
                source_column,
                target_table,
                target_column,
                source_stats,
                target_stats,
                True
            )

            if result["overlap"] >= 0.80:

                relationships.append({
                    "from_table": source_table,
                    "from_column": source_column,
                    "to_table": target_table,
                    "to_column": target_column,
                    "confidence": result[
                        "confidence"
                    ],
                    "overlap": result[
                        "overlap"
                    ],
                    "name_similarity": result[
                        "name_similarity"
                    ],
                })

    # ========================================================
    # REMOVE DUPLICATE / WEAKER RELATIONSHIPS
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

        candidates.sort(
            key=lambda x: (
                x["confidence"],
                x["overlap"],
                x["name_similarity"]
            ),
            reverse=True
        )

        best = candidates[0]

        for candidate in candidates:

            if (
                candidate["confidence"] >= 0.80
                or
                candidate["confidence"]
                >= best["confidence"] - 0.10
            ):
                final_relationships.append(
                    candidate
                )

    return final_relationships