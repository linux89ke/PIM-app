import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import logging
from typing import Dict, List, Tuple, Optional
import traceback
import json

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
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# -------------------------------------------------
# Constants
# -------------------------------------------------
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]
REJECTION_REASONS_COLS = ['CODE - REJECTION_REASON', 'COMMENT']
FULL_DATA_COLS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE",
    "COLOR", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU",
    "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG",
    "LISTING_STATUS", "SELLER_RATING", "STOCK_QTY"
]
FX_RATE = 132.0

# -------------------------------------------------
# CACHED FILE LOADING
# -------------------------------------------------
@st.cache_data(ttl=3600)
def load_txt_file(filename: str) -> List[str]:
    """Load and cache text file contents"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = [line.strip() for line in f if line.strip()]
        logger.info(f"Loaded {len(data)} lines from {filename}")
        return data
    except FileNotFoundError:
        logger.warning(f"{filename} not found")
        st.warning(f"{filename} not found – related check disabled.")
        return []
    except Exception as e:
        logger.error(f"Error reading {filename}: {e}", exc_info=True)
        st.error(f"Error reading {filename}: {e}")
        return []

@st.cache_data(ttl=3600)
def load_excel_file(filename: str, column: Optional[str] = None) -> pd.DataFrame:
    """Load and cache Excel file"""
    try:
        # Use openpyxl for Excel files with formulas/complex structure
        df = pd.read_excel(filename, engine='openpyxl')
        df.columns = df.columns.str.strip()
        logger.info(f"Loaded {len(df)} rows from {filename}")
        
        if column and column in df.columns:
            # Return list of values if only one column is requested
            return df[column].astype(str).str.strip().tolist()
        return df
    except FileNotFoundError:
        logger.warning(f"{filename} not found")
        st.warning(f"{filename} not found – related functionality disabled.")
        return [] if column else pd.DataFrame()
    except Exception as e:
        logger.error(f"Error reading {filename}: {e}", exc_info=True)
        st.error(f"Error reading {filename}: {e}")
        return [] if column else pd.DataFrame()

@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    """
    Load flags.xlsx for reason/comment mapping.
    Returns: Dictionary mapping flag names to (reason_code, comment) tuples
    """
    try:
        # NOTE: Ideally this loads from flags.xlsx dynamically. 
        # Here we manually define the mapping to ensure the new flag works immediately.
        flag_mapping = {
            'Sensitive words': (
                '1000001 - Brand NOT Allowed',
                "Your listing was rejected because it includes brands that are not allowed on Jumia, such as Chanel, Rolex, and My Salat Mat. These brands are banned from being sold on our platform."
            ),
            'BRAND name repeated in NAME': (
                '1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name',
                "Please do not write the brand name in the Product Name field. The brand name should only be written in the Brand field.\nIf you include it in both fields, it will show up twice in the product title on the website"
            ),
            'Missing COLOR': (
                '1000005 - Kindly confirm the actual product colour',
                "Please make sure that the product color is clearly mentioned in both the title and in the color tab.\nAlso, the images you upload must match the exact color being sold in this specific listing.\nAvoid including pictures of other colors, as this may confuse customers and lead to order cancellations."
            ),
            'Duplicate product': (
                '1000007 - Other Reason',
                "kindly note product was rejected because its a duplicate product"
            ),
            'Prohibited products': (
                '1000007 - Other Reason',
                "Kindly note this product is not allowed for listing on Jumia. Your product listing has been rejected due to the absence of a required license for this item. As a result, the product cannot be authorized for sale on Jumia.\nPlease ensure that you obtain and submit the necessary license(s) before attempting to relist the product. For further assistance or clarification, Please raise a claim via Vendor Center."
            ),
            'Single-word NAME': (
                '1000008 - Kindly Improve Product Name Description',
                "Kindly update the product title using this format: Name – Type of the Products – Color.\nIf available, please also add key details such as weight, capacity, type, and warranty to make the title clear and complete for customers."
            ),
            'Generic BRAND Issues': (
                '1000014 - Kindly request for the creation of this product\'s actual brand name by filling this form: https://bit.ly/2kpjja8',
                "To create the actual brand name for this product, please fill out the form at: https://bit.ly/2kpjja8.\nYou will receive an email within the coming 48 working hours the result of your request — whether it's approved or rejected, along with the reason.\n\nFor Fashion items, please use 'Fashion' as brand."
            ),
            'Counterfeit Sneakers': (
                '1000023 - Confirmation of counterfeit product by Jumia technical team (Not Authorized)',
                "Your listing has been rejected as Jumia's technical team has confirmed the product is counterfeit.\nAs a result, this item cannot be sold on the platform.\n\nPlease ensure that all products listed are 100% authentic to comply with Jumia's policies and protect customer trust.\n\nIf you believe this decision is incorrect or need further clarification, please contact the Seller Support team"
            ),
            'Seller Approve to sell books': (
                '1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim',
                "Please contact Jumia Seller Support and raise a claim to confirm whether this product is eligible for listing.\nThis step will help ensure that all necessary requirements and approvals are addressed before proceeding with the sale, and prevent any future compliance issues."
            ),
            'Seller Approved to Sell Perfume': (
                '1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim',
                "Please contact Jumia Seller Support and raise a claim to confirm whether this product is eligible for listing.\nThis step will help ensure that all necessary requirements and approvals are addressed before proceeding with the sale, and prevent any future compliance issues."
            ),
            'Perfume Price Check': (
                '1000029 - Kindly Contact Jumia Seller Support To Verify This Product\'s Authenticity By Raising A Claim',
                "Please contact Jumia Seller Support to raise a claim and begin the process of verifying the authenticity of this product.\nConfirming the product's authenticity is mandatory for listing approval and helps maintain customer trust and platform standards.\n\nNote: Price is $30+ below reference price."
            ),
            # NEW FLAG MAPPING
            'Suspected counterfeit Jerseys': (
                '1000030 - Suspected Counterfeit Product',
                "Your listing has been rejected as it is suspected to be a counterfeit jersey based on name and brand. Products must be 100% authentic. Please contact Seller Support if you believe this is an error."
            ),
        }
        
        logger.info(f"Loaded {len(flag_mapping)} flag mappings")
        return flag_mapping
    
    except Exception as e:
        logger.error(f"Error loading flags mapping: {e}", exc_info=True)
        return {}

@st.cache_data(ttl=3600)
def load_all_support_files() -> Dict:
    """Load all support files with caching"""
    logger.info("Loading all support files...")
    
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
        # LOAD NEW JERSEYS FILE
        'jerseys_config': load_excel_file('Jerseys.xlsx'),
    }
    
    logger.info("All support files loaded successfully")
    return files

@st.cache_data(ttl=3600)
def compile_regex_patterns(words: List[str]) -> re.Pattern:
    """Pre-compile regex patterns"""
    if not words:
        return None
    pattern = '|'.join(r'\b' + re.escape(w) + r'\b' for w in words)
    return re.compile(pattern, re.IGNORECASE)

# -------------------------------------------------
# Country-Specific Configuration
# -------------------------------------------------
class CountryValidator:
    """Handles country-specific validation logic"""
    
    COUNTRY_CONFIG = {
        "Kenya": {
            "code": "KE",
            "skip_validations": [],
            "prohibited_products_file": "prohibited_productsKE.txt"
        },
        "Uganda": {
            "code": "UG",
            "skip_validations": [
                "Seller Approve to sell books",
                "Perfume Price Check",
                "Seller Approved to Sell Perfume",
                "Counterfeit Sneakers"
            ],
            "prohibited_products_file": "prohibited_productsUG.txt"
        }
    }
    
    def __init__(self, country: str):
        self.country = country
        self.config = self.COUNTRY_CONFIG.get(country, self.COUNTRY_CONFIG["Kenya"])
        self.code = self.config["code"]
        self.skip_validations = self.config["skip_validations"]
        
    def should_skip_validation(self, validation_name: str) -> bool:
        """Check if validation should be skipped for this country"""
        return validation_name in self.skip_validations
    
    def ensure_status_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure Status column exists"""
        if df.empty:
            return df
        
        if 'Status' not in df.columns:
            df['Status'] = 'Approved'
        
        return df
    
    @st.cache_data(ttl=3600)
    def load_prohibited_products(_self) -> List[str]:
        """Load country-specific prohibited products"""
        filename = _self.config["prohibited_products_file"]
        return [w.lower() for w in load_txt_file(filename)]

