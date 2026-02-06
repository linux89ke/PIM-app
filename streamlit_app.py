import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import logging
from typing import Dict, List, Tuple, Optional, Set
import traceback
import json
import xlsxwriter
import zipfile
import os
import time

# -------------------------------------------------
# 0. IMPORTS & SETUP
# -------------------------------------------------
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

logger = logging.getLogger(__name__)

# -------------------------------------------------
# CONSTANTS & MAPPING
# -------------------------------------------------
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]
FULL_DATA_COLS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE",
    "COLOR", "COLOR_FAMILY", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU",
    "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG", "LISTING_STATUS", 
    "PRODUCT_WARRANTY", "WARRANTY_DURATION", "WARRANTY_ADDRESS", "WARRANTY_TYPE"
]
FX_RATE = 132.0
SPLIT_LIMIT = 9998 

NEW_FILE_MAPPING = {
    'cod_productset_sid': 'PRODUCT_SET_SID', 'dsc_name': 'NAME', 'dsc_brand_name': 'BRAND',
    'cod_category_code': 'CATEGORY_CODE', 'dsc_category_name': 'CATEGORY', 'dsc_shop_seller_name': 'SELLER_NAME',
    'dsc_shop_active_country': 'ACTIVE_STATUS_COUNTRY', 'cod_parent_sku': 'PARENTSKU', 'color': 'COLOR',
    'color_family': 'COLOR_FAMILY', 'list_seller_skus': 'SELLER_SKU', 'image1': 'MAIN_IMAGE',
    'dsc_status': 'LISTING_STATUS', 'dsc_shop_email': 'SELLER_EMAIL', 'product_warranty': 'PRODUCT_WARRANTY',
    'warranty_duration': 'WARRANTY_DURATION', 'warranty_address': 'WARRANTY_ADDRESS', 'warranty_type': 'WARRANTY_TYPE'
}

# -------------------------------------------------
# UTILITIES
# -------------------------------------------------
def clean_category_code(code) -> str:
    try:
        if pd.isna(code): return ""
        s = str(code).strip()
        if s.replace('.', '', 1).isdigit() and '.' in s: return str(int(float(s)))
        return s
    except: return str(code).strip()

def normalize_text(text: str) -> str:
    if pd.isna(text): return ""
    text = str(text).lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', '', text)
    return text

def create_match_key(row: pd.Series) -> str:
    return f"{normalize_text(row.get('BRAND', ''))}|{normalize_text(row.get('NAME', ''))}|{normalize_text(row.get('COLOR', ''))}"

# -------------------------------------------------
# HELPER & LOADING FUNCTIONS
# -------------------------------------------------
def load_txt_file(filename: str) -> List[str]:
    if not os.path.exists(filename): return []
    with open(filename, 'r', encoding='utf-8') as f: return [line.strip() for line in f if line.strip()]

@st.cache_data(ttl=3600)
def load_excel_file(filename: str, column: Optional[str] = None):
    if not os.path.exists(filename): return [] if column else pd.DataFrame()
    df = pd.read_excel(filename, engine='openpyxl', dtype=str)
    df.columns = df.columns.str.strip()
    if column and column in df.columns: return df[column].apply(clean_category_code).tolist()
    return df

@st.cache_data(ttl=3600)
def load_restricted_brands_config(filename: str) -> Dict:
    config = {}
    if not os.path.exists(filename): return {}
    df1 = pd.read_excel(filename, sheet_name=0, engine='openpyxl', dtype=str)
    for _, row in df1.iterrows():
        brand_raw = str(row.get('Brand', '')).strip()
        if not brand_raw or brand_raw.lower() == 'nan': continue
        brand_key = brand_raw.lower()
        sellers = set()
        if 'Sellers' in row and pd.notna(row['Sellers']):
            s = str(row['Sellers']).strip()
            if s.lower() != 'nan': sellers.add(s.lower())
        config[brand_key] = {'sellers': sellers, 'categories': None}
    return config

@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    return {
        'Wrong Category (AI)': ('1000006 - Product Assigned to Wrong Category', "Our AI system detected this product is likely in the wrong category (e.g. Accessory in Main Category, Gender Mismatch)."),
        'Restricted brands': ('1000024 - Product does not have a license', "Product listing rejected due to absence of required license."),
        'Suspected Fake product': ('1000023 - Confirmation of counterfeit product', "Rejected as counterfeit by technical team."),
        'Duplicate product': ('1000007 - Other Reason', "Duplicate product detected."),
    }

