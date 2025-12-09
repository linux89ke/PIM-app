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
FX_RATE = 132.0

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
    """Loads flag mapping (e.g., 'Sensitive words' -> ('CODE', 'COMMENT'))"""
    try:
        flag_mapping = {
            'Sensitive words': ('1000001 - Brand NOT Allowed', "Your listing was rejected because it includes brands that are not allowed on Jumia..."),
            'BRAND name repeated in NAME': ('1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name', "Please do not write the brand name in the Product Name field..."),
            'Missing COLOR': ('1000005 - Kindly confirm the actual product colour', "Please make sure that the product color is clearly mentioned..."),
            'Duplicate product': ('1000007 - Other Reason', "kindly note product was rejected because its a duplicate product"),
            'Prohibited products': ('1000007 - Other Reason', "Kindly note this product is not allowed for listing on Jumia..."),
            'Single-word NAME': ('1000008 - Kindly Improve Product Name Description', "Kindly update the product title using this format..."),
            'Generic BRAND Issues': ('1000014 - Kindly request for the creation of this product\'s actual brand name...', "To create the actual brand name for this product..."),
            'Counterfeit Sneakers': ('1000023 - Confirmation of counterfeit product by Jumia technical team...', "Your listing has been rejected as Jumia's technical team has confirmed..."),
            'Seller Approve to sell books': ('1000028 - Kindly Contact Jumia Seller Support...', "Please contact Jumia Seller Support and raise a claim..."),
            'Seller Approved to Sell Perfume': ('1000028 - Kindly Contact Jumia Seller Support...', "Please contact Jumia Seller Support and raise a claim..."),
            'Perfume Price Check': ('1000029 - Kindly Contact Jumia Seller Support To Verify This Product\'s Authenticity...', "Please contact Jumia Seller Support to raise a claim..."),
            'Suspected counterfeit Jerseys': ('1000030 - Suspected Counterfeit Product', "Your listing has been rejected as it is suspected to be a counterfeit jersey..."),
            'Product Warranty': ('1000013 - Kindly Provide Product Warranty Details', "For listing this type of product requires a valid warranty as per our platform guidelines.\nTo proceed, please ensure the warranty details are clearly mentioned in:\n\nProduct Description tab\n\nWarranty Tab.\n\nThis helps build customer trust and ensures your listing complies with Jumia\'s requirements."),
        }
        return flag_mapping
    except Exception: return {}

@st.cache_data(ttl=3600)
def load_all_support_files() -> Dict:
    """Loads all configuration and support files."""
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
        'colors': [c.lower() for c in load_txt_file('colors.txt')],
        'color_categories': load_txt_file('color_cats.txt'),
        'check_variation': load_excel_file('check_variation.xlsx'),
        'category_fas': load_excel_file('category_FAS.xlsx'),
        'perfumes': load_excel_file('perfumes.xlsx'),
        'reasons': load_excel_file('reasons.xlsx'),
        'flags_mapping': load_flags_mapping(),
        'jerseys_config': load_excel_file('Jerseys.xlsx'),
        'warranty_category_codes': load_txt_file('warranty.txt'),
    }
    return files

@st.cache_data(ttl=3600)
def compile_regex_patterns(words: List[str]) -> Optional[re.Pattern]:
    """Compiles a list of words into a single regex pattern for fast search."""
    if not words: return None
    pattern = '|'.join(r'\b' + re.escape(w) + r'\b' for w in words)
    return re.compile(pattern, re.IGNORECASE)

