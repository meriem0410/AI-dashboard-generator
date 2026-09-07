from config import engine
from config import client
from Modules.quality import profile_table
from Modules.Column_profiler import profile_column
from Modules.relationship_detector import detect_relationships
# PROFILING
# =========================


def profile_data(data):

    profile = {}

    for table_name, df in data.items():

        columns = {}

        for column in df.columns:

            columns[column] = profile_column(

                column,

                df[column]

            )

        profile[table_name] = {

            "table_info": profile_table(df),

            "columns": columns

        }

    profile["relationships"] = detect_relationships(

        data,

        profile

    )

    return profile