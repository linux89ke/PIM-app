import pandas as pd
import streamlit as st
from io import BytesIO
import re

# -------------------------------------------------
# CONFIGURATION
# -------------------------------------------------
st.set_page_config(page_title="Exact Match Validator", layout="wide")

@st.cache_data
def load_category_reference(file):
    """
    Loads the reference file and creates a lookup dictionary:
    {'home & office / appliances / ...': 1000311}
    """
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            # Read Excel, find the correct sheet
            xl = pd.ExcelFile(file)
            target_sheet = None
            for sheet in xl.sheet_names:
                cols = pd.read_excel(xl, sheet_name=sheet, nrows=0).columns
                if 'Category Path' in cols:
                    target_sheet = sheet
                    break
            df = pd.read_excel(file, sheet_name=target_sheet) if target_sheet else pd.read_excel(file, sheet_name=0)

        # Standardize columns
        df.columns = df.columns.str.strip()
        
        if 'Category Path' not in df.columns or 'category_code' not in df.columns:
            st.error("Reference file must have 'Category Path' and 'category_code' columns.")
            return {}

        # Create Lookup Dictionary
        # Key: Lowercase path with ' / ' separator
        # Value: Category Code
        lookup = {}
        for _, row in df.iterrows():
            path = str(row['Category Path']).strip().lower()
            # Ensure single spaces around slashes for consistency
            path = path.replace(' / ', '/').replace('/', ' / ')
            code = str(row['category_code']).strip().replace('.0', '')
            lookup[path] = code
            
        return lookup
    except Exception as e:
        st.error(f"Error loading reference: {e}")
        return {}

def normalize_input_path(text):
    """
    Converts input format 'A->B->C' to reference format 'a / b / c'
    """
    if pd.isna(text): return ""
    text = str(text).strip().lower()
    # vital step: convert -> to / and ensure spacing matches the reference
    text = text.replace('->', ' / ').replace('/', ' / ')
    # remove duplicate spaces if any
    text = re.sub(r'\s+', ' ', text)
    return text

def check_missing_attributes(row, code):
    """
    Runs checks based on the retrieved code.
    Add your specific rules here.
    """
    reasons = []
    
    # 1. Basic Data Integrity
    if pd.isna(row.get('name')) or len(str(row.get('name'))) < 3:
        reasons.append("Invalid Name")
    if pd.isna(row.get('brand')):
        reasons.append("Missing Brand")
        
    # 2. Example: Check specifically for Code 1000311 (Induction Cookers)
    # You can add logic here: "If code is 1000311, assume it must have 'Induction' in the name"
    if code == '1000311':
        name = str(row.get('name', '')).lower()
        if 'induction' not in name:
            reasons.append("Induction Cooker missing 'Induction' keyword")

    return reasons

# -------------------------------------------------
# MAIN APP
# -------------------------------------------------
st.title("🛡️ Exact Match Validator")
st.markdown("Upload your files to map Category Paths to Codes and run validations.")

# 1. SETUP
with st.sidebar:
    st.header("1. Upload Reference")
    ref_file = st.file_uploader("Upload category_check.xlsx", type=['xlsx', 'csv'])
    path_map = {}
    
    if ref_file:
        with st.spinner("Building Lookup Map..."):
            path_map = load_category_reference(ref_file)
            if path_map:
                st.success(f"Indexed {len(path_map)} categories.")

# 2. PROCESS
st.header("2. Upload Product Data")
prod_file = st.file_uploader("Upload Product File (CSV/XLSX)", type=['csv', 'xlsx'])

if prod_file and path_map:
    # Read Product File
    try:
        if prod_file.name.endswith('.xlsx'):
            df = pd.read_excel(prod_file, dtype=str)
        else:
            # Smart CSV loader
            prod_file.seek(0)
            try:
                df = pd.read_csv(prod_file, sep='|', dtype=str, on_bad_lines='skip')
                if len(df.columns) < 2: raise Exception
            except:
                prod_file.seek(0)
                df = pd.read_csv(prod_file, sep=',', dtype=str)
    except Exception as e:
        st.error(f"Error reading product file: {e}")
        st.stop()
        
    st.info(f"Processing {len(df)} products...")
    
    results = []
    
    for idx, row in df.iterrows():
        raw_cat = row.get('categories', '')
        
        # A. Normalize Path
        clean_cat = normalize_input_path(raw_cat)
        
        # B. Lookup Code
        code = path_map.get(clean_cat, None)
        
        # C. Validate
        status = "Approved"
        reasons = []
        
        if not code:
            status = "Rejected"
            reasons.append(f"Category not found in reference")
        else:
            # Only run specific checks if we found the code
            attr_errors = check_missing_attributes(row, code)
            if attr_errors:
                status = "Rejected"
                reasons.extend(attr_errors)
        
        # Save Results
        row['Mapped_Code'] = code if code else "N/A"
        row['Validation_Status'] = status
        row['Validation_Reason'] = "; ".join(reasons)
        results.append(row)

    res_df = pd.DataFrame(results)

    # 3. DISPLAY
    st.markdown("---")
    c1, c2 = st.columns(2)
    c1.metric("Approved", len(res_df[res_df['Validation_Status'] == 'Approved']))
    c2.metric("Rejected", len(res_df[res_df['Validation_Status'] == 'Rejected']))
    
    st.subheader("Results Preview")
    st.dataframe(res_df[['sku', 'categories', 'Mapped_Code', 'Validation_Status', 'Validation_Reason']], use_container_width=True)
    
    # 4. EXPORT
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        res_df.to_excel(writer, index=False, sheet_name='Validated_Data')
        
        # Add formatting
        wb = writer.book
        ws = writer.sheets['Validated_Data']
        red = wb.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        green = wb.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        
        stat_col = res_df.columns.get_loc('Validation_Status')
        ws.conditional_format(1, stat_col, len(res_df), stat_col, {'type': 'cell', 'criteria': 'equal', 'value': '"Rejected"', 'format': red})
        ws.conditional_format(1, stat_col, len(res_df), stat_col, {'type': 'cell', 'criteria': 'equal', 'value': '"Approved"', 'format': green})

    output.seek(0)
    st.download_button("📥 Download Validated File", output, "validated_products.xlsx")
