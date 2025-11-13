import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import logging
from typing import Dict, List, Tuple, Optional
import traceback

# Import Data Lake module
try:
    import data_lake
    DATA_LAKE_AVAILABLE = True
except ImportError:
    DATA_LAKE_AVAILABLE = False
    st.warning("⚠️ data_lake.py not found - Data Lake tab will show placeholder")

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
# CACHED FILE LOADING (CRITICAL FIX #1)
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
        st.warning(f"⚠️ {filename} not found – related check disabled.")
        return []
    except Exception as e:
        logger.error(f"Error reading {filename}: {e}", exc_info=True)
        st.error(f"❌ Error reading {filename}: {e}")
        return []

@st.cache_data(ttl=3600)
def load_excel_file(filename: str, column: Optional[str] = None) -> pd.DataFrame:
    """Load and cache Excel file"""
    try:
        df = pd.read_excel(filename)
        df.columns = df.columns.str.strip()
        logger.info(f"Loaded {len(df)} rows from {filename}")
        
        if column and column in df.columns:
            return df[column].astype(str).str.strip().tolist()
        return df
    except FileNotFoundError:
        logger.warning(f"{filename} not found")
        st.warning(f"⚠️ {filename} not found – related functionality disabled.")
        return [] if column else pd.DataFrame()
    except Exception as e:
        logger.error(f"Error reading {filename}: {e}", exc_info=True)
        st.error(f"❌ Error reading {filename}: {e}")
        return [] if column else pd.DataFrame()

@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    """
    Load flags.xlsx for reason/comment mapping (CRITICAL FIX #2)
    Expected columns: rejection_reason_code, Comment
    Returns: Dictionary mapping flag names to (reason_code, comment) tuples
    """
    try:
        flags_df = pd.read_excel('flags.xlsx')
        flags_df.columns = flags_df.columns.str.strip()
        
        required_cols = ['rejection_reason_code', 'Comment']
        missing = [col for col in required_cols if col not in flags_df.columns]
        
        if missing:
            logger.error(f"flags.xlsx missing columns: {missing}")
            st.error(f"❌ flags.xlsx missing required columns: {missing}. Expected: {required_cols}")
            return {}
        
        # Manual mapping based on your actual flags.xlsx content
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
        }
        
        logger.info(f"Loaded {len(flag_mapping)} flag mappings")
        st.success(f"✅ Loaded {len(flag_mapping)} validation flag mappings")
        
        return flag_mapping
    
    except FileNotFoundError:
        logger.error("flags.xlsx not found")
        st.error("❌ flags.xlsx not found. This file is required for validation.")
        return {}
    except Exception as e:
        logger.error(f"Error loading flags.xlsx: {e}", exc_info=True)
        st.error(f"❌ Error loading flags.xlsx: {e}")
        return {}

@st.cache_data(ttl=3600)
def load_all_support_files() -> Dict:
    """Load all support files with caching (CRITICAL FIX #1)"""
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
        'flags_mapping': load_flags_mapping(),  # Returns dict now
    }
    
    logger.info("All support files loaded successfully")
    return files

@st.cache_data(ttl=3600)
def compile_regex_patterns(words: List[str]) -> re.Pattern:
    """Pre-compile regex patterns (CRITICAL FIX #1)"""
    if not words:
        return None
    pattern = '|'.join(r'\b' + re.escape(w) + r'\b' for w in words)
    return re.compile(pattern, re.IGNORECASE)

# -------------------------------------------------
# Country-Specific Configuration (CRITICAL FIX #3)
# -------------------------------------------------
class CountryValidator:
    """Handles country-specific validation logic (CRITICAL FIX #3)"""
    
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
        """Ensure Status column exists (CRITICAL FIX #3 - replaces Uganda safety nets)"""
        if df.empty:
            return df
        
        if 'Status' not in df.columns:
            df['Status'] = 'Approved'
            logger.info(f"Added default 'Status' column for {self.country}")
        
        return df
    
    @st.cache_data(ttl=3600)
    def load_prohibited_products(_self) -> List[str]:
        """Load country-specific prohibited products"""
        filename = _self.config["prohibited_products_file"]
        return [w.lower() for w in load_txt_file(filename)]

