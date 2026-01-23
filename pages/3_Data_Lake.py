import pandas as pd
import streamlit as st
from io import BytesIO
import re
import os
import warnings

# Suppress warnings
warnings.filterwarnings('ignore')

# -------------------------------------------------
# 1. SETUP & UTILS
# -------------------------------------------------
st.set_page_config(page_title="Production Validator", layout="wide")

# Column Mapping (User File -> System Standard)
COLUMN_MAPPING = {
    'sku': 'PRODUCT_SET_SID', 'SKU': 'PRODUCT_SET_SID',
    'name': 'NAME', 'Name': 'NAME',
    'brand': 'BRAND', 'Brand': 'BRAND',
    'sellerName': 'SELLER_NAME', 'Seller Name': 'SELLER_NAME',
    'image': 'MAIN_IMAGE', 'Image': 'MAIN_IMAGE',
    'newPrice': 'GLOBAL_SALE_PRICE', 'New Price': 'GLOBAL_SALE_PRICE', # Price Check
    'url': 'PRODUCT_URL',
    'color': 'COLOR', 'Color': 'COLOR',
    'categories': 'CATEGORY_PATH_RAW', 'Category': 'CATEGORY_PATH_RAW',
    'product_warranty': 'PRODUCT_WARRANTY',
    'warranty_duration': 'WARRANTY_DURATION'
}

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

def parse_ksh_price(price_str):
    """Converts 'KSh 7,899' or '7899' to float 7899.0"""
    try:
        if pd.isna(price_str): return 0.0
        # Remove 'KSh', commas, and whitespace
        clean = re.sub(r'[^\d.]', '', str(price_str))
        return float(clean) if clean else 0.0
    except:
        return 0.0

@st.cache_data
def load_config_file(filename, file_type='excel', col=None):
    """Robust file loader."""
    if not os.path.exists(filename):
        return [] if col else None
    try:
        if file_type == 'excel': df = pd.read_excel(filename, dtype=str)
        elif file_type == 'csv': df = pd.read_csv(filename, dtype=str)
        elif file_type == 'txt': 
            with open(filename, 'r', encoding='utf-8') as f:
                return [line.strip().lower() for line in f if line.strip()]
        
        if col and not df.empty:
            found_col = next((c for c in df.columns if c.lower() == col.lower()), None)
            if found_col: return df[found_col].dropna().apply(clean_code).tolist()
            return []
        return df
    except: return [] if col else None

# -------------------------------------------------
# 2. VALIDATION LOGIC MODULES
# -------------------------------------------------

def check_suspected_fake_price(row, fake_config_df):
    """
    Checks if Price < Minimum Reference Price for that Brand/Category.
    Assumes fake_config_df has Brands as columns, Rows as Category codes, Values as MinPrice.
    """
    if fake_config_df is None: return None
    
    brand = str(row.get('BRAND', '')).strip().lower()
    cat_code = str(row.get('CATEGORY_CODE', ''))
    
    # 1. Check if Brand exists in config columns
    # Normalize config columns to lowercase for matching
    config_brands = {c.lower(): c for c in fake_config_df.columns}
    
    if brand in config_brands:
        real_col_name = config_brands[brand]
        
        # 2. Find the price threshold for this Category (simplified lookup)
        # Note: Real implementation needs complex matching of category hierarchy.
        # Here we attempt to find if the category ID or Name exists in the Brand Column
        
        # Taking a safer approach: Global Threshold per Brand if structure is complex
        # Or finding the first numeric value for that brand as a baseline
        try:
            threshold_series = pd.to_numeric(fake_config_df[real_col_name], errors='coerce').dropna()
            if not threshold_series.empty:
                min_threshold = threshold_series.min() # Conservative approach
                
                # 3. Compare Price
                current_price = parse_ksh_price(row.get('GLOBAL_SALE_PRICE', 0))
                
                if current_price > 0 and current_price < min_threshold:
                    return f"Suspected Fake: Price ({current_price}) below reference ({min_threshold})"
        except:
            pass
            
    return None

def validate_sneakers(row, sneaker_cats, sensitive_brands):
    if row['CATEGORY_CODE'] in sneaker_cats:
        brand = str(row.get('BRAND', '')).strip().lower()
        if brand in ['generic', 'fashion', 'no brand', 'other']:
            name = str(row.get('NAME', '')).lower()
            for bad_brand in sensitive_brands:
                if f" {bad_brand} " in f" {name} ":
                    return f"Counterfeit: Generic brand with '{bad_brand}' in name"
    return None

