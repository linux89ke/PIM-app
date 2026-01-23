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
st.set_page_config(page_title="Data Lake Validator", layout="wide")

# FX Rate for Price Check (USD -> KSh)
FX_RATE = 132.0

# Standardize User Columns to System Columns
COLUMN_MAPPING = {
    'sku': 'PRODUCT_SET_SID', 'SKU': 'PRODUCT_SET_SID',
    'name': 'NAME', 'Name': 'NAME',
    'brand': 'BRAND', 'Brand': 'BRAND',
    'sellerName': 'SELLER_NAME', 'Seller Name': 'SELLER_NAME',
    'image': 'MAIN_IMAGE', 'Image': 'MAIN_IMAGE',
    'newPrice': 'GLOBAL_SALE_PRICE', 'New Price': 'GLOBAL_SALE_PRICE',
    'oldPrice': 'GLOBAL_PRICE', 'Old Price': 'GLOBAL_PRICE',
    'url': 'PRODUCT_URL', 'URL': 'PRODUCT_URL',
    'color': 'COLOR', 'Color': 'COLOR',
    'categories': 'CATEGORY_PATH_RAW', 'Category': 'CATEGORY_PATH_RAW',
    'product_warranty': 'PRODUCT_WARRANTY',
    'warranty_duration': 'WARRANTY_DURATION'
}