# -------------------------------------------------
# Input Validation (CRITICAL FIX #4)
# -------------------------------------------------
def validate_input_schema(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """Validate input DataFrame schema before processing"""
    errors = []
    required_fields = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'ACTIVE_STATUS_COUNTRY']
    
    # Check required columns
    for field in required_fields:
        if field not in df.columns:
            errors.append(f"Missing required column: {field}")
    
    if errors:
        return False, errors
    
    # Check data types
    if df['PRODUCT_SET_SID'].isna().all():
        errors.append("PRODUCT_SET_SID column is entirely empty")
    
    if df['NAME'].isna().all():
        errors.append("NAME column is entirely empty")
    
    # Check for minimum rows
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
        st.warning(f"⚠️ ACTIVE_STATUS_COUNTRY missing in {source}")
        return df
    
    df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.strip().str.upper()
    
    # Valid rows
    mask_valid = df['ACTIVE_STATUS_COUNTRY'].notna() & \
                 (df['ACTIVE_STATUS_COUNTRY'] != '') & \
                 (df['ACTIVE_STATUS_COUNTRY'] != 'NAN')
    
    # Country-specific rows
    mask_country = df['ACTIVE_STATUS_COUNTRY'].str.contains(
        rf'\b{country_validator.code}\b', 
        na=False, 
        regex=True
    )
    
    filtered = df[mask_valid & mask_country].copy()
    excluded = len(df[mask_valid]) - len(filtered)
    
    if excluded:
        others = ', '.join(sorted(df[mask_valid & ~mask_country]['ACTIVE_STATUS_COUNTRY'].unique())[:5])
        if len(df[mask_valid & ~mask_country]['ACTIVE_STATUS_COUNTRY'].unique()) > 5:
            others += f" (+{len(df[mask_valid & ~mask_country]['ACTIVE_STATUS_COUNTRY'].unique())-5} more)"
        logger.info(f"Excluded {excluded} non-{country_validator.code} rows from {source}")
        st.info(f"ℹ️ Excluded {excluded} non-{country_validator.code} rows: {others}")
    else:
        logger.info(f"All valid rows in {source} are {country_validator.code}")
        st.info(f"✅ All valid rows in {source} are {country_validator.code}")
    
    if filtered.empty:
        logger.error(f"No {country_validator.code} rows left in {source}")
        st.error(f"❌ No {country_validator.code} rows left in {source}")
        st.stop()
    
    return filtered

# -------------------------------------------------
# VECTORIZED Validation checks (CRITICAL FIX #1)
# -------------------------------------------------
def check_sensitive_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    """Check for sensitive words using pre-compiled pattern"""
    if not {'NAME'}.issubset(data.columns) or pattern is None:
        return pd.DataFrame(columns=data.columns)
    
    data = data.copy()
    data['NAME_LOWER'] = data['NAME'].astype(str).str.strip().str.lower()
    mask = data['NAME_LOWER'].str.contains(pattern, na=False)
    
    return data[mask].drop(columns=['NAME_LOWER'])

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    """Check for prohibited products using pre-compiled pattern"""
    if not {'NAME'}.issubset(data.columns) or pattern is None:
        return pd.DataFrame(columns=data.columns)
    
    data = data.copy()
    data['NAME_LOWER'] = data['NAME'].astype(str).str.strip().str.lower()
    mask = data['NAME_LOWER'].str.contains(pattern, na=False)
    
    return data[mask].drop(columns=['NAME_LOWER'])

def check_missing_color(data: pd.DataFrame, pattern: re.Pattern, color_categories: List[str]) -> pd.DataFrame:
    """SMART Missing COLOR Check using pre-compiled pattern"""
    if not {'NAME', 'COLOR', 'CATEGORY_CODE'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    if pattern is None or not color_categories:
        return pd.DataFrame(columns=data.columns)
    
    # Filter to only categories that require color
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
    """Vectorized brand in name check"""
    if not {'BRAND','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    
    data = data.copy()
    data['BRAND_LOWER'] = data['BRAND'].astype(str).str.strip().str.lower()
    data['NAME_LOWER'] = data['NAME'].astype(str).str.strip().str.lower()
    
    # Vectorized check
    mask = data.apply(lambda r: r['BRAND_LOWER'] in r['NAME_LOWER'] if r['BRAND_LOWER'] and r['NAME_LOWER'] else False, axis=1)
    
    return data[mask].drop(columns=['BRAND_LOWER', 'NAME_LOWER'])

def check_duplicate_products(data: pd.DataFrame) -> pd.DataFrame:
    """Check for duplicate products"""
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    if len(cols) < 4:
        return pd.DataFrame(columns=data.columns)
    return data[data.duplicated(subset=cols, keep=False)]

def check_seller_approved_for_books(data: pd.DataFrame, book_category_codes: List[str], 
                                   approved_book_sellers: List[str]) -> pd.DataFrame:
    """Check if seller is approved for books"""
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if books.empty or not approved_book_sellers:
        return pd.DataFrame(columns=data.columns)
    
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)]

