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
        # Assuming support files are available in the local directory
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
        # Assuming support files are available in the local directory
        df = pd.read_excel(filename)
        df.columns = df.columns.str.strip()
        logger.info(f"Loaded {len(df)} rows from {filename}")

        if column and column in df.columns:
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
    NOTE: The hardcoded dictionary below ensures the logic runs even if the file
    'flags.xlsx' is unavailable, based on the content shared in previous steps.
    """
    try:
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
        return flag_mapping
    except Exception as e:
        logger.error(f"Error loading flags mapping: {e}", exc_info=True)
        st.error(f"Error loading flags mapping: {e}")
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
            logger.info(f"Added default 'Status' column for {self.country}")

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
        st.warning(f"ACTIVE_STATUS_COUNTRY missing in {source}")
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
        st.info(f"Excluded {excluded} non-{country_validator.code} rows: {others}")
    else:
        logger.info(f"All valid rows in {source} are {country_validator.code}")
        st.info(f"All valid rows in {source} are {country_validator.code}")

    if filtered.empty:
        logger.error(f"No {country_validator.code} rows left in {source}")
        st.error(f"No {country_validator.code} rows left in {source}")
        st.stop()

    return filtered

# -------------------------------------------------
# VECTORIZED Validation checks
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

    fake_brands = ['designers collection', 'smart collection', 'generic', 'ORIGINAL', 'original' 'designer', 'fashion']
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
    """VECTORIZED perfume price check"""
    req = ['CATEGORY_CODE','NAME','BRAND','GLOBAL_SALE_PRICE','GLOBAL_PRICE']
    if not all(c in data.columns for c in req) or perfumes_df.empty or not perfume_category_codes:
        return pd.DataFrame(columns=data.columns)

    perf = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perf.empty:
        return pd.DataFrame(columns=data.columns)

    # Vectorized price calculation
    perf['GLOBAL_SALE_PRICE'] = pd.to_numeric(perf['GLOBAL_SALE_PRICE'], errors='coerce')
    perf['GLOBAL_PRICE'] = pd.to_numeric(perf['GLOBAL_PRICE'], errors='coerce')

    perf['price_to_use'] = perf['GLOBAL_SALE_PRICE'].where(
        (perf['GLOBAL_SALE_PRICE'].notna()) & (perf['GLOBAL_SALE_PRICE'] > 0),
        perf['GLOBAL_PRICE']
    )
    
    # Drop rows without a valid price after calculation
    perf = perf.dropna(subset=['price_to_use'])

    # Convert to USD
    currency = perf.get('CURRENCY', pd.Series(['KES'] * len(perf), index=perf.index))
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
        perfumes_df['PRICE_USD'] = pd.to_numeric(perfumes_df['PRICE_USD'], errors='coerce')

    # Merge and filter
    merged = perf.merge(perfumes_df, on='BRAND_LOWER', how='left', suffixes=('', '_ref'))

    if 'PRODUCT_NAME_LOWER' in merged.columns:
        merged['name_match'] = merged.apply(
            lambda r: r['PRODUCT_NAME_LOWER'] in r['NAME_LOWER'] if pd.notna(r['PRODUCT_NAME_LOWER']) else False,
            axis=1
        )
        # Filter for products where a reference price exists and the name loosely matches
        merged = merged[merged['name_match']].dropna(subset=['PRICE_USD'])


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
    """

    # Get flags mapping (now a dictionary)
    flags_mapping = support_files['flags_mapping']
    if not flags_mapping:
        st.error("Cannot proceed without flags mapping")
        return pd.DataFrame(), {}

    # Pre-compile regex patterns
    sensitive_pattern = compile_regex_patterns(support_files['sensitive_words'])
    prohibited_pattern = compile_regex_patterns(country_validator.load_prohibited_products())
    color_pattern = compile_regex_patterns(support_files['colors'])

    # Get FAS categories for Generic BRAND Issues
    fas_df = support_files.get('category_fas', pd.DataFrame())
    fas_category_codes = (
        fas_df['ID'].astype(str).tolist() if not fas_df.empty and 'ID' in fas_df.columns else []
    )

    # Define validations (Order matters for rejection priority)
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
        ("Generic BRAND Issues", check_generic_brand_issues,
         {'valid_category_codes_fas': fas_category_codes}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color,
         {'pattern': color_pattern, 'color_categories': support_files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
    ]

    # Filter validations by country
    validations = [v for v in validations if not country_validator.should_skip_validation(v[0])]

    # Progress bar and status text (Streamlit UI elements)
    progress_bar = st.progress(0)
    status_text = st.empty()

    validation_results_dfs = {}

    for i, (flag_name, check_func, func_kwargs) in enumerate(validations):
        status_text.text(f"Running validation {i+1}/{len(validations)}: {flag_name}")

        current_kwargs = {'data': data}
        current_kwargs.update(func_kwargs) # Merge dynamic args

        try:
            result_df = check_func(**current_kwargs)

            if not result_df.empty and 'PRODUCT_SET_SID' not in result_df.columns:
                logger.warning(f"Check '{flag_name}' missing PRODUCT_SET_SID")
                st.warning(f"Check '{flag_name}' did not return 'PRODUCT_SET_SID'")
                validation_results_dfs[flag_name] = pd.DataFrame(columns=data.columns)
            else:
                validation_results_dfs[flag_name] = result_df
                logger.info(f"Validation '{flag_name}': {len(result_df)} flagged")

        except Exception as e:
            logger.error(f"Error during validation '{flag_name}': {e}", exc_info=True)
            st.error(f"Error during '{flag_name}': {e}")
            with st.expander("Technical Details"):
                st.code(traceback.format_exc())
            validation_results_dfs[flag_name] = pd.DataFrame(columns=data.columns)

        progress_bar.progress((i + 1) / len(validations))

    status_text.text("Building final report...")

    # Build report using flags mapping (CRITICAL: Order of iteration determines priority)
    final_report_rows = []
    processed_sids = set()

    for flag_name, _, _ in validations:
        validation_df = validation_results_dfs.get(flag_name, pd.DataFrame())
        if validation_df.empty or 'PRODUCT_SET_SID' not in validation_df.columns:
            continue

        # Get reason and comment from flags mapping
        if flag_name in flags_mapping:
            rejection_reason, comment = flags_mapping[flag_name]
        else:
            logger.warning(f"No mapping found for '{flag_name}'")
            st.warning(f"No mapping found for '{flag_name}' - using defaults")
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
            # Handle potential non-string SIDs
            if pd.isna(sid) or str(sid).strip() == "":
                continue

            # Skip if already processed (Priority enforcement)
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

    # Ensure Status column
    final_report_df = country_validator.ensure_status_column(final_report_df)

    status_text.empty()
    progress_bar.empty()

    return final_report_df, validation_results_dfs


# -------------------------------------------------
# Streamlit Main App Layout
# -------------------------------------------------

def to_excel(df):
    """Function to convert DataFrame to Excel for download"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='ValidationReport')
    return output.getvalue()

def to_rejection_csv(df: pd.DataFrame) -> str:
    """Format the report into the required Rejection reasons format"""
    rejection_df = df[df['Status'] == 'Rejected'].copy()
    if rejection_df.empty:
        return ""
    
    # Extract only the code part if the reason is formatted "CODE - REASON"
    rejection_df['CODE - REJECTION_REASON'] = rejection_df['Reason'].apply(
        lambda x: x.split(' - ')[0] if ' - ' in x else x
    )
    rejection_df['COMMENT'] = rejection_df['Comment']
    
    # Ensure correct columns and format
    rejection_df = rejection_df[['ProductSetSid', 'CODE - REJECTION_REASON', 'COMMENT']]
    rejection_df.rename(columns={'ProductSetSid': 'ProductSetSid'}, inplace=True)
    
    return rejection_df.to_csv(index=False).encode('utf-8')

def main():
    st.title("Jumia Product Validation Tool")

    # --- Sidebar ---
    st.sidebar.header("Configuration & Data")

    # 1. Country Selection
    country_name = st.sidebar.selectbox(
        "Select Country:",
        list(CountryValidator.COUNTRY_CONFIG.keys()),
        index=0
    )
    country_validator = CountryValidator(country_name)
    st.sidebar.info(f"Using FX Rate: ${1/FX_RATE:.4f} USD per KES")
    st.sidebar.info(f"Country Code: {country_validator.code}")
    if country_validator.skip_validations:
        st.sidebar.warning(f"Skipping validations for {country_name}: {', '.join(country_validator.skip_validations)}")

    # 2. File Uploader
    uploaded_file = st.sidebar.file_uploader(
        "Upload Product Data (CSV/Excel)",
        type=['csv', 'xlsx']
    )

    # Load Support Files
    support_files = load_all_support_files()

    if uploaded_file is not None:
        try:
            # Determine file type and read
            if uploaded_file.name.endswith('.csv'):
                # --- FIX: Robust CSV reading for common ParserError (semicolon delimiter) ---
                try:
                    # 1. Try standard comma separator
                    input_df = pd.read_csv(uploaded_file)
                except pd.errors.ParserError:
                    # 2. If ParserError, reset file pointer and try semicolon separator
                    st.warning("CSV read failed (ParserError). Attempting read with semicolon (';') separator.")
                    uploaded_file.seek(0) # Reset pointer for second read
                    input_df = pd.read_csv(uploaded_file, sep=';')
                # --- END FIX ---
            else:
                input_df = pd.read_excel(uploaded_file)

            st.sidebar.success(f"File loaded: {len(input_df)} total rows.")
            
            # 3. Validation Check
            is_valid, errors = validate_input_schema(input_df)

            if not is_valid:
                st.error("Input data validation failed:")
                for error in errors:
                    st.write(f"- {error}")
                st.stop()
            
            # Ensure column names are stripped/cleaned for consistency
            input_df.columns = input_df.columns.str.strip().str.replace(r'[\s\.\-\(\)]', '_', regex=True).str.upper()

            # Filter data by country
            st.subheader(f"Filtering Data for {country_name}")
            df_filtered = filter_by_country(input_df, country_validator, "Input Data")

            # --- Main Processing ---
            if st.button(f"Run {country_name} Validation"):
                st.subheader("Validation Results")
                
                # Run the master validation function
                final_report_df, validation_results_dfs = validate_products(
                    df_filtered, support_files, country_validator
                )
                
                # --- Summary Metrics (Sidebar) ---
                rejected_count = final_report_df[final_report_df['Status'] == 'Rejected'].shape[0]
                approved_count = final_report_df[final_report_df['Status'] == 'Approved'].shape[0]
                total_count = final_report_df.shape[0]

                st.sidebar.subheader("Processing Summary")
                st.sidebar.metric("Total Products", total_count)
                st.sidebar.metric("Rejected", rejected_count)
                st.sidebar.metric("Approved", approved_count)

                # --- Rejection Breakdown (Sidebar) ---
                if rejected_count > 0:
                    flag_counts = final_report_df[final_report_df['Status'] == 'Rejected']['FLAG'].value_counts()
                    st.sidebar.subheader("Rejection Breakdown")
                    st.sidebar.dataframe(flag_counts, use_container_width=True)
                
                # --- Main Report Output ---
                st.subheader("Final Validation Report (All Products)")
                st.dataframe(final_report_df, use_container_width=True)

                st.download_button(
                    label="📥 Download Full Report (.xlsx)",
                    data=to_excel(final_report_df),
                    file_name=f'validation_report_{country_validator.code}_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )

                # --- Rejection File for Upload (Jumia Format) ---
                rejection_csv = to_rejection_csv(final_report_df)
                if rejection_csv:
                    st.subheader("Rejection File for Bulk Upload")
                    st.download_button(
                        label="📥 Download Rejection Reasons (.csv)",
                        data=rejection_csv,
                        file_name=f'rejection_reasons_{country_validator.code}_{datetime.now().strftime("%Y%m%d_%H%M")}.csv',
                        mime='text/csv'
                    )

        except Exception as e:
            # Catch all other exceptions, including the second ParserError if semicolon fails
            st.error(f"An error occurred during processing. Please check your file format and headers.")
            with st.expander("Technical Details"):
                st.code(traceback.format_exc())

    else:
        st.info("Please upload your product data file in the sidebar to begin validation.")
        st.info(f"Ready to process data for **{country_name}**.")

if __name__ == '__main__':
    main()
