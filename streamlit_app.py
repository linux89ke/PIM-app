import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
from collections import defaultdict
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
FX_RATE = 132.0 

# Define numerical priority for all flags (Lower number = Higher Priority)
FLAG_PRIORITIES = {
    'Suspected Fake product': 1,
    'Seller Not approved to sell Refurb': 2,
    'Product Warranty': 3,
    'Sensitive words': 4,
    'Seller Approve to sell books': 5,
    'Seller Approved to Sell Perfume': 6,
    'Counterfeit Sneakers': 7,
    'Suspected counterfeit Jerseys': 8,
    'Prohibited products': 9,
    'Unnecessary words in NAME': 10,
    'Single-word NAME': 11,
    'Generic BRAND Issues': 12,
    'BRAND name repeated in NAME': 13,
    'Missing COLOR': 14,
    'Duplicate product': 15, # LOWEST PRIORITY - Handled via Propagation Logic
}


# MAPPING: New File Columns -> Script Internal Columns
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
    """Loads a list of strings from a file, handling UTF-8 encoding."""
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
            'Seller Not approved to sell Refurb': ('1000001 - Seller Not Approved to Sell Refurb Product', "Your listing was rejected because it mentions \'Refurb\', \'Refurbished\', \'Renewed\' or the brand is \'Renewed\', but your seller account is not on the approved list for refurbished products in this country."),
            'BRAND name repeated in NAME': ('1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name', "Please do not write the brand name in the Product Name field..."),
            'Missing COLOR': ('1000005 - Kindly confirm the actual product colour', "Please make sure that the product color is clearly mentioned..."),
            'Duplicate product': ('1000007 - Other Reason', "kindly note product was rejected because its a duplicate product"),
            'Prohibited products': ('1000007 - Other Reason', "Kindly note this product is not allowed for listing on Jumia..."),
            'Single-word NAME': ('1000008 - Kindly Improve Product Name Description', "Kindly update the product title using this format..."),
            'Unnecessary words in NAME': ('1000010 - Kindly remove unnecessary words from product name', "Your listing was rejected because the product name contains unnecessary promotional or keyword stuffing words. Please remove them to comply with platform guidelines."),
            'Generic BRAND Issues': ('1000014 - Kindly request for the creation of this product\'s actual brand name...', "To create the actual brand name for this product..."),
            'Counterfeit Sneakers': ('1000023 - Confirmation of counterfeit product by Jumia technical team...', "Your listing has been rejected as Jumia\'s technical team has confirmed..."),
            'Seller Approve to sell books': ('1000028 - Kindly Contact Jumia Seller Support...', "Please contact Jumia Seller Support and raise a claim..."),
            'Seller Approved to Sell Perfume': ('1000028 - Kindly Contact Jumia Seller Support...', "Please contact Jumia Seller Support and raise a claim..."),
            'Suspected counterfeit Jerseys': ('1000030 - Suspected Counterfeit Product', "Your listing has been rejected as it is suspected to be a counterfeit jersey..."),
            'Suspected Fake product': ('1000031 - Suspected Fake Product', "Your listing has been rejected as the pricing suggests this may be a counterfeit or fake product. Products from reputable brands like Sony, JBL, Adidas, Nike, Apple, Samsung, and others must meet minimum price thresholds to ensure authenticity. Please verify the product\'s authenticity and adjust the pricing accordingly, or contact Jumia Seller Support if you believe this is an error."),
            'Product Warranty': ('1000013 - Kindly Provide Product Warranty Details', "For listing this type of product requires a valid warranty as per our platform guidelines.\nTo proceed, please ensure the warranty details are clearly mentioned in:\n\nProduct Description tab\n\nWarranty Tab.\n\nThis helps build customer trust and ensures your listing complies with Jumia\'s requirements."),
            'Sensitive words': ('1000001 - Brand NOT Allowed', "Your listing was rejected because it includes brands that are not allowed on Jumia..."), # Keeping old flag name in map just in case of dependency elsewhere
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
        'unnecessary_words': [w.lower() for w in load_txt_file('unnecessary.txt')], # NEW FILE LOAD
        'colors': [c.lower() for c in load_txt_file('colors.txt')],
        'color_categories': load_txt_file('color_cats.txt'),
        'check_variation': load_excel_file('check_variation.xlsx'),
        'category_fas': load_excel_file('category_FAS.xlsx'),
        'reasons': load_excel_file('reasons.xlsx'),
        'flags_mapping': load_flags_mapping(),
        'jerseys_config': load_excel_file('Jerseys.xlsx'),
        'warranty_category_codes': load_txt_file('warranty.txt'),
        # Assuming the CSV version of the suspected_fake file is accessible as its original name:
        'suspected_fake': pd.read_csv("suspected_fake.xlsx", header=None, dtype=str),
        
        # Dynamic loading for Refurb lists 
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
    def should_skip_validation(self, validation_name: str) -> bool:
        return validation_name in self.config["skip_validations"]
    def ensure_status_column(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty: return df
        if 'Status' not in df.columns: df['Status'] = 'Approved'
        return df
    @st.cache_data(ttl=3600)
    def load_prohibited_products(_self) -> List[str]:
        filename = _self.config["prohibited_products_file"]
        return [w.lower() for w in load_txt_file(filename)]

# -------------------------------------------------
# Data Loading & Validation Functions
# -------------------------------------------------
def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.rename(columns=NEW_FILE_MAPPING)
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

def filter_by_country(df: pd.DataFrame, country_validator: CountryValidator, source: str) -> pd.DataFrame:
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns: return df
    df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.strip().str.upper()
    mask = df['ACTIVE_STATUS_COUNTRY'] == country_validator.code
    filtered = df[mask].copy()
    if filtered.empty:
        st.error(f"No {country_validator.code} rows left in {source}")
        st.stop()
    return filtered

def propagate_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """
    Propagates metadata (COLOR_FAMILY, WARRANTY) across duplicate SIDs before filtering.
    """
    if df.empty: return df
    cols_to_propagate = ['COLOR_FAMILY', 'PRODUCT_WARRANTY', 'WARRANTY_DURATION', 'WARRANTY_ADDRESS', 'WARRANTY_TYPE']
    
    for col in cols_to_propagate:
        if col not in df.columns: df[col] = pd.NA
        
    # Forward fill and Backward fill to spread data between rows of same SID
    for col in cols_to_propagate:
        df[col] = df.groupby('PRODUCT_SET_SID')[col].transform(lambda x: x.ffill().bfill())
        
    return df

# --- Validation Logic Functions ---

def check_refurb_seller_approval(data: pd.DataFrame, approved_sellers_ke: List[str], approved_sellers_ug: List[str], country_code: str) -> pd.DataFrame:
    if country_code == 'KE': approved_sellers = set(approved_sellers_ke)
    elif country_code == 'UG': approved_sellers = set(approved_sellers_ug)
    else: return pd.DataFrame(columns=data.columns)

    if not {'NAME', 'BRAND', 'SELLER_NAME', 'PRODUCT_SET_SID'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    
    data = data.copy()
    refurb_words = r'\b(refurb|refurbished|renewed)\b'
    refurb_brand = 'renewed'
    
    data['NAME_LOWER'] = data['NAME'].astype(str).str.strip().str.lower()
    data['BRAND_LOWER'] = data['BRAND'].astype(str).str.strip().str.lower()
    data['SELLER_LOWER'] = data['SELLER_NAME'].astype(str).str.strip().str.lower()

    name_match = data['NAME_LOWER'].str.contains(refurb_words, regex=True, na=False)
    brand_match = data['BRAND_LOWER'] == refurb_brand
    
    trigger_mask = name_match | brand_match
    triggered_data = data[trigger_mask].copy()
    if triggered_data.empty: return pd.DataFrame(columns=data.columns)
        
    seller_not_approved_mask = ~triggered_data['SELLER_LOWER'].isin(approved_sellers)
    flagged = triggered_data[seller_not_approved_mask]
    
    return flagged[['PRODUCT_SET_SID']].drop_duplicates()


def check_unnecessary_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME', 'PRODUCT_SET_SID'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    return data[mask][['PRODUCT_SET_SID']].drop_duplicates()


def check_product_warranty(data: pd.DataFrame, warranty_category_codes: List[str]) -> pd.DataFrame:
    for col in ['PRODUCT_WARRANTY', 'WARRANTY_DURATION']:
        if col not in data.columns: data[col] = ""
        data[col] = data[col].astype(str).fillna('').str.strip()
    if not warranty_category_codes: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    
    data['CAT_CLEAN'] = data['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
    target_cats = [str(c).strip() for c in warranty_category_codes]
    target_data = data[data['CAT_CLEAN'].isin(target_cats)].copy()
    if target_data.empty: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    
    def is_present(series):
        s = series.astype(str).str.strip().str.lower()
        return (s != 'nan') & (s != '') & (s != 'none') & (s != 'nat') & (s != 'n/a')
    
    has_any_warranty = is_present(target_data['PRODUCT_WARRANTY']) | is_present(target_data['WARRANTY_DURATION'])
    mask = ~has_any_warranty
    flagged = target_data[mask]
    
    return flagged[['PRODUCT_SET_SID']].drop_duplicates()

def check_missing_color(data: pd.DataFrame, pattern: re.Pattern, color_categories: List[str], country_code: str = 'KE') -> pd.DataFrame:
    req = ['NAME', 'COLOR', 'CATEGORY_CODE', 'PRODUCT_SET_SID']
    if not set(req).issubset(data.columns): return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    data = data[data['CATEGORY_CODE'].isin(color_categories)].copy()
    if data.empty: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    
    name_check = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    color_check = data['COLOR'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    family_check = pd.Series([False] * len(data), index=data.index)
    
    if country_code == 'KE' and 'COLOR_FAMILY' in data.columns:
        family_check = data['COLOR_FAMILY'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    
    if country_code == 'KE':
        mask = ~(name_check | color_check | family_check)
    else:
        mask = ~(name_check | color_check)
    return data[mask][['PRODUCT_SET_SID']].drop_duplicates()

def check_sensitive_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME', 'PRODUCT_SET_SID'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    return data[mask][['PRODUCT_SET_SID']].drop_duplicates()

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME', 'PRODUCT_SET_SID'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    return data[mask][['PRODUCT_SET_SID']].drop_duplicates()

def check_brand_in_name(data: pd.DataFrame) -> pd.DataFrame:
    if not {'BRAND','NAME', 'PRODUCT_SET_SID'}.issubset(data.columns): return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    mask = data.apply(lambda r: str(r['BRAND']).strip().lower() in str(r['NAME']).strip().lower()  
                     if pd.notna(r['BRAND']) and pd.notna(r['NAME']) else False, axis=1)
    return data[mask][['PRODUCT_SET_SID']].drop_duplicates()

def check_duplicate_products(data: pd.DataFrame) -> pd.DataFrame:
    """
    Identifies all SIDs that belong to a duplicate group (keep=False marks all copies).
    Returns PRODUCT_SET_SID and the unique DUPLICATE_KEY.
    """
    cols_for_duplication = [c for c in ['NAME', 'BRAND', 'SELLER_NAME'] if c in data.columns]
    
    if len(cols_for_duplication) < 3:
        return pd.DataFrame(columns=['PRODUCT_SET_SID', 'DUPLICATE_KEY'])

    data = data.copy()
    data['DUPLICATE_KEY'] = data[cols_for_duplication].astype(str).agg('::'.join, axis=1)
    
    is_duplicate = data.duplicated(subset=cols_for_duplication, keep=False)
    duplicate_rows = data[is_duplicate].copy()
    
    return duplicate_rows[['PRODUCT_SET_SID', 'DUPLICATE_KEY']].drop_duplicates()


def check_seller_approved_for_books(data: pd.DataFrame, book_category_codes: List[str], approved_book_sellers: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME', 'PRODUCT_SET_SID'}.issubset(data.columns): return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if books.empty: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)][['PRODUCT_SET_SID']].drop_duplicates()

def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_category_codes: List[str], approved_perfume_sellers: List[str], sensitive_perfume_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME','BRAND','NAME', 'PRODUCT_SET_SID'}.issubset(data.columns): return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perfume_data.empty: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    brand_lower = perfume_data['BRAND'].astype(str).str.strip().str.lower()
    name_lower = perfume_data['NAME'].astype(str).str.strip().str.lower()
    sensitive_mask = brand_lower.isin(sensitive_perfume_brands)
    fake_brands = ['designers collection', 'smart collection', 'generic', 'original', 'fashion']
    fake_brand_mask = brand_lower.isin(fake_brands)
    name_contains_sensitive = name_lower.apply(lambda x: any(brand in x for brand in sensitive_perfume_brands))
    final_mask = (sensitive_mask | (fake_brand_mask & name_contains_sensitive)) & (~perfume_data['SELLER_NAME'].isin(approved_perfume_sellers))
    return perfume_data[final_mask][['PRODUCT_SET_SID']].drop_duplicates()

def check_counterfeit_sneakers(data: pd.DataFrame, sneaker_category_codes: List[str], sneaker_sensitive_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'NAME', 'BRAND', 'PRODUCT_SET_SID'}.issubset(data.columns): return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    sneaker_data = data[data['CATEGORY_CODE'].isin(sneaker_category_codes)].copy()
    if sneaker_data.empty: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    brand_lower = sneaker_data['BRAND'].astype(str).str.strip().str.lower()
    name_lower = sneaker_data['NAME'].astype(str).str.strip().str.lower()
    fake_brand_mask = brand_lower.isin(['generic', 'fashion'])
    name_contains_brand = name_lower.apply(lambda x: any(brand in x for brand in sneaker_sensitive_brands))
    return sneaker_data[fake_brand_mask & name_contains_brand][['PRODUCT_SET_SID']].drop_duplicates()

def check_suspected_fake_products(data: pd.DataFrame, suspected_fake_df: pd.DataFrame, fx_rate: float = 132.0) -> pd.DataFrame:
    required_cols = ['CATEGORY_CODE', 'BRAND', 'GLOBAL_SALE_PRICE', 'GLOBAL_PRICE', 'PRODUCT_SET_SID']
    
    if not all(c in data.columns for c in required_cols) or suspected_fake_df.empty: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    
    try:
        # 1. Parse the reference file structure
        ref_data = suspected_fake_df.copy()
        
        # Assume the first row contains headers/brands
        if ref_data.iloc[0].str.contains('Price').any():
            ref_data.columns = ref_data.iloc[0]
            ref_data = ref_data[1:].reset_index(drop=True)
        
        brand_cols = [col for col in ref_data.columns if pd.notna(col) and col not in ['Brand', 'Price', 'Unnamed: 0']]
        brand_category_price = {}
        
        for brand in brand_cols:
            try:
                price_threshold = pd.to_numeric(ref_data[brand].iloc[0], errors='coerce')
                if pd.isna(price_threshold) or price_threshold <= 0: continue
            except: continue
            
            categories = ref_data[brand].iloc[1:].dropna()
            brand_lower = brand.strip().lower()
            
            for cat in categories:
                cat_base = str(cat).split('.')[0].strip()
                if cat_base and cat_base.lower() != 'nan':
                    key = (brand_lower, cat_base)
                    brand_category_price[key] = price_threshold
        
        if not brand_category_price: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
        
        # 2. Prepare Check Data and Prices
        check_data = data.copy()
        check_data['price_to_use'] = pd.to_numeric(check_data['GLOBAL_SALE_PRICE'], errors='coerce').where(
            (pd.to_numeric(check_data['GLOBAL_SALE_PRICE'], errors='coerce').notna()) & 
            (pd.to_numeric(check_data['GLOBAL_SALE_PRICE'], errors='coerce') > 0),
            pd.to_numeric(check_data['GLOBAL_PRICE'], errors='coerce')
        ).fillna(0)
        
        check_data['price_usd'] = check_data['price_to_use']
        check_data['BRAND_LOWER'] = check_data['BRAND'].astype(str).str.strip().str.lower()
        check_data['CAT_BASE'] = check_data['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
        
        # 3. Check Logic
        def is_suspected_fake(row):
            key = (row['BRAND_LOWER'], row['CAT_BASE'])
            if key in brand_category_price:
                threshold = brand_category_price[key]
                if row['price_usd'] < threshold: return True
            return False
        
        check_data['is_fake'] = check_data.apply(is_suspected_fake, axis=1)
        flagged = check_data[check_data['is_fake'] == True].copy()
        
        return flagged[['PRODUCT_SET_SID']].drop_duplicates()
        
    except Exception as e:
        logger.error(f"Error in suspected fake product check: {e}")
        return pd.DataFrame(columns=['PRODUCT_SET_SID'])


def check_single_word_name(data: pd.DataFrame, book_category_codes: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','NAME', 'PRODUCT_SET_SID'}.issubset(data.columns): return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1][['PRODUCT_SET_SID']].drop_duplicates()

def check_generic_brand_issues(data: pd.DataFrame, valid_category_codes_fas: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','BRAND', 'PRODUCT_SET_SID'}.issubset(data.columns): return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    return data[data['CATEGORY_CODE'].isin(valid_category_codes_fas) & (data['BRAND']=='Generic')][['PRODUCT_SET_SID']].drop_duplicates()

def check_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'NAME', 'SELLER_NAME', 'PRODUCT_SET_SID'}.issubset(data.columns) or jerseys_df.empty: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    jersey_cats = jerseys_df['Categories'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().unique().tolist()
    jersey_cats = [c for c in jersey_cats if c.lower() != 'nan']
    keywords = [w for w in jerseys_df['Checklist'].astype(str).str.strip().str.lower().unique().tolist() if w and w!='nan']
    exempt = [s for s in jerseys_df['Exempted'].astype(str).str.strip().unique().tolist() if s and s.lower()!='nan']
    if not jersey_cats or not keywords: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    regex = compile_regex_patterns(keywords)
    data['CAT_STR'] = data['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
    jerseys = data[data['CAT_STR'].isin(jersey_cats)].copy()
    if jerseys.empty: return pd.DataFrame(columns=['PRODUCT_SET_SID'])
    target = jerseys[~jerseys['SELLER_NAME'].isin(exempt)].copy()
    mask = target['NAME'].astype(str).str.strip().str.lower().str.contains(regex, na=False)
    return target[mask][['PRODUCT_SET_SID']].drop_duplicates()


# -------------------------------------------------
# The ENHANCED Master validation runner
# -------------------------------------------------
def validate_products(data: pd.DataFrame, support_files: Dict, country_validator: CountryValidator, data_has_warranty_cols: bool, common_sids: Optional[set] = None):
    
    flags_mapping = support_files['flags_mapping']
    
    # Define the checks and their priority rank (P1=Highest, P14=Lowest Non-Duplicate)
    # The order MUST align with the FLAG_PRIORITIES map
    NON_DUPLICATE_CHECKS = [
        ("Suspected Fake product", check_suspected_fake_products, {'suspected_fake_df': support_files['suspected_fake'], 'fx_rate': FX_RATE}), # P1
        ("Seller Not approved to sell Refurb", check_refurb_seller_approval, {
            'approved_sellers_ke': support_files['approved_refurb_sellers_ke'],
            'approved_sellers_ug': support_files['approved_refurb_sellers_ug'],
            'country_code': country_validator.code
        }), # P2
        ("Product Warranty", check_product_warranty, {'warranty_category_codes': support_files['warranty_category_codes']}), # P3
        ("Sensitive words", check_sensitive_words, {'pattern': compile_regex_patterns(support_files['sensitive_words'])}), # P4
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': support_files['book_category_codes'], 'approved_book_sellers': support_files['approved_book_sellers']}), # P5
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'perfume_category_codes': support_files['perfume_category_codes'], 'approved_perfume_sellers': support_files['approved_perfume_sellers'], 'sensitive_perfume_brands': support_files['sensitive_perfume_brands']}), # P6
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'sneaker_category_codes': support_files['sneaker_category_codes'], 'sneaker_sensitive_brands': support_files['sneaker_sensitive_brands']}), # P7
        ("Suspected counterfeit Jerseys", check_counterfeit_jerseys, {'jerseys_df': support_files['jerseys_config']}), # P8
        ("Prohibited products", check_prohibited_products, {'pattern': compile_regex_patterns(country_validator.load_prohibited_products())}), # P9
        ("Unnecessary words in NAME", check_unnecessary_words, {'pattern': compile_regex_patterns(support_files['unnecessary_words'])}), # P10
        ("Single-word NAME", check_single_word_name, {'book_category_codes': support_files['book_category_codes']}), # P11
        ("Generic BRAND Issues", check_generic_brand_issues, {}), # P12
        ("BRAND name repeated in NAME", check_brand_in_name, {}), # P13
        ("Missing COLOR", check_missing_color, {'pattern': compile_regex_patterns(support_files['colors']), 'color_categories': support_files['color_categories']}), # P14 (P15 in old list)
    ]
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 1. PHASE 1: Run all non-duplicate checks and record highest priority flag per SID
    all_flagged_sids = pd.DataFrame(columns=['PRODUCT_SET_SID', 'FLAG', 'PRIORITY'])
    flag_results_tracker = {} 

    data_for_checks = data.copy()
    
    # --- 1a: Pre-calculate Duplicate Groups for Propagation ---
    duplicate_groups = {}
    cols_for_dup_key = [c for c in ['NAME','BRAND','SELLER_NAME'] if c in data.columns]
    
    if len(cols_for_dup_key) >= 3:
        data_temp = data.copy()
        # Create a consistent key for grouping
        data_temp['dup_key'] = data_temp[cols_for_dup_key].astype(str).agg('::'.join, axis=1)
        
        # Find all duplicate SIDs based on the key
        dup_counts = data_temp.groupby('dup_key')['PRODUCT_SET_SID'].apply(list).to_dict()
        
        # Map each SID to its full list of duplicates (including itself)
        for sid_list in dup_counts.values():
             if len(sid_list) > 1:
                for sid in sid_list:
                    duplicate_groups[sid] = sid_list

    # --- 1b: Run all Non-Duplicate Checks ---
    for rank, (name, func, kwargs) in enumerate(NON_DUPLICATE_CHECKS):
        # Apply country skip logic
        if country_validator.should_skip_validation(name): continue
        
        ckwargs = {'data': data_for_checks, **kwargs}

        # Handle specific logic for Generic Brand Issues and Missing Color (uses extra kwargs)
        if name == "Generic BRAND Issues":
            fas = support_files.get('category_fas', pd.DataFrame())
            ckwargs['valid_category_codes_fas'] = fas['ID'].astype(str).tolist() if not fas.empty and 'ID' in fas.columns else []
        elif name == "Missing COLOR":
            ckwargs['country_code'] = country_validator.code
        
        # Handle custom logic for Product Warranty
        if name == "Product Warranty":
            if not data_has_warranty_cols:
                continue

        status_text.text(f"Running: {name}")
        
        try:
            # Result contains only [PRODUCT_SET_SID] column(s)
            flagged_res = func(**ckwargs)
            flag_results_tracker[name] = flagged_res.copy() # Store full result (SIDs only)
            
            if not flagged_res.empty:
                new_flags = flagged_res[['PRODUCT_SET_SID']].drop_duplicates().copy()
                new_flags['FLAG'] = name
                new_flags['PRIORITY'] = FLAG_PRIORITIES.get(name, 99)
                
                # Merge new flags, keeping the lowest priority number (highest severity)
                all_flagged_sids = pd.concat([all_flagged_sids, new_flags], ignore_index=True)
                all_flagged_sids = all_flagged_sids.sort_values('PRIORITY').drop_duplicates(subset=['PRODUCT_SET_SID'], keep='first')
                
        except Exception as e:
            logger.error(f"Error in {name}: {e}")
            flag_results_tracker[name] = pd.DataFrame(columns=['PRODUCT_SET_SID'])
            
        progress_bar.progress((rank + 1) / len(NON_DUPLICATE_CHECKS))

    # 2. PHASE 2: Final Rejection Assignment with Propagation (P15)
    
    # a. Identify all unique duplicate keys
    duplicates_df = check_duplicate_products(data)
    
    final_rejections = pd.DataFrame(columns=['ProductSetSid', 'Reason', 'Comment', 'FLAG'])
    processed_sids = set() # Tracks SIDs that have received a final rejection reason
    
    # b. Process Duplicate Sets (Propagation Logic)
    if not duplicates_df.empty:
        # Group duplicates by their key
        for key, group in duplicates_df.groupby('DUPLICATE_KEY'):
            group_sids = set(group['PRODUCT_SET_SID'].unique())
            
            # Find the highest-priority flag among the members of this duplicate group
            high_priority_matches = all_flagged_sids[all_flagged_sids['PRODUCT_SET_SID'].isin(group_sids)].sort_values('PRIORITY')
            
            if not high_priority_matches.empty:
                # Assign the highest priority flag (P1-P14) found in the set to ALL members
                highest_flag_name = high_priority_matches.iloc[0]['FLAG']
                
                reason_info = flags_mapping.get(highest_flag_name, ("1000007 - Other Reason", f"Flagged by {highest_flag_name}"))
                
                for sid in group_sids:
                    if sid not in processed_sids: 
                         final_rejections.loc[len(final_rejections)] = {
                            'ProductSetSid': sid,
                            'Reason': reason_info[0],
                            'Comment': reason_info[1],
                            'FLAG': highest_flag_name,
                        }
                         processed_sids.add(sid)
            else:
                # Assign the lowest priority flag: Duplicate product (P15)
                duplicate_flag_name = 'Duplicate product'
                reason_info = flags_mapping.get(duplicate_flag_name, ("1000007 - Other Reason", f"Flagged by {duplicate_flag_name}"))
                
                # Assign to all SIDs in the group
                for sid in group_sids:
                     if sid not in processed_sids:
                        final_rejections.loc[len(final_rejections)] = {
                            'ProductSetSid': sid,
                            'Reason': reason_info[0],
                            'Comment': reason_info[1],
                            'FLAG': duplicate_flag_name,
                        }
                        processed_sids.add(sid)

    # c. Process SIDs with a P1-P14 Flag that are NOT Duplicates
    # This step handles single listings that had an issue (P1-P14) but had no duplicates.
    non_duplicate_flagged = all_flagged_sids[~all_flagged_sids['PRODUCT_SET_SID'].isin(processed_sids)].copy()
    
    for _, r in non_duplicate_flagged.iterrows():
        sid = r['PRODUCT_SET_SID']
        name = r['FLAG']
        reason_info = flags_mapping.get(name, ("1000007 - Other Reason", f"Flagged by {name}"))
        
        final_rejections.loc[len(final_rejections)] = {
            'ProductSetSid': sid,
            'Reason': reason_info[0],
            'Comment': reason_info[1],
            'FLAG': name,
        }
        processed_sids.add(sid)


    # 3. Finalization: Merge results back to data to get full metadata and 'Approved' status
    
    # We must use unique SIDs from the original data as the final report index
    report_df = data[['PRODUCT_SET_SID', 'PARENTSKU', 'SELLER_NAME']].drop_duplicates(subset=['PRODUCT_SET_SID']).copy()
    report_df = report_df.rename(columns={'PRODUCT_SET_SID': 'ProductSetSid', 'PARENTSKU': 'ParentSKU', 'SELLER_NAME': 'SellerName'})

    # Merge final rejections
    report_df = pd.merge(report_df, final_rejections, on='ProductSetSid', how='left')
    
    # Fill NaN values (products that were not flagged) as Approved
    report_df['Status'] = report_df['FLAG'].apply(lambda x: 'Rejected' if pd.notna(x) else 'Approved')
    report_df['Reason'] = report_df['Reason'].fillna("")
    report_df['Comment'] = report_df['Comment'].fillna("")
    report_df['FLAG'] = report_df['FLAG'].fillna("")

    # Ensure required columns exist
    final_cols = [c for c in PRODUCTSETS_COLS if c in report_df.columns]
    
    # Return the final report structure and the raw flag tracker results (for expander views)
    return report_df[final_cols], flag_results_tracker

# -------------------------------------------------
# Export Logic
# -------------------------------------------------
def to_excel_base(df, sheet, cols, writer):
    df_p = df.copy()
    for c in cols:  
        if c not in df_p.columns: df_p[c] = pd.NA
    df_p[[c for c in cols if c in df_p.columns]].to_excel(writer, index=False, sheet_name=sheet)

def to_excel_full_data(data_df, final_report_df):
    try:
        output = BytesIO()
        d_cp = data_df.copy()
        r_cp = final_report_df.copy()
        
        d_cp['PRODUCT_SET_SID'] = d_cp['PRODUCT_SET_SID'].astype(str).str.strip()
        r_cp['ProductSetSid'] = r_cp['ProductSetSid'].astype(str).str.strip()
        
        # Merge by the unique SIDs in the final report
        merged = pd.merge(d_cp.drop_duplicates(subset=['PRODUCT_SET_SID']), 
                          r_cp[["ProductSetSid", "Status", "Reason", "Comment", "FLAG", "SellerName"]],
                          left_on="PRODUCT_SET_SID", right_on="ProductSetSid", how='left', suffixes=('_data', '_report'))
        
        # Harmonize column names and drop redundancy
        merged['SELLER_NAME'] = merged['SellerName_report'].fillna(merged['SellerName_data'])
        merged.drop(columns=['ProductSetSid_report', 'SellerName_report', 'SellerName_data'], inplace=True, errors='ignore')
        merged.rename(columns={'ProductSetSid_data': 'PRODUCT_SET_SID'}, inplace=True)
        
        export_cols = FULL_DATA_COLS + [c for c in ["Status", "Reason", "Comment", "FLAG"] if c not in FULL_DATA_COLS]
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            to_excel_base(merged, "ProductSets", export_cols, writer)
            
            wb = writer.book
            ws = wb.add_worksheet('Sellers Data')
            fmt = wb.add_format({'bold': True, 'bg_color': '#E6F0FA', 'border': 1, 'align': 'center'})
            
            if 'SELLER_RATING' in merged.columns:
                merged['Rejected_Count'] = (merged['Status'] == 'Rejected').astype(int)
                merged['Approved_Count'] = (merged['Status'] == 'Approved').astype(int)
                summ = merged.groupby('SELLER_NAME').agg(
                    Rejected=('Rejected_Count', 'sum'), Approved=('Approved_Count', 'sum'),
                    AvgRating=('SELLER_RATING', lambda x: pd.to_numeric(x, errors='coerce').mean()),  
                    TotalStock=('STOCK_QTY', lambda x: pd.to_numeric(x, errors='coerce').sum())
                ).reset_index().sort_values('Rejected', ascending=False)
                summ.insert(0, 'Rank', range(1, len(summ) + 1))
                ws.write(0, 0, "Sellers Summary", fmt)
                summ.to_excel(writer, sheet_name='Sellers Data', startrow=1, index=False)
                row_cursor = len(summ) + 4
            else:
                row_cursor = 1

            if 'CATEGORY' in merged.columns:
                cat_summ = merged[merged['Status']=='Rejected'].groupby('CATEGORY').size().reset_index(name='Rejected Products').sort_values('Rejected Products', ascending=False)
                cat_summ.insert(0, 'Rank', range(1, len(cat_summ) + 1))
                ws.write(row_cursor, 0, "Categories Summary", fmt)
                cat_summ.to_excel(writer, sheet_name='Sellers Data', startrow=row_cursor+1, index=False)
                row_cursor += len(cat_summ) + 4
            
            if 'Reason' in merged.columns:
                rsn_summ = merged[merged['Status']=='Rejected'].groupby('Reason').size().reset_index(name='Rejected Products').sort_values('Rejected Products', ascending=False)
                rsn_summ.insert(0, 'Rank', range(1, len(rsn_summ) + 1))
                ws.write(row_cursor, 0, "Rejection Reasons Summary", fmt)
                rsn_summ.to_excel(writer, sheet_name='Sellers Data', startrow=row_cursor+1, index=False)
        
        output.seek(0)
        return output
    except Exception: return BytesIO()

def to_excel(report_df, reasons_config_df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(report_df, "ProductSets", PRODUCTSETS_COLS, writer)
        if not reasons_config_df.empty:
            to_excel_base(reasons_config_df, "RejectionReasons", REJECTION_REASONS_COLS, writer)
    output.seek(0)
    return output

def to_excel_flag_data(flag_df, flag_name):
    output = BytesIO()
    df_copy = flag_df.copy()
    df_copy['FLAG'] = flag_name
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(df_copy, "ProductSets", FULL_DATA_COLS, writer)
    output.seek(0)
    return output

def log_validation_run(country, file, total, app, rej):
    try:
        entry = {'timestamp': datetime.now().isoformat(), 'country': country, 'file': file, 'total': total, 'approved': app, 'rejected': rej}
        with open('validation_audit.jsonl', 'a') as f: f.write(json.dumps(entry)+'\n')
    except: pass

# -------------------------------------------------
# UI
# -------------------------------------------------
st.title("Product Validation Tool")
st.markdown("---")

with st.spinner("Loading configuration files..."):
    support_files = load_all_support_files()

if not support_files['flags_mapping']:
    st.error("Critical: flags.xlsx could not be loaded.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Daily Validation", "Weekly Analysis", "Data Lake"])

# -------------------------------------------------
# TAB 1: DAILY VALIDATION
# -------------------------------------------------
with tab1:
    st.header("Daily Product Validation")
    country = st.selectbox("Select Country", ["Kenya", "Uganda"], key="daily_country")
    country_validator = CountryValidator(country)
    
    uploaded_files = st.file_uploader("Upload files (CSV/XLSX)", type=['csv', 'xlsx'], accept_multiple_files=True, key="daily_files")
    
    if uploaded_files:
        try:
            current_date = datetime.now().strftime('%Y-%m-%d')
            file_prefix = country_validator.code
            
            all_dfs = []
            file_sids_sets = []
            
            for uploaded_file in uploaded_files:
                try:
                    if uploaded_file.name.endswith('.xlsx'):
                        raw_data = pd.read_excel(uploaded_file, engine='openpyxl', dtype=str)
                    else:
                        try:  
                            raw_data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype=str)
                            if len(raw_data.columns) <= 1:
                                uploaded_file.seek(0)
                                raw_data = pd.read_csv(uploaded_file, sep=',', encoding='ISO-8859-1', dtype=str)
                        except:
                            uploaded_file.seek(0)
                            raw_data = pd.read_csv(uploaded_file, sep=',', encoding='ISO-8859-1', dtype=str)
                    
                    std_data = standardize_input_data(raw_data)
                    
                    if 'PRODUCT_SET_SID' in std_data.columns:
                        file_sids_sets.append(set(std_data['PRODUCT_SET_SID'].unique()))
                    
                    all_dfs.append(std_data)
                    
                except Exception as e:
                    st.error(f"Failed to read file {uploaded_file.name}: {e}")
                    st.stop()
            
            if not all_dfs:
                st.error("No valid data loaded.")
                st.stop()
                
            merged_data = pd.concat(all_dfs, ignore_index=True)
            st.success(f"Loaded total {len(merged_data)} rows from {len(uploaded_files)} files.")
            
            intersection_count = 0
            intersection_sids = set()
            if len(file_sids_sets) > 1:
                intersection_sids = set.intersection(*file_sids_sets)
                intersection_count = len(intersection_sids)
            
            data_prop = propagate_metadata(merged_data)
            
            is_valid, errors = validate_input_schema(data_prop)
            
            if is_valid:
                data_filtered = filter_by_country(data_prop, country_validator, "Uploaded Files")
                
                # Run checks on all rows initially (not just unique SIDs) for accurate duplicate detection
                data = data_filtered 
                
                # Check if the necessary columns are present in the final data
                data_has_warranty_cols = all(col in data.columns for col in ['PRODUCT_WARRANTY', 'WARRANTY_DURATION'])
                
                for col in ['NAME', 'BRAND', 'COLOR', 'SELLER_NAME', 'CATEGORY_CODE']:
                    if col in data.columns: data[col] = data[col].astype(str).fillna('')
                
                if 'COLOR_FAMILY' not in data.columns: data['COLOR_FAMILY'] = ""
                
                with st.spinner("Running validations..."):
                    # Determine common SIDs set to pass (only if multiple files uploaded)
                    common_sids_to_pass = intersection_sids if intersection_count > 0 else None
                    
                    final_report, flag_dfs = validate_products(
                        data,  
                        support_files,  
                        country_validator,  
                        data_has_warranty_cols, # Pass the boolean check for column presence
                        common_sids_to_pass     # Pass the set of common SIDs
                    )
                
                approved_df = final_report[final_report['Status'] == 'Approved']
                rejected_df = final_report[final_report['Status'] == 'Rejected']
                
                # We log the unique SIDs counted as rejected/approved
                unique_rejected_count = final_report[final_report['Status'] == 'Rejected']['ProductSetSid'].nunique()
                unique_approved_count = final_report[final_report['Status'] == 'Approved']['ProductSetSid'].nunique()
                unique_total_count = final_report['ProductSetSid'].nunique()

                log_validation_run(country, "Multi-Upload", unique_total_count, unique_approved_count, unique_rejected_count)
                
                st.sidebar.header("Seller Options")
                seller_opts = ['All Sellers'] + (data['SELLER_NAME'].dropna().unique().tolist() if 'SELLER_NAME' in data.columns else [])
                sel_sellers = st.sidebar.multiselect("Select Sellers", seller_opts, default=['All Sellers'])
                
                filt_data = data.copy()
                filt_report = final_report.copy()
                lbl = "All_Sellers"
                
                if 'All Sellers' not in sel_sellers and sel_sellers:
                    filt_data = data[data['SELLER_NAME'].isin(sel_sellers)]
                    filt_report = final_report[final_report['ProductSetSid'].isin(filt_data['PRODUCT_SET_SID'])]
                    lbl = "Selected_Sellers"
                
                filt_rej = filt_report[filt_report['Status']=='Rejected']
                filt_app = filt_report[filt_report['Status']=='Approved']
                
                st.markdown("---")
                st.header("Overall Results")
                
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Total Unique SKUs", unique_total_count)
                c2.metric("Approved Unique SKUs", unique_approved_count)
                c3.metric("Rejected Unique SKUs", unique_rejected_count)
                rt = (unique_rejected_count/unique_total_count*100) if unique_total_count>0 else 0
                c4.metric("Rate", f"{rt:.1f}%")
                c5.metric("SKUs in Both Files", intersection_count)
                
                st.subheader("Validation Results by Flag")
                
                for title, df_flagged_sids in flag_dfs.items():
                    # flag_dfs now contains only SIDs, which need to be merged back for display
                    if 'PRODUCT_SET_SID' in df_flagged_sids.columns:
                        display_df = pd.merge(df_flagged_sids[['PRODUCT_SET_SID']].drop_duplicates(), merged_data, on='PRODUCT_SET_SID', how='left')
                    else:
                        display_df = pd.DataFrame(columns=merged_data.columns)

                    with st.expander(f"{title} ({len(display_df)})"):
                        if not display_df.empty:
                            st.dataframe(display_df)
                            st.download_button(f"Export {title}", to_excel_flag_data(display_df, title), f"{file_prefix}_{title}.xlsx")
                        else:
                            st.success("No issues found.")
                
                st.markdown("---")
                st.header("Overall Exports")
                c1, c2, c3, c4 = st.columns(4)
                c1.download_button("Final Report", to_excel(final_report, support_files['reasons']), f"{file_prefix}_Final_Report_{current_date}.xlsx")
                c2.download_button("Rejected", to_excel(rejected_df, support_files['reasons']), f"{file_prefix}_Rejected_{current_date}.xlsx")
                c3.download_button("Approved", to_excel(approved_df, support_files['reasons']), f"{file_prefix}_Approved_{current_date}.xlsx")
                c4.download_button("Full Data", to_excel_full_data(merged_data, final_report), f"{file_prefix}_Full_Data_{current_date}.xlsx")
            else:
                for e in errors: st.error(e)
        except Exception as e:
            st.error(f"Error: {e}")
            st.code(traceback.format_exc())

# -------------------------------------------------
# TAB 2: WEEKLY ANALYSIS
# -------------------------------------------------
with tab2:
    st.header("Weekly Analysis Dashboard")
    st.info("Upload multiple 'Full Data' files exported from the Daily tab to see aggregated trends.")
    
    weekly_files = st.file_uploader("Upload Full Data Files (XLSX/CSV)", accept_multiple_files=True, type=['xlsx', 'csv'], key="weekly_files")
    
    if weekly_files:
        combined_df = pd.DataFrame()
        with st.spinner("Aggregating files..."):
            for f in weekly_files:
                try:
                    if f.name.endswith('.xlsx'):
                        try:
                            df = pd.read_excel(f, sheet_name='ProductSets', engine='openpyxl', dtype=str)
                        except:
                            f.seek(0)
                            df = pd.read_excel(f, engine='openpyxl', dtype=str)
                    else:
                        df = pd.read_csv(f, dtype=str)
                    
                    df.columns = df.columns.str.strip()
                    df = standardize_input_data(df)

                    required_weekly_cols = ['Status', 'Reason', 'FLAG', 'SELLER_NAME', 'CATEGORY', 'PRODUCT_SET_SID']
                    for col in required_weekly_cols:
                        if col not in df.columns:
                            df[col] = pd.NA  
                    
                    combined_df = pd.concat([combined_df, df], ignore_index=True)
                except Exception as e:
                    st.error(f"Error reading {f.name}: {e}")
        
        if not combined_df.empty:
            combined_df = combined_df.drop_duplicates(subset=['PRODUCT_SET_SID'])
            
            rejected = combined_df[combined_df['Status'] == 'Rejected'].copy()  
            
            st.markdown("### Key Metrics")
            m1, m2, m3, m4 = st.columns(4)
            total = len(combined_df)
            rej_count = len(rejected)
            rej_rate = (rej_count/total * 100) if total else 0
            
            m1.metric("Total Products Checked", f"{total:,}")
            m2.metric("Total Rejected", f"{rej_count:,}")
            m3.metric("Rejection Rate", f"{rej_rate:.1f}%")
            m4.metric("Unique Sellers", f"{combined_df['SELLER_NAME'].nunique():,}")
            
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Top Rejection Reasons (Flags)")
                if not rejected.empty and 'FLAG' in rejected.columns:
                    reason_counts = rejected['FLAG'].value_counts().reset_index()
                    reason_counts.columns = ['Flag', 'Count']
                    chart = alt.Chart(reason_counts.head(10)).mark_bar().encode(
                        x=alt.X('Count', title='Number of Products'),
                        y=alt.Y('Flag', sort='-x', title=None),
                        color=alt.value('#FF6B6B'),
                        tooltip=['Flag', 'Count']
                    ).interactive()
                    st.altair_chart(chart, use_container_width=True)

            with c2:
                st.subheader("Top Rejected Categories")
                if not rejected.empty and 'CATEGORY' in rejected.columns:
                    cat_counts = rejected['CATEGORY'].value_counts().reset_index()
                    cat_counts.columns = ['Category', 'Count']
                    chart = alt.Chart(cat_counts.head(10)).mark_bar().encode(
                        x=alt.X('Count', title='Number of Rejections'),
                        y=alt.Y('Category', sort='-x', title=None),
                        color=alt.value('#4ECDC4'),
                        tooltip=['Category', 'Count']
                    ).interactive()
                    st.altair_chart(chart, use_container_width=True)

            with c3:
                st.subheader("Top 10 Rejected Sellers")
                if not rejected.empty and 'SELLER_NAME' in rejected.columns:
                    seller_counts = rejected['SELLER_NAME'].value_counts().reset_index()
                    seller_counts.columns = ['Seller', 'Count']
                    chart = alt.Chart(seller_counts.head(10)).mark_bar().encode(
                        x=alt.X('Seller', sort='-y', axis=alt.Axis(labelAngle=-45)),
                        y=alt.Y('Count', title='Rejections'),
                        color=alt.value('#FFE66D'),
                        tooltip=['Seller', 'Count']
                    ).interactive()
                    st.altair_chart(chart, use_container_width=True)

            with c4:
                st.subheader("Seller vs. Reason Breakdown (Top 5)")
                if not rejected.empty and 'SELLER_NAME' in rejected.columns and 'Reason' in rejected.columns:
                    top_sellers = rejected['SELLER_NAME'].value_counts().head(5).index.tolist()
                    filtered_rej = rejected[rejected['SELLER_NAME'].isin(top_sellers)]
                    if not filtered_rej.empty:
                        breakdown = filtered_rej.groupby(['SELLER_NAME', 'Reason']).size().reset_index(name='Count')
                        chart = alt.Chart(breakdown).mark_bar().encode(
                            x=alt.X('SELLER_NAME', title='Seller'),
                            y=alt.Y('Count', title='Count'),
                            color=alt.Color('Reason', legend=alt.Legend(title="Rejection Reason", orient="bottom")),
                            tooltip=['SELLER_NAME', 'Reason', 'Count']
                        ).interactive()
                        st.altair_chart(chart, use_container_width=True)

            st.markdown("---")
            st.subheader("Top 5 Summaries")

            if not rejected.empty:
                top_reasons = rejected['FLAG'].value_counts().head(5).reset_index()
                top_reasons.columns = ['Flag', 'Count']
                
                top_sellers = rejected['SELLER_NAME'].value_counts().head(5).reset_index()
                top_sellers.columns = ['Seller', 'Rejection Count']
                top_cats = rejected['CATEGORY'].value_counts().head(5).reset_index()
                top_cats.columns = ['Category', 'Rejection Count']
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown("**Top 5 Reasons (Flags)**")
                    st.dataframe(top_reasons, hide_index=True, use_container_width=True)
                with c2:
                    st.markdown("**Top 5 Sellers**")
                    st.dataframe(top_sellers, hide_index=True, use_container_width=True)
                with c3:
                    st.markdown("**Top 5 Categories**")
                    st.dataframe(top_cats, hide_index=True, use_container_width=True)
                
                summary_excel = BytesIO()
                with pd.ExcelWriter(summary_excel, engine='xlsxwriter') as writer:
                    pd.DataFrame([
                        {'Metric': 'Total Rejected SKUs', 'Value': len(rejected)},
                        {'Metric': 'Total Products Checked', 'Value': len(combined_df)},
                        {'Metric': 'Rejection Rate (%)', 'Value': (len(rejected)/len(combined_df)*100)}
                    ]).to_excel(writer, sheet_name='Summary', index=False)
                    top_reasons.to_excel(writer, sheet_name='Top 5 Reasons', index=False)
                    top_sellers.to_excel(writer, sheet_name='Top 5 Sellers', index=False)
                    top_cats.to_excel(writer, sheet_name='Top 5 Categories', index=False)
                    workbook = writer.book
                    for sheet in writer.sheets.values():
                        sheet.set_column(0, 1, 25)
                
                summary_excel.seek(0)
                st.download_button(
                    label="📥 Download Summary Excel",
                    data=summary_excel,
                    file_name=f"Weekly_Analysis_Summary_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# -------------------------------------------------
# TAB 3: DATA LAKE
# -------------------------------------------------
with tab3:
    st.header("Data Lake Audit")
    file = st.file_uploader("Upload audit file", type=['jsonl','csv','xlsx'], key="audit_file")
    if file:
        if file.name.endswith('.jsonl'): df = pd.read_json(file, lines=True)
        elif file.name.endswith('.csv'): df = pd.read_csv(file)
        else: df = pd.read_excel(file)
        st.dataframe(df.head(50))
    else:
        try:
            st.dataframe(pd.read_json('validation_audit.jsonl', lines=True).tail(50))
        except:
            st.info("No audit log found.")