# -------------------------------------------------
# Country & Helper Classes
# -------------------------------------------------
class CountryValidator:
    COUNTRY_CONFIG = {
        "Kenya": {"code": "KE", "skip_validations": [], "prohibited_products_file": "prohibited_productsKE.txt"},
        "Uganda": {"code": "UG", "skip_validations": ["Seller Approve to sell books", "Perfume Price Check", "Seller Approved to Sell Perfume", "Counterfeit Sneakers"], "prohibited_products_file": "prohibited_productsUG.txt"}
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
# Data Loading & Preparation Functions
# -------------------------------------------------
def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    """Renames columns and cleans country status."""
    df = df.copy()
    df = df.rename(columns=NEW_FILE_MAPPING)
    if 'ACTIVE_STATUS_COUNTRY' in df.columns:
        df['ACTIVE_STATUS_COUNTRY'] = (
            df['ACTIVE_STATUS_COUNTRY'].astype(str).str.lower()
            .str.replace('jumia-', '', regex=False).str.strip().str.upper()
        )
    return df

def validate_input_schema(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """Checks for required columns."""
    errors = []
    required = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'ACTIVE_STATUS_COUNTRY']
    for field in required:
        if field not in df.columns: errors.append(f"Missing: {field}")
    return len(errors) == 0, errors

def filter_by_country(df: pd.DataFrame, country_validator: CountryValidator, source: str) -> pd.DataFrame:
    """Filters data frame to include only rows matching the selected country code."""
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns: return df
    df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.strip().str.upper()
    mask = df['ACTIVE_STATUS_COUNTRY'] == country_validator.code
    filtered = df[mask].copy()
    return filtered

def propagate_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """Propagates metadata (COLOR_FAMILY, WARRANTY) across duplicate SIDs before filtering."""
    if df.empty: return df
    cols_to_propagate = ['COLOR_FAMILY', 'PRODUCT_WARRANTY', 'WARRANTY_DURATION', 'WARRANTY_ADDRESS', 'WARRANTY_TYPE']
    
    for col in cols_to_propagate:
        if col not in df.columns: df[col] = pd.NA
    
    # Forward fill and Backward fill to spread data between rows of same SID
    for col in cols_to_propagate:
        df[col] = df.groupby('PRODUCT_SET_SID')[col].transform(lambda x: x.ffill().bfill())
        
    return df

# --- Validation Logic Functions ---

def check_product_warranty(data: pd.DataFrame, warranty_category_codes: List[str]) -> pd.DataFrame:
    """
    Checks if products in warranty-required categories have warranty information.
    A product needs AT LEAST ONE of: PRODUCT_WARRANTY or WARRANTY_DURATION filled.
    """
    # 1. Ensure warranty columns exist
    data_to_check = data.copy()
    for col in ['PRODUCT_WARRANTY', 'WARRANTY_DURATION']:
        if col not in data_to_check.columns: 
            data_to_check[col] = ""
        # Ensure it's treated as a string and missing values are handled
        data_to_check[col] = data_to_check[col].astype(str).fillna('').str.strip()
    
    if not warranty_category_codes: 
        return pd.DataFrame(columns=data.columns)
    
    # 2. Filter to warranty-required categories
    data_to_check['CAT_CLEAN'] = data_to_check['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
    target_cats = [str(c).strip() for c in warranty_category_codes]
    
    target_data = data_to_check[data_to_check['CAT_CLEAN'].isin(target_cats)].copy()
    if target_data.empty: 
        return pd.DataFrame(columns=data.columns)
    
    # 3. Check if ANY warranty field has meaningful data
    def is_present(series):
        """Check if a field has meaningful data (not empty, nan, none, etc.)"""
        s = series.astype(str).str.strip().str.lower()
        return (s != 'nan') & (s != '') & (s != 'none') & (s != 'nat') & (s != 'n/a')
    
    # Check each warranty field
    has_product_warranty = is_present(target_data['PRODUCT_WARRANTY'])
    has_duration = is_present(target_data['WARRANTY_DURATION'])
    
    # Product is OK if it has EITHER field filled
    has_any_warranty = has_product_warranty | has_duration
    
    # Flag products that have NO warranty information at all
    mask = ~has_any_warranty
    flagged = target_data[mask]
    
    if 'CAT_CLEAN' in flagged.columns: 
        flagged = flagged.drop(columns=['CAT_CLEAN'])
    
    # Return only unique Product Set SIDs
    return flagged.drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_missing_color(data: pd.DataFrame, pattern: re.Pattern, color_categories: List[str], country_code: str = 'KE') -> pd.DataFrame:
    """Checks for color presence in required categories."""
    req = ['NAME', 'COLOR', 'CATEGORY_CODE']
    if not set(req).issubset(data.columns): return pd.DataFrame(columns=data.columns)
    data = data[data['CATEGORY_CODE'].isin(color_categories)].copy()
    if data.empty: return pd.DataFrame(columns=data.columns)
    
    name_check = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    color_check = data['COLOR'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    family_check = pd.Series([False] * len(data), index=data.index)
    
    if country_code == 'KE' and 'COLOR_FAMILY' in data.columns:
        family_check = data['COLOR_FAMILY'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    
    if country_code == 'KE':
        mask = ~(name_check | color_check | family_check)
    else:
        mask = ~(name_check | color_check)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_sensitive_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    """Flags products whose name contains sensitive words."""
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    """Flags products whose name contains prohibited product words."""
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_brand_in_name(data: pd.DataFrame) -> pd.DataFrame:
    """Flags products where the brand name is repeated in the product name."""
    if not {'BRAND','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    mask = data.apply(lambda r: str(r['BRAND']).strip().lower() in str(r['NAME']).strip().lower() 
                     if pd.notna(r['BRAND']) and pd.notna(r['NAME']) else False, axis=1)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_duplicate_products(data: pd.DataFrame) -> pd.DataFrame:
    """Flags product sets that appear to be duplicates based on key attributes."""
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    if len(cols) < 4: return pd.DataFrame(columns=data.columns)
    return data[data.duplicated(subset=cols, keep=False)].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_seller_approved_for_books(data: pd.DataFrame, book_category_codes: List[str], approved_book_sellers: List[str]) -> pd.DataFrame:
    """Flags unapproved sellers trying to sell books."""
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if books.empty: return pd.DataFrame(columns=data.columns)
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_category_codes: List[str], approved_perfume_sellers: List[str], sensitive_perfume_brands: List[str]) -> pd.DataFrame:
    """Flags unapproved sellers selling sensitive perfume brands/names."""
    if not {'CATEGORY_CODE','SELLER_NAME','BRAND','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perfume_data.empty: return pd.DataFrame(columns=data.columns)
    brand_lower = perfume_data['BRAND'].astype(str).str.strip().str.lower()
    name_lower = perfume_data['NAME'].astype(str).str.strip().str.lower()
    sensitive_mask = brand_lower.isin(sensitive_perfume_brands)
    fake_brands = ['designers collection', 'smart collection', 'generic', 'original', 'fashion']
    fake_brand_mask = brand_lower.isin(fake_brands)
    name_contains_sensitive = name_lower.apply(lambda x: any(brand in x for brand in sensitive_perfume_brands))
    final_mask = (sensitive_mask | (fake_brand_mask & name_contains_sensitive)) & (~perfume_data['SELLER_NAME'].isin(approved_perfume_sellers))
    return perfume_data[final_mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_counterfeit_sneakers(data: pd.DataFrame, sneaker_category_codes: List[str], sneaker_sensitive_brands: List[str]) -> pd.DataFrame:
    """Flags generic sneakers using sensitive brand names."""
    if not {'CATEGORY_CODE', 'NAME', 'BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    sneaker_data = data[data['CATEGORY_CODE'].isin(sneaker_category_codes)].copy()
    if sneaker_data.empty: return pd.DataFrame(columns=data.columns)
    brand_lower = sneaker_data['BRAND'].astype(str).str.strip().str.lower()
    name_lower = sneaker_data['NAME'].astype(str).str.strip().str.lower()
    fake_brand_mask = brand_lower.isin(['generic', 'fashion'])
    name_contains_brand = name_lower.apply(lambda x: any(brand in x for brand in sneaker_sensitive_brands))
    return sneaker_data[fake_brand_mask & name_contains_brand].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_perfume_price_vectorized(data: pd.DataFrame, perfumes_df: pd.DataFrame, perfume_category_codes: List[str]) -> pd.DataFrame:
    """Flags perfumes where the price is significantly lower than a reference price."""
    req = ['CATEGORY_CODE','NAME','BRAND','GLOBAL_SALE_PRICE','GLOBAL_PRICE']
    if not all(c in data.columns for c in req) or perfumes_df.empty: return pd.DataFrame(columns=data.columns)
    perf = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perf.empty: return pd.DataFrame(columns=data.columns)
    perf['price_to_use'] = perf['GLOBAL_SALE_PRICE'].where((perf['GLOBAL_SALE_PRICE'].notna()) & (pd.to_numeric(perf['GLOBAL_SALE_PRICE'], errors='coerce') > 0), perf['GLOBAL_PRICE'])
    perf['price_to_use'] = pd.to_numeric(perf['price_to_use'], errors='coerce').fillna(0)
    
    currency = perf.get('CURRENCY', pd.Series(['KES'] * len(perf)))
    perf['price_usd'] = perf['price_to_use'].where(currency.astype(str).str.upper() != 'KES', perf['price_to_use'] / FX_RATE)
    perf['BRAND_LOWER'] = perf['BRAND'].astype(str).str.strip().str.lower()
    perf['NAME_LOWER'] = perf['NAME'].astype(str).str.strip().str.lower()
    perfumes_df = perfumes_df.copy()
    perfumes_df['BRAND_LOWER'] = perfumes_df['BRAND'].astype(str).str.strip().str.lower()
    if 'PRODUCT_NAME' in perfumes_df.columns:
        perfumes_df['PRODUCT_NAME_LOWER'] = perfumes_df['PRODUCT_NAME'].astype(str).str.strip().str.lower()
    merged = perf.merge(perfumes_df, on='BRAND_LOWER', how='left', suffixes=('', '_ref'))
    if 'PRODUCT_NAME_LOWER' in merged.columns:
        merged = merged[merged.apply(lambda r: r['PRODUCT_NAME_LOWER'] in r['NAME_LOWER'] if pd.notna(r['PRODUCT_NAME_LOWER']) else False, axis=1)]
    if 'PRICE_USD' in merged.columns:
        merged['PRICE_USD_ref'] = pd.to_numeric(merged['PRICE_USD'], errors='coerce')
        merged = merged.dropna(subset=['PRICE_USD_ref'])
        flagged = merged[merged['PRICE_USD_ref'] - merged['price_usd'] >= 30]
        return flagged[data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])
    return pd.DataFrame(columns=data.columns)

def check_single_word_name(data: pd.DataFrame, book_category_codes: List[str]) -> pd.DataFrame:
    """Flags non-book products with single-word names."""
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_generic_brand_issues(data: pd.DataFrame, valid_category_codes_fas: List[str]) -> pd.DataFrame:
    """Flags 'Generic' brand in specific categories."""
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    return data[data['CATEGORY_CODE'].isin(valid_category_codes_fas) & (data['BRAND']=='Generic')].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    """Flags suspected counterfeit jerseys based on keywords and seller exceptions."""
    req = ['CATEGORY_CODE', 'NAME', 'SELLER_NAME']
    if not all(c in data.columns for c in req) or jerseys_df.empty: return pd.DataFrame(columns=data.columns)
    jersey_cats = jerseys_df['Categories'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().unique().tolist()
    jersey_cats = [c for c in jersey_cats if c.lower() != 'nan']
    keywords = [w for w in jerseys_df['Checklist'].astype(str).str.strip().str.lower().unique().tolist() if w and w!='nan']
    exempt = [s for s in jerseys_df['Exempted'].astype(str).str.strip().unique().tolist() if s and s.lower()!='nan']
    if not jersey_cats or not keywords: return pd.DataFrame(columns=data.columns)
    regex = re.compile('|'.join(r'\b' + re.escape(w) + r'\b' for w in keywords), re.IGNORECASE)
    data['CAT_STR'] = data['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
    jerseys = data[data['CAT_STR'].isin(jersey_cats)].copy()
    if jerseys.empty: return pd.DataFrame(columns=data.columns)
    target = jerseys[~jerseys['SELLER_NAME'].isin(exempt)].copy()
    mask = target['NAME'].astype(str).str.strip().str.lower().str.contains(regex, na=False)
    flagged = target[mask]
    return flagged.drop(columns=['CAT_STR']) if 'CAT_STR' in flagged.columns else flagged.drop_duplicates(subset=['PRODUCT_SET_SID'])

# -------------------------------------------------
# Master validation runner
# -------------------------------------------------
def validate_products(data: pd.DataFrame, support_files: Dict, country_validator: CountryValidator):
    flags_mapping = support_files['flags_mapping']
    
    # ORDER MATTERS: This list defines the priority of the rejection flags.
    validations = [
        ("Product Warranty", check_product_warranty, {'warranty_category_codes': support_files['warranty_category_codes']}),
        ("Sensitive words", check_sensitive_words, {'pattern': compile_regex_patterns(support_files['sensitive_words'])}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': support_files['book_category_codes'], 'approved_book_sellers': support_files['approved_book_sellers']}),
        ("Perfume Price Check", check_perfume_price_vectorized, {'perfumes_df': support_files['perfumes'], 'perfume_category_codes': support_files['perfume_category_codes']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'perfume_category_codes': support_files['perfume_category_codes'], 'approved_perfume_sellers': support_files['approved_perfume_sellers'], 'sensitive_perfume_brands': support_files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'sneaker_category_codes': support_files['sneaker_category_codes'], 'sneaker_sensitive_brands': support_files['sneaker_sensitive_brands']}),
        ("Suspected counterfeit Jerseys", check_counterfeit_jerseys, {'jerseys_df': support_files['jerseys_config']}),
        ("Prohibited products", check_prohibited_products, {'pattern': compile_regex_patterns(country_validator.load_prohibited_products())}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': support_files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': compile_regex_patterns(support_files['colors']), 'color_categories': support_files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
    ]
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    results = {} # Dictionary to hold the DataFrame for each specific flag
    
    for i, (name, func, kwargs) in enumerate(validations):
        if country_validator.should_skip_validation(name): 
            results[name] = pd.DataFrame(columns=data.columns) # Add empty result for skipped validation
            continue 

        status_text.text(f"Running: {name}")
        ckwargs = {'data': data, **kwargs}
        if name == "Generic BRAND Issues":
            fas = support_files.get('category_fas', pd.DataFrame())
            ckwargs['valid_category_codes_fas'] = fas['ID'].astype(str).tolist() if not fas.empty and 'ID' in fas.columns else []
        elif name == "Missing COLOR":
            ckwargs['country_code'] = country_validator.code
        
        try:
            # Run the validation function
            res = func(**ckwargs)
            # Store the resulting DataFrame (unique SIDs already ensured by validation functions)
            results[name] = res if not res.empty else pd.DataFrame(columns=data.columns)
        except Exception as e:
            logger.error(f"Error in validation {name}: {e}\n{traceback.format_exc()}")
            results[name] = pd.DataFrame(columns=data.columns)
        progress_bar.progress((i + 1) / len(validations))
    
    status_text.text("Finalizing...")
    rows = []
    processed_sids = set()
    
    # Process Rejected Products based on priority
    for name, _, _ in validations:
        if name not in results or results[name].empty: continue
        res = results[name]
        if 'PRODUCT_SET_SID' not in res.columns: continue
        
        reason_info = flags_mapping.get(name, ("1000007 - Other Reason", f"Flagged by {name}"))
        
        # Identify new SIDs for this flag that haven't been rejected by a higher-priority flag
        newly_flagged_sids = res['PRODUCT_SET_SID'].astype(str).drop_duplicates().tolist()
        sids_to_process = [sid for sid in newly_flagged_sids if sid not in processed_sids]
        
        if sids_to_process:
            # Get the full product set data for these SIDs
            flagged = data[data['PRODUCT_SET_SID'].astype(str).isin(sids_to_process)]
            
            for _, r in flagged.iterrows():
                sid = r['PRODUCT_SET_SID']
                if sid in processed_sids: continue # Safety check
                
                processed_sids.add(sid)
                rows.append({
                    'ProductSetSid': sid, 'ParentSKU': r.get('PARENTSKU', ''), 'Status': 'Rejected',
                    'Reason': reason_info[0], 'Comment': reason_info[1], 'FLAG': name, 'SellerName': r.get('SELLER_NAME', '')
                })
    
    # Process Approved Products
    approved = data[~data['PRODUCT_SET_SID'].astype(str).isin(processed_sids)].drop_duplicates(subset=['PRODUCT_SET_SID'])
    for _, r in approved.iterrows():
        rows.append({
            'ProductSetSid': r['PRODUCT_SET_SID'], 'ParentSKU': r.get('PARENTSKU', ''), 'Status': 'Approved',
            'Reason': "", 'Comment': "", 'FLAG': "", 'SellerName': r.get('SELLER_NAME', '')
        })
    
    progress_bar.empty()
    status_text.empty()
    return country_validator.ensure_status_column(pd.DataFrame(rows)), results

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
        
        # Merge the validation results (Status, Reason, FLAG) back onto the full data
        merged = pd.merge(d_cp, r_cp[["ProductSetSid", "Status", "Reason", "Comment", "FLAG", "SellerName"]],
                          left_on="PRODUCT_SET_SID", right_on="ProductSetSid", how='left', suffixes=('_data', '_report'))
        
        # Clean up merged columns
        if 'ProductSetSid_report' in merged.columns: merged.drop(columns=['ProductSetSid_report'], inplace=True)
        if 'ProductSetSid_data' in merged.columns: merged.rename(columns={'ProductSetSid_data': 'PRODUCT_SET_SID'}, inplace=True)
        
        # Ensure final list of columns for export
        export_cols = FULL_DATA_COLS + [c for c in ["Status", "Reason", "Comment", "FLAG", "SellerName"] if c not in FULL_DATA_COLS]
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            to_excel_base(merged, "ProductSets", export_cols, writer)
            
            wb = writer.book
            ws = wb.add_worksheet('Sellers Data')
            fmt = wb.add_format({'bold': True, 'bg_color': '#E6F0FA', 'border': 1, 'align': 'center'})
            
            row_cursor = 1
            if 'SELLER_RATING' in merged.columns and 'SELLER_NAME' in merged.columns and 'STOCK_QTY' in merged.columns:
                merged['Rejected_Count'] = (merged['Status'] == 'Rejected').astype(int)
                merged['Approved_Count'] = (merged['Status'] == 'Approved').astype(int)
                
                # Group by SELLER_NAME and calculate summary metrics
                summ = merged.groupby('SELLER_NAME').agg(
                    Rejected=('Rejected_Count', 'sum'), 
                    Approved=('Approved_Count', 'sum'),
                    AvgRating=('SELLER_RATING', lambda x: pd.to_numeric(x, errors='coerce').mean()),  
                    TotalStock=('STOCK_QTY', lambda x: pd.to_numeric(x, errors='coerce').sum())
                ).reset_index().sort_values('Rejected', ascending=False)
                
                summ.insert(0, 'Rank', range(1, len(summ) + 1))
                ws.write(0, 0, "Sellers Summary", fmt)
                summ.to_excel(writer, sheet_name='Sellers Data', startrow=1, index=False)
                row_cursor = len(summ) + 4

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
    except Exception as e:
        logger.error(f"Error creating full data excel: {e}\n{traceback.format_exc()}")
        return BytesIO()

def to_excel(report_df, reasons_config_df):
    """Exports the final status report and rejection reasons config."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(report_df, "ProductSets", PRODUCTSETS_COLS, writer)
        if not reasons_config_df.empty:
            to_excel_base(reasons_config_df, "RejectionReasons", REJECTION_REASONS_COLS, writer)
    output.seek(0)
    return output

def to_excel_flag_data(flag_df, flag_name):
    """Exports the full product data for a single specific flag."""
    output = BytesIO()
    df_copy = flag_df.copy()
    df_copy['FLAG'] = flag_name
    
    # Ensure all necessary columns exist for the full data export
    export_cols = FULL_DATA_COLS + [c for c in ["FLAG"] if c not in FULL_DATA_COLS]
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(df_copy, "FlaggedProducts", export_cols, writer)
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

if support_files['flags_mapping'].empty: # Check if flag mapping loaded correctly
    st.error("Critical: Flag mapping data could not be loaded. Check support files.")
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
            
            for uploaded_file in uploaded_files:
                try:
                    if uploaded_file.name.endswith('.xlsx'):
                        raw_data = pd.read_excel(uploaded_file, engine='openpyxl', dtype=str)
                    else:
                        try: 
                            raw_data = pd.read_csv(uploaded_file, encoding='utf-8', sep=None, engine='python', dtype=str)
                        except UnicodeDecodeError:
                            raw_data = pd.read_csv(uploaded_file, encoding='latin1', sep=None, engine='python', dtype=str)
                            
                    st.success(f"Successfully loaded file: {uploaded_file.name}")
                    
                    df = standardize_input_data(raw_data)
                    
                    # Schema check
                    schema_ok, errors = validate_input_schema(df)
                    if not schema_ok:
                        st.error(f"Schema validation failed for {uploaded_file.name}: {', '.join(errors)}")
                        continue

                    # Filter by country
                    df = filter_by_country(df, country_validator, uploaded_file.name)
                    if df.empty:
                        st.warning(f"No {country_validator.code} products found in {uploaded_file.name}. Skipping.")
                        continue
                        
                    df = propagate_metadata(df) # Propagate warranty info across variations
                    df['SourceFile'] = uploaded_file.name # Track source file
                    all_dfs.append(df)
                    
                except Exception as e:
                    logger.error(f"Error processing {uploaded_file.name}: {e}\n{traceback.format_exc()}")
                    st.error(f"An error occurred while processing {uploaded_file.name}: {e}")
                    
            if all_dfs:
                # 1. Concatenate all data
                data_df_full = pd.concat(all_dfs, ignore_index=True)
                total_products = len(data_df_full.drop_duplicates(subset=['PRODUCT_SET_SID']))
                
                # Check for empty data after filtering
                if data_df_full.empty:
                    st.error("No valid data remaining after filtering by country and applying schema checks.")
                    st.stop()
                    
                # 2. Run Validation
                final_report_df, flag_data = validate_products(data_df_full, support_files, country_validator)
                
                # 3. Summarize Results
                rejected_count = final_report_df[final_report_df['Status'] == 'Rejected']['ProductSetSid'].nunique()
                approved_count = final_report_df[final_report_df['Status'] == 'Approved']['ProductSetSid'].nunique()
                
                st.subheader("Validation Run Summary")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total Unique Product Sets", f"{total_products:,}")
                col2.metric("Approved Product Sets", f"{approved_count:,}", delta_color="normal")
                col3.metric("Rejected Product Sets", f"{rejected_count:,}", delta_color="inverse")
                
                rejection_rate = (rejected_count / total_products) * 100 if total_products > 0 else 0
                col4.metric("Rejection Rate", f"{rejection_rate:.1f}%")
                
                st.markdown("---")

                # 4. Main Download Buttons
                st.subheader("Final Reports Download ⬇️")
                
                # Report with just SIDs, Status, Reason
                final_report_output = to_excel(final_report_df.drop_duplicates(subset=['ProductSetSid']), support_files['reasons'])
                st.download_button(
                    label=f"Download 📋 Final Status Report ({file_prefix}_{current_date})",
                    data=final_report_output, 
                    file_name=f"Final_Validation_Report_{file_prefix}_{current_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                # Full Data Report
                full_data_output = to_excel_full_data(data_df_full, final_report_df)
                st.download_button(
                    label=f"Download 📁 Full Data + Status & Summary ({file_prefix}_{current_date})",
                    data=full_data_output, file_name=f"Full_Data_Validation_{file_prefix}_{current_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                st.markdown("---")
                
                # 5. Interactive Flag Data View (Matching the Image)
                st.subheader("Validation Results by Flag 🚩")
                
                # Sort flags by the count of flagged products (descending)
                flag_counts = {
                    name: len(df.drop_duplicates(subset=['PRODUCT_SET_SID']))
                    for name, df in flag_data.items() if not df.empty
                }
                sorted_flags = sorted(flag_counts.items(), key=lambda item: item[1], reverse=True)
                
                if not sorted_flags:
                    st.success("🎉 All products passed all active validation checks!")
                else:
                    
                    # Display the data for each flag in an expander
                    for flag_name, count in sorted_flags:
                        flag_specific_data = flag_data.get(flag_name, pd.DataFrame())
                        
                        # Use the count of unique SIDs in the expander title
                        with st.expander(f"**{flag_name}** ({count:,} products)"):
                            if not flag_specific_data.empty:
                                st.markdown("##### Flagged Data Preview (First 50 Rows)")
                                st.dataframe(flag_specific_data.head(50), use_container_width=True)
                                
                                # Download button for the specific flag data
                                flag_output = to_excel_flag_data(flag_specific_data, flag_name)
                                st.download_button(
                                    label=f"Download Full Data for **{flag_name}** ({count:,} products)",
                                    data=flag_output, 
                                    file_name=f"{flag_name}_Data_{file_prefix}_{current_date}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    key=f"dl_{flag_name}_view"
                                )
                            else:
                                st.info("No data available for this flag.")

            else:
                st.info("No valid files processed or no products matched the selected country.")
                
        except Exception as e:
            logger.error(f"Global error during validation: {e}\n{traceback.format_exc()}")
            st.error(f"An unexpected error occurred: {e}")

# -------------------------------------------------
# TAB 2 & 3 (Placeholders)
# -------------------------------------------------
with tab2:
    st.header("Weekly Analysis (To be implemented)")
    st.markdown("This tab will host interactive charts and aggregations for weekly trends.")

with tab3:
    st.header("Data Lake Connection (To be implemented)")
    st.markdown("This tab will allow connection to a data source (e.g., S3, Google Drive) for loading larger datasets.")
