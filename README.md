
# 96-to-384 Plate Layout Toggler

## Overview

This repository contains a **Streamlit-based interactive application** that converts, sorts, and visualizes plate-mapping data between:

- **96‑well plate layout**
- **384‑well plate layout**

The application is designed for laboratory workflows where samples originate from multiple 96‑well plates but must be visualized, validated, or exported in a 384‑well ordering (or vice versa).

Key capabilities:

- Upload Excel or CSV plate mapping files
- Automatically detect header rows (even if messy)
- Fuzzy-match column names (e.g., “96 Well”, “96well”, “Well_96”)
- Apply a **custom interleaved 96‑well ordering**
- Compute deterministic **global 384‑well positions**
- Toggle between 96‑well and 384‑well sorted views
- Download the sorted result as Excel

This tool focuses on **layout correctness, robustness to imperfect input files, and reproducibility**.

---

## Repository Structure

```
96-to-384-plate/
│
├── 96 v 384 conversion.py     # Main Streamlit application
├── requirements.txt           # Python dependencies
├── .gitattributes
└── .git/                      # Git metadata
```

There is a single executable application file. All logic is contained inside it.

---

## Installation

### 1. Create Environment (recommended)

```bash
python -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate         # Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run Application

```bash
streamlit run "96 v 384 conversion.py"
```

A browser window will open automatically.

---

## Expected Input File Format

Excel (`.xlsx`) or CSV (`.csv`) with **at minimum** three logical columns:

- 96 Well  
- 384 Well  
- Plate  

Column names do NOT need to match exactly. Examples that will work:

- `96well`, `96 Well ID`, `Well96`
- `384-well`, `dest well`, `384well`
- `plate`, `plate number`, `Plate_ID`

Rows missing any of these three values are preserved but excluded from sorting.

---

## High-Level Data Flow

```
Upload File
   ↓
Preview first 20 rows
   ↓
Auto-detect header row (fuzzy)
   ↓
Rename columns → canonical names
   ↓
Compute global 384 positions
   ↓
User selects view mode
   ↓
Apply sorting
   ↓
Display table
   ↓
Download Excel
```

---

## Core Concepts

### Canonical Columns

Internally, the app standardizes columns to:

- `96 Well`
- `384 Well`
- `Plate`

Everything downstream relies on these names.

---

### Custom 96‑Well Interleaved Ordering

Instead of standard row-major A→H ordering, this tool uses:

```
A1, B1, A2, B2, ...
C1, D1, ...
E1, F1, ...
G1, H1, ...
```

Why?  
Many liquid-handling and replication workflows pair rows (A/B, C/D, etc.). This preserves physical transfer patterns.

Defined in code as:

```python
CUSTOM_96_ORDER = [ ... ]
ORDER_INDEX_96 = {well: index}
```

Any unknown well receives a large index so it sorts last.

---

### Global 384 Position

384‑well plates have:

- Rows: A–P (16)
- Columns: 1–24

Each group of **four 96‑well plates** maps into one 384‑well plate.

Global index formula:

```
plate_group = (plate_number - 1) // 4
global_position = plate_group * 384 + local_384_index
```

This allows consistent ordering across multiple plates.

---

## Major Functions (Explained)

### `pos96(well)`

Returns the numeric ordering index of a 96‑well label based on the custom interleaving.

Purpose:
- Enables deterministic sorting for 96‑well view.

---

### `compute_global_384_index(df)`

Adds a new column:

```
Global_384_Position
```

Uses row-major 384 indexing + plate grouping.

Purpose:
- Enables absolute ordering across many plates.

---

### `extract_sortable_rows(df)`

Filters rows where:

```
Plate, 96 Well, 384 Well are all non-null
```

Purpose:
- Prevents partial rows from breaking sorting.

---

### `inject_sorted_back(original_df, sorted_rows)`

Returns:

```
[sorted rows]
+
[rows missing required columns]
```

Purpose:
- Preserves user data integrity.

---

### `sort_by_toggle(df, view_mode)`

If mode is:

- `96-well layout` → sort by Plate then custom 96 order
- `384-well layout` → sort by Global_384_Position

Stable mergesort is used to prevent unexpected reshuffling.

---

### `read_preview(file)`

Reads first 20 rows **without assuming header**.

Purpose:
- Allows header detection even when headers are not row 0.

---

### `find_header_row_fuzzy(preview_df)`

Scans first 20 rows and attempts fuzzy matching against:

```
96 well
384 well
plate
```

Returns detected header row index.

---

### `match_required_columns(row_values)`

Uses `difflib.SequenceMatcher` to score similarity.

- Accepts matches ≥ 70%
- Warns when multiple high-confidence matches exist

Purpose:
- Handles messy spreadsheets.

---

### `rename_columns_to_canonical(df, mapping)`

Renames matched columns → canonical names.

---

### `to_excel_bytes(df)`

Serializes DataFrame to in-memory Excel file for download.

---

## Streamlit User Interface

### Upload Section

- Upload CSV or Excel
- Preview of first 20 rows

### Header Detection Panel

- Shows auto-detected header index
- User may override

### Layout Toggle

Radio buttons:

- 96-well layout
- 384-well layout

### Debug Expanders

- Column names after fuzzy matching
- First rows after sorting

### Download Button

Exports:

```
sorted_plate_layout.xlsx
```

---

## Error Handling

| Situation | Behavior |
|---------|----------|
| Missing required columns | App stops with message |
| Multiple fuzzy matches | Warning displayed |
| Unknown wells | Sorted last |
| Encoding issues | Latin-1 fallback |
| Empty cells | Row preserved but unsorted |

---

## How to Modify / Extend

### Change 96‑Well Ordering

Edit:

```python
CUSTOM_96_ORDER = [...]
```

### Change Fuzzy Match Threshold

Inside `match_required_columns`:

```python
if score >= 70:
```

Increase for stricter matching.

### Add New Required Column

1. Add to `REQUIRED_COLUMNS`
2. Add search term in `search_terms`
3. Update downstream logic

### Add Additional Sorting Mode

1. Add new option in `st.radio`
2. Add branch in `sort_by_toggle()`

---

## Design Philosophy

- Deterministic ordering
- Non-destructive transformations
- Transparent debugging
- No hidden state
- Single-file deployment

---

## Typical Use Cases

- Plate replication validation
- Sample tracking QA
- Liquid-handler mapping review
- Plate reformatting workflows

---

## Known Limitations

- No database storage
- Single-file app
- No authentication
- No visualization of plate grids (tabular only)

---

## Future Improvements

- Visual plate heatmaps
- Drag-and-drop column mapping UI
- Batch file processing
- Saved presets

---

## License

MIT

---

## Maintainer Notes

Treat this application as a **data transformation utility**. Avoid introducing business logic into the UI layer. Keep transformations deterministic and testable.
