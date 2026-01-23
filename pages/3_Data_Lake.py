import pandas as pd
import streamlit as st
from io import BytesIO
import xlsxwriter
import re

# -------------------------------------------------
# CONFIGURATION & UTILS
# -------------------------------------------------
st.set_page_config(page_title="Simple Validator", layout="wide")

@st.cache_data
def load_category_reference(file):
    """
    Loads the category reference file (Sheet3 based on your request).
    Expects columns: 'category_code', 'Category Path'
    """
    try:
        # Load excel, assuming the relevant data is in the sheet with 'Category Path'
        # If it's a CSV, read as CSV; if Excel, read as Excel.
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file, sheet_name=None)
            # Find the sheet with 'Category Path'
            target_sheet = None
            for sheet, data in df.items():
                if 'Category Path' in data.columns:
                    target_sheet = sheet
                    break
            if target_sheet:
                df = df[target_sheet]
            else:
                # Fallback to first sheet
                df = list(df.values())[0]

        # Standardize columns
        df.columns = df.columns.str.strip()
        
        # specific fix for the file provided
        if 'Category Path' in df.columns:
            # Normalize: lowercase, strip, ensure spaces around slash
            df['clean_path'] = df['Category Path'].astype(str).apply(lambda x: x.replace(' / ', '/').replace('/', ' / ').strip().lower())
            return df
        else:
            st.error("Reference file missing 'Category Path' column.")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading reference: {e}")
        return pd.DataFrame()

def normalize_input_category(cat_str):
    """Converts 'Home & Office->Appliances' to 'home & office / appliances'"""
    if pd.isna(cat_str): return ""
    # Replace -> with / and normalize spacing/case
    return str(cat_str).replace('->', ' / ').replace('/', ' / ').lower().strip()

def check_duplicates_simple(df):
    """Checks for duplicates based on Brand + Name + Seller"""
    if df.empty: return df
    
    # Create a match key
    df['match_key'] = df.apply(
        lambda x: f"{str(x.get('brand', '')).strip().lower()}|{str(x.get('name', '')).strip().lower()}|{str(x.get('sellerName', '')).strip().lower()}", 
        axis=1
    )
    
    # Find duplicates
    dupes = df[df.duplicated(subset=['match_key'], keep=False)]
    return dupes

# -------------------------------------------------
# MAIN APP
# -------------------------------------------------
st.title("🛡️ Simplified Product Validator")
st.markdown("Reverse-engineered tool to validate products using `category_check.xlsx`.")

# SIDEBAR: Reference File
with st.sidebar:
    st.header("1. Setup")
    ref_file = st.file_uploader("Upload Category Reference (xlsx)", type=['xlsx', 'csv'])
    
    ref_df = pd.DataFrame()
    valid_paths = set()
    
    if ref_file:
        with st.spinner("Processing reference..."):
            ref_df = load_category_reference(ref_file)
            if not ref_df.empty:
                valid_paths = set(ref_df['clean_path'].unique())
                st.success(f"Loaded {len(valid_paths)} valid categories.")

# MAIN: Product File
st.header("2. Upload Product Data")
prod_file = st.file_uploader("Upload Product File (CSV/XLSX)", type=['csv', 'xlsx'])

