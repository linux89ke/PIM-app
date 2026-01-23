import pandas as pd
import streamlit as st
from io import BytesIO
import re
import os
import warnings

# Suppress warnings
warnings.filterwarnings('ignore')

# -------------------------------------------------
# 1. SETUP & CONSTANTS
# -------------------------------------------------
st.set_page_config(page_title="Advanced Product Validator", layout="wide")

# Standardize User Columns to System Columns
COLUMN_MAPPING = {
    'sku': 'PRODUCT_SET_SID', 'SKU': 'PRODUCT_SET_SID',
    'name': 'NAME', 'Name': 'NAME',
    'brand': 'BRAND', 'Brand': 'BRAND',
    'sellerName': 'SELLER_NAME', 'Seller Name': 'SELLER_NAME',
    'image': 'MAIN_IMAGE', 'Image': 'MAIN_IMAGE',
    'newPrice': 'GLOBAL_SALE_PRICE',
    'url': 'PRODUCT_URL',
    'color': 'COLOR', 'Color': 'COLOR',
    'categories': 'CATEGORY_PATH_RAW', 'Category': 'CATEGORY_PATH_RAW',
    'product_warranty': 'PRODUCT_WARRANTY',
    'warranty_duration': 'WARRANTY_DURATION'
}

# -------------------------------------------------
# 2. FILE LOADING UTILITIES
# -------------------------------------------------
def normalize_path_input(text):
    """Converts 'Home & Office->Appliances' to 'home & office / appliances'"""
    if pd.isna(text): return ""
    return str(text).strip().lower().replace('->', ' / ').replace('/', ' / ').strip()

def clean_code(code):
    """Standardizes IDs to strings without decimals."""
    if pd.isna(code): return ""
    s = str(code).strip()
    if s.endswith('.0'): return s[:-2]
    return s

@st.cache_data
def load_config_file(filename, file_type='excel', col=None):
    """
    Tries to load a config file from disk. 
    Returns a List (if col specified) or DataFrame.
    """
    if not os.path.exists(filename):
        return [] if col else None
    
    try:
        if file_type == 'excel':
            df = pd.read_excel(filename, dtype=str)
        elif file_type == 'csv':
            df = pd.read_csv(filename, dtype=str)
        elif file_type == 'txt':
            with open(filename, 'r', encoding='utf-8') as f:
                return [line.strip().lower() for line in f if line.strip()]
                
        if col and not df.empty:
            # Try to find the column case-insensitively
            found_col = next((c for c in df.columns if c.lower() == col.lower()), None)
            if found_col:
                return df[found_col].dropna().apply(clean_code).tolist()
            return []
        return df
    except Exception:
        return [] if col else None

# -------------------------------------------------
# 3. SPECIFIC VALIDATION FUNCTIONS
# -------------------------------------------------

def validate_books(row, book_cats, approved_sellers):
    """
    Rule: If Category is Book, Seller MUST be in Approved List.
    """
    if row['CATEGORY_CODE'] in book_cats:
        seller = str(row.get('SELLER_NAME', '')).strip().lower()
        # Check against approved list (normalized)
        approved_norm = [str(s).strip().lower() for s in approved_sellers]
        if seller not in approved_norm:
            return "Restricted: Seller not approved for Books"
    return None

def validate_sneakers(row, sneaker_cats, sensitive_brands):
    """
    Rule: If Category is Sneaker AND Brand is Generic/Fashion,
    Name CANNOT contain protected brands (Nike, Adidas, etc).
    """
    if row['CATEGORY_CODE'] in sneaker_cats:
        brand = str(row.get('BRAND', '')).strip().lower()
        if brand in ['generic', 'fashion', 'no brand', 'other']:
            name = str(row.get('NAME', '')).lower()
            # Check if any sensitive brand is in the name
            for bad_brand in sensitive_brands:
                if f" {bad_brand} " in f" {name} ": # Simple word boundary check
                    return f"Counterfeit: Generic brand with '{bad_brand}' in name"
    return None

