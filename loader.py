import os
import pandas as pd


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def load_data_folder(folder_path):
    """
    Load CSV/Excel files from a local folder.

    Returns:
        dict[str, pd.DataFrame]
    """

    if not os.path.exists(folder_path):
        raise FileNotFoundError(
            f"Dataset folder not found: {folder_path}"
        )

    if not os.path.isdir(folder_path):
        raise ValueError(
            f"Expected a directory: {folder_path}"
        )

    data = {}

    for filename in sorted(os.listdir(folder_path)):

        file_path = os.path.join(folder_path, filename)

        if not os.path.isfile(file_path):
            continue

        name, extension = os.path.splitext(filename)
        extension = extension.lower()

        if extension not in SUPPORTED_EXTENSIONS:
            continue

        try:

            if extension == ".csv":

                df = pd.read_csv(file_path)
                table_name = name

                data[table_name] = df

                print(
                    f"   ✓ {table_name} "
                    f"({len(df)} rows, {len(df.columns)} columns)"
                )

            elif extension in {".xlsx", ".xls"}:

                sheets = pd.read_excel(
                    file_path,
                    sheet_name=None
                )

                for sheet_name, df in sheets.items():

                    table_name = f"{name}_{sheet_name}"

                    data[table_name] = df

                    print(
                        f"   ✓ {table_name} "
                        f"({len(df)} rows, {len(df.columns)} columns)"
                    )

        except Exception as e:

            print(
                f"   ✗ Failed to load {filename}: {e}"
            )

    if not data:
        raise ValueError(
            "No supported data files were found."
        )

    return data


def load_uploaded_files(uploaded_files):
    """
    Load files uploaded through Streamlit.

    Returns:
        dict[str, pd.DataFrame]
    """

    data = {}

    for uploaded_file in uploaded_files:

        filename = uploaded_file.name

        name, extension = os.path.splitext(filename)
        extension = extension.lower()

        try:

            if extension == ".csv":

                df = pd.read_csv(uploaded_file)

                table_name = name

                data[table_name] = df

            elif extension in {".xlsx", ".xls"}:

                sheets = pd.read_excel(
                    uploaded_file,
                    sheet_name=None
                )

                for sheet_name, df in sheets.items():

                    table_name = f"{name}_{sheet_name}"

                    data[table_name] = df

            else:

                print(
                    f"⚠ Unsupported file: {filename}"
                )

        except Exception as e:

            print(
                f"✗ Failed to load {filename}: {e}"
            )

    if not data:
        raise ValueError(
            "No supported files could be loaded."
        )

    return data