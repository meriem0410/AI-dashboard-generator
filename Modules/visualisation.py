from config import engine
from config import client
# =========================
# choix du visuel
# =========================

def choose_visual(question, df=None):

    question = question.lower()

    # KPI
    # à revoir (ki naamel avg revenue of best client y proposi table / w ki yebda famma top toul yaatini line )
    if df is not None:
        if len(df.columns) == 1:
            return "card"

    # évolution temporelle
    if any(x in question for x in [
        "by month",
        "by year",
        "over time",
        "trend"
    ]):
        return "line"

    # top N
    if "top" in question:
        return "bar"

    # répartition
    if any(x in question for x in [
        "share",
        "distribution",
        "percentage",
        "proportion"
    ]):
        return "pie"

    return "table"
 # =====================
 # build metadata (x,y)
 # =====================
def build_visual_metadata(df, visual_type):

    metadata = {
        "chart": visual_type,
        "x": None,
        "y": None
    }

    cols = df.columns.tolist()

    # =====================
    # CARD
    # =====================
    if visual_type == "card":

        metadata["y"] = cols[0]
        return metadata

    # =====================
    # NUMERIC COLUMNS
    # =====================
    numeric_cols = df.select_dtypes(
        include=["int64", "float64", "int32", "float32"]
    ).columns.tolist()

    non_numeric_cols = [
        c for c in cols
        if c not in numeric_cols
    ]

    # =====================
    # LINE CHART
    # =====================
    if visual_type == "line":

        if len(cols) >= 2:
            metadata["x"] = cols[0]
            metadata["y"] = cols[1]

        return metadata

    # =====================
    # BAR CHART
    # =====================
    if visual_type == "bar":

        if non_numeric_cols:
            metadata["x"] = non_numeric_cols[0]

        if numeric_cols:
            metadata["y"] = numeric_cols[0]

        return metadata

    # =====================
    # PIE CHART
    # =====================
    if visual_type == "pie":

        if non_numeric_cols:
            metadata["x"] = non_numeric_cols[0]

        if numeric_cols:
            metadata["y"] = numeric_cols[0]

        return metadata

    # =====================
    # TABLE
    # =====================
    return metadata