def normalize_path_input(text):
    """Converts 'Home & Office->Appliances' to 'home & office / appliances'"""
    if pd.isna(text): return ""
    text = str(text).strip().lower().replace('->', ' / ').replace('/', ' / ')
    return re.sub(r'\s+', ' ', text).strip()

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
    # Check paths
    paths_to_check = [filename, f"pages/{filename}", f"../{filename}"]
    valid_path = next((p for p in paths_to_check if os.path.exists(p)), None)
    
    if not valid_path: return [] if col else None

    try:
        if file_type == 'excel': df = pd.read_excel(valid_path, dtype=str)
        elif file_type == 'csv': df = pd.read_csv(valid_path, dtype=str)
        elif file_type == 'txt': 
            with open(valid_path, 'r', encoding='utf-8') as f:
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
    Parses specific matrix structure of suspected_fake.xlsx:
    Row 0 (Header): Brands
    Row 1: Price in USD
    Rows 2+: Category Codes
    """
    if fake_config_df is None or fake_config_df.empty: return None
    
    brand = str(row.get('BRAND', '')).strip().lower()
    cat_code = str(row.get('CATEGORY_CODE', ''))
    
    if not cat_code or cat_code == 'N/A': return None

    # Map brand columns (lowercase -> actual name)
    col_map = {str(c).lower().strip(): c for c in fake_config_df.columns}
    
    if brand in col_map:
        real_col = col_map[brand]
        
        try:
            # 1. Get USD Price from First Row
            price_usd = float(fake_config_df[real_col].iloc[0])
            threshold_ksh = price_usd * FX_RATE
            
            # 2. Check if Product Category is listed in the column
            # (Skip row 0 which is price)
            valid_cats = fake_config_df[real_col].iloc[1:].dropna().astype(str).apply(clean_code).tolist()
            
            if cat_code in valid_cats:
                # 3. Compare Price
                product_price = parse_ksh_price(row.get('GLOBAL_SALE_PRICE', 0))
                
                # Flag if price is suspiciously low (but not zero/free)
                if 0 < product_price < threshold_ksh:
                    return f"Suspected Fake: Price ({product_price:,.0f}) < Threshold ({threshold_ksh:,.0f})"
                    
        except Exception:
            pass # Handle parsing errors gracefully
            
    return None

def validate_sneakers(row, sneaker_cats, sensitive_brands):
    """Strict regex check for protected brands in Generic items."""
    if row['CATEGORY_CODE'] in sneaker_cats:
        brand = str(row.get('BRAND', '')).strip().lower()
        if brand in ['generic', 'fashion', 'no brand', 'other', '', 'nan']:
            name = str(row.get('NAME', '')).lower()
            for bad_brand in sensitive_brands:
                if re.search(r'\b' + re.escape(bad_brand) + r'\b', name):
                    return f"Counterfeit: Generic brand with '{bad_brand}' in name"
    return None

def validate_jerseys(row, jerseys_df):
    """Checks for protected team names in Jerseys category."""
    if jerseys_df is None: return None
    
    if 'Categories' in jerseys_df:
        jersey_cats = set(jerseys_df['Categories'].astype(str).apply(clean_code))
        if row['CATEGORY_CODE'] not in jersey_cats: return None

    exempt = set([str(s).lower().strip() for s in jerseys_df['Exempted'] if str(s)!='nan']) if 'Exempted' in jerseys_df else set()
    seller = str(row.get('SELLER_NAME', '')).lower().strip()
    if seller in exempt: return None
        
    keywords = [str(k).lower().strip() for k in jerseys_df['Checklist'] if str(k)!='nan'] if 'Checklist' in jerseys_df else []
    name = str(row.get('NAME', '')).lower()
    
    for k in keywords:
        if k and re.search(r'\b' + re.escape(k) + r'\b', name):
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
        if col_val not in ['nan', '', 'none', 'null', '']: return None
        if valid_colors_regex:
            name_val = str(row.get('NAME', ''))
            if valid_colors_regex.search(name_val): return None
        return "Missing Color: Not found in Column or Name"
    return None

def validate_warranty(row, warranty_cats):
    if row['CATEGORY_CODE'] in warranty_cats:
        w = str(row.get('PRODUCT_WARRANTY', '')).strip().lower()
        d = str(row.get('WARRANTY_DURATION', '')).strip().lower()
        if w in ['nan', '', 'none', ''] and d in ['nan', '', 'none', '']:
             return "Missing Warranty Details"
    return None

def validate_restricted_brands(row, restricted_brands_df):
    if restricted_brands_df is None: return None
    brand = str(row.get('BRAND', '')).strip().lower()
    if not brand: return None
    
    match = restricted_brands_df[restricted_brands_df['Brand'].astype(str).str.lower() == brand]
    if not match.empty:
        allowed_raw = str(match.iloc[0]['Sellers']).lower()
        current_seller = str(row.get('SELLER_NAME', '')).lower()
        if allowed_raw != 'nan' and current_seller not in allowed_raw:
            return f"Restricted Brand: '{row.get('BRAND')}'"
    return None

def validate_prohibited(row, prohibited_list):
    if not prohibited_list: return None
    name = str(row.get('NAME', '')).lower()
    for word in prohibited_list:
        if re.search(r'\b' + re.escape(word) + r'\b', name):
             return f"Prohibited Item: Contains '{word}'"
    return None

def validate_single_word(row):
    name = str(row.get('NAME', '')).strip()
    if len(name.split()) < 2:
        return "Invalid Name: Single word title"
    return None

# -------------------------------------------------
# 3. MAIN APPLICATION
# -------------------------------------------------

with st.sidebar:
    st.header("1. Configuration")
    cat_ref_file = st.file_uploader("Upload Category Reference (xlsx/csv)", type=['xlsx', 'csv'])
    
    with st.spinner("Loading Validation Rules..."):
        suspected_fake_df = load_config_file("suspected_fake.xlsx", "excel")
        jerseys_config = load_config_file("Jerseys.xlsx", "excel")
        sneaker_cats = set(load_config_file("Sneakers_Cat.txt", "txt"))
        sensitive_sneakers = load_config_file("Sneakers_Sensitive.txt", "txt")
        book_cats = set(load_config_file("Books_cat.xlsx", "excel", "CategoryCode"))
        approved_book_sellers = set(load_config_file("Books_Approved_Sellers.xlsx", "excel", "SellerName"))
        color_cats = set(load_config_file("color_cats.txt", "txt"))
        valid_colors = load_config_file("colors.txt", "txt")
        warranty_cats = set(load_config_file("warranty.txt", "txt"))
        prohibited_ke = load_config_file("prohibited_productsKE.txt", "txt")
        rb_df = load_config_file("restric_brands.xlsx", "excel")

        color_regex = None
        if valid_colors:
            pattern = '|'.join(r'\b' + re.escape(c) + r'\b' for c in sorted(valid_colors, key=len, reverse=True))
            color_regex = re.compile(pattern, re.IGNORECASE)

    st.success("System Rules Loaded")

st.title("🛡️ Data Lake Validator")
st.markdown("Full compliance check including **USD Price Thresholds**.")

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
    for col in ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'SELLER_NAME', 'GLOBAL_SALE_PRICE', 'COLOR', 'PRODUCT_WARRANTY']:
        if col not in df.columns: df[col] = ""

    # Map Categories
    cat_col = 'categories' if 'categories' in raw_df.columns else 'Category'
    if cat_col in raw_df.columns:
        df['normalized_path'] = raw_df[cat_col].apply(normalize_path_input)
        df['CATEGORY_CODE'] = df['normalized_path'].map(path_to_code).fillna("N/A")
    else:
        st.error("Could not find 'categories' column.")
        st.stop()
    
    st.info(f"Validating {len(df)} products...")
    
    results = []
    progress = st.progress(0)
    
    for idx, row in df.iterrows():
        reasons = []
        
        if row['CATEGORY_CODE'] == 'N/A':
            reasons.append("Unmapped Category (Not found in Ref)")
        else:
            # 1. Fake Price Check
            res = check_suspected_fake_price(row, suspected_fake_df)
            if res: reasons.append(res)
                
            # 2. Counterfeit Sneakers
            if sneaker_cats:
                res = validate_sneakers(row, sneaker_cats, sensitive_sneakers)
                if res: reasons.append(res)
                
            # 3. Counterfeit Jerseys
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
            res = validate_restricted_brands(row, rb_df)
            if res: reasons.append(res)
            
            # 8. Prohibited Words
            res = validate_prohibited(row, prohibited_ke)
            if res: reasons.append(res)
            
        # 9. Single Word
        res = validate_single_word(row)
        if res: reasons.append(res)

        status = "Rejected" if reasons else "Approved"
        row['Validation_Status'] = status
        row['Validation_Reason'] = "; ".join(reasons)
        results.append(row)
        
        if idx % 100 == 0: progress.progress(min(idx/len(df), 1.0))
        
    progress.progress(1.0)
    final_df = pd.DataFrame(results)
    
    # 4. DISPLAY & EXPORT
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total", len(final_df))
    c2.metric("✅ Approved", len(final_df[final_df['Validation_Status']=='Approved']))
    c3.metric("❌ Rejected", len(final_df[final_df['Validation_Status']=='Rejected']))
    
    rejected = final_df[final_df['Validation_Status']=='Rejected']
    if not rejected.empty:
        st.subheader("Rejection Analysis")
        st.dataframe(rejected[['PRODUCT_SET_SID', 'NAME', 'GLOBAL_SALE_PRICE', 'Validation_Reason']], use_container_width=True)
    else:
        st.success("No issues found! All items approved.")
        
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        export_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'SELLER_NAME', 'GLOBAL_SALE_PRICE', 'Validation_Status', 'Validation_Reason']
        if 'categories' in raw_df.columns: export_cols.append('categories')
        
        final_cols = [c for c in export_cols if c in final_df.columns]
        final_df[final_cols].to_excel(writer, index=False, sheet_name='Results')
        
        wb = writer.book
        ws = writer.sheets['Results']
        red = wb.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        green = wb.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        
        idx = final_df[final_cols].columns.get_loc('Validation_Status')
        ws.conditional_format(1, idx, len(final_df), idx, {'type': 'cell', 'criteria': 'equal', 'value': '"Rejected"', 'format': red})
        ws.conditional_format(1, idx, len(final_df), idx, {'type': 'cell', 'criteria': 'equal', 'value': '"Approved"', 'format': green})
        
    output.seek(0)
    st.download_button("📥 Download Result", output, "validation_result.xlsx")

elif prod_file and not path_to_code:
    st.warning("Please upload the Category Reference file first.")
