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
    try:
        flag_mapping = {
            # REPLACED 'Sensitive words' with 'Seller Not approved to sell Refurb'
            'Seller Not approved to sell Refurb': ('1000001 - Seller Not Approved to Sell Refurb Product', "Your listing was rejected because it mentions \'Refurb\', \'Refurbished\', \'Renewed\' or the brand is \'Renewed\', but your seller account is not on the approved list for refurbished products in this country."),
            'BRAND name repeated in NAME': ('1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name', "Please do not write the brand name in the Product Name field..."),
            'Missing COLOR': ('1000005 - Kindly confirm the actual product colour', "Please make sure that the product color is clearly mentioned..."),
            'Duplicate product': ('1000007 - Other Reason', "kindly note product was rejected because its a duplicate product"),
            'Prohibited products': ('1000007 - Other Reason', "Kindly note this product is not allowed for listing on Jumia..."),
            'Single-word NAME': ('1000008 - Kindly Improve Product Name Description', "Kindly update the product title using this format..."),
            'Generic BRAND Issues': ('1000014 - Kindly request for the creation of this product\'s actual brand name...', "To create the actual brand name for this product..."),
            'Counterfeit Sneakers': ('1000023 - Confirmation of counterfeit product by Jumia technical team...', "Your listing has been rejected as Jumia\'s technical team has confirmed..."),
            'Seller Approve to sell books': ('1000028 - Kindly Contact Jumia Seller Support...', "Please contact Jumia Seller Support and raise a claim..."),
            'Seller Approved to Sell Perfume': ('1000028 - Kindly Contact Jumia Seller Support...', "Please contact Jumia Seller Support and raise a claim..."),
            'Suspected counterfeit Jerseys': ('1000030 - Suspected Counterfeit Product', "Your listing has been rejected as it is suspected to be a counterfeit jersey..."),
            'Suspected Fake product': ('1000031 - Suspected Fake Product', "Your listing has been rejected as the pricing suggests this may be a counterfeit or fake product. Products from reputable brands like Sony, JBL, Adidas, Nike, Apple, Samsung, and others must meet minimum price thresholds to ensure authenticity. Please verify the product\'s authenticity and adjust the pricing accordingly, or contact Jumia Seller Support if you believe this is an error."),
            'Product Warranty': ('1000013 - Kindly Provide Product Warranty Details', "For listing this type of product requires a valid warranty as per our platform guidelines.\nTo proceed, please ensure the warranty details are clearly mentioned in:\n\nProduct Description tab\n\nWarranty Tab.\n\nThis helps build customer trust and ensures your listing complies with Jumia\'s requirements."),
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
        # Removing sensitive_words.txt as it's replaced by the refurb check
        'colors': [c.lower() for c in load_txt_file('colors.txt')],
        'color_categories': load_txt_file('color_cats.txt'),
        'check_variation': load_excel_file('check_variation.xlsx'),
        'category_fas': load_excel_file('category_FAS.xlsx'),
        'reasons': load_excel_file('reasons.xlsx'),
        'flags_mapping': load_flags_mapping(),
        'jerseys_config': load_excel_file('Jerseys.xlsx'),
        'warranty_category_codes': load_txt_file('warranty.txt'),
        'suspected_fake': load_excel_file('suspected_fake.xlsx'),
        # NEW: Refurb Approved Sellers Lists
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
    """
    Flags a product if it mentions 'Refurb/Renewed' in NAME/BRAND, and the seller
    is NOT in the country's approved list.
    """
    
    # 1. Determine which approved list to use
    if country_code == 'KE':
        approved_sellers = set(approved_sellers_ke)
    elif country_code == 'UG':
        approved_sellers = set(approved_sellers_ug)
    else:
        # If the country is not KE or UG, we skip this specific check for refurbished
        return pd.DataFrame(columns=data.columns)

    if not {'NAME', 'BRAND', 'SELLER_NAME'}.issubset(data.columns): 
        return pd.DataFrame(columns=data.columns)
    
    data = data.copy()
    
    # 2. Define the refurb/renewed trigger words/brands
    refurb_words = r'\b(refurb|refurbished|renewed)\b'
    refurb_brand = 'renewed'
    
    data['NAME_LOWER'] = data['NAME'].astype(str).str.strip().str.lower()
    data['BRAND_LOWER'] = data['BRAND'].astype(str).str.strip().str.lower()
    data['SELLER_LOWER'] = data['SELLER_NAME'].astype(str).str.strip().str.lower()

    # Condition 1: Product is a suspected refurb item
    name_match = data['NAME_LOWER'].str.contains(refurb_words, regex=True, na=False)
    brand_match = data['BRAND_LOWER'] == refurb_brand
    
    trigger_mask = name_match | brand_match
    
    triggered_data = data[trigger_mask].copy()
    if triggered_data.empty:
        return pd.DataFrame(columns=data.columns)
        
    # Condition 2: Seller is NOT in the approved list (case-insensitive check)
    seller_not_approved_mask = ~triggered_data['SELLER_LOWER'].isin(approved_sellers)
    
    # Final mask: Triggered AND Seller is NOT approved
    flagged = triggered_data[seller_not_approved_mask]
    
    # Clean up and return
    columns_to_drop = ['NAME_LOWER', 'BRAND_LOWER', 'SELLER_LOWER']
    flagged = flagged.drop(columns=[col for col in columns_to_drop if col in flagged.columns])
    
    return flagged[data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_product_warranty(data: pd.DataFrame, warranty_category_codes: List[str]) -> pd.DataFrame:
    """
    Checks if products in warranty-required categories have warranty information.
    A product needs AT LEAST ONE of: PRODUCT_WARRANTY or WARRANTY_DURATION filled.
    """
    # 1. Ensure warranty columns exist
    for col in ['PRODUCT_WARRANTY', 'WARRANTY_DURATION']:
        if col not in data.columns:  
            data[col] = ""
        # Ensure it's treated as a string and missing values are handled
        data[col] = data[col].astype(str).fillna('').str.strip()
    
    if not warranty_category_codes:  
        return pd.DataFrame(columns=data.columns)
    
    # 2. Filter to warranty-required categories
    data['CAT_CLEAN'] = data['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
    target_cats = [str(c).strip() for c in warranty_category_codes]
    
    target_data = data[data['CAT_CLEAN'].isin(target_cats)].copy()
    if target_data.empty:  
        return pd.DataFrame(columns=data.columns)
    
    # 3. Check if ANY warranty field has meaningful data
    def is_present(series):
        """Check if a field has meaningful data (not empty, nan, none, etc.)"""
        s = series.astype(str).str.strip().str.lower()
        # Checks for actual presence of data, ignoring common NA representations
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
    return data[mask]

def check_sensitive_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    # This function is now OBSOLETE, but kept as a placeholder if other checks depended on it
    # As the user replaced this flag with `check_refurb_seller_approval`, we will adapt the calling in validate_products
    # but keep this stub just in case. However, based on the prompt, sensitive_words.txt is no longer needed.
    # The actual implementation of the new logic is in check_refurb_seller_approval.
    return pd.DataFrame(columns=data.columns)

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    return data[mask]

def check_brand_in_name(data: pd.DataFrame) -> pd.DataFrame:
    if not {'BRAND','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    mask = data.apply(lambda r: str(r['BRAND']).strip().lower() in str(r['NAME']).strip().lower()  
                     if pd.notna(r['BRAND']) and pd.notna(r['NAME']) else False, axis=1)
    return data[mask]

def check_duplicate_products(data: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    if len(cols) < 4: return pd.DataFrame(columns=data.columns)
    return data[data.duplicated(subset=cols, keep=False)]

def check_seller_approved_for_books(data: pd.DataFrame, book_category_codes: List[str], approved_book_sellers: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if books.empty: return pd.DataFrame(columns=data.columns)
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)]

def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_category_codes: List[str], approved_perfume_sellers: List[str], sensitive_perfume_brands: List[str]) -> pd.DataFrame:
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
    return perfume_data[final_mask]

def check_counterfeit_sneakers(data: pd.DataFrame, sneaker_category_codes: List[str], sneaker_sensitive_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'NAME', 'BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    sneaker_data = data[data['CATEGORY_CODE'].isin(sneaker_category_codes)].copy()
    if sneaker_data.empty: return pd.DataFrame(columns=data.columns)
    brand_lower = sneaker_data['BRAND'].astype(str).str.strip().str.lower()
    name_lower = sneaker_data['NAME'].astype(str).str.strip().str.lower()
    fake_brand_mask = brand_lower.isin(['generic', 'fashion'])
    name_contains_brand = name_lower.apply(lambda x: any(brand in x for brand in sneaker_sensitive_brands))
    return sneaker_data[fake_brand_mask & name_contains_brand]

def check_suspected_fake_products(data: pd.DataFrame, suspected_fake_df: pd.DataFrame, fx_rate: float = 132.0) -> pd.DataFrame:
    """
    Checks for suspected fake products based on brand, category, and price.
    Assumes product prices are in USD.
    """
    required_cols = ['CATEGORY_CODE', 'BRAND', 'GLOBAL_SALE_PRICE', 'GLOBAL_PRICE']
    
    if not all(c in data.columns for c in required_cols) or suspected_fake_df.empty:
        return pd.DataFrame(columns=data.columns)
    
    try:
        # Parse the reference file structure
        ref_data = suspected_fake_df.copy()
        
        brand_cols = [col for col in ref_data.columns if col not in ['Unnamed: 0', 'Brand', 'Price'] and pd.notna(col)]
        brand_category_price = {}
        
        for brand in brand_cols:
            try:
                price_threshold = pd.to_numeric(ref_data[brand].iloc[0], errors='coerce')
                if pd.isna(price_threshold) or price_threshold <= 0:
                    continue
            except:
                continue
            
            categories = ref_data[brand].iloc[1:].dropna()
            categories = categories[categories.astype(str).str.strip() != '']
            
            brand_lower = brand.strip().lower()
            
            for cat in categories:
                cat_str = str(cat).strip()
                cat_base = cat_str.split('.')[0]
                
                if cat_base and cat_base.lower() != 'nan':
                    key = (brand_lower, cat_base)
                    brand_category_price[key] = price_threshold
        
        if not brand_category_price:
            logger.warning("No valid brand-category-price combinations found in reference file. Check reference file structure.")
            return pd.DataFrame(columns=data.columns)
        
        check_data = data.copy()
        
        # 1. Determine price to use (prefer sale price if valid)
        check_data['price_to_use'] = check_data['GLOBAL_SALE_PRICE'].where(
            (check_data['GLOBAL_SALE_PRICE'].notna()) & 
            (pd.to_numeric(check_data['GLOBAL_SALE_PRICE'], errors='coerce') > 0),
            check_data['GLOBAL_PRICE']
        )
        check_data['price_to_use'] = pd.to_numeric(check_data['price_to_use'], errors='coerce').fillna(0)
        
        # 2. Assign price for comparison (price_usd) - NO FX CONVERSION
        check_data['price_usd'] = check_data['price_to_use']
        
        # 3. Normalize brand and extract base category
        check_data['BRAND_LOWER'] = check_data['BRAND'].astype(str).str.strip().str.lower()
        check_data['CAT_BASE'] = check_data['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
        
        # 4. Check each product against reference data
        def is_suspected_fake(row):
            key = (row['BRAND_LOWER'], row['CAT_BASE'])
            if key in brand_category_price:
                threshold = brand_category_price[key]
                if row['price_usd'] < threshold:
                    return True
            return False
        
        check_data['is_fake'] = check_data.apply(is_suspected_fake, axis=1)
        flagged = check_data[check_data['is_fake'] == True].copy()
        
        # Clean up temporary columns and return
        columns_to_drop = ['price_to_use', 'price_usd', 'BRAND_LOWER', 'CAT_BASE', 'is_fake']
        flagged = flagged.drop(columns=[col for col in columns_to_drop if col in flagged.columns])
        
        return flagged[data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])
        
    except Exception as e:
        logger.error(f"Error in suspected fake product check: {e}")
        logger.error(traceback.format_exc())
        return pd.DataFrame(columns=data.columns)

def check_single_word_name(data: pd.DataFrame, book_category_codes: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1]

def check_generic_brand_issues(data: pd.DataFrame, valid_category_codes_fas: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    return data[data['CATEGORY_CODE'].isin(valid_category_codes_fas) & (data['BRAND']=='Generic')]

def check_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
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
    return flagged.drop(columns=['CAT_STR']) if 'CAT_STR' in flagged.columns else flagged

# -------------------------------------------------
# Master validation runner
# -------------------------------------------------
def validate_products(data: pd.DataFrame, support_files: Dict, country_validator: CountryValidator, data_has_warranty_cols: bool, common_sids: Optional[set] = None):
    flags_mapping = support_files['flags_mapping']
    
    # ORDER MATTERS: This list defines the priority of the rejection flags.
    validations = [
        ("Suspected Fake product", check_suspected_fake_products, {'suspected_fake_df': support_files['suspected_fake'], 'fx_rate': FX_RATE}),
        ("Product Warranty", check_product_warranty, {'warranty_category_codes': support_files['warranty_category_codes']}),
        # REPLACED 'Sensitive words' CHECK with 'Seller Not approved to sell Refurb'
        ("Seller Not approved to sell Refurb", check_refurb_seller_approval, {
            'approved_sellers_ke': support_files['approved_refurb_sellers_ke'],
            'approved_sellers_ug': support_files['approved_refurb_sellers_ug'],
            'country_code': country_validator.code
        }),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': support_files['book_category_codes'], 'approved_book_sellers': support_files['approved_book_sellers']}),
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
    results = {}
    
    for i, (name, func, kwargs) in enumerate(validations):
        # Constraint 1: Skip based on country (handles Uganda)
        if country_validator.should_skip_validation(name): continue
        
        ckwargs = {'data': data, **kwargs}
        
        # --- Custom Logic for 'Product Warranty' (Constraints 2 & 3) ---
        if name == "Product Warranty":
            if not data_has_warranty_cols:
                # Constraint 2: Skip if necessary columns are missing (i.e., local file not uploaded)
                continue

            # Apply common SIDs filter (Constraint 3)
            check_data = data.copy()
            if common_sids is not None and len(common_sids) > 0:
                check_data = check_data[check_data['PRODUCT_SET_SID'].isin(common_sids)]
                if check_data.empty:
                    # If no common SIDs, skip the check
                    continue
            
            ckwargs = {'data': check_data, **kwargs} # Use the potentially filtered data
        
        # --- End Custom Logic ---

        status_text.text(f"Running: {name}")
        
        # Re-assign ckwargs for non-warranty checks that need special handling
        if name == "Generic BRAND Issues":
            fas = support_files.get('category_fas', pd.DataFrame())
            ckwargs['valid_category_codes_fas'] = fas['ID'].astype(str).tolist() if not fas.empty and 'ID' in fas.columns else []
        elif name == "Missing COLOR":
            ckwargs['country_code'] = country_validator.code
        
        try:
            res = func(**ckwargs)
            results[name] = res if not res.empty else pd.DataFrame(columns=data.columns)
        except Exception as e:
            logger.error(f"Error in {name}: {e}\n{traceback.format_exc()}")
            results[name] = pd.DataFrame(columns=data.columns)
        progress_bar.progress((i + 1) / len(validations))
    
    status_text.text("Finalizing...")
    rows = []
    processed = set()
    
    for name, _, _ in validations:
        if name not in results or results[name].empty: continue
        res = results[name]
        if 'PRODUCT_SET_SID' not in res.columns: continue
        
        reason_info = flags_mapping.get(name, ("1000007 - Other Reason", f"Flagged by {name}"))
        # Only merge the flagged SIDs back to retain full data columns for the output report
        flagged = pd.merge(res[['PRODUCT_SET_SID']].drop_duplicates(), data, on='PRODUCT_SET_SID', how='left')
        
        for _, r in flagged.iterrows():
            sid = r['PRODUCT_SET_SID']
            if sid in processed: continue  
            
            processed.add(sid)
            rows.append({
                'ProductSetSid': sid, 'ParentSKU': r.get('PARENTSKU', ''), 'Status': 'Rejected',
                'Reason': reason_info[0], 'Comment': reason_info[1], 'FLAG': name, 'SellerName': r.get('SELLER_NAME', '')
            })
    
    approved = data[~data['PRODUCT_SET_SID'].isin(processed)]
    for _, r in approved.iterrows():
        # Ensure we only add a row once per ProductSetSid to match the behavior of the original code
        if r['PRODUCT_SET_SID'] not in processed:
             rows.append({
                'ProductSetSid': r['PRODUCT_SET_SID'], 'ParentSKU': r.get('PARENTSKU', ''), 'Status': 'Approved',
                'Reason': "", 'Comment': "", 'FLAG': "", 'SellerName': r.get('SELLER_NAME', '')
            })
             processed.add(r['PRODUCT_SET_SID']) # Add to processed list to avoid duplicates here
    
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
        merged = pd.merge(d_cp, r_cp[["ProductSetSid", "Status", "Reason", "Comment", "FLAG", "SellerName"]],
                          left_on="PRODUCT_SET_SID", right_on="ProductSetSid", how='left')
        
        if 'ProductSetSid_y' in merged.columns: merged.drop(columns=['ProductSetSid_y'], inplace=True)
        if 'ProductSetSid_x' in merged.columns: merged.rename(columns={'ProductSetSid_x': 'PRODUCT_SET_SID'}, inplace=True)
        
        export_cols = FULL_DATA_COLS + [c for c in ["Status", "Reason", "Comment", "FLAG", "SellerName"] if c not in FULL_DATA_COLS]
        
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
                
                data = data_filtered.drop_duplicates(subset=['PRODUCT_SET_SID'], keep='first')
                
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
                log_validation_run(country, "Multi-Upload", len(data), len(approved_df), len(rejected_df))
                
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
                c1.metric("Total", len(data))
                c2.metric("Approved", len(approved_df))
                c3.metric("Rejected", len(rejected_df))
                rt = (len(rejected_df)/len(data)*100) if len(data)>0 else 0
                c4.metric("Rate", f"{rt:.1f}%")
                c5.metric("SKUs in Both Files", intersection_count)
                
                if intersection_count > 0:
                    common_skus_df = data[data['PRODUCT_SET_SID'].isin(intersection_sids)]
                    
                    csv_buffer = BytesIO()
                    common_skus_df.to_csv(csv_buffer, index=False)
                    st.download_button(
                        label=f"📥 Download Common SKUs ({intersection_count})",
                        data=csv_buffer.getvalue(),
                        file_name=f"{file_prefix}_Common_SKUs_{current_date}.csv",
                        mime="text/csv",
                    )
                
                st.subheader("Validation Results by Flag")
                for title, df_flagged in flag_dfs.items():
                    with st.expander(f"{title} ({len(df_flagged)})"):
                        if not df_flagged.empty:
                            st.dataframe(df_flagged)
                            st.download_button(f"Export {title}", to_excel_flag_data(df_flagged, title), f"{file_prefix}_{title}.xlsx")
                        else:
                            st.success("No issues found.")
                
                st.markdown("---")
                st.header("Overall Exports")
                c1, c2, c3, c4 = st.columns(4)
                c1.download_button("Final Report", to_excel(final_report, support_files['reasons']), f"{file_prefix}_Final_Report_{current_date}.xlsx")
                c2.download_button("Rejected", to_excel(rejected_df, support_files['reasons']), f"{file_prefix}_Rejected_{current_date}.xlsx")
                c3.download_button("Approved", to_excel(approved_df, support_files['reasons']), f"{file_prefix}_Approved_{current_date}.xlsx")
                c4.download_button("Full Data", to_excel_full_data(data, final_report), f"{file_prefix}_Full_Data_{current_date}.xlsx")
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

            c3, c4 = st.columns(2)
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
