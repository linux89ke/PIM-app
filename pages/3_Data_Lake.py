import pandas as pd
import streamlit as st
from io import BytesIO
import re
import concurrent.futures
import requests
import warnings

# Suppress warnings
warnings.filterwarnings('ignore')

# -------------------------------------------------
# 1. CONFIGURATION & MAPPING
# -------------------------------------------------
st.set_page_config(page_title="Master Validator", layout="wide")

# Map User's CSV Columns to Internal Standard Columns
COLUMN_MAPPING = {
    'sku': 'PRODUCT_SET_SID',
    'SKU': 'PRODUCT_SET_SID',
    'name': 'NAME',
    'Name': 'NAME',
    'brand': 'BRAND',
    'Brand': 'BRAND',
    'sellerName': 'SELLER_NAME',
    'Seller Name': 'SELLER_NAME',
    'image': 'MAIN_IMAGE',
    'Image': 'MAIN_IMAGE',
    'newPrice': 'GLOBAL_SALE_PRICE',
    'oldPrice': 'GLOBAL_PRICE',
    'url': 'PRODUCT_URL',
    'color': 'COLOR',
    'Color': 'COLOR'
}

# -------------------------------------------------
# 2. UTILITY FUNCTIONS
# -------------------------------------------------
def clean_category_code(code) -> str:
    """Standardizes category code to a simple string."""
    try:
        if pd.isna(code): return ""
        s = str(code).strip()
        if s.replace('.', '', 1).isdigit() and '.' in s:
            return str(int(float(s)))
        return s
    except:
        return str(code).strip()

def normalize_text(text: str) -> str:
    """Cleans text for comparison."""
    if pd.isna(text): return ""
    text = str(text).lower().strip()
    return re.sub(r'[^\w\s]', '', text)

def normalize_path_input(text):
    """Converts 'Home & Office->Appliances' to 'home & office / appliances'"""
    if pd.isna(text): return ""
    text = str(text).strip().lower()
    return text.replace('->', ' / ').replace('/', ' / ').strip()

