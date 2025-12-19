import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import logging
from typing import Dict, List, Tuple, Optional
import traceback
import json
import xlsxwriter
import altair as alt

# -------------------------------------------------
# Logging Configuration
# -------------------------------------------------
logging.basicConfig(
    filename=f'validation_{datetime.now().strftime("%Y%m%d")}.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# -------------------------------------------------
# Page config
# -------------------------------------------------
st.set_page_config(page_title="Product Validation Tool", layout="wide")

# -------------------------------------------------
# Constants & Mapping
# -------------------------------------------------
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]
REJECTION_REASONS_COLS = ['CODE - REJECTION_REASON', 'COMMENT']
FULL_DATA_COLS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE",
    "COLOR", "COLOR_FAMILY", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU",
    "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG",
    "LISTING_STATUS", "SELLER_RATING", "STOCK_QTY", "PRODUCT_WARRANTY", "WARRANTY_DURATION",
    "WARRANTY_ADDRESS", "WARRANTY_TYPE"
]

VISIBLE_COLUMNS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", 
    "CATEGORY", "CATEGORY_CODE", "COLOR", "MAIN_IMAGE", 
    "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU"
]

FX_RATE = 132.0 

NEW_FILE_MAPPING = {
    'cod_productset_sid': 'PRODUCT_SET_SID',
    'dsc_name': 'NAME',
    'dsc_brand_name': 'BRAND',
    'cod_category_code': 'CATEGORY_CODE',
    'dsc_category_name': 'CATEGORY',
    'dsc_shop_seller_name': 'SELLER_NAME',
    'dsc_shop_active_country': 'ACTIVE_STATUS_COUNTRY',
    'cod_parent_sku': 'PARENTSKU',
    'color': 'COLOR',
    'color_family': 'COLOR_FAMILY',
    'list_seller_skus': 'SELLER_SKU',
    'image1': 'MAIN_IMAGE',
    'dsc_status': 'LISTING_STATUS',
    'dsc_shop_email': 'SELLER_EMAIL',
    'product_warranty': 'PRODUCT_WARRANTY',
    'warranty_duration': 'WARRANTY_DURATION',
    'warranty_address': 'WARRANTY_ADDRESS',
    'warranty_type': 'WARRANTY_TYPE'
}

# -------------------------------------------------
# CACHED FILE LOADING
# -------------------------------------------------
@st.cache_data(ttl=3600)
def load_txt_file(filename: str) -> List[str]:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = [line.strip() for line in f if line.strip()]
        return data
    except Exception as e:
        logger.error(f"Error reading {filename}: {e}")
        return []

@st.cache_data(ttl=3600)
def load_excel_file(filename: str, column: Optional[str] = None) -> pd.DataFrame:
    try:
        df = pd.read_excel(filename, engine='openpyxl', dtype=str)
        df.columns = df.columns.str.strip()
        if column and column in df.columns:
            return df[column].astype(str).str.strip().tolist()
        return df
    except Exception as e:
        logger.error(f"Error reading {filename}: {e}")
        return [] if column else pd.DataFrame()