def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_category_codes: List[str],
                                     approved_perfume_sellers: List[str],
                                     sensitive_perfume_brands: List[str]) -> pd.DataFrame:
    """Vectorized perfume seller check"""
    if not {'CATEGORY_CODE','SELLER_NAME','BRAND','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    
    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perfume_data.empty or not approved_perfume_sellers:
        return pd.DataFrame(columns=data.columns)
    
    perfume_data['BRAND_LOWER'] = perfume_data['BRAND'].astype(str).str.strip().str.lower()
    perfume_data['NAME_LOWER'] = perfume_data['NAME'].astype(str).str.strip().str.lower()
    
    sensitive_mask = perfume_data['BRAND_LOWER'].isin(sensitive_perfume_brands)
    
    fake_brands = ['designers collection', 'smart collection', 'generic', 'designer', 'fashion']
    fake_brand_mask = perfume_data['BRAND_LOWER'].isin(fake_brands)
    
    # Vectorized brand check in name
    name_contains_sensitive = perfume_data['NAME_LOWER'].apply(
        lambda x: any(brand in x for brand in sensitive_perfume_brands)
    )
    fake_name_mask = fake_brand_mask & name_contains_sensitive
    
    final_mask = (sensitive_mask | fake_name_mask) & (~perfume_data['SELLER_NAME'].isin(approved_perfume_sellers))
    
    return perfume_data[final_mask].drop(columns=['BRAND_LOWER', 'NAME_LOWER'])

def check_counterfeit_sneakers(data: pd.DataFrame, sneaker_category_codes: List[str],
                               sneaker_sensitive_brands: List[str]) -> pd.DataFrame:
    """Vectorized counterfeit sneakers check"""
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

def check_perfume_price_vectorized(data: pd.DataFrame, perfumes_df: pd.DataFrame,
                                   perfume_category_codes: List[str]) -> pd.DataFrame:
    """VECTORIZED perfume price check (CRITICAL FIX #1)"""
    req = ['CATEGORY_CODE','NAME','BRAND','GLOBAL_SALE_PRICE','GLOBAL_PRICE']
    if not all(c in data.columns for c in req) or perfumes_df.empty or not perfume_category_codes:
        return pd.DataFrame(columns=data.columns)
    
    perf = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perf.empty:
        return pd.DataFrame(columns=data.columns)
    
    # Vectorized price calculation
    perf['price_to_use'] = perf['GLOBAL_SALE_PRICE'].where(
        (perf['GLOBAL_SALE_PRICE'].notna()) & (perf['GLOBAL_SALE_PRICE'] > 0),
        perf['GLOBAL_PRICE']
    )
    
    # Convert to USD
    currency = perf.get('CURRENCY', pd.Series(['KES'] * len(perf)))
    perf['price_usd'] = perf['price_to_use'].where(
        currency.astype(str).str.upper() != 'KES',
        perf['price_to_use'] / FX_RATE
    )
    
    # Prepare for matching
    perf['BRAND_LOWER'] = perf['BRAND'].astype(str).str.strip().str.lower()
    perf['NAME_LOWER'] = perf['NAME'].astype(str).str.strip().str.lower()
    
    perfumes_df = perfumes_df.copy()
    perfumes_df['BRAND_LOWER'] = perfumes_df['BRAND'].astype(str).str.strip().str.lower()
    
    if 'PRODUCT_NAME' in perfumes_df.columns:
        perfumes_df['PRODUCT_NAME_LOWER'] = perfumes_df['PRODUCT_NAME'].astype(str).str.strip().str.lower()
    
    # Merge and filter
    merged = perf.merge(perfumes_df, on='BRAND_LOWER', how='left', suffixes=('', '_ref'))
    
    if 'PRODUCT_NAME_LOWER' in merged.columns:
        merged['name_match'] = merged.apply(
            lambda r: r['PRODUCT_NAME_LOWER'] in r['NAME_LOWER'] if pd.notna(r['PRODUCT_NAME_LOWER']) else False,
            axis=1
        )
        merged = merged[merged['name_match']]
    
    # Check price deviation
    if 'PRICE_USD' in merged.columns:
        merged['price_deviation'] = merged['PRICE_USD'] - merged['price_usd']
        flagged = merged[merged['price_deviation'] >= 30]
        
        # Return original columns
        return flagged[data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])
    
    return pd.DataFrame(columns=data.columns)

def check_single_word_name(data: pd.DataFrame, book_category_codes: List[str]) -> pd.DataFrame:
    """Check for single-word names (excluding books)"""
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1]

def check_generic_brand_issues(data: pd.DataFrame, valid_category_codes_fas: List[str]) -> pd.DataFrame:
    """Check generic brand issues"""
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    return data[data['CATEGORY_CODE'].isin(valid_category_codes_fas) & (data['BRAND']=='Generic')]