# -------------------------------------------------
# Input Validation
# -------------------------------------------------
def validate_input_schema(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """Validate input DataFrame schema before processing"""
    errors = []
    required_fields = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'ACTIVE_STATUS_COUNTRY']
    
    for field in required_fields:
        if field not in df.columns:
            errors.append(f"Missing required column: {field}")
    
    if errors:
        return False, errors
    
    if df['PRODUCT_SET_SID'].isna().all():
        errors.append("PRODUCT_SET_SID column is entirely empty")
    
    if df['NAME'].isna().all():
        errors.append("NAME column is entirely empty")
    
    if len(df) == 0:
        errors.append("DataFrame is empty")
    
    return len(errors) == 0, errors

# -------------------------------------------------
# Country filter
# -------------------------------------------------
def filter_by_country(df: pd.DataFrame, country_validator: CountryValidator, source: str) -> pd.DataFrame:
    """Filter DataFrame by country code"""
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns:
        logger.warning(f"ACTIVE_STATUS_COUNTRY missing in {source}")
        st.warning(f"ACTIVE_STATUS_COUNTRY missing in {source}")
        return df
    
    df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.strip().str.upper()
    
    mask_valid = df['ACTIVE_STATUS_COUNTRY'].notna() & \
                 (df['ACTIVE_STATUS_COUNTRY'] != '') & \
                 (df['ACTIVE_STATUS_COUNTRY'] != 'NAN')
    
    mask_country = df['ACTIVE_STATUS_COUNTRY'].str.contains(
        rf'\b{country_validator.code}\b',
        na=False,
        regex=True
    )
    
    filtered = df[mask_valid & mask_country].copy()
    excluded = len(df[mask_valid]) - len(filtered)
    
    if excluded:
        st.info(f"Excluded {excluded} non-{country_validator.code} rows.")
    
    if filtered.empty:
        st.error(f"No {country_validator.code} rows left in {source}")
        st.stop()
    
    return filtered