def validate_jerseys(row, jerseys_df):
    if jerseys_df is None: return None
    # Load logic inside function or pre-load
    jersey_cats = set(jerseys_df['Categories'].astype(str).apply(clean_code)) if 'Categories' in jerseys_df else set()
    
    if row['CATEGORY_CODE'] in jersey_cats:
        exempt = [s.lower() for s in jerseys_df['Exempted'].astype(str) if str(s)!='nan'] if 'Exempted' in jerseys_df else []
        keywords = [k.lower() for k in jerseys_df['Checklist'].astype(str) if str(k)!='nan'] if 'Checklist' in jerseys_df else []
        
        seller = str(row.get('SELLER_NAME', '')).lower()
        if seller not in exempt:
            name = str(row.get('NAME', '')).lower()
            for k in keywords:
                if k in name:
                    return f"Counterfeit Jersey: Protected term '{k}' detected"
    return None

def validate_books(row, book_cats, approved_sellers):
    if row['CATEGORY_CODE'] in book_cats:
        seller = str(row.get('SELLER_NAME', '')).strip().lower()
        approved_norm = [str(s).strip().lower() for s in approved_sellers]
        if seller not in approved_norm:
            return "Restricted: Seller not approved for Books"
    return None

def validate_color(row, color_cats, valid_colors_regex):
    if row['CATEGORY_CODE'] in color_cats:
        col_val = str(row.get('COLOR', '')).strip().lower()
        if col_val not in ['nan', '', 'none', 'null']: return None
        if valid_colors_regex:
            name_val = str(row.get('NAME', ''))
            if valid_colors_regex.search(name_val): return None
        return "Missing Color: Not found in Column or Name"
    return None

def validate_warranty(row, warranty_cats):
    if row['CATEGORY_CODE'] in warranty_cats:
        w = str(row.get('PRODUCT_WARRANTY', '')).strip().lower()
        d = str(row.get('WARRANTY_DURATION', '')).strip().lower()
        if w in ['nan', '', 'none'] and d in ['nan', '', 'none']:
             return "Missing Warranty Details"
    return None

def validate_restricted_brands(row, restricted_brands_df):
    if restricted_brands_df is None: return None
    brand = str(row.get('BRAND', '')).strip().lower()
    
    # Simple check: Is brand in column A? Is seller in Column B?
    # This assumes structure: Brand | Sellers
    match = restricted_brands_df[restricted_brands_df['Brand'].astype(str).str.lower() == brand]
    if not match.empty:
        allowed_raw = str(match.iloc[0]['Sellers']).lower()
        current_seller = str(row.get('SELLER_NAME', '')).lower()
        
        # If 'nan' or empty, usually means NO ONE is allowed or ALL allowed? 
        # Usually restricted file implies ONLY these sellers.
        if allowed_raw != 'nan':
            allowed_list = [s.strip() for s in allowed_raw.split(',')] # Assuming comma sep if multiple
            # Or usually it's one row per brand
            if current_seller not in allowed_raw: # Loose match
                return f"Restricted Brand: '{row.get('BRAND')}'"
    return None

# -------------------------------------------------
# 3. MAIN APPLICATION
# -------------------------------------------------

with st.sidebar:
    st.header("1. Configuration")
    cat_ref_file = st.file_uploader("Upload Category Reference (xlsx)", type=['xlsx', 'csv'])
    
    # Load System Rules from Disk
    with st.spinner("Loading Rules..."):
        # Counterfeit / Fake
        suspected_fake_df = load_config_file("suspected_fake.xlsx", "excel")
        jerseys_config = load_config_file("Jerseys.xlsx", "excel")
        sneaker_cats = set(load_config_file("Sneakers_Cat.txt", "txt"))
        sensitive_sneakers = load_config_file("Sneakers_Sensitive.txt", "txt")
        
        # Specific Cats
        book_cats = set(load_config_file("Books_cat.xlsx", "excel", "CategoryCode"))
        approved_book_sellers = set(load_config_file("Books_Approved_Sellers.xlsx", "excel", "SellerName"))
        
        # Attributes
        color_cats = set(load_config_file("color_cats.txt", "txt"))
        valid_colors = load_config_file("colors.txt", "txt")
        warranty_cats = set(load_config_file("warranty.txt", "txt"))
        
        # Brands
        rb_df = load_config_file("restric_brands.xlsx", "excel")

        # Color Regex
        color_regex = None
        if valid_colors:
            pattern = '|'.join(r'\b' + re.escape(c) + r'\b' for c in sorted(valid_colors, key=len, reverse=True))
            color_regex = re.compile(pattern, re.IGNORECASE)