# -------------------------------------------------
# Master validation runner with FLAGS.XLSX mapping
# -------------------------------------------------
def validate_products(
    data: pd.DataFrame,
    support_files: Dict,
    country_validator: CountryValidator
) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """
    Master validation function with progress tracking
    Uses flags.xlsx for reason/comment mapping (CRITICAL FIX #2)
    """
    
    # Get flags mapping (now a dictionary)
    flags_mapping = support_files['flags_mapping']
    if not flags_mapping:
        st.error("❌ Cannot proceed without flags.xlsx mapping")
        return pd.DataFrame(), {}
    
    # Pre-compile regex patterns (CRITICAL FIX #1)
    sensitive_pattern = compile_regex_patterns(support_files['sensitive_words'])
    prohibited_pattern = compile_regex_patterns(country_validator.load_prohibited_products())
    color_pattern = compile_regex_patterns(support_files['colors'])
    
    # Define validations
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
        ("Prohibited products", check_prohibited_products, {'pattern': prohibited_pattern}),
        ("Single-word NAME", check_single_word_name,
         {'book_category_codes': support_files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color,
         {'pattern': color_pattern, 'color_categories': support_files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
    ]
    
    # Filter validations by country (CRITICAL FIX #3)
    validations = [v for v in validations if not country_validator.should_skip_validation(v[0])]
    
    # Progress bar
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
                logger.warning(f"Check '{flag_name}' missing PRODUCT_SET_SID")
                st.warning(f"⚠️ Check '{flag_name}' did not return 'PRODUCT_SET_SID'")
                validation_results_dfs[flag_name] = pd.DataFrame(columns=data.columns)
            else:
                validation_results_dfs[flag_name] = result_df
                logger.info(f"Validation '{flag_name}': {len(result_df)} flagged")
        
        except Exception as e:
            logger.error(f"Error during validation '{flag_name}': {e}", exc_info=True)
            st.error(f"❌ Error during '{flag_name}': {e}")
            with st.expander("Technical Details"):
                st.code(traceback.format_exc())
            validation_results_dfs[flag_name] = pd.DataFrame(columns=data.columns)
        
        progress_bar.progress((i + 1) / len(validations))
    
    status_text.text("Building final report...")
    
    # Build report using flags.xlsx mapping (CRITICAL FIX #2)
    final_report_rows = []
    processed_sids = set()
    
    for flag_name, _, _ in validations:
        validation_df = validation_results_dfs.get(flag_name, pd.DataFrame())
        if validation_df.empty or 'PRODUCT_SET_SID' not in validation_df.columns:
            continue
        
        # Get reason and comment from flags.xlsx mapping (dictionary lookup)
        if flag_name in flags_mapping:
            rejection_reason, comment = flags_mapping[flag_name]
        else:
            logger.warning(f"No mapping found in flags.xlsx for '{flag_name}'")
            st.warning(f"⚠️ No mapping found in flags.xlsx for '{flag_name}' - using defaults")
            rejection_reason = "1000007 - Other Reason"
            comment = f"Product flagged by validation: {flag_name}"
        
        flagged_sids_df = pd.merge(
            validation_df[['PRODUCT_SET_SID']],
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
    
    # Add approved products
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
    
    # Ensure Status column (CRITICAL FIX #3)
    final_report_df = country_validator.ensure_status_column(final_report_df)
    
    progress_bar.empty()
    status_text.empty()
    
    logger.info(f"Validation complete: {len(approved_sids)} approved, {len(processed_sids)} rejected")
    
    return final_report_df, validation_results_dfs

# -------------------------------------------------
# Export functions
# -------------------------------------------------
def to_excel_base(df_to_export: pd.DataFrame, sheet_name: str, 
                  columns_to_include: List[str], writer) -> None:
    """Base Excel export function"""
    df_prepared = df_to_export.copy()
    for col in columns_to_include:
        if col not in df_prepared.columns:
            df_prepared[col] = pd.NA
    df_prepared[columns_to_include].to_excel(writer, index=False, sheet_name=sheet_name)

def to_excel_full_data(data_df: pd.DataFrame, final_report_df: pd.DataFrame) -> BytesIO:
    """Generate full data export with summary sheets"""
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
        
        if merged_df.empty:
            logger.error("Merged DataFrame is empty in to_excel_full_data")
            st.error("❌ Merged DataFrame is empty. Verify PRODUCT_SET_SID values match.")
            return output
        
        if 'ProductSetSid_y' in merged_df.columns:
            merged_df.drop(columns=['ProductSetSid_y'], inplace=True)
        if 'ProductSetSid_x' in merged_df.columns:
            merged_df.rename(columns={'ProductSetSid_x': 'PRODUCT_SET_SID'}, inplace=True)
        if 'FLAG' in merged_df.columns:
            merged_df['FLAG'] = merged_df['FLAG'].fillna('')
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            to_excel_base(merged_df, "ProductSets", FULL_DATA_COLS, writer)
            
            workbook = writer.book
            worksheet = workbook.add_worksheet('Sellers Data')
            header_fmt = workbook.add_format({'bold': True, 'bg_color': '#E6F0FA', 'border': 1, 'align': 'center'})
            red_fill = workbook.add_format({'bg_color': '#FFC7CE', 'border': 1})
            
            sellers_data_rows = []
            start_row = 0
            
            sellers_data_rows.append(pd.DataFrame([['', '', '', '']]))
            sellers_data_rows.append(pd.DataFrame([['Sellers Summary', '', '', '']]))
            
            if 'SELLER_RATING' in merged_df.columns:
                seller_summary = merged_df.groupby('SELLER_NAME').agg(
                    Rejected=('Status', lambda x: (x == 'Rejected').sum()),
                    Approved=('Status', lambda x: (x == 'Approved').sum()),
                    AvgRating=('SELLER_RATING', 'mean'),
                    TotalStock=('STOCK_QTY', 'sum')
                ).reset_index()
                seller_summary['Rejection %'] = (
                    seller_summary['Rejected'] / (seller_summary['Rejected'] + seller_summary['Approved']) * 100
                ).round(1)
                seller_summary = seller_summary.sort_values('Rejected', ascending=False)
                sellers_data_rows.append(seller_summary)
            
            try:
                if 'CATEGORY' in merged_df.columns and not merged_df['CATEGORY'].isna().all():
                    category_rejections = (
                        merged_df[merged_df['Status'] == 'Rejected']
                        .groupby('CATEGORY').size()
                        .reset_index(name='Rejected Products')
                    )
                    category_rejections = category_rejections.sort_values('Rejected Products', ascending=False)
                    category_rejections.insert(0, 'Rank', range(1, len(category_rejections) + 1))
                    sellers_data_rows.append(pd.DataFrame([['', '', '', '']]))
                    sellers_data_rows.append(pd.DataFrame([['Categories Summary', '', '', '']]))
                    sellers_data_rows.append(
                        category_rejections.rename(columns={
                            'CATEGORY': 'Category',
                            'Rejected Products': 'Number of Rejected Products'
                        })
                    )
            except Exception as e:
                logger.error(f"Error creating category summary: {e}")
                sellers_data_rows.append(pd.DataFrame([['Categories Summary', f'Error: {str(e)}', '', '']]))
            
            try:
                if 'Reason' in merged_df.columns and not merged_df['Reason'].isna().all():
                    reason_rejections = (
                        merged_df[merged_df['Status'] == 'Rejected']
                        .groupby('Reason').size()
                        .reset_index(name='Rejected Products')
                    )
                    reason_rejections = reason_rejections.sort_values('Rejected Products', ascending=False)
                    reason_rejections.insert(0, 'Rank', range(1, len(reason_rejections) + 1))
                    sellers_data_rows.append(pd.DataFrame([['', '', '', '']]))
                    sellers_data_rows.append(pd.DataFrame([['Rejection Reasons Summary', '', '', '']]))
                    sellers_data_rows.append(
                        reason_rejections.rename(columns={
                            'Reason': 'Rejection Reason',
                            'Rejected Products': 'Number of Rejected Products'
                        })
                    )
            except Exception as e:
                logger.error(f"Error creating reasons summary: {e}")
                sellers_data_rows.append(pd.DataFrame([['Rejection Reasons Summary', f'Error: {str(e)}', '', '']]))
            
            for df in sellers_data_rows:
                if df.empty or len(df.columns) < 2:
                    continue
                if 'Rank' in df.columns:
                    for col_num, col_name in enumerate(df.columns):
                        worksheet.write(start_row, col_num, col_name, header_fmt)
                    for row_num, row_data in enumerate(df.values, start=start_row + 1):
                        for col_num, value in enumerate(row_data):
                            fmt = red_fill if col_num == 4 and len(row_data) > 4 and value > 30 else None
                            worksheet.write(row_num, col_num, value, fmt or header_fmt)
                else:
                    worksheet.write(start_row, 0, df.iloc[0, 0], header_fmt)
                start_row += len(df) + 1
            
            worksheet.set_column('A:A', 30)
            worksheet.set_column('B:B', 10)
            worksheet.set_column('C:C', 20)
        
        output.seek(0)
        logger.info("Full data export generated successfully")
        return output
    except Exception as e:
        logger.error(f"Error generating Full Data Export: {e}", exc_info=True)
        st.error(f"❌ Error generating Full Data Export: {str(e)}")
        return BytesIO()

def to_excel_flag_data(flag_df: pd.DataFrame, flag_name: str) -> BytesIO:
    """Export individual flag data"""
    output = BytesIO()
    df_copy = flag_df.copy()
    df_copy['FLAG'] = flag_name
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(df_copy, "ProductSets", FULL_DATA_COLS, writer)
    output.seek(0)
    return output

def to_excel(report_df: pd.DataFrame, reasons_config_df: pd.DataFrame,
             sheet1_name: str = "ProductSets", sheet2_name: str = "RejectionReasons") -> BytesIO:
    """Standard report export"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(report_df, sheet1_name, PRODUCTSETS_COLS, writer)
        if not reasons_config_df.empty:
            to_excel_base(reasons_config_df, sheet2_name, REJECTION_REASONS_COLS, writer)
        else:
            pd.DataFrame(columns=REJECTION_REASONS_COLS).to_excel(writer, index=False, sheet_name=sheet2_name)
    output.seek(0)
    return output

# -------------------------------------------------
# Audit Logging (CRITICAL FIX #4)
# -------------------------------------------------
def log_validation_run(country: str, file_name: str, total_rows: int,
                      approved: int, rejected: int, user: str = None) -> None:
    """Log validation run for audit trail"""
    import json
    
    audit_entry = {
        'timestamp': datetime.now().isoformat(),
        'country': country,
        'file': file_name,
        'total_rows': total_rows,
        'approved': approved,
        'rejected': rejected,
        'rejection_rate': round((rejected / total_rows * 100) if total_rows > 0 else 0, 2),
        'user': user or 'anonymous'
    }
    
    try:
        with open('validation_audit.jsonl', 'a') as f:
            f.write(json.dumps(audit_entry) + '\n')
        logger.info(f"Audit log entry created: {audit_entry}")
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")

# -------------------------------------------------
# UI
# -------------------------------------------------
st.title("🔍 Product Validation Tool")
st.markdown("---")

# Load support files once (CRITICAL FIX #1)
with st.spinner("Loading configuration files..."):
    support_files = load_all_support_files()

# Check if flags.xlsx loaded successfully (CRITICAL FIX #2)
if not support_files['flags_mapping']:
    st.error("❌ Critical: flags.xlsx could not be loaded. Please ensure the file exists with columns: rejection_reason_code, Comment")
    st.info("📋 Expected format: Each row should have a rejection code (e.g., '1000001 - Brand NOT Allowed') and corresponding comment")
    st.stop()

tab1, tab2, tab3 = st.tabs(["📅 Daily Validation", "📊 Weekly Analysis", "💾 Data Lake"])

# ================================
# DAILY VALIDATION TAB
# ================================
with tab1:
    st.header("Daily Product Validation")
    
    country = st.selectbox("Select Country", ["Kenya", "Uganda"], key="daily_country")
    country_validator = CountryValidator(country)
    
    uploaded_file = st.file_uploader("Upload your CSV file", type='csv', key="daily_file")
    
    if uploaded_file is not None:
        current_date = datetime.now().strftime('%Y-%m-%d')
        file_prefix = country_validator.code
        
        try:
            # Input validation
            dtype_spec = {
                'CATEGORY_CODE': str,
                'PRODUCT_SET_SID': str,
                'PARENTSKU': str,
                'ACTIVE_STATUS_COUNTRY': str,
            }
            
            with st.spinner("Loading CSV file..."):
                raw_data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype=dtype_spec)
                logger.info(f"Loaded CSV: {uploaded_file.name}, {len(raw_data)} rows")
            
            st.success(f"✅ Loaded CSV with {len(raw_data)} rows")
            
            # Validate input schema (CRITICAL FIX #4)
            is_valid, errors = validate_input_schema(raw_data)
            if not is_valid:
                st.error("❌ Input validation failed:")
                for error in errors:
                    st.error(f"  • {error}")
                logger.error(f"Input validation failed: {errors}")
                st.stop()
            
            # Filter by country
            data = filter_by_country(raw_data, country_validator, "Daily CSV")
            
            if data.empty:
                st.stop()
            
            # Ensure essential columns
            essential_input_cols = [
                'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'COLOR',
                'SELLER_NAME', 'GLOBAL_PRICE', 'GLOBAL_SALE_PRICE', 'PARENTSKU'
            ]
            for col in essential_input_cols:
                if col not in data.columns:
                    data[col] = pd.NA
            
            for col in ['NAME', 'BRAND', 'COLOR', 'SELLER_NAME', 'CATEGORY_CODE', 'PARENTSKU']:
                if col in data.columns:
                    data[col] = data[col].astype(str).fillna('')
            
            # Run validation
            with st.spinner("Running validations..."):
                final_report_df, individual_flag_dfs = validate_products(
                    data, support_files, country_validator
                )
            
            # Ensure Status column (CRITICAL FIX #3)
            final_report_df = country_validator.ensure_status_column(final_report_df)
            
            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']
            
            # Audit logging (CRITICAL FIX #4)
            log_validation_run(
                country=country,
                file_name=uploaded_file.name,
                total_rows=len(data),
                approved=len(approved_df),
                rejected=len(rejected_df)
            )
            
            # Sidebar - Seller Options
            st.sidebar.header("🔎 Seller Options")
            seller_options = ['All Sellers']
            
            if 'SELLER_NAME' in data.columns and 'ProductSetSid' in final_report_df.columns:
                final_report_df_for_join = final_report_df.copy()
                final_report_df_for_join['ProductSetSid'] = final_report_df_for_join['ProductSetSid'].astype(str)
                data_for_join = data[['PRODUCT_SET_SID', 'SELLER_NAME']].copy()
                data_for_join['PRODUCT_SET_SID'] = data_for_join['PRODUCT_SET_SID'].astype(str)
                data_for_join.drop_duplicates(subset=['PRODUCT_SET_SID'], inplace=True)
                
                report_with_seller = pd.merge(
                    final_report_df_for_join,
                    data_for_join,
                    left_on='ProductSetSid',
                    right_on='PRODUCT_SET_SID',
                    how='left'
                )
                
                if not report_with_seller.empty:
                    seller_options.extend(list(report_with_seller['SELLER_NAME'].dropna().unique()))
            
            selected_sellers = st.sidebar.multiselect(
                "Select Sellers",
                seller_options,
                default=['All Sellers'],
                key="daily_sellers"
            )
            
            # Filter by seller
            seller_data_filtered = data.copy()
            seller_final_report_df_filtered = final_report_df.copy()
            seller_label_filename = "All_Sellers"
            
            if 'All Sellers' not in selected_sellers and selected_sellers:
                if 'SELLER_NAME' in data.columns:
                    seller_data_filtered = data[data['SELLER_NAME'].isin(selected_sellers)].copy()
                    seller_final_report_df_filtered = final_report_df[
                        final_report_df['ProductSetSid'].isin(seller_data_filtered['PRODUCT_SET_SID'])
                    ].copy()
                    seller_label_filename = "_".join(
                        s.replace(" ", "_").replace("/", "_") for s in selected_sellers
                    )
                else:
                    st.sidebar.warning("⚠️ SELLER_NAME column missing, cannot filter by seller.")
            
            # Ensure Status column for filtered data
            seller_final_report_df_filtered = country_validator.ensure_status_column(seller_final_report_df_filtered)
            
            seller_rejected_df_filtered = seller_final_report_df_filtered[
                seller_final_report_df_filtered['Status'] == 'Rejected'
            ]
            seller_approved_df_filtered = seller_final_report_df_filtered[
                seller_final_report_df_filtered['Status'] == 'Approved'
            ]
            
            # Sidebar metrics
            st.sidebar.subheader("📊 Seller SKU Metrics")
            if 'SELLER_NAME' in data.columns and 'report_with_seller' in locals() and not report_with_seller.empty:
                sellers_to_display = (
                    selected_sellers if 'All Sellers' not in selected_sellers and selected_sellers
                    else seller_options[1:]
                )
                for seller in sellers_to_display:
                    if seller == 'All Sellers':
                        continue
                    current_seller_data = report_with_seller[report_with_seller['SELLER_NAME'] == seller]
                    rej_count = current_seller_data[current_seller_data['Status'] == 'Rejected'].shape[0]
                    app_count = current_seller_data[current_seller_data['Status'] == 'Approved'].shape[0]
                    st.sidebar.write(f"**{seller}**: Rej: {rej_count}, App: {app_count}")
            else:
                st.sidebar.write("Seller metrics unavailable.")
            
            # Sidebar exports
            st.sidebar.markdown("---")
            st.sidebar.subheader(f"📥 Exports: {seller_label_filename.replace('_', ' ')}")
            
            st.sidebar.download_button(
                "📄 Seller Final Export",
                to_excel(seller_final_report_df_filtered, support_files['reasons']),
                f"{file_prefix}_Final_Report_{current_date}_{seller_label_filename}.xlsx",
                key="daily_final"
            )
            st.sidebar.download_button(
                "❌ Seller Rejected Export",
                to_excel(seller_rejected_df_filtered, support_files['reasons']),
                f"{file_prefix}_Rejected_Products_{current_date}_{seller_label_filename}.xlsx",
                key="daily_rejected"
            )
            st.sidebar.download_button(
                "✅ Seller Approved Export",
                to_excel(seller_approved_df_filtered, support_files['reasons']),
                f"{file_prefix}_Approved_Products_{current_date}_{seller_label_filename}.xlsx",
                key="daily_approved"
            )
            st.sidebar.download_button(
                "📊 Seller Full Data Export",
                to_excel_full_data(seller_data_filtered, seller_final_report_df_filtered),
                f"{file_prefix}_Seller_Data_Export_{current_date}_{seller_label_filename}.xlsx",
                key="daily_full"
            )
            
            # Main content - Results
            st.markdown("---")
            st.header("📈 Overall Results")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📦 Total Products", len(data))
            with col2:
                st.metric("✅ Approved", len(approved_df))
            with col3:
                st.metric("❌ Rejected", len(rejected_df))
            with col4:
                rate = (len(rejected_df)/len(data)*100) if len(data) > 0 else 0
                st.metric("📉 Rejection Rate", f"{rate:.1f}%")
            
            st.markdown("---")
            st.subheader("🚩 Validation Results by Flag")
            
            # Display individual flags - CLOSED by default, only open if has issues
            for title, df_flagged in individual_flag_dfs.items():
                with st.expander(f"**{title}** ({len(df_flagged)} products)", expanded=False):
                    if not df_flagged.empty:
                        cols = [c for c in ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'SELLER_NAME', 'CATEGORY_CODE']
                               if c in df_flagged.columns]
                        st.dataframe(df_flagged[cols], use_container_width=True)
                        
                        safe = title.replace(' ', '_').replace('/', '_')
                        st.download_button(
                            f"📥 Export {title}",
                            to_excel_flag_data(df_flagged.copy(), title),
                            f"{file_prefix}_{safe}_{current_date}.xlsx",
                            key=f"flag_{safe}"
                        )
                    else:
                        st.success("✅ No issues found for this validation.")
            
            # Overall exports
            st.markdown("---")
            st.header("📥 Overall Exports (All Sellers)")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.download_button(
                    "📄 Final Report",
                    to_excel(final_report_df, support_files['reasons']),
                    f"{file_prefix}_Final_{current_date}_ALL.xlsx",
                    use_container_width=True
                )
            with col2:
                st.download_button(
                    "❌ Rejected",
                    to_excel(rejected_df, support_files['reasons']),
                    f"{file_prefix}_Rejected_{current_date}_ALL.xlsx",
                    use_container_width=True
                )
            with col3:
                st.download_button(
                    "✅ Approved",
                    to_excel(approved_df, support_files['reasons']),
                    f"{file_prefix}_Approved_{current_date}_ALL.xlsx",
                    use_container_width=True
                )
            with col4:
                st.download_button(
                    "📊 Full Data",
                    to_excel_full_data(data.copy(), final_report_df),
                    f"{file_prefix}_Full_{current_date}_ALL.xlsx",
                    use_container_width=True
                )
        
        except Exception as e:
            logger.error(f"Critical error in daily validation: {e}", exc_info=True)
            st.error(f"❌ Critical Error: {e}")
            with st.expander("🔧 Technical Details"):
                st.code(traceback.format_exc())

# ================================
# WEEKLY & DATA LAKE TABS
# ================================
with tab2:
    st.header("📊 Weekly Analysis")
    st.info("ℹ️ Weekly analysis functionality - Coming soon")
    st.write("This tab will provide weekly trend analysis and reporting.")

with tab3:
    if DATA_LAKE_AVAILABLE:
        # Pass all necessary functions to the Data Lake module
        data_lake.render_data_lake_tab(
            support_files=support_files,
            validate_products_func=validate_products,
            CountryValidator=CountryValidator,
            validate_input_schema=validate_input_schema,
            filter_by_country=filter_by_country,
            to_excel=to_excel,
            to_excel_full_data=to_excel_full_data,
            to_excel_flag_data=to_excel_flag_data,
            log_validation_run=log_validation_run
        )
    else:
        st.header("💾 Data Lake")
        st.error("❌ data_lake.py module not found")
        st.info("""
        To enable Data Lake functionality:
        1. Create a file named `data_lake.py` in the same directory as your main app
        2. Copy the data_lake module code provided
        3. Restart the app
        """)
        st.info("ℹ️ Data lake functionality - Coming soon")
        st.write("This tab will provide access to historical validation data.")