@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    try:
        flag_mapping = {
            'Seller Not approved to sell Refurb': (
                '1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim',
                "Please contact Jumia Seller Support and raise a claim to confirm whether this product is eligible for listing."
            ),
            'BRAND name repeated in NAME': (
                '1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name',
                "Please do not write the brand name in the Product Name field."
            ),
            'Missing COLOR': (
                '1000005 - Kindly confirm the actual product colour',
                "Please make sure that the product color is clearly mentioned in both the title and in the color tab."
            ),
            'Duplicate product': (
                '1000007 - Other Reason',
                "Kindly avoid creating duplicate SKUs"
            ),
            'Prohibited products': (
                '1000024 - Product does not have a license to be sold via Jumia (Not Authorized)',
                "Your product listing has been rejected due to the absence of a required license for this item."
            ),
            'Single-word NAME': (
                '1000008 - Kindly Improve Product Name Description',
                "Kindly update the product title using this format: Name – Type of the Products – Color."
            ),
            'Unnecessary words in NAME': (
                '1000008 - Kindly Improve Product Name Description',
                "Kindly avoid unnecessary words in product title."
            ),
            'Generic BRAND Issues': (
                '1000014 - Kindly request for the creation of this product\'s brand',
                "To create the actual brand name for this product, please fill out the form at: https://bit.ly/2kpjja8."
            ),
            'Counterfeit Sneakers': (
                '1000030 - Suspected Counterfeit/Fake Product',
                "This product is suspected to be counterfeit or fake and is not authorized for sale."
            ),
            'Seller Approve to sell books': (
                '1000028 - Kindly Contact Jumia Seller Support',
                "Please contact Jumia Seller Support to confirm possibility of sale for books."
            ),
            'Seller Approved to Sell Perfume': (
                '1000028 - Kindly Contact Jumia Seller Support',
                "Please contact Jumia Seller Support to confirm possibility of sale for perfume."
            ),
            'Suspected counterfeit Jerseys': (
                '1000030 - Suspected Counterfeit/Fake Product',
                "This product is suspected to be counterfeit or fake and is not authorized for sale."
            ),
            'Suspected Fake product': (
                '1000030 - Suspected Counterfeit/Fake Product',
                "This product is suspected to be counterfeit or fake and is not authorized for sale."
            ),
            'Product Warranty': (
                '1000013 - Kindly Provide Product Warranty Details',
                "For listing this type of product requires a valid warranty as per our platform guidelines."
            ),
            'Sensitive words': (
                '1000001 - Brand NOT Allowed', 
                "Your listing was rejected because it includes brands that are not allowed on Jumia."
            ),
        }
        return flag_mapping
    except Exception: return {}

@st.cache_data(ttl=3600)
def load_all_support_files() -> Dict:
    files = {
        'blacklisted_words': load_txt_file('blacklisted.txt'),
        'book_category_codes': load_excel_file('Books_cat.xlsx', 'CategoryCode'),
        'approved_book_sellers': load_excel_file('Books_Approved_Sellers.xlsx', 'SellerName'),
        'perfume_category_codes': load_txt_file('Perfume_cat.txt'),
        'sensitive_perfume_brands': [b.lower() for b in load_txt_file('sensitive_perfumes.txt')],
        'approved_perfume_sellers': load_excel_file('perfumeSellers.xlsx', 'SellerName'),
        'sneaker_category_codes': load_txt_file('Sneakers_Cat.txt'),
        'sneaker_sensitive_brands': [b.lower() for b in load_txt_file('Sneakers_Sensitive.txt')],
        'sensitive_words': [w.lower() for w in load_txt_file('sensitive_words.txt')], 
        'unnecessary_words': [w.lower() for w in load_txt_file('unnecessary.txt')], 
        'colors': [c.lower() for c in load_txt_file('colors.txt')],
        'color_categories': load_txt_file('color_cats.txt'),
        'check_variation': load_excel_file('check_variation.xlsx'),
        'category_fas': load_excel_file('category_FAS.xlsx'),
        'reasons': load_excel_file('reasons.xlsx'),
        'flags_mapping': load_flags_mapping(),
        'jerseys_config': load_excel_file('Jerseys.xlsx'),
        'warranty_category_codes': load_txt_file('warranty.txt'),
        'suspected_fake': load_excel_file('suspected_fake.xlsx'),
        'approved_refurb_sellers_ke': [s.lower() for s in load_txt_file('Refurb_LaptopKE.txt')],
        'approved_refurb_sellers_ug': [s.lower() for s in load_txt_file('Refurb_LaptopUG.txt')],
    }
    return files

@st.cache_data(ttl=3600)
def compile_regex_patterns(words: List[str]) -> re.Pattern:
    if not words: return None
    pattern = '|'.join(r'\b' + re.escape(w) + r'\b' for w in words)
    return re.compile(pattern, re.IGNORECASE)