@st.cache_data(ttl=3600)
def load_all_support_files() -> Dict:
    return {
        'restricted_brands_config': load_restricted_brands_config('restric_brands.xlsx'),
        'flags_mapping': load_flags_mapping(),
        'suspected_fake': load_excel_file('suspected_fake.xlsx'),
        'duplicate_exempt_codes': load_txt_file('duplicate_exempt.txt'),
        'colors': load_txt_file('colors.txt'),
    }

@st.cache_data(ttl=3600)
def compile_regex_patterns(words: List[str]) -> re.Pattern:
    if not words: return None
    words = sorted(words, key=len, reverse=True)
    return re.compile('|'.join(r'\b' + re.escape(w) + r'\b' for w in words), re.IGNORECASE)

# -------------------------------------------------
# VALIDATION LOGIC
# -------------------------------------------------
def check_duplicate_products(data: pd.DataFrame, **kwargs) -> pd.DataFrame:
    # Simplified duplicate check for this example
    if 'NAME' not in data.columns: return pd.DataFrame(columns=data.columns)
    dup_mask = data.duplicated(subset=['NAME', 'SELLER_NAME'], keep='first')
    return data[dup_mask].copy()

def check_restricted_brands(data: pd.DataFrame, restricted_config: Dict) -> pd.DataFrame:
    if not restricted_config or 'BRAND' not in data.columns: return pd.DataFrame(columns=data.columns)
    # Simplified check
    brand_keys = set(restricted_config.keys())
    mask = data['BRAND'].astype(str).str.lower().isin(brand_keys)
    return data[mask].copy()

def check_suspected_fake_products(data: pd.DataFrame, suspected_fake_df: pd.DataFrame, fx_rate: float) -> pd.DataFrame:
    # Placeholder for logic
    return pd.DataFrame(columns=data.columns)