st.title("🛡️ Integrated Product Validator")
st.markdown("Checks: **Price (Shillings), Counterfeits, Restricted Brands, Attributes** based on Category Code.")

# 1. BUILD CATEGORY MAP
path_to_code = {}
if cat_ref_file:
    try:
        if cat_ref_file.name.endswith('.csv'): ref_df = pd.read_csv(cat_ref_file)
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

# 2. UPLOAD & PROCESS
prod_file = st.file_uploader("Upload Product File (download (3).csv)", type=['csv', 'xlsx'])

if prod_file and path_to_code:
    # Read
    try:
        if prod_file.name.endswith('.xlsx'): raw_df = pd.read_excel(prod_file, dtype=str)
        else:
            prod_file.seek(0)
            try:
                raw_df = pd.read_csv(prod_file, sep='|', dtype=str, on_bad_lines='skip')
                if len(raw_df.columns) < 2: raise Exception
            except:
                prod_file.seek(0)
                raw_df = pd.read_csv(prod_file, sep=',', dtype=str)
    except Exception as e:
        st.error(f"Read Error: {e}"); st.stop()
        
    # Standardize
    df = raw_df.rename(columns=COLUMN_MAPPING)
    
    # Map Categories
    df['normalized_path'] = df['CATEGORY_PATH_RAW'].apply(normalize_path_input)
    df['CATEGORY_CODE'] = df['normalized_path'].map(path_to_code).fillna("N/A")
    
    st.info(f"Validating {len(df)} products...")
    
    results = []
    progress = st.progress(0)
    
    for idx, row in df.iterrows():
        reasons = []
        
        if row['CATEGORY_CODE'] == 'N/A':
            reasons.append("Unmapped Category")
        else:
            # --- START VALIDATIONS ---
            
            # 1. Suspected Fake (Price Check)
            if suspected_fake_df is not None:
                res = check_suspected_fake_price(row, suspected_fake_df)
                if res: reasons.append(res)
                
            # 2. Counterfeit Sneakers
            if sneaker_cats:
                res = validate_sneakers(row, sneaker_cats, sensitive_sneakers)
                if res: reasons.append(res)
                
            # 3. Counterfeit Jerseys
            if jerseys_config is not None:
                res = validate_jerseys(row, jerseys_config)
                if res: reasons.append(res)
                
            # 4. Books
            if book_cats:
                res = validate_books(row, book_cats, approved_book_sellers)
                if res: reasons.append(res)
                
            # 5. Color
            if color_cats:
                res = validate_color(row, color_cats, color_regex)
                if res: reasons.append(res)
                
            # 6. Warranty
            if warranty_cats:
                res = validate_warranty(row, warranty_cats)
                if res: reasons.append(res)
                
            # 7. Restricted Brands
            if rb_df is not None:
                res = validate_restricted_brands(row, rb_df)
                if res: reasons.append(res)
                
            # --- END VALIDATIONS ---

        status = "Rejected" if reasons else "Approved"
        row['Validation_Status'] = status
        row['Validation_Reason'] = "; ".join(reasons)
        results.append(row)
        
        if idx % 100 == 0: progress.progress(min(idx/len(df), 1.0))
        
    progress.progress(1.0)
    final_df = pd.DataFrame(results)
    
    # Show Results
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total", len(final_df))
    c2.metric("✅ Approved", len(final_df[final_df['Validation_Status']=='Approved']))
    c3.metric("❌ Rejected", len(final_df[final_df['Validation_Status']=='Rejected']))
    
    rejected = final_df[final_df['Validation_Status']=='Rejected']
    if not rejected.empty:
        st.subheader("Rejection Analysis")
        st.dataframe(rejected[['PRODUCT_SET_SID', 'NAME', 'GLOBAL_SALE_PRICE', 'Validation_Reason']], use_container_width=True)
        
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
    st.download_button("📥 Download Result", output, "validation_result.xlsx")

elif prod_file and not path_to_code:
    st.warning("Upload Category Reference First.")
