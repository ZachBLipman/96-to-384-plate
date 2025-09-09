import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import re

# -----------------------------------------------------------------------------
# Custom 96-well interleaved order (A/B, then C/D, then E/F, then G/H)
# -----------------------------------------------------------------------------
CUSTOM_96_ORDER = [
    "A1","B1","A2","B2","A3","B3","A4","B4","A5","B5","A6","B6","A7","B7","A8","B8","A9","B9","A10","B10","A11","B11","A12","B12",
    "C1","D1","C2","D2","C3","D3","C4","D4","C5","D5","C6","D6","C7","D7","C8","D8","C9","D9","C10","D10","C11","D11","C12","D12",
    "E1","F1","E2","F2","E3","F3","E4","F4","E5","F5","E6","F6","E7","F7","E8","F8","E9","F9","E10","F10","E11","F11","E12","F12",
    "G1","H1","G2","H2","G3","H3","G4","H4","G5","H5","G6","H6","G7","H7","G8","H8","G9","H9","G10","H10","G11","H11","G12","H12",
]
ORDER_INDEX_96 = {w: i for i, w in enumerate(CUSTOM_96_ORDER)}
BIG_POS = 10_000  # unknowns go to end of their plate

def pos96(well: str) -> int:
    if pd.isna(well):
        return BIG_POS
    return ORDER_INDEX_96.get(str(well).strip().upper(), BIG_POS)

# -----------------------------------------------------------------------------
# Plate utilities
# -----------------------------------------------------------------------------
def compute_global_384_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds Global_384_Position = row-major index across groups of four 96-well plates.
    """
    rows_384 = list("ABCDEFGHIJKLMNOP")
    cols_384 = list(range(1, 25))
    well_384_positions = [f"{r}{c}" for r in rows_384 for c in cols_384]
    well_384_index = {well: i + 1 for i, well in enumerate(well_384_positions)}

    df['Plate'] = pd.to_numeric(df['Plate'], errors='coerce')

    def get_index(row):
        plate = row.get('Plate', np.nan)
        local = well_384_index.get(str(row.get('384 Well', '')).strip().upper(), None)
        if pd.notnull(plate) and local is not None:
            plate_group = int((plate - 1) // 4)
            return plate_group * 384 + local
        return None

    df['Global_384_Position'] = df.apply(get_index, axis=1)
    return df

def extract_sortable_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only rows that have Plate, 96 Well, and 384 Well populated.
    (This mirrors your original intent and ensures stable reinsertion.)
    """
    return df[df[['Plate', '96 Well', '384 Well']].notnull().all(axis=1)].copy()

def inject_sorted_back(original_df: pd.DataFrame, sorted_rows: pd.DataFrame) -> pd.DataFrame:
    """
    Replaces only the sortable rows in their original positions with the newly-sorted ones.
    Non-sortable rows remain untouched and in place.
    """
    sorted_iter = iter(sorted_rows.to_dict(orient='records'))
    result_rows = []
    for _, row in original_df.iterrows():
        if pd.notnull(row.get('Plate')) and pd.notnull(row.get('96 Well')) and pd.notnull(row.get('384 Well')):
            result_rows.append(next(sorted_iter))
        else:
            result_rows.append(row.to_dict())
    return pd.DataFrame(result_rows)

# --- (old generic A1..H12 key kept for reference; no longer used) ---
def sort_96_well_labels(well_label):
    match = re.match(r"([A-H])([0-9]{1,2})", str(well_label))
    if match:
        row_letter = match.group(1)
        col_number = int(match.group(2))
        return (row_letter, col_number)
    return ("Z", 99)  # fallback

# -----------------------------------------------------------------------------
# Sorting toggle
# -----------------------------------------------------------------------------
def sort_by_toggle(df: pd.DataFrame, view_mode: str) -> pd.DataFrame:
    """
    - '96-well layout'  : sort by Plate, then CUSTOM_96_ORDER interleaving (A/B, C/D, E/F, G/H)
    - '384-well layout' : sort by Global_384_Position (precomputed)
    """
    sortable = extract_sortable_rows(df)

    if view_mode == '96-well layout':
        # Ensure numeric plates so "10" doesn't come before "2"
        sortable['Plate'] = pd.to_numeric(sortable['Plate'], errors='coerce')

        # Stable two-step: group by Plate, then apply custom position within plate
        sortable = (
            sortable
            .sort_values(['Plate'], kind='mergesort')
            .assign(_pos=sortable['96 Well'].map(pos96))
            .sort_values(['Plate', '_pos'], ascending=[True, True], kind='mergesort')
            .drop(columns=['_pos'])
        )

    elif view_mode == '384-well layout':
        # Assumes compute_global_384_index already ran
        sortable = sortable.sort_values(by='Global_384_Position', kind='mergesort')

    else:
        return df

    return inject_sorted_back(df, sortable)

# -----------------------------------------------------------------------------
# Download helper
# -----------------------------------------------------------------------------
def download_link(df: pd.DataFrame, filename: str) -> BytesIO:
    towrite = BytesIO()
    df.to_excel(towrite, index=False, sheet_name="Sorted")
    towrite.seek(0)
    return towrite

# -----------------------------------------------------------------------------
# Header detection
# -----------------------------------------------------------------------------
REQUIRED_COLUMNS = {'96 Well', '384 Well', 'Plate'}

def find_header_row(df: pd.DataFrame, required_columns: set) -> int | None:
    for i in range(min(20, len(df))):
        row = df.iloc[i]
        if required_columns.issubset(set(row.values)):
            return i
    return None

# -----------------------------------------------------------------------------
# Streamlit UI
# -----------------------------------------------------------------------------
st.title("Plate Layout Toggler: 96-Well ⇄ 384-Well (with custom 96-well order)")

uploaded_file = st.file_uploader("Upload your Excel or CSV file", type=["xlsx", "csv"])

if uploaded_file is not None:
    st.write("📄 Preview of first 20 rows:")
    if uploaded_file.name.endswith(".csv"):
        preview_df = pd.read_csv(uploaded_file, header=None)
    else:
        preview_df = pd.read_excel(uploaded_file, header=None)

    st.dataframe(preview_df.head(20))

    st.markdown("### 🔍 Header Row Detection")
    auto_header_row = find_header_row(preview_df, REQUIRED_COLUMNS)
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

    # Load full data using the selected header
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file, header=selected_row)
    else:
        df = pd.read_excel(uploaded_file, header=selected_row)

    if REQUIRED_COLUMNS.issubset(df.columns):
        # Precompute 384 global index (used for the 384-well layout option)
        df = compute_global_384_index(df)

        view_mode = st.radio("Toggle view mode:", ["96-well layout", "384-well layout"], horizontal=True)
        sorted_df = sort_by_toggle(df, view_mode)

        st.write(f"### Displaying data in **{view_mode}**")
        st.dataframe(sorted_df.reset_index(drop=True))

        output = download_link(sorted_df, "sorted_plate_layout.xlsx")
        st.download_button("Download Sorted File", data=output, file_name="sorted_plate_layout.xlsx")
    else:
        st.error(f"The selected row does not contain all required columns: {REQUIRED_COLUMNS}")
