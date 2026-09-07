import pandas as pd
import os

def load_data_folder(folder_path):
    data = {}

    for file in os.listdir(folder_path):
        if file.endswith(".csv"):
            table_name = file.replace(".csv", "")
            file_path = os.path.join(folder_path, file)

            df = pd.read_csv(file_path)
            data[table_name] = df

            print(f"Loaded {table_name}")

    return data