# -------------------------------------------------
# Country & Helper Classes
# -------------------------------------------------
class CountryValidator:
    COUNTRY_CONFIG = {
        "Kenya": {"code": "KE", "skip_validations": [], "prohibited_products_file": "prohibited_productsKE.txt"},
        "Uganda": {"code": "UG", "skip_validations": ["Seller Approve to sell books", "Seller Approved to Sell Perfume", "Counterfeit Sneakers", "Product Warranty"], "prohibited_products_file": "prohibited_productsUG.txt"}
    }
    def __init__(self, country: str):
        self.country = country
        self.config = self.COUNTRY_CONFIG.get(country, self.COUNTRY_CONFIG["Kenya"])
        self.code = self.config["code"]
        self.skip_validations = self.config["skip_validations"]
    def should_skip_validation(self, validation_name: str) -> bool:
        return validation_name in self.skip_validations
    def ensure_status_column(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty: return df
        if 'Status' not in df.columns: df['Status'] = 'Approved'
        return df
    @st.cache_data(ttl=3600)
    def load_prohibited_products(_self) -> List[str]:
        filename = _self.config["prohibited_products_file"]
        return [w.lower() for w in load_txt_file(filename)]

# -------------------------------------------------
# Improved Data Loading & Standardization
# -------------------------------------------------
def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Force lowercase for matching
    df.columns = [str(c).strip().lower() for c in df.columns]
    # Create lowercase mapping to handle case-insensitive input headers
    lower_mapping = {k.lower(): v for k, v in NEW_FILE_MAPPING.items()}
    df = df.rename(columns=lower_mapping)
    
    if 'ACTIVE_STATUS_COUNTRY' in df.columns:
        df['ACTIVE_STATUS_COUNTRY'] = (
            df['ACTIVE_STATUS_COUNTRY'].astype(str).str.lower()
            .str.replace('jumia-', '', regex=False).str.strip().str.upper()
        )
    return df

def validate_input_schema(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    errors = []
    required = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'ACTIVE_STATUS_COUNTRY']
    for field in required:
        if field not in df.columns: errors.append(f"Missing: {field}")
    return len(errors) == 0, errors

def propagate_metadata(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    cols_to_propagate = ['COLOR_FAMILY', 'PRODUCT_WARRANTY', 'WARRANTY_DURATION', 'WARRANTY_ADDRESS', 'WARRANTY_TYPE']
    for col in cols_to_propagate:
        if col not in df.columns: df[col] = pd.NA
    for col in cols_to_propagate:
        df[col] = df.groupby('PRODUCT_SET_SID')[col].transform(lambda x: x.ffill().bfill())
    return df

def filter_by_country(df: pd.DataFrame, country_validator: CountryValidator, source: str) -> pd.DataFrame:
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns: return df
    df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.strip().str.upper()
    mask = df['ACTIVE_STATUS_COUNTRY'] == country_validator.code
    filtered = df[mask].copy()
    if filtered.empty:
        st.error(f"No {country_validator.code} rows left in {source}")
        st.stop()
    return filtered

# --- Validation Logic Functions ---
def check_refurb_seller_approval(data, approved_sellers_ke, approved_sellers_ug, country_code):
    approved = set(approved_sellers_ke) if country_code == 'KE' else set(approved_sellers_ug)
    refurb_words = r'\b(refurb|refurbished|renewed)\b'
    data = data.copy()
    data['NAME_LOWER'] = data['NAME'].astype(str).str.lower()
    data['BRAND_LOWER'] = data['BRAND'].astype(str).str.lower()
    data['SELLER_LOWER'] = data['SELLER_NAME'].astype(str).str.lower()
    mask = (data['NAME_LOWER'].str.contains(refurb_words, regex=True, na=False)) | (data['BRAND_LOWER'] == 'renewed')
    flagged = data[mask & ~data['SELLER_LOWER'].isin(approved)]
    return flagged.drop(columns=['NAME_LOWER', 'BRAND_LOWER', 'SELLER_LOWER'])

def check_unnecessary_words(data, pattern):
    mask = data['NAME'].astype(str).str.lower().str.contains(pattern, na=False)
    return data[mask]

def check_product_warranty(data, warranty_category_codes):
    data = data.copy()
    data['CAT_CLEAN'] = data['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
    target_data = data[data['CAT_CLEAN'].isin(warranty_category_codes)].copy()
    def is_present(s): return (s.astype(str).str.strip().str.lower().isin(['nan', '', 'none', 'nat', 'n/a'])) == False
    mask = ~(is_present(target_data['PRODUCT_WARRANTY']) | is_present(target_data['WARRANTY_DURATION']))
    return target_data[mask]

def check_missing_color(data, pattern, color_categories, country_code='KE'):
    data = data[data['CATEGORY_CODE'].isin(color_categories)].copy()
    name_check = data['NAME'].astype(str).str.lower().str.contains(pattern, na=False)
    color_check = data['COLOR'].astype(str).str.lower().str.contains(pattern, na=False)
    mask = ~(name_check | color_check)
    return data[mask]

def check_brand_in_name(data):
    mask = data.apply(lambda r: str(r['BRAND']).lower() in str(r['NAME']).lower() if pd.notna(r['BRAND']) and pd.notna(r['NAME']) else False, axis=1)
    return data[mask]

def check_duplicate_products(data):
    cols = ['NAME','BRAND','SELLER_NAME','COLOR']
    return data[data.duplicated(subset=cols, keep=False)]

def check_seller_approved_for_books(data, book_category_codes, approved_book_sellers):
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)]

def check_seller_approved_for_perfume(data, perfume_category_codes, approved_perfume_sellers, sensitive_perfume_brands):
    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    brand_lower = perfume_data['BRAND'].astype(str).str.lower()
    name_lower = perfume_data['NAME'].astype(str).str.lower()
    sensitive_mask = brand_lower.isin(sensitive_perfume_brands) | name_lower.apply(lambda x: any(b in x for b in sensitive_perfume_brands))
    return perfume_data[sensitive_mask & ~perfume_data['SELLER_NAME'].isin(approved_perfume_sellers)]

def check_counterfeit_sneakers(data, sneaker_category_codes, sneaker_sensitive_brands):
    sneakers = data[data['CATEGORY_CODE'].isin(sneaker_category_codes)].copy()
    name_lower = sneakers['NAME'].astype(str).str.lower()
    mask = (sneakers['BRAND'].str.lower().isin(['generic', 'fashion'])) & (name_lower.apply(lambda x: any(b in x for b in sneaker_sensitive_brands)))
    return sneakers[mask]

def check_suspected_fake_products(data, suspected_fake_df, fx_rate=132.0):
    # Simplified placeholder version based on the original logic
    return pd.DataFrame(columns=data.columns)

def check_single_word_name(data, book_category_codes):
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1]

