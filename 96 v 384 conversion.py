import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import re

# ----------------------------
# Plate utilities
# ----------------------------
def compute_global_384_index(df):
    rows_384 = list("ABCDEFGHIJKLMNOP")
    cols_384 = list(range(1, 25))
    well_384_positions = [f"{r}{c}" for r in rows_384 for c in cols_384]
    well_384_index = {well: i + 1 for i, well in enumerate(well_384_positions)}

    df['Plate'] = pd.to_numeric(df['Plate'], errors='coerce')

    def get_index(row):
        plate_group = (row['Plate'] - 1) // 4 if pd.notnull(row['Plate']) else None
        local_index = well_384_index.get(row['384 Well'], None)
        return plate_group * 384 + local_index if local_index is not None and plate_group is not None else None

    df['Global_384_Position'] = df.apply(get_index, axis=1)
    return df

def extract_sortable_rows(df):
    valid_rows = df[df[['Plate', '96 Well', '384 Well']].notnull().all(axis=1)].copy()
    return valid_rows

def inject_sorted_back(original_df, sorted_rows):
    sorted_iter = iter(sorted_rows.to_dict(orient='records'))
    result_rows = []
    for _, row in original_df.iterrows():
        if pd.notnull(row['Plate']) and pd.notnull(row['96 Well']) and pd.notnull(row['384 Well']):
            result_rows.append(next(sorted_iter))
        else:
            result_rows.append(row.to_dict())
    return pd.DataFrame(result_rows)

def sort_96_well_labels(well_label):
    match = re.match(r"([A-H])([0-9]{1,2})", str(well_label))
    if match:
        row_letter = match.group(1)
        col_number = int(match.group(2))
        return (row_letter, col_number)
    return ("Z", 99)  # Push unrecognized to the end

def sort_by_toggle(df, view_mode):
    sortable = extract_sortable_rows(df)
    if view_mode == '96-well layout':
        sortable = sortable.assign(_96Key=sortable['96 Well'].apply(sort_96_well_labels))
        sorted_rows = sortable.sort_values(by=['Plate', '_96Key'])
        sorted_rows = sorted_rows.drop(columns=['_96Key'])
    elif view_mode == '384-well layout':
        sorted_rows = sortable.sort_values(by='Global_384_Position')
    else:
        return df
    return inject_sorted_back(df, sorted_rows)

def download_link(df, filename):
    towrite = BytesIO()
    df.to_excel(towrite, index=False, sheet_name="Sorted")
    towrite.seek(0)
    return towrite

# ----------------------------
# Header detection
# ----------------------------
REQUIRED_COLUMNS = {'96 Well', '384 Well', 'Plate'}

def find_header_row(df, required_columns):
    for i in range(min(20, len(df))):
        row = df.iloc[i]
        if required_columns.issubset(set(row.values)):
            return i
    return None

# ----------------------------
# Streamlit UI
# ----------------------------
st.title("Plate Layout Toggler: 96-Well ⇄ 384-Well")

uploaded_file = st.file_uploader("Upload your Excel or CSV file", type=["xlsx", "csv"])

if uploaded_file is not None:
    st.write("📄 Preview of first 20 rows:")
    if uploaded_file.name.endswith(".csv"):
        preview_df = pd.read_csv(uploaded_file, header=None)
    else:
        preview_df = pd.read_excel(uploaded_file, header=None)

    st.dataframe(preview_df.head(20))

    auto_header_row = find_header_row(preview_df, REQUIRED_COLUMNS)
    st.markdown("### 🔍 Header Row Detection")
    if auto_header_row is not None:
        st.success(f"Automatically detected header row at index {auto_header_row}")
    else:
        st.warning("No header row detected automatically.")

    selected_row = st.number_input(
        "Select the row number to use as header:",
        min_value=0,
        max_value=min(50, len(preview_df) - 1),
        value=auto_header_row if auto_header_row is not None else 0,
        step=1
    )

    # Load full data using selected header
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file, header=selected_row)
    else:
        df = pd.read_excel(uploaded_file, header=selected_row)

    if REQUIRED_COLUMNS.issubset(df.columns):
        df = compute_global_384_index(df)
        view_mode = st.radio("Toggle view mode:", ["96-well layout", "384-well layout"])
        sorted_df = sort_by_toggle(df, view_mode)

        st.write(f"### Displaying data in **{view_mode}**")
        st.dataframe(sorted_df.reset_index(drop=True))

        output = download_link(sorted_df, "sorted_plate_layout.xlsx")
        st.download_button("Download Sorted File", data=output, file_name="sorted_plate_layout.xlsx")
    else:
        st.error(f"The selected row does not contain all required columns: {REQUIRED_COLUMNS}")
