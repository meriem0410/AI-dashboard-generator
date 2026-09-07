from config import engine
from config import client
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine(
    "mssql+pyodbc://localhost/LogisticsDB?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
)

def execute_sql(sql):
    try:
        return pd.read_sql(sql, engine)
    except Exception as e:
        print(e)
        return None