def validate_color(row, color_cats, valid_colors_regex):
    """
    Rule: If Category requires Color:
    1. Check 'Color' column.
    2. If empty, check 'Name' for valid color keywords.
    """
    if row['CATEGORY_CODE'] in color_cats:
        # 1. Check Column
        col_val = str(row.get('COLOR', '')).strip().lower()
        if col_val not in ['nan', '', 'none', 'null']:
            return None # Valid color found in column
            
        # 2. Check Name
        if valid_colors_regex:
            name_val = str(row.get('NAME', ''))
            if valid_colors_regex.search(name_val):
                return None # Valid color found in name
                
        return "Missing Color: Not found in Column or Name"
    return None

def validate_warranty(row, warranty_cats):
    """
    Rule: If Category requires Warranty, fields must be filled.
    """
    if row['CATEGORY_CODE'] in warranty_cats:
        w = str(row.get('PRODUCT_WARRANTY', '')).strip().lower()
        d = str(row.get('WARRANTY_DURATION', '')).strip().lower()
        if w in ['nan', '', 'none'] and d in ['nan', '', 'none']:
             return "Missing Warranty Details"
    return None

def validate_restricted_brands(row, restricted_brands_df):
    """
    Rule: Check if Seller is allowed to sell the Brand.
    """
    if restricted_brands_df is None: return None
    
    brand = str(row.get('BRAND', '')).strip().lower()
    
    # Locate brand in config (inefficient for large loops, but functional)
    # Ideally, convert config to dict outside loop (done in main)
    # Here we assume 'restricted_brands_df' is a dictionary: {brand: [allowed_sellers]}
    
    if brand in restricted_brands_df:
        allowed = restricted_brands_df[brand]
        seller = str(row.get('SELLER_NAME', '')).strip().lower()
        if allowed and seller not in allowed:
            return f"Restricted Brand: '{row.get('BRAND')}' not authorized for this seller"
            
    return None

# -------------------------------------------------
# 4. MAIN APP
# -------------------------------------------------

# A. SIDEBAR - LOAD RULES
with st.sidebar:
    st.header("1. Configuration")
    
    # 1. Category Map (Essential)
    cat_ref_file = st.file_uploader("Upload Category Reference (xlsx)", type=['xlsx', 'csv'])
    
    # 2. Load System Rules (Attempt to load from local directory)
    with st.spinner("Loading Validation Rules..."):
        # BOOKS
        book_cats = set(load_config_file("Books_cat.xlsx", "excel", "CategoryCode"))
        approved_book_sellers = set(load_config_file("Books_Approved_Sellers.xlsx", "excel", "SellerName"))
        
        # SNEAKERS
        sneaker_cats = set(load_config_file("Sneakers_Cat.txt", "txt"))
        sensitive_sneakers = load_config_file("Sneakers_Sensitive.txt", "txt")
        
        # COLOR
        color_cats = set(load_config_file("color_cats.txt", "txt"))
        valid_colors = load_config_file("colors.txt", "txt")
        # Compile Regex for Colors (Optimization)
        color_regex = None
        if valid_colors:
            pattern = '|'.join(r'\b' + re.escape(c) + r'\b' for c in sorted(valid_colors, key=len, reverse=True))
            color_regex = re.compile(pattern, re.IGNORECASE)

        # WARRANTY
        warranty_cats = set(load_config_file("warranty.txt", "txt"))
        
        # RESTRICTED BRANDS (Convert to efficient Dict)
        rb_df = load_config_file("restric_brands.xlsx", "excel")
        restricted_rules = {}
        if rb_df is not None:
            for _, r in rb_df.iterrows():
                b = str(r.get('Brand', '')).strip().lower()
                if b and b!='nan':
                    s = str(r.get('Sellers', '')).strip().lower()
                    restricted_rules[b] = set([s]) if s != 'nan' else set()

    # Status Indicators
    st.markdown("---")
    st.markdown("**Active Rules:**")
    st.caption(f"📚 Books: {'Active' if book_cats else 'Inactive'}")
    st.caption(f"👟 Sneakers: {'Active' if sneaker_cats else 'Inactive'}")
    st.caption(f"🎨 Colors: {'Active' if color_cats else 'Inactive'}")
    st.caption(f"🛡️ Brands: {'Active' if restricted_rules else 'Inactive'}")


# B. MAIN - UPLOAD & PROCESS
st.title("🛡️ Smart Validator (Context-Aware)")
st.markdown("Validates products based on their **Mapped Category Code**.")