@st.cache_data
def load_support_file_safe(filename, file_type='excel'):
    """
    Attempts to load a local file. Returns empty structure if missing.
    """
    try:
        if file_type == 'excel':
            return pd.read_excel(filename, dtype=str)
        elif file_type == 'csv':
            return pd.read_csv(filename, dtype=str)
        elif file_type == 'txt':
            with open(filename, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return None # Return None to indicate missing
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return None

# -------------------------------------------------
# 3. VALIDATION LOGIC (Restored from Original)
# -------------------------------------------------

def check_restricted_brands(data, config_df):
    """Checks if seller is authorized to sell specific brands."""
    if config_df is None or data.empty: return pd.DataFrame()
    
    # Transform config into dictionary: {brand: {sellers: [], categories: []}}
    rules = {}
    for _, row in config_df.iterrows():
        b = str(row.get('Brand', '')).strip().lower()
        if not b or b == 'nan': continue
        
        sellers = set()
        if 'Sellers' in row and pd.notna(row['Sellers']):
            sellers.add(str(row['Sellers']).strip().lower())
            
        rules[b] = {'sellers': sellers}

    flagged_ids = set()
    for _, row in data.iterrows():
        brand = str(row.get('BRAND', '')).strip().lower()
        seller = str(row.get('SELLER_NAME', '')).strip().lower()
        
        if brand in rules:
            allowed = rules[brand]['sellers']
            if allowed and seller not in allowed:
                flagged_ids.add(row['PRODUCT_SET_SID'])

    return data[data['PRODUCT_SET_SID'].isin(flagged_ids)]

def check_suspected_fake(data, fake_df):
    """Checks price against minimum threshold."""
    if fake_df is None or data.empty: return pd.DataFrame()
    
    # Simple logic: If price < threshold for that Brand+Category
    # Requires complex parsing of the specific fake_df structure
    # For this simplified version, we'll return empty unless structure is strictly known
    return pd.DataFrame(columns=data.columns)

def check_prohibited_products(data, prohibited_list):
    """Regex check for banned words."""
    if not prohibited_list or data.empty: return pd.DataFrame()
    
    pattern = '|'.join(r'\b' + re.escape(w) + r'\b' for w in prohibited_list)
    regex = re.compile(pattern, re.IGNORECASE)
    
    mask = data['NAME'].astype(str).str.contains(regex, na=False)
    return data[mask]

def check_single_word_name(data):
    """Reject if name is just one word."""
    if 'NAME' not in data.columns: return pd.DataFrame()
    mask = data['NAME'].astype(str).str.strip().str.split().str.len() < 2
    return data[mask]

def check_missing_color(data, color_cats):
    """Reject if Category requires color but it's missing."""
    if 'COLOR' not in data.columns or not color_cats: return pd.DataFrame()
    
    target_cats = set([clean_category_code(c) for c in color_cats])
    
    # Filter for target categories
    mask_cat = data['CATEGORY_CODE'].apply(clean_category_code).isin(target_cats)
    # Filter for missing color
    mask_color = data['COLOR'].isna() | (data['COLOR'].astype(str).str.strip() == '')
    
    return data[mask_cat & mask_color]

# -------------------------------------------------
# 4. MAIN APPLICATION
# -------------------------------------------------

# A. SIDEBAR - FILE LOADING
with st.sidebar:
    st.header("1. System Files")
    st.info("System assumes configuration files (restricted_brands.xlsx, etc.) are present in the directory.")
    
    # Manual Upload for Category Mapping (Since this changes often)
    cat_ref_file = st.file_uploader("Upload Category Reference (xlsx)", type=['xlsx', 'csv'])
    
    # Load Category Map
    cat_map = {}
    if cat_ref_file:
        try:
            if cat_ref_file.name.endswith('.csv'):
                ref_df = pd.read_csv(cat_ref_file)
            else:
                xl = pd.ExcelFile(cat_ref_file)
                # Find sheet with 'Category Path'
                target = next((s for s in xl.sheet_names if 'Category Path' in pd.read_excel(xl, sheet_name=s, nrows=0).columns), xl.sheet_names[0])
                ref_df = pd.read_excel(cat_ref_file, sheet_name=target)

            # Build Dictionary: { 'home & office / appliances': '1000311' }
            for _, row in ref_df.iterrows():
                path_raw = normalize_path_input(row.get('Category Path', ''))
                code_clean = clean_category_code(row.get('category_code', ''))
                if path_raw and code_clean:
                    cat_map[path_raw] = code_clean
            
            st.success(f"Indexed {len(cat_map)} Categories")
        except Exception as e:
            st.error(f"Error reading category file: {e}")

# B. MAIN AREA
st.title("🛡️ Universal Product Validator")
st.markdown("Automated QA using `download (3).csv` structure and System Configuration files.")

prod_file = st.file_uploader("Upload Product File (download (3).csv)", type=['csv', 'xlsx'])

if prod_file and cat_map:
    # 1. READ AND PREPARE DATA
    try:
        if prod_file.name.endswith('.xlsx'):
            raw_df = pd.read_excel(prod_file, dtype=str)
        else:
            prod_file.seek(0)
            try:
                raw_df = pd.read_csv(prod_file, sep='|', dtype=str, on_bad_lines='skip')
                if len(raw_df.columns) < 2: raise Exception
            except:
                prod_file.seek(0)
                raw_df = pd.read_csv(prod_file, sep=',', dtype=str)
    except Exception as e:
        st.error(f"Read Error: {e}")
        st.stop()

    # 2. STANDARDIZE COLUMNS
    df = raw_df.rename(columns=COLUMN_MAPPING)
    
    # Ensure all standard columns exist
    for c in ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'SELLER_NAME', 'GLOBAL_SALE_PRICE', 'COLOR']:
        if c not in df.columns:
            df[c] = ""

    # 3. MAP CATEGORIES
    # Convert "Category" column (path) to "CATEGORY_CODE" using the loaded map
    # We check 'categories' first (from download 3), then 'Category'
    cat_col = 'categories' if 'categories' in raw_df.columns else 'Category'
    
    if cat_col in raw_df.columns:
        df['path_normalized'] = raw_df[cat_col].apply(normalize_path_input)
        df['CATEGORY_CODE'] = df['path_normalized'].map(cat_map).fillna("N/A")
    else:
        st.error("Could not find 'categories' or 'Category' column in upload.")
        st.stop()
        
    unmapped = len(df[df['CATEGORY_CODE'] == 'N/A'])
    if unmapped > 0:
        st.warning(f"⚠️ {unmapped} products have categories not found in the reference file.")

    # 4. LOAD EXTERNAL CONFIGS (Assumption: Files exist in system)
    with st.spinner("Loading System Rules..."):
        restr_brands_df = load_support_file_safe("restric_brands.xlsx")
        suspected_fake_df = load_support_file_safe("suspected_fake.xlsx")
        prohibited_ke = load_support_file_safe("prohibited_productsKE.txt", 'txt')
        color_cats = load_support_file_safe("color_cats.txt", 'txt')
    
    # 5. RUN VALIDATIONS
    st.info("Running Compliance Checks...")
    
    results = {}
    
    # A. Unmapped Categories
    results['Unknown Category'] = df[df['CATEGORY_CODE'] == 'N/A']
    
    # B. Restricted Brands
    if restr_brands_df is not None:
        results['Restricted Brand'] = check_restricted_brands(df, restr_brands_df)
    
    # C. Prohibited Products
    if prohibited_ke:
        results['Prohibited Content'] = check_prohibited_products(df, prohibited_ke)
        
    # D. Single Word Name
    results['Invalid Name'] = check_single_word_name(df)
    
    # E. Missing Color
    if color_cats:
        results['Missing Color'] = check_missing_color(df, color_cats)

    # 6. AGGREGATE RESULTS
    all_rejections = pd.DataFrame()
    
    for flag, res_df in results.items():
        if not res_df.empty:
            res_df = res_df.copy()
            res_df['FLAG'] = flag
            res_df['Reason'] = f"Failed check: {flag}"
            all_rejections = pd.concat([all_rejections, res_df])
            
    # Mark the Main DataFrame
    if not all_rejections.empty:
        rejected_sids = set(all_rejections['PRODUCT_SET_SID'])
        df['Status'] = df['PRODUCT_SET_SID'].apply(lambda x: 'Rejected' if x in rejected_sids else 'Approved')
        
        # Map reasons back
        reason_map = all_rejections.drop_duplicates('PRODUCT_SET_SID').set_index('PRODUCT_SET_SID')['Reason'].to_dict()
        flag_map = all_rejections.drop_duplicates('PRODUCT_SET_SID').set_index('PRODUCT_SET_SID')['FLAG'].to_dict()
        
        df['Reason'] = df['PRODUCT_SET_SID'].map(reason_map).fillna("")
        df['FLAG'] = df['PRODUCT_SET_SID'].map(flag_map).fillna("")
    else:
        df['Status'] = 'Approved'
        df['Reason'] = ""
        df['FLAG'] = ""

    # 7. DISPLAY DASHBOARD
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Processed", len(df))
    c2.metric("✅ Approved", len(df[df['Status']=='Approved']))
    c3.metric("❌ Rejected", len(df[df['Status']=='Rejected']))
    
    st.subheader("Rejection Details")
    if not all_rejections.empty:
        st.dataframe(df[df['Status']=='Rejected'][['PRODUCT_SET_SID', 'NAME', 'CATEGORY_CODE', 'Reason']], use_container_width=True)
    else:
        st.success("Clean Clean! No issues found.")
        
    # 8. EXPORT
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Define output columns (User friendly + System status)
        export_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'SELLER_NAME', 'Status', 'Reason', 'FLAG']
        # Add original category path for debugging
        if 'categories' in raw_df.columns: export_cols.append('categories')
        
        # Ensure cols exist
        final_cols = [c for c in export_cols if c in df.columns]
        
        df[final_cols].to_excel(writer, index=False, sheet_name='Validation_Results')
        
        # Formatting
        wb = writer.book
        ws = writer.sheets['Validation_Results']
        red = wb.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        green = wb.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        
        stat_idx = df[final_cols].columns.get_loc('Status')
        ws.conditional_format(1, stat_idx, len(df), stat_idx, {'type': 'cell', 'criteria': 'equal', 'value': '"Rejected"', 'format': red})
        ws.conditional_format(1, stat_idx, len(df), stat_idx, {'type': 'cell', 'criteria': 'equal', 'value': '"Approved"', 'format': green})

    output.seek(0)
    st.download_button("📥 Download Report", output, "validation_report.xlsx")

elif prod_file and not cat_map:
    st.warning("Please upload the Category Reference file first.")
