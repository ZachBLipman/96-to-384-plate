import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import re
from difflib import SequenceMatcher

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
            plate_group = int((plate - 1) // 4)  # 4 x 96-well plates per 384
            return plate_group * 384 + local
        return None

    df['Global_384_Position'] = df.apply(get_index, axis=1)
    return df

def extract_sortable_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only rows that have Plate, 96 Well, and 384 Well populated.
    """
    return df[df[['Plate', '96 Well', '384 Well']].notnull().all(axis=1)].copy()

def inject_sorted_back(original_df: pd.DataFrame, sorted_rows: pd.DataFrame) -> pd.DataFrame:
    """
    Return sorted rows first, then append any non-sortable rows at the end.
    """
    # Get non-sortable rows (those missing any of the required columns)
    non_sortable = original_df[~(
        original_df[['Plate', '96 Well', '384 Well']].notnull().all(axis=1)
    )].copy()
    
    # Concatenate sorted rows first, then non-sortable rows
    result = pd.concat([sorted_rows, non_sortable], ignore_index=True)
    
    return result

# (legacy parser kept for reference; not used by the new custom order)
def sort_96_well_labels(well_label):
    match = re.match(r"([A-H])([0-9]{1,2})", str(well_label))
    if match:
        row_letter = match.group(1)
        col_number = int(match.group(2))
        return (row_letter, col_number)
    return ("Z", 99)

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
        sortable['Plate'] = pd.to_numeric(sortable['Plate'], errors='coerce')
        sortable = (
            sortable
            .sort_values(['Plate'], kind='mergesort')
            .assign(_pos=lambda x: x['96 Well'].map(pos96))
            .sort_values(['Plate', '_pos'], ascending=[True, True], kind='mergesort')
            .drop(columns=['_pos'])
        )

    elif view_mode == '384-well layout':
        sortable = sortable.sort_values(by='Global_384_Position', kind='mergesort')

    else:
        return df

    return inject_sorted_back(df, sortable)

# -----------------------------------------------------------------------------
# Download helper
# -----------------------------------------------------------------------------
def to_excel_bytes(df: pd.DataFrame) -> BytesIO:
    buf = BytesIO()
    df.to_excel(buf, index=False, sheet_name="Sorted")
    buf.seek(0)
    return buf

# -----------------------------------------------------------------------------
# Header detection (scans first 20 lines of preview)
# -----------------------------------------------------------------------------
REQUIRED_COLUMNS = {'96 Well', '384 Well', 'Plate'}

def normalize_header(header: str) -> str:
    """
    Normalize a header string for fuzzy matching.
    Converts to lowercase, strips whitespace, removes common punctuation.
    """
    if pd.isna(header):
        return ""
    s = str(header).lower().strip()
    # Remove common punctuation characters
    for char in ['#', '-', '_', '.', '/', '\\', ':', ';', '(', ')', '[', ']']:
        s = s.replace(char, '')
    # Replace multiple spaces with single space
    s = ' '.join(s.split())
    return s

def fuzzy_match_score(search_term: str, column: str) -> float:
    """
    Calculate fuzzy match score using difflib.
    Returns a score from 0-100 for partial substring matching.
    """
    if not search_term or not column:
        return 0.0

    search_norm = normalize_header(search_term)
    column_norm = normalize_header(column)

    # Check for exact substring match
    if search_norm in column_norm:
        return 100.0

    # Use difflib for partial ratio matching
    # Compare search term against all substrings of column
    if len(search_norm) > len(column_norm):
        return SequenceMatcher(None, search_norm, column_norm).ratio() * 100

    best_ratio = 0.0
    for i in range(len(column_norm) - len(search_norm) + 1):
        substring = column_norm[i:i + len(search_norm)]
        ratio = SequenceMatcher(None, search_norm, substring).ratio()
        best_ratio = max(best_ratio, ratio)

    return best_ratio * 100

def match_required_columns(row_values: list, required_columns: set) -> tuple[dict | None, list]:
    """
    Match required columns using fuzzy, case-insensitive logic.
    Returns (mapping, warnings) where mapping is {canonical_name: matched_column_name}
    or (None, warnings) if matching fails.
    """
    # Define search terms for each canonical column
    search_terms = {
        '96 Well': '96 well',
        '384 Well': '384 well',
        'Plate': 'plate'
    }

    mapping = {}
    warnings = []

    for canonical_name, search_term in search_terms.items():
        candidates = []

        for col in row_values:
            if pd.isna(col):
                continue

            col_str = str(col)
            score = fuzzy_match_score(search_term, col_str)

            # Accept matches with score >= 70%
            if score >= 70:
                candidates.append((col_str, score, len(col_str)))

        if len(candidates) == 0:
            # No match found for this required column
            return None, []

        # Sort by score (descending), then by length (ascending for shortest name)
        candidates.sort(key=lambda x: (-x[1], x[2]))
        best_match = candidates[0][0]

        # Warn if multiple high-scoring matches exist
        if len(candidates) > 1 and candidates[1][1] >= 85:
            other_matches = [c[0] for c in candidates[1:3]]
            warnings.append(f"Multiple matches for '{canonical_name}': [{best_match!r}, {', '.join(repr(m) for m in other_matches)}]. Using {best_match!r}.")

        mapping[canonical_name] = best_match

    return mapping, warnings

def find_header_row_fuzzy(preview_df: pd.DataFrame, required_columns: set) -> tuple[int | None, dict | None, list]:
    """
    Find header row with fuzzy matching.
    Returns (row_index, column_mapping, warnings) or (None, None, []).
    """
    for i in range(min(20, len(preview_df))):
        row = preview_df.iloc[i]
        mapping, warnings = match_required_columns(row.values.tolist(), required_columns)
        if mapping is not None:
            return i, mapping, warnings
    return None, None, []

def rename_columns_to_canonical(df: pd.DataFrame, column_mapping: dict) -> pd.DataFrame:
    """
    Rename matched columns to canonical names.
    column_mapping: {canonical_name: actual_column_name}
    """
    # Create inverse mapping: {actual_name: canonical_name}
    inverse_mapping = {v: k for k, v in column_mapping.items()}
    return df.rename(columns=inverse_mapping)

def find_header_row(preview_df: pd.DataFrame, required_columns: set) -> int | None:
    for i in range(min(20, len(preview_df))):
        row = preview_df.iloc[i]
        if required_columns.issubset(set(row.values)):
            return i
    return None

# -----------------------------------------------------------------------------
# Robust file readers with rewind
# -----------------------------------------------------------------------------
def read_preview(uploaded_file) -> pd.DataFrame:
    """Read first 20 rows without assuming a header (CSV/Excel)."""
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    if name.endswith(".csv"):
        try:
            return pd.read_csv(uploaded_file, header=None)
        except Exception:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, header=None, encoding="latin-1", engine="python")
    else:
        uploaded_file.seek(0)
        try:
            return pd.read_excel(uploaded_file, header=None, engine="openpyxl")
        except Exception:
            # fall back to default engine if openpyxl missing
            uploaded_file.seek(0)
            return pd.read_excel(uploaded_file, header=None)

def read_with_header(uploaded_file, header_row: int) -> pd.DataFrame:
    """Rewind and read with a chosen header row (CSV/Excel)."""
    name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    if name.endswith(".csv"):
        try:
            return pd.read_csv(uploaded_file, header=header_row)
        except Exception:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, header=header_row, encoding="latin-1", engine="python")
    else:
        uploaded_file.seek(0)
        try:
            return pd.read_excel(uploaded_file, header=header_row, engine="openpyxl")
        except Exception:
            uploaded_file.seek(0)
            return pd.read_excel(uploaded_file, header=header_row)

# -----------------------------------------------------------------------------
# Streamlit UI
# -----------------------------------------------------------------------------
st.title("Plate Layout Toggler: 96-Well ⇄ 384-Well (with custom 96 order)")

uploaded_file = st.file_uploader("Upload your Excel or CSV file", type=["xlsx", "csv"])

if uploaded_file is not None:
    # Preview (no header)
    preview_df = read_preview(uploaded_file)
    st.write("📄 Preview of first 20 rows:")
    st.dataframe(preview_df.head(20))

    # Header detection UI
    st.markdown("### 🔍 Header Row Detection")
    auto_header_row, column_mapping, warnings = find_header_row_fuzzy(preview_df, REQUIRED_COLUMNS)
    if auto_header_row is not None:
        st.success(f"Automatically detected header row at index {auto_header_row}")
        if column_mapping:
            # Show mapping if columns were renamed
            renamed = {v: k for k, v in column_mapping.items() if v != k}
            if renamed:
                st.info(f"Mapped columns: {renamed}")
        for warning in warnings:
            st.warning(warning)
    else:
        st.warning("No header row detected automatically.")

    selected_row = st.number_input(
        "Select the row number to use as header:",
        min_value=0,
        max_value=min(50, len(preview_df) - 1),
        value=auto_header_row if auto_header_row is not None else 0,
        step=1
    )

    # Load full data with selected header (rewind before read)
    df = read_with_header(uploaded_file, int(selected_row))

    # Apply fuzzy column matching if exact match fails
    if not REQUIRED_COLUMNS.issubset(df.columns):
        row_values = df.columns.tolist()
        column_mapping, match_warnings = match_required_columns(row_values, REQUIRED_COLUMNS)

        if column_mapping is not None:
            # Show detected mapping
            renamed = {v: k for k, v in column_mapping.items() if v != k}
            if renamed:
                st.info(f"Applied fuzzy matching: {renamed}")

            # Display any warnings
            for warning in match_warnings:
                st.warning(warning)

            # Rename columns to canonical names
            df = rename_columns_to_canonical(df, column_mapping)
        else:
            st.error("Could not find columns matching: 96 well, 384 well, plate")
            st.stop()

    if REQUIRED_COLUMNS.issubset(df.columns):
        # Debug: Show actual column names after fuzzy matching
        with st.expander("🔍 Debug Info - Column Names"):
            st.write("Column names after fuzzy matching:", list(df.columns))
        
        # Precompute 384 index (used for the 384 layout)
        df = compute_global_384_index(df)

        view_mode = st.radio("Toggle view mode:", ["96-well layout", "384-well layout"], horizontal=True)
        
        sorted_df = sort_by_toggle(df, view_mode)
        
        # Debug: Show comparison of sorting
        with st.expander("🔍 Debug Info - Sorting Verification"):
            st.write("**First 10 rows with key columns:**")
            if '96 Well' in sorted_df.columns and '384 Well' in sorted_df.columns and 'Plate' in sorted_df.columns:
                st.write(sorted_df[['Plate', '96 Well', '384 Well']].head(10))
            else:
                st.write("Required columns not found!")
                st.write("Available columns:", list(sorted_df.columns))

        st.write(f"### Displaying data in **{view_mode}**")
        st.dataframe(sorted_df.reset_index(drop=True))

        st.download_button(
            "Download Sorted File",
            data=to_excel_bytes(sorted_df),
            file_name="sorted_plate_layout.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.error(f"The selected header row does not contain all required columns: {REQUIRED_COLUMNS}")