# 1. Load Category Map
path_to_code = {}
if cat_ref_file:
    try:
        if cat_ref_file.name.endswith('.csv'):
            ref_df = pd.read_csv(cat_ref_file)
        else:
            xl = pd.ExcelFile(cat_ref_file)
            target = next((s for s in xl.sheet_names if 'Category Path' in pd.read_excel(xl, sheet_name=s, nrows=0).columns), xl.sheet_names[0])
            ref_df = pd.read_excel(cat_ref_file, sheet_name=target)
        
        for _, row in ref_df.iterrows():
            p = normalize_path_input(row.get('Category Path', ''))
            c = clean_code(row.get('category_code', ''))
            if p and c: path_to_code[p] = c
        st.success(f"Mapped {len(path_to_code)} Categories")
    except Exception as e:
        st.error(f"Error reading category file: {e}")

# 2. Upload Product File
prod_file = st.file_uploader("Upload Product File (download (3).csv)", type=['csv', 'xlsx'])

if prod_file and path_to_code:
    # Read
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
        
    # Standardize
    df = raw_df.rename(columns=COLUMN_MAPPING)
    
    # Map Categories
    df['normalized_path'] = df['CATEGORY_PATH_RAW'].apply(normalize_path_input)
    df['CATEGORY_CODE'] = df['normalized_path'].map(path_to_code).fillna("N/A")
    
    st.info(f"Processing {len(df)} rows...")
    
    results = []
    
    # Iterate and Validate
    progress = st.progress(0)
    for idx, row in df.iterrows():
        reasons = []
        
        # 0. Global Check: Unmapped Category
        if row['CATEGORY_CODE'] == 'N/A':
            reasons.append("Category not found in Reference File")
        else:
            # 1. Books Check
            if book_cats:
                res = validate_books(row, book_cats, approved_book_sellers)
                if res: reasons.append(res)
            
            # 2. Sneakers Check
            if sneaker_cats:
                res = validate_sneakers(row, sneaker_cats, sensitive_sneakers)
                if res: reasons.append(res)
                
            # 3. Color Check (Column OR Name)
            if color_cats:
                res = validate_color(row, color_cats, color_regex)
                if res: reasons.append(res)
                
            # 4. Warranty Check
            if warranty_cats:
                res = validate_warranty(row, warranty_cats)
                if res: reasons.append(res)
                
            # 5. Restricted Brands
            if restricted_rules:
                res = validate_restricted_brands(row, restricted_rules)
                if res: reasons.append(res)

        status = "Rejected" if reasons else "Approved"
        row['Validation_Status'] = status
        row['Validation_Reason'] = "; ".join(reasons)
        results.append(row)
        
        if idx % 100 == 0: progress.progress(min(idx/len(df), 1.0))
        
    progress.progress(1.0)
    final_df = pd.DataFrame(results)
    
    # Display
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total", len(final_df))
    c2.metric("✅ Approved", len(final_df[final_df['Validation_Status']=='Approved']))
    c3.metric("❌ Rejected", len(final_df[final_df['Validation_Status']=='Rejected']))
    
    # Show Rejections
    rejected = final_df[final_df['Validation_Status']=='Rejected']
    if not rejected.empty:
        st.subheader("Rejection Issues")
        st.dataframe(rejected[['PRODUCT_SET_SID', 'NAME', 'CATEGORY_CODE', 'Validation_Reason']], use_container_width=True)
    else:
        st.balloons()
        st.success("No issues found!")
        
    # Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        final_df.to_excel(writer, index=False, sheet_name='Results')
        wb = writer.book
        ws = writer.sheets['Results']
        red = wb.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        green = wb.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        idx = final_df.columns.get_loc('Validation_Status')
        ws.conditional_format(1, idx, len(final_df), idx, {'type': 'cell', 'criteria': 'equal', 'value': '"Rejected"', 'format': red})
        ws.conditional_format(1, idx, len(final_df), idx, {'type': 'cell', 'criteria': 'equal', 'value': '"Approved"', 'format': green})
        
    output.seek(0)
    st.download_button("📥 Download Validated File", output, "validation_report.xlsx")

elif prod_file and not path_to_code:
    st.warning("Please upload Category Reference file first.")