if prod_file and not ref_df.empty:
    # 1. READ FILE
    try:
        if prod_file.name.endswith('.xlsx'):
            df = pd.read_excel(prod_file, dtype=str)
        else:
            # Try sniffing delimiter for CSV (handling | vs ,)
            content = prod_file.read()
            prod_file.seek(0)
            try:
                df = pd.read_csv(prod_file, sep='|', dtype=str, on_bad_lines='skip')
                if len(df.columns) < 2: # Fallback if | didn't work
                    prod_file.seek(0)
                    df = pd.read_csv(prod_file, sep=',', dtype=str)
            except:
                prod_file.seek(0)
                df = pd.read_csv(prod_file, sep=',', dtype=str)
                
        st.info(f"Loaded {len(df)} rows. Columns: {', '.join(df.columns)}")
        
    except Exception as e:
        st.error(f"Failed to read file: {e}")
        st.stop()

    # 2. RUN CHECKS
    results = []
    
    progress = st.progress(0)
    
    # Ensure required columns exist
    req_cols = ['name', 'categories', 'brand', 'sku']
    missing_cols = [c for c in req_cols if c not in df.columns]
    
    if missing_cols:
        st.error(f"Missing columns in upload: {missing_cols}")
        st.stop()

    # Create mapping dictionary for faster lookup (clean_path -> category_code)
    path_to_code = pd.Series(ref_df.category_code.values, index=ref_df.clean_path).to_dict()

    for idx, row in df.iterrows():
        status = "Approved"
        reasons = []
        
        # A. Category Check
        raw_cat = row.get('categories', '')
        clean_cat = normalize_input_category(raw_cat)
        
        if not clean_cat:
            status = "Rejected"
            reasons.append("Missing Category")
        elif clean_cat not in valid_paths:
            status = "Rejected"
            reasons.append(f"Invalid Category: {raw_cat}")
        else:
            # If valid, we can grab the code
            row['Mapped_Category_Code'] = path_to_code.get(clean_cat, "")

        # B. Missing Data Check
        if pd.isna(row.get('name')) or len(str(row.get('name'))) < 3:
            status = "Rejected"
            reasons.append("Invalid Name")
        
        if pd.isna(row.get('brand')):
            status = "Rejected"
            reasons.append("Missing Brand")
            
        if pd.isna(row.get('url')) and pd.isna(row.get('image')):
             # Soft warning or rejection depending on strictness
             pass 

        # Store Result
        row['Status'] = status
        row['Reason'] = "; ".join(reasons)
        results.append(row)
        
        if idx % 100 == 0:
            progress.progress(min(idx / len(df), 1.0))
            
    progress.progress(1.0)
    result_df = pd.DataFrame(results)

    # C. Duplicate Check (Batch Operation)
    dupes = check_duplicates_simple(result_df)
    if not dupes.empty:
        # Mark duplicates as rejected
        dup_indices = dupes.index
        result_df.loc[dup_indices, 'Status'] = 'Rejected'
        # Append reason, handling existing reasons
        result_df.loc[dup_indices, 'Reason'] = result_df.loc[dup_indices, 'Reason'].apply(
            lambda x: (x + "; Duplicate Product") if x else "Duplicate Product"
        )

    # 3. DISPLAY RESULTS
    st.markdown("---")
    st.subheader("Validation Results")
    
    col1, col2, col3 = st.columns(3)
    approved = result_df[result_df['Status'] == 'Approved']
    rejected = result_df[result_df['Status'] == 'Rejected']
    
    col1.metric("Total Processed", len(result_df))
    col2.metric("Approved", len(approved))
    col3.metric("Rejected", len(rejected))

    with st.expander("Review Rejected Items"):
        st.dataframe(rejected[['sku', 'name', 'categories', 'Reason', 'sellerName']], use_container_width=True)

    # 4. EXPORT
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        result_df.to_excel(writer, index=False, sheet_name='Validation_Results')
        # Add simple formatting
        workbook = writer.book
        worksheet = writer.sheets['Validation_Results']
        red_format = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        green_format = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        
        # Apply conditional formatting to Status column
        # Find column index for 'Status'
        status_col_idx = result_df.columns.get_loc("Status")
        worksheet.conditional_format(1, status_col_idx, len(result_df), status_col_idx,
                                     {'type': 'cell', 'criteria': 'equal', 'value': '"Rejected"', 'format': red_format})
        worksheet.conditional_format(1, status_col_idx, len(result_df), status_col_idx,
                                     {'type': 'cell', 'criteria': 'equal', 'value': '"Approved"', 'format': green_format})

    output.seek(0)
    st.download_button(
        label="📥 Download Validation Report",
        data=output,
        file_name="validation_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

elif prod_file and ref_df.empty:
    st.warning("Please upload the Category Reference file in the sidebar first.")