def check_generic_brand_issues(data, valid_category_codes_fas):
    return data[data['CATEGORY_CODE'].isin(valid_category_codes_fas) & (data['BRAND']=='Generic')]

def check_counterfeit_jerseys(data, jerseys_df):
    # Placeholder version based on original logic
    return pd.DataFrame(columns=data.columns)

def check_prohibited_products(data, pattern):
    mask = data['NAME'].astype(str).str.lower().str.contains(pattern, na=False)
    return data[mask]

# -------------------------------------------------
# Master validation runner
# -------------------------------------------------
def validate_products(data, support_files, country_validator, data_has_warranty_cols, common_sids=None):
    flags_mapping = support_files['flags_mapping']
    validations = [
        ("Suspected Fake product", check_suspected_fake_products, {'suspected_fake_df': support_files['suspected_fake']}),
        ("Seller Not approved to sell Refurb", check_refurb_seller_approval, {'approved_sellers_ke': support_files['approved_refurb_sellers_ke'], 'approved_sellers_ug': support_files['approved_refurb_sellers_ug'], 'country_code': country_validator.code}),
        ("Product Warranty", check_product_warranty, {'warranty_category_codes': support_files['warranty_category_codes']}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': support_files['book_category_codes'], 'approved_book_sellers': support_files['approved_book_sellers']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'perfume_category_codes': support_files['perfume_category_codes'], 'approved_perfume_sellers': support_files['approved_perfume_sellers'], 'sensitive_perfume_brands': support_files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'sneaker_category_codes': support_files['sneaker_category_codes'], 'sneaker_sensitive_brands': support_files['sneaker_sensitive_brands']}),
        ("Suspected counterfeit Jerseys", check_counterfeit_jerseys, {'jerseys_df': support_files['jerseys_config']}),
        ("Prohibited products", check_prohibited_products, {'pattern': compile_regex_patterns(country_validator.load_prohibited_products())}),
        ("Unnecessary words in NAME", check_unnecessary_words, {'pattern': compile_regex_patterns(support_files['unnecessary_words'])}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': support_files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {'valid_category_codes_fas': support_files['category_fas']['ID'].astype(str).tolist() if 'ID' in support_files['category_fas'].columns else []}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': compile_regex_patterns(support_files['colors']), 'color_categories': support_files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
    ]
    
    results = {}
    rows = []
    processed = set()
    
    for name, func, kwargs in validations:
        if country_validator.should_skip_validation(name): continue
        ckwargs = {'data': data, **kwargs}
        res = func(**ckwargs)
        if not res.empty:
            results[name] = res.drop_duplicates(subset=['PRODUCT_SET_SID'])
            reason_info = flags_mapping.get(name, ("Other", "Flagged"))
            for sid in results[name]['PRODUCT_SET_SID'].unique():
                if sid not in processed:
                    r = data[data['PRODUCT_SET_SID'] == sid].iloc[0]
                    rows.append({'ProductSetSid': sid, 'ParentSKU': r.get('PARENTSKU', ''), 'Status': 'Rejected', 'Reason': reason_info[0], 'Comment': reason_info[1], 'FLAG': name, 'SellerName': r.get('SELLER_NAME', '')})
                    processed.add(sid)

    approved = data[~data['PRODUCT_SET_SID'].isin(processed)]
    for _, r in approved.iterrows():
        rows.append({'ProductSetSid': r['PRODUCT_SET_SID'], 'ParentSKU': r.get('PARENTSKU', ''), 'Status': 'Approved', 'Reason': "", 'Comment': "", 'FLAG': "", 'SellerName': r.get('SELLER_NAME', '')})
    
    return pd.DataFrame(rows), results

# -------------------------------------------------
# UI - Daily Validation
# -------------------------------------------------
if 'manual_approvals' not in st.session_state: st.session_state.manual_approvals = set()

with st.spinner("Loading config..."): support_files = load_all_support_files()

tab1, tab2, tab3 = st.tabs(["Daily Validation", "Weekly Analysis", "Data Lake"])

with tab1:
    country = st.selectbox("Select Country", ["Kenya", "Uganda"])
    cv = CountryValidator(country)
    uploaded_files = st.file_uploader("Upload Files", type=['csv', 'xlsx'], accept_multiple_files=True)

    if uploaded_files:
        all_dfs = []
        for f in uploaded_files:
            try:
                if f.name.endswith('.xlsx'): df = pd.read_excel(f, dtype=str)
                else:
                    f.seek(0)
                    df = pd.read_csv(f, sep=None, engine='python', encoding='ISO-8859-1', dtype=str)
                all_dfs.append(standardize_input_data(df))
            except Exception as e: st.error(f"Error reading {f.name}: {e}")
        
        if all_dfs:
            merged_data = pd.concat(all_dfs, ignore_index=True)
            
            # --- CRITICAL FIX FOR KEYERROR ---
            if 'PRODUCT_SET_SID' not in merged_data.columns:
                st.error("Column 'PRODUCT_SET_SID' missing.")
                st.info(f"Detected: {list(merged_data.columns)}")
                st.stop()
            
            data_prop = propagate_metadata(merged_data)
            data = data_prop.drop_duplicates(subset=['PRODUCT_SET_SID'])
            
            report, flag_dfs = validate_products(data, support_files, cv, True)
            
            # Apply Session Overrides
            report.loc[report['ProductSetSid'].isin(st.session_state.manual_approvals), 'Status'] = 'Approved'
            
            # Search UI
            search = st.text_input("🔍 Global Search", "").lower()

            for title, df_flagged in flag_dfs.items():
                df_rem = df_flagged[~df_flagged['PRODUCT_SET_SID'].isin(st.session_state.manual_approvals)]
                if search:
                    mask = df_rem.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)
                    df_disp = df_rem[mask].copy()
                else: df_disp = df_rem.copy()

                with st.expander(f"{title} ({len(df_disp)})"):
                    if not df_disp.empty:
                        df_disp.insert(0, "QC Pass", False)
                        cols = ["QC Pass"] + [c for c in VISIBLE_COLUMNS if c in df_disp.columns]
                        ed = st.data_editor(df_disp[cols], column_config={"QC Pass": st.column_config.CheckboxColumn("Approve?"), "MAIN_IMAGE": st.column_config.ImageColumn("Preview")}, disabled=[c for c in cols if c != "QC Pass"], hide_index=True, key=f"ed_{title}")
                        
                        passed = ed[ed["QC Pass"] == True]["PRODUCT_SET_SID"].tolist()
                        if passed and st.button(f"Confirm Bulk Approval for {title}"):
                            st.session_state.manual_approvals.update(passed)
                            st.rerun()
                    else: st.success("Clear!")
            
            st.divider()
            c1, c2 = st.columns(2)
            c1.download_button("Download Final Report", report.to_csv(index=False), "Report.csv")
            if st.sidebar.button("Reset Overrides"): 
                st.session_state.manual_approvals.clear()
                st.rerun()