# -------------------------------------------------
# AI CHECK (Gemini Text)
# -------------------------------------------------
def check_categories_with_ai(data: pd.DataFrame, api_key: str) -> pd.DataFrame:
    """
    AI Check: Uses Gemini to find context-based errors.
    """
    if not HAS_GENAI or not api_key or data.empty:
        return pd.DataFrame(columns=data.columns)

    if not {'PRODUCT_SET_SID', 'NAME', 'CATEGORY'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)

    genai.configure(api_key=api_key)
    safety = [{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"}]
    model = genai.GenerativeModel('gemini-1.5-flash', safety_settings=safety)
    
    batch_size = 60
    records = data[['PRODUCT_SET_SID', 'NAME', 'CATEGORY']].to_dict('records')
    flagged_reasons = {}
    
    progress_text = st.empty()
    bar = st.progress(0)

    base_prompt = """
    Review this list of products (ID | Name | Category).
    Identify clearly MISCATEGORIZED items.
    Examples of errors:
    - "iPhone Case" inside "Mobile Phones" (Should be Accessories)
    - "Laptop Charger" inside "Laptops" (Should be Accessories)
    - "Women's Dress" inside "Men's Fashion"
    
    Return a JSON object: {"ID": "Reason"} for ERRORS ONLY.
    Return {} if no errors.
    
    Data:
    """

    total = len(records)
    for i in range(0, total, batch_size):
        batch = records[i:i+batch_size]
        batch_text = "\n".join([f"{r['PRODUCT_SET_SID']}|{r['NAME']}|{r['CATEGORY']}" for r in batch])
        
        try:
            response = model.generate_content(base_prompt + batch_text)
            text_res = response.text.strip().replace("```json", "").replace("```", "")
            batch_res = json.loads(text_res)
            flagged_reasons.update(batch_res)
            
            progress_text.text(f"AI Scanning: {min(i+batch_size, total)}/{total} items... Found {len(flagged_reasons)} issues.")
            bar.progress(min((i+batch_size)/total, 1.0))
            time.sleep(2.0) 
        except Exception:
            time.sleep(1)
            continue

    bar.empty()
    progress_text.empty()

    if not flagged_reasons:
        return pd.DataFrame(columns=data.columns)

    mask = data['PRODUCT_SET_SID'].astype(str).isin(flagged_reasons.keys())
    result_df = data[mask].drop_duplicates(subset=['PRODUCT_SET_SID']).copy()
    result_df['Comment_Detail'] = result_df['PRODUCT_SET_SID'].astype(str).map(flagged_reasons)
    
    return result_df

# -------------------------------------------------
# MASTER VALIDATION RUNNER
# -------------------------------------------------
def validate_products(data, support_files, api_key=None, enable_ai=False):
    data['PRODUCT_SET_SID'] = data['PRODUCT_SET_SID'].astype(str).str.strip()
    
    # 1. Standard Checks (Removed Rule-Based Category Check)
    validations = [
        ("Restricted brands", check_restricted_brands, {'restricted_config': support_files['restricted_brands_config']}),
        ("Suspected Fake product", check_suspected_fake_products, {'suspected_fake_df': support_files['suspected_fake'], 'fx_rate': FX_RATE}),
        ("Duplicate product", check_duplicate_products, {}),
    ]
    
    # 2. Add AI Check
    ai_run_status = "Skipped"
    if enable_ai and api_key and HAS_GENAI:
        validations.append(("Wrong Category (AI)", check_categories_with_ai, {'api_key': api_key}))
        ai_run_status = "Running"
    
    results = {}
    progress = st.progress(0)
    status = st.empty()
    
    for i, (name, func, kwargs) in enumerate(validations):
        status.text(f"Running: {name}")
        ckwargs = {'data': data, **kwargs}
        try:
            res = func(**ckwargs)
            if not res.empty:
                results[name] = res
            elif name == "Wrong Category (AI)":
                ai_run_status = "Completed (0 Issues)"
        except Exception as e:
            logger.error(f"Error in {name}: {e}")
        progress.progress((i+1)/len(validations))
    
    progress.empty()
    status.empty()
    
    return results, ai_run_status

# -------------------------------------------------
# DATA LOADING HELPERS
# -------------------------------------------------
def standardize_input_data(df):
    df.columns = df.columns.str.strip()
    map_lower = {k.lower(): v for k, v in NEW_FILE_MAPPING.items()}
    new_cols = {col: map_lower.get(col.lower(), col.upper()) for col in df.columns}
    return df.rename(columns=new_cols)

def filter_by_country(df, country_code):
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns: return df
    return df[df['ACTIVE_STATUS_COUNTRY'].astype(str).str.upper() == country_code]

# -------------------------------------------------
# UI
# -------------------------------------------------
st.set_page_config(page_title="Validation Tool", layout="wide")

with st.sidebar:
    st.header("⚙️ Configuration")
    
    # AI Setup
    st.subheader("🤖 AI Settings")
    if not HAS_GENAI:
        st.error("❌ Library `google-generativeai` missing.")
        api_key = None
        enable_ai = False
    else:
        api_key = st.text_input("Gemini API Key", type="password")
        if api_key:
            enable_ai = st.checkbox("Enable AI Category Check", value=True)
            st.success("Ready")
        else:
            enable_ai = False
            st.info("Enter Key to use AI")

    if st.button("♻️ Reload Config"):
        st.cache_data.clear()
        st.rerun()

st.title("Product Validation Tool (AI Only)")

uploaded_files = st.file_uploader("Upload CSV", type=['csv'], accept_multiple_files=True)

if uploaded_files:
    try:
        all_dfs = []
        for f in uploaded_files:
            df = pd.read_csv(f, sep=';', encoding='ISO-8859-1', dtype=str)
            all_dfs.append(standardize_input_data(df))
        
        full_df = pd.concat(all_dfs, ignore_index=True)
        st.info(f"Loaded {len(full_df)} rows.")
        
        if st.button("Run Validation"):
            support_files = load_all_support_files()
            
            results, ai_status = validate_products(full_df, support_files, api_key, enable_ai)
            
            st.success("Validation Complete")
            
            # Show AI Status explicitly
            if enable_ai:
                if ai_status == "Completed (0 Issues)":
                    st.success("✅ AI Check Completed: No wrong categories found.")
                elif "Wrong Category (AI)" in results:
                    st.error(f"❌ AI Check Found {len(results['Wrong Category (AI)'])} Issues")
            
            # Show all results
            for name, res_df in results.items():
                with st.expander(f"{name} ({len(res_df)})", expanded=True):
                    cols = ['PRODUCT_SET_SID', 'NAME', 'CATEGORY', 'Comment_Detail']
                    st.dataframe(res_df[[c for c in cols if c in res_df.columns]])
            
    except Exception as e:
        st.error(f"Error: {e}")