# -------------------------------------------------
# VECTORIZED Validation checks
# -------------------------------------------------
def check_sensitive_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None:
        return pd.DataFrame(columns=data.columns)
    
    data = data.copy()
    data['NAME_LOWER'] = data['NAME'].astype(str).str.strip().str.lower()
    mask = data['NAME_LOWER'].str.contains(pattern, na=False)
    return data[mask].drop(columns=['NAME_LOWER'])

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None:
        return pd.DataFrame(columns=data.columns)
    
    data = data.copy()
    data['NAME_LOWER'] = data['NAME'].astype(str).str.strip().str.lower()
    mask = data['NAME_LOWER'].str.contains(pattern, na=False)
    return data[mask].drop(columns=['NAME_LOWER'])

def check_missing_color(data: pd.DataFrame, pattern: re.Pattern, color_categories: List[str]) -> pd.DataFrame:
    if not {'NAME', 'COLOR', 'CATEGORY_CODE'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    if pattern is None or not color_categories:
        return pd.DataFrame(columns=data.columns)
    
    data = data[data['CATEGORY_CODE'].isin(color_categories)].copy()
    if data.empty:
        return pd.DataFrame(columns=data.columns)
    
    data['NAME_LOWER'] = data['NAME'].astype(str).str.strip().str.lower()
    data['COLOR_LOWER'] = data['COLOR'].astype(str).str.strip().str.lower()
    
    name_has_color = data['NAME_LOWER'].str.contains(pattern, na=False)
    color_has_color = data['COLOR_LOWER'].str.contains(pattern, na=False)
    
    mask = ~(name_has_color | color_has_color)
    return data[mask].drop(columns=['NAME_LOWER', 'COLOR_LOWER'])

def check_brand_in_name(data: pd.DataFrame) -> pd.DataFrame:
    if not {'BRAND','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    
    data = data.copy()
    data['BRAND_LOWER'] = data['BRAND'].astype(str).str.strip().str.lower()
    data['NAME_LOWER'] = data['NAME'].astype(str).str.strip().str.lower()
    
    mask = data.apply(lambda r: r['BRAND_LOWER'] in r['NAME_LOWER'] if r['BRAND_LOWER'] and r['NAME_LOWER'] else False, axis=1)
    return data[mask].drop(columns=['BRAND_LOWER', 'NAME_LOWER'])

def check_duplicate_products(data: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    if len(cols) < 4:
        return pd.DataFrame(columns=data.columns)
    return data[data.duplicated(subset=cols, keep=False)]

def check_seller_approved_for_books(data: pd.DataFrame, book_category_codes: List[str], approved_book_sellers: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if books.empty or not approved_book_sellers:
        return pd.DataFrame(columns=data.columns)
    
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)]

def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_category_codes: List[str], approved_perfume_sellers: List[str], sensitive_perfume_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME','BRAND','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    
    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perfume_data.empty or not approved_perfume_sellers:
        return pd.DataFrame(columns=data.columns)
    
    perfume_data['BRAND_LOWER'] = perfume_data['BRAND'].astype(str).str.strip().str.lower()
    perfume_data['NAME_LOWER'] = perfume_data['NAME'].astype(str).str.strip().str.lower()
    
    sensitive_mask = perfume_data['BRAND_LOWER'].isin(sensitive_perfume_brands)
    fake_brands = ['designers collection', 'smart collection', 'generic', 'ORIGINAL', 'original' 'designer', 'fashion']
    fake_brand_mask = perfume_data['BRAND_LOWER'].isin(fake_brands)
    
    name_contains_sensitive = perfume_data['NAME_LOWER'].apply(
        lambda x: any(brand in x for brand in sensitive_perfume_brands)
    )
    fake_name_mask = fake_brand_mask & name_contains_sensitive
    
    final_mask = (sensitive_mask | fake_name_mask) & (~perfume_data['SELLER_NAME'].isin(approved_perfume_sellers))
    return perfume_data[final_mask].drop(columns=['BRAND_LOWER', 'NAME_LOWER'])

def check_counterfeit_sneakers(data: pd.DataFrame, sneaker_category_codes: List[str], sneaker_sensitive_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'NAME', 'BRAND'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    
    sneaker_data = data[data['CATEGORY_CODE'].isin(sneaker_category_codes)].copy()
    if sneaker_data.empty or not sneaker_sensitive_brands:
        return pd.DataFrame(columns=data.columns)
    
    sneaker_data['NAME_LOWER'] = sneaker_data['NAME'].astype(str).str.strip().str.lower()
    sneaker_data['BRAND_LOWER'] = sneaker_data['BRAND'].astype(str).str.strip().str.lower()
    
    fake_brand_mask = sneaker_data['BRAND_LOWER'].isin(['generic', 'fashion'])
    name_contains_brand = sneaker_data['NAME_LOWER'].apply(
        lambda x: any(brand in x for brand in sneaker_sensitive_brands)
    )
    
    final_mask = fake_brand_mask & name_contains_brand
    return sneaker_data[final_mask].drop(columns=['NAME_LOWER', 'BRAND_LOWER'])

# -------------------------------------------------
# NEW CHECK: SUSPECTED COUNTERFEIT JERSEYS
# -------------------------------------------------
def check_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    """
    Checks for suspected counterfeit jerseys.
    Includes FIX for float vs string category code matching.
    """
    req_cols = ['CATEGORY_CODE', 'NAME', 'SELLER_NAME']
    if not all(c in data.columns for c in req_cols) or jerseys_df.empty:
        return pd.DataFrame(columns=data.columns)

    jerseys_df = jerseys_df.copy()
    config_cols = ['Categories', 'Checklist', 'Exempted']
    if not all(c in jerseys_df.columns for c in config_cols):
        logger.error(f"Jerseys.xlsx missing columns: {config_cols}")
        return pd.DataFrame(columns=data.columns)

    # --- FIX: HANDLE FLOAT CATEGORIES (Remove .0) ---
    jersey_category_codes = (
        jerseys_df['Categories']
        .astype(str)
        .str.replace(r'\.0$', '', regex=True)  # Remove .0 suffix
        .str.strip()
        .unique()
        .tolist()
    )
    jersey_category_codes = [c for c in jersey_category_codes if c.lower() != 'nan']

    # --- HANDLE KEYWORDS ---
    checklist_keywords = (
        jerseys_df['Checklist']
        .astype(str)
        .str.strip()
        .str.lower()
        .unique()
        .tolist()
    )
    checklist_keywords = [w for w in checklist_keywords if w and w.lower() != 'nan']

    # --- HANDLE EXEMPTED SELLERS ---
    exempted_sellers = (
        jerseys_df['Exempted']
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )
    exempted_sellers = [s for s in exempted_sellers if s and s.lower() != 'nan']

    if not jersey_category_codes or not checklist_keywords:
        return pd.DataFrame(columns=data.columns)
        
    keyword_pattern = '|'.join(r'\b' + re.escape(w) + r'\b' for w in checklist_keywords)
    keyword_regex = re.compile(keyword_pattern, re.IGNORECASE)

    # 1. Filter data by category (Ensure data Category Code is clean string)
    data['CATEGORY_CODE_STR'] = data['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
    jersey_products = data[data['CATEGORY_CODE_STR'].isin(jersey_category_codes)].copy()
    
    if jersey_products.empty:
        return pd.DataFrame(columns=data.columns)

    # 2. Exclude exempted sellers
    non_exempted_jerseys = jersey_products[~jersey_products['SELLER_NAME'].isin(exempted_sellers)].copy()
    if non_exempted_jerseys.empty:
        return pd.DataFrame(columns=data.columns)

    # 3. Check keywords
    non_exempted_jerseys['NAME_LOWER'] = non_exempted_jerseys['NAME'].astype(str).str.strip().str.lower()
    name_contains_keyword = non_exempted_jerseys['NAME_LOWER'].str.contains(keyword_regex, na=False)
    
    flagged_products = non_exempted_jerseys[name_contains_keyword]

    # Clean up temp columns
    cols_to_drop = ['NAME_LOWER', 'CATEGORY_CODE_STR']
    return flagged_products.drop(columns=[c for c in cols_to_drop if c in flagged_products.columns])

# -------------------------------------------------
# CONTINUED CHECKS
# -------------------------------------------------

def check_perfume_price_vectorized(data: pd.DataFrame, perfumes_df: pd.DataFrame, perfume_category_codes: List[str]) -> pd.DataFrame:
    req = ['CATEGORY_CODE','NAME','BRAND','GLOBAL_SALE_PRICE','GLOBAL_PRICE']
    if not all(c in data.columns for c in req) or perfumes_df.empty or not perfume_category_codes:
        return pd.DataFrame(columns=data.columns)
    
    perf = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perf.empty:
        return pd.DataFrame(columns=data.columns)
    
    perf['price_to_use'] = perf['GLOBAL_SALE_PRICE'].where(
        (perf['GLOBAL_SALE_PRICE'].notna()) & (perf['GLOBAL_SALE_PRICE'] > 0),
        perf['GLOBAL_PRICE']
    )
    
    currency = perf.get('CURRENCY', pd.Series(['KES'] * len(perf)))
    perf['price_usd'] = perf['price_to_use'].where(
        currency.astype(str).str.upper() != 'KES',
        perf['price_to_use'] / FX_RATE
    )
    
    perf['BRAND_LOWER'] = perf['BRAND'].astype(str).str.strip().str.lower()
    perf['NAME_LOWER'] = perf['NAME'].astype(str).str.strip().str.lower()
    
    perfumes_df = perfumes_df.copy()
    perfumes_df['BRAND_LOWER'] = perfumes_df['BRAND'].astype(str).str.strip().str.lower()
    if 'PRODUCT_NAME' in perfumes_df.columns:
        perfumes_df['PRODUCT_NAME_LOWER'] = perfumes_df['PRODUCT_NAME'].astype(str).str.strip().str.lower()
    
    merged = perf.merge(perfumes_df, on='BRAND_LOWER', how='left', suffixes=('', '_ref'))
    
    if 'PRODUCT_NAME_LOWER' in merged.columns:
        merged['name_match'] = merged.apply(
            lambda r: r['PRODUCT_NAME_LOWER'] in r['NAME_LOWER'] if pd.notna(r['PRODUCT_NAME_LOWER']) else False,
            axis=1
        )
        merged = merged[merged['name_match']]
    
    if 'PRICE_USD' in merged.columns:
        merged['price_deviation'] = merged['PRICE_USD'] - merged['price_usd']
        flagged = merged[merged['price_deviation'] >= 30]
        return flagged[data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])
    
    return pd.DataFrame(columns=data.columns)

def check_single_word_name(data: pd.DataFrame, book_category_codes: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1]

def check_generic_brand_issues(data: pd.DataFrame, valid_category_codes_fas: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    return data[data['CATEGORY_CODE'].isin(valid_category_codes_fas) & (data['BRAND']=='Generic')]

# -------------------------------------------------
# Master validation runner
# -------------------------------------------------
def validate_products(
    data: pd.DataFrame,
    support_files: Dict,
    country_validator: CountryValidator
) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """Master validation function"""
    
    flags_mapping = support_files['flags_mapping']
    if not flags_mapping:
        st.error("Cannot proceed without flags mapping")
        return pd.DataFrame(), {}
    
    sensitive_pattern = compile_regex_patterns(support_files['sensitive_words'])
    prohibited_pattern = compile_regex_patterns(country_validator.load_prohibited_products())
    color_pattern = compile_regex_patterns(support_files['colors'])
    
    validations = [
        ("Sensitive words", check_sensitive_words, {'pattern': sensitive_pattern}),
        ("Seller Approve to sell books", check_seller_approved_for_books,
         {'book_category_codes': support_files['book_category_codes'],
          'approved_book_sellers': support_files['approved_book_sellers']}),
        ("Perfume Price Check", check_perfume_price_vectorized,
         {'perfumes_df': support_files['perfumes'],
          'perfume_category_codes': support_files['perfume_category_codes']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume,
         {'perfume_category_codes': support_files['perfume_category_codes'],
          'approved_perfume_sellers': support_files['approved_perfume_sellers'],
          'sensitive_perfume_brands': support_files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers,
         {'sneaker_category_codes': support_files['sneaker_category_codes'],
          'sneaker_sensitive_brands': support_files['sneaker_sensitive_brands']}),
        # --- NEW JERSEY CHECK ---
        ("Suspected counterfeit Jerseys", check_counterfeit_jerseys,
         {'jerseys_df': support_files['jerseys_config']}),
         
        ("Prohibited products", check_prohibited_products, {'pattern': prohibited_pattern}),
        ("Single-word NAME", check_single_word_name,
         {'book_category_codes': support_files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color,
         {'pattern': color_pattern, 'color_categories': support_files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
    ]
    
    validations = [v for v in validations if not country_validator.should_skip_validation(v[0])]
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    validation_results_dfs = {}
    
    for i, (flag_name, check_func, func_kwargs) in enumerate(validations):
        status_text.text(f"Running validation {i+1}/{len(validations)}: {flag_name}")
        
        current_kwargs = {'data': data}
        
        if flag_name == "Generic BRAND Issues":
            fas_df = support_files.get('category_fas', pd.DataFrame())
            current_kwargs['valid_category_codes_fas'] = (
                fas_df['ID'].astype(str).tolist() if not fas_df.empty and 'ID' in fas_df.columns else []
            )
        else:
            current_kwargs.update(func_kwargs)
        
        try:
            result_df = check_func(**current_kwargs)
            
            if not result_df.empty and 'PRODUCT_SET_SID' not in result_df.columns:
                validation_results_dfs[flag_name] = pd.DataFrame(columns=data.columns)
            else:
                validation_results_dfs[flag_name] = result_df
                logger.info(f"Validation '{flag_name}': {len(result_df)} flagged")
        
        except Exception as e:
            logger.error(f"Error during validation '{flag_name}': {e}", exc_info=True)
            validation_results_dfs[flag_name] = pd.DataFrame(columns=data.columns)
        
        progress_bar.progress((i + 1) / len(validations))
    
    status_text.text("Building final report...")
    
    final_report_rows = []
    processed_sids = set()
    
    for flag_name, _, _ in validations:
        validation_df = validation_results_dfs.get(flag_name, pd.DataFrame())
        if validation_df.empty or 'PRODUCT_SET_SID' not in validation_df.columns:
            continue
        
        if flag_name in flags_mapping:
            rejection_reason, comment = flags_mapping[flag_name]
        else:
            rejection_reason = "1000007 - Other Reason"
            comment = f"Product flagged by validation: {flag_name}"
        
        flagged_sids_df = pd.merge(
            validation_df[['PRODUCT_SET_SID']].drop_duplicates(),
            data,
            on='PRODUCT_SET_SID',
            how='left'
        )
        
        for _, row in flagged_sids_df.iterrows():
            sid = row.get('PRODUCT_SET_SID')
            if sid in processed_sids:
                continue
            processed_sids.add(sid)
            
            final_report_rows.append({
                'ProductSetSid': sid,
                'ParentSKU': row.get('PARENTSKU', ''),
                'Status': 'Rejected',
                'Reason': rejection_reason,
                'Comment': comment,
                'FLAG': flag_name,
                'SellerName': row.get('SELLER_NAME', '')
            })
    
    all_sids = set(data['PRODUCT_SET_SID'].astype(str).unique())
    approved_sids = all_sids - processed_sids
    approved_data = data[data['PRODUCT_SET_SID'].isin(approved_sids)]
    
    for _, row in approved_data.iterrows():
        final_report_rows.append({
            'ProductSetSid': row.get('PRODUCT_SET_SID'),
            'ParentSKU': row.get('PARENTSKU', ''),
            'Status': 'Approved',
            'Reason': "",
            'Comment': "",
            'FLAG': "",
            'SellerName': row.get('SELLER_NAME', '')
        })
    
    final_report_df = pd.DataFrame(final_report_rows)
    final_report_df = country_validator.ensure_status_column(final_report_df)
    
    progress_bar.empty()
    status_text.empty()
    
    return final_report_df, validation_results_dfs

# -------------------------------------------------
# Export functions
# -------------------------------------------------
def to_excel_base(df_to_export: pd.DataFrame, sheet_name: str, columns_to_include: List[str], writer) -> None:
    df_prepared = df_to_export.copy()
    for col in columns_to_include:
        if col not in df_prepared.columns:
            df_prepared[col] = pd.NA
    df_prepared[[c for c in columns_to_include if c in df_prepared.columns]].to_excel(writer, index=False, sheet_name=sheet_name)

def to_excel_full_data(data_df: pd.DataFrame, final_report_df: pd.DataFrame) -> BytesIO:
    try:
        output = BytesIO()
        data_df_copy = data_df.copy()
        final_report_df_copy = final_report_df.copy()
        
        data_df_copy['PRODUCT_SET_SID'] = data_df_copy['PRODUCT_SET_SID'].astype(str).str.strip()
        final_report_df_copy['ProductSetSid'] = final_report_df_copy['ProductSetSid'].astype(str).str.strip()
        
        merged_df = pd.merge(
            data_df_copy,
            final_report_df_copy[["ProductSetSid", "Status", "Reason", "Comment", "FLAG", "SellerName"]],
            left_on="PRODUCT_SET_SID",
            right_on="ProductSetSid",
            how='left'
        )
        
        if 'ProductSetSid_y' in merged_df.columns:
            merged_df.drop(columns=['ProductSetSid_y'], inplace=True)
        if 'ProductSetSid_x' in merged_df.columns:
            merged_df.rename(columns={'ProductSetSid_x': 'PRODUCT_SET_SID'}, inplace=True)
        
        export_cols = FULL_DATA_COLS + [c for c in ["Status", "Reason", "Comment", "FLAG", "SellerName"] if c not in FULL_DATA_COLS]
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            to_excel_base(merged_df, "ProductSets", export_cols, writer)
            
            # --- SELLERS DATA SHEET ---
            workbook = writer.book
            worksheet = workbook.add_worksheet('Sellers Data')
            header_fmt = workbook.add_format({'bold': True, 'bg_color': '#E6F0FA', 'border': 1, 'align': 'center'})
            red_fill = workbook.add_format({'bg_color': '#FFC7CE', 'border': 1})
            
            sellers_data_rows = []
            
            if 'SELLER_RATING' in merged_df.columns:
                merged_df['Rejected_Count'] = (merged_df['Status'] == 'Rejected').astype(int)
                merged_df['Approved_Count'] = (merged_df['Status'] == 'Approved').astype(int)
                
                seller_summary = merged_df.groupby('SELLER_NAME').agg(
                    Rejected=('Rejected_Count', 'sum'),
                    Approved=('Approved_Count', 'sum'),
                    AvgRating=('SELLER_RATING', 'mean'),
                    TotalStock=('STOCK_QTY', 'sum')
                ).reset_index()
                
                total = seller_summary['Rejected'] + seller_summary['Approved']
                seller_summary['Rejection %'] = (seller_summary['Rejected'] / total.where(total > 0, 1) * 100).round(1)
                seller_summary = seller_summary.sort_values('Rejected', ascending=False)
                seller_summary.insert(0, 'Rank', range(1, len(seller_summary) + 1))
                
                sellers_data_rows.append(pd.DataFrame([['Sellers Summary', '', '', '', '', '']]))
                sellers_data_rows.append(seller_summary)

            start_row = 0
            for df in sellers_data_rows:
                if df.empty: continue
                # Write header
                if 'Rank' not in df.columns:
                     worksheet.write(start_row, 0, df.iloc[0,0], header_fmt)
                     start_row += 1
                     continue

                for col_num, col_name in enumerate(df.columns):
                    worksheet.write(start_row, col_num, col_name, header_fmt)
                
                for row_num, row_data in enumerate(df.values, start=start_row + 1):
                    for col_num, value in enumerate(row_data):
                        fmt = None
                        if 'Rejection %' in df.columns and col_num == list(df.columns).index('Rejection %') and value > 30:
                            fmt = red_fill
                        worksheet.write(row_num, col_num, value if pd.notna(value) else '', fmt)
                start_row += len(df) + 2
                
        output.seek(0)
        return output
    except Exception as e:
        logger.error(f"Error generating full export: {e}")
        return BytesIO()

def to_excel_flag_data(flag_df: pd.DataFrame, flag_name: str) -> BytesIO:
    output = BytesIO()
    df_copy = flag_df.copy()
    df_copy['FLAG'] = flag_name
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(df_copy, "ProductSets", FULL_DATA_COLS, writer)
    output.seek(0)
    return output

def to_excel(report_df: pd.DataFrame, reasons_config_df: pd.DataFrame) -> BytesIO:
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(report_df, "ProductSets", PRODUCTSETS_COLS, writer)
        if not reasons_config_df.empty:
            to_excel_base(reasons_config_df, "RejectionReasons", REJECTION_REASONS_COLS, writer)
    output.seek(0)
    return output

# -------------------------------------------------
# Audit Logging
# -------------------------------------------------
def log_validation_run(country: str, file_name: str, total_rows: int, approved: int, rejected: int):
    audit_entry = {
        'timestamp': datetime.now().isoformat(),
        'country': country,
        'file': file_name,
        'total_rows': total_rows,
        'approved': approved,
        'rejected': rejected,
        'rejection_rate': round((rejected / total_rows * 100) if total_rows > 0 else 0, 2)
    }
    try:
        with open('validation_audit.jsonl', 'a') as f:
            f.write(json.dumps(audit_entry) + '\n')
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")

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

with tab1:
    st.header("Daily Product Validation")
    country = st.selectbox("Select Country", ["Kenya", "Uganda"], key="daily_country")
    country_validator = CountryValidator(country)
    uploaded_file = st.file_uploader("Upload your CSV file", type='csv', key="daily_file")
    
    if uploaded_file:
        try:
            dtype_spec = {'CATEGORY_CODE': str, 'PRODUCT_SET_SID': str, 'PARENTSKU': str}
            try:
                raw_data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype=dtype_spec)
            except:
                uploaded_file.seek(0)
                raw_data = pd.read_csv(uploaded_file, sep=',', encoding='ISO-8859-1', dtype=dtype_spec)
                
            st.success(f"Loaded CSV with {len(raw_data)} rows")
            is_valid, errors = validate_input_schema(raw_data)
            
            if is_valid:
                data = filter_by_country(raw_data, country_validator, "Daily CSV")
                
                # Fill missing cols for processing
                for col in ['NAME', 'BRAND', 'COLOR', 'SELLER_NAME', 'CATEGORY_CODE']:
                    if col in data.columns: data[col] = data[col].astype(str).fillna('')
                
                with st.spinner("Running validations..."):
                    final_report, flag_dfs = validate_products(data, support_files, country_validator)
                
                approved_df = final_report[final_report['Status'] == 'Approved']
                rejected_df = final_report[final_report['Status'] == 'Rejected']
                
                log_validation_run(country, uploaded_file.name, len(data), len(approved_df), len(rejected_df))
                
                # METRICS
                col1, col2, col3 = st.columns(3)
                col1.metric("Total", len(data))
                col2.metric("Approved", len(approved_df))
                col3.metric("Rejected", len(rejected_df))
                
                # EXPORTS
                st.download_button("Final Report", to_excel(final_report, support_files['reasons']), f"Final_Report_{datetime.now().strftime('%Y%m%d')}.xlsx")
                st.download_button("Full Data", to_excel_full_data(data, final_report), f"Full_Data_{datetime.now().strftime('%Y%m%d')}.xlsx")
                
                # FLAG DETAILS
                st.subheader("Results by Flag")
                for title, df_flagged in flag_dfs.items():
                    with st.expander(f"{title} ({len(df_flagged)})"):
                        if not df_flagged.empty:
                            st.dataframe(df_flagged)
                            st.download_button(f"Export {title}", to_excel_flag_data(df_flagged, title), f"{title}.xlsx")
            else:
                for e in errors: st.error(e)
                
        except Exception as e:
            st.error(f"Error: {e}")
            st.code(traceback.format_exc())

with tab3:
    st.header("Data Lake")
    file = st.file_uploader("Upload audit file", type=['jsonl','csv','xlsx'])
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
