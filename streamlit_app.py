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
import altair as alt
import requests
from difflib import SequenceMatcher

# We keep these imports to avoid breaking the script structure
try:
    import imagehash
    from PIL import Image
except ImportError:
    pass 

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
    "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG", "LISTING_STATUS", "SELLER_RATING",
    "STOCK_QTY", "PRODUCT_WARRANTY", "WARRANTY_DURATION", "WARRANTY_ADDRESS", "WARRANTY_TYPE"
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
# UTILITIES
# -------------------------------------------------

def clean_category_code(code) -> str:
    """Robust cleaner for category codes to handle .0 suffixes and whitespace."""
    try:
        if pd.isna(code): return ""
        s = str(code).strip()
        if s.replace('.', '', 1).isdigit() and '.' in s:
            return str(int(float(s)))
        return s
    except:
        return str(code).strip()

def normalize_text(text: str) -> str:
    """Normalize text by removing noise words, special characters, and extra spaces."""
    if pd.isna(text): return ""
    text = str(text).lower().strip()
    # Remove noise words (English & Common) to improve duplicate detection
    noise = r'\b(new|sale|original|genuine|authentic|official|premium|quality|best|hot|2024|2025)\b'
    text = re.sub(noise, '', text)
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', '', text)
    return text

def calculate_text_similarity(text1: str, text2: str) -> float:
    return SequenceMatcher(None, text1, text2).ratio()

def create_match_key(row: pd.Series) -> str:
    name = normalize_text(row.get('NAME', ''))
    brand = normalize_text(row.get('BRAND', ''))
    color = normalize_text(row.get('COLOR', ''))
    return f"{brand}|{name}|{color}"

def check_duplicate_products_enhanced(
    data: pd.DataFrame,
    use_image_hash: bool = False, 
    similarity_threshold: float = 0.85,
    max_images_to_hash: int = 0
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    
    required_cols = ['NAME', 'BRAND', 'SELLER_NAME', 'COLOR', 'PRODUCT_SET_SID']
    if not all(col in data.columns for col in required_cols):
        return pd.DataFrame(columns=data.columns), {}
    
    data_copy = data.copy()
    
    # Strategy 1: Normalized Text Matching (Fast & Exact)
    data_copy['match_key'] = data_copy.apply(create_match_key, axis=1)
    normalized_duplicates = data_copy[
        data_copy.duplicated(subset=['match_key', 'SELLER_NAME'], keep=False)
    ]['PRODUCT_SET_SID'].tolist()
    
    # Strategy 2: Image Hash Matching (DISABLED)
    image_duplicates = []
    
    # Strategy 3: Fuzzy Text Matching (Complexity Limited)
    fuzzy_duplicates = []
    SAFE_GROUP_SIZE = 200 
    
    grouped = data_copy.groupby('SELLER_NAME')
    
    for seller, group in grouped:
        if len(group) < 2 or len(group) > SAFE_GROUP_SIZE:
            continue
            
        products = group[['PRODUCT_SET_SID', 'NAME', 'BRAND', 'COLOR']].to_dict('records')
        
        for i, prod1 in enumerate(products):
            for prod2 in products[i+1:]:
                if normalize_text(prod1['BRAND']) != normalize_text(prod2['BRAND']):
                    continue
                
                name_sim = calculate_text_similarity(
                    normalize_text(prod1['NAME']),
                    normalize_text(prod2['NAME'])
                )
                
                if (name_sim >= similarity_threshold and
                    normalize_text(prod1['COLOR']) == normalize_text(prod2['COLOR'])):
                    fuzzy_duplicates.extend([prod1['PRODUCT_SET_SID'], prod2['PRODUCT_SET_SID']])
    
    all_duplicate_sids = set(normalized_duplicates + image_duplicates + fuzzy_duplicates)
    result = data_copy[data_copy['PRODUCT_SET_SID'].isin(all_duplicate_sids)].copy()
    
    if 'match_key' in result.columns: result = result.drop(columns=['match_key'])
    if 'image_hash' in result.columns: result = result.drop(columns=['image_hash'])
    
    stats = {
        'normalized': len(normalized_duplicates),
        'image_hash': len(image_duplicates),
        'fuzzy': len(fuzzy_duplicates),
        'total': len(all_duplicate_sids)
    }
    return result[data.columns].drop_duplicates(subset=['PRODUCT_SET_SID']), stats

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
def load_excel_file(filename: str, column: Optional[str] = None):
    try:
        df = pd.read_excel(filename, engine='openpyxl', dtype=str)
        df.columns = df.columns.str.strip()
        if column and column in df.columns:
            # Improvement: Clean category codes on load
            return df[column].apply(clean_category_code).tolist()
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
                "Please contact Jumia Seller Support and raise a claim to confirm whether this product is eligible for listing.\nThis step will help ensure that all necessary requirements and approvals are addressed before proceeding with the sale, and prevent any future compliance issues."
            ),
            'BRAND name repeated in NAME': (
                '1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name',
                "Please do not write the brand name in the Product Name field. The brand name should only be written in the Brand field.\nIf you include it in both fields, it will show up twice in the product title on the website"
            ),
            'Missing COLOR': (
                '1000005 - Kindly confirm the actual product colour',
                "Please make sure that the product color is clearly mentioned in both the title and in the color tab.\nAlso, the images you upload must match the exact color being sold in this specific listing.\nAvoid including pictures of other colors, as this may confuse customers and lead to order cancellations."
            ),
            'Duplicate product': ('1000007 - Other Reason', "Kindly avoid creating duplicate SKUs"),
            'Prohibited products': (
                '1000024 - Product does not have a license to be sold via Jumia (Not Authorized)',
                "Your product listing has been rejected due to the absence of a required license for this item.\nAs a result, the product cannot be authorized for sale on Jumia.\n\nPlease ensure that you obtain and submit the necessary license(s) before attempting to relist the product.\nFor further assistance or clarification, Please raise a claim via Vendor Center."
            ),
            'Single-word NAME': (
                '1000008 - Kindly Improve Product Name Description',
                "Kindly update the product title using this format: Name – Type of the Products – Color.\nIf available, please also add key details such as weight, capacity, type, and warranty to make the title clear and complete for customers."
            ),
            'Unnecessary words in NAME': (
                '1000008 - Kindly Improve Product Name Description',
                "Kindly update the product title using this format: Name – Type of the Products – Color.\nIf available, please also add key details such as weight, capacity, type, and warranty to make the title clear and complete for customers.Kindly avoid unnecesary words "
            ),
            'Generic BRAND Issues': (
                '1000014 - Kindly request for the creation of this product\'s actual brand name by filling this form: https://bit.ly/2kpjja8',
                "To create the actual brand name for this product, please fill out the form at: https://bit.ly/2kpjja8.\nYou will receive an email within the coming 48 working hours the result of your request — whether it's approved or rejected, along with the reason..Avoid using Generic for fashion items"
            ),
            'Counterfeit Sneakers': (
                '1000030 - Suspected Counterfeit/Fake Product.Please Contact Seller Support By Raising A Claim , For Questions & Inquiries (Not Authorized)',
                "This product is suspected to be counterfeit or fake and is not authorized for sale on our platform.\n\nPlease contact Seller Support to raise a claim and initiate the necessary verification process.\nIf you have any questions or need further assistance, don't hesitate to reach out to Seller Support."
            ),
            'Seller Approve to sell books': (
                '1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim',
                "Please contact Jumia Seller Support and raise a claim to confirm whether this product is eligible for listing.\nThis step will help ensure that all necessary requirements and approvals are addressed before proceeding with the sale, and prevent any future compliance issues."
            ),
            'Seller Approved to Sell Perfume': (
                '1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim',
                "Please contact Jumia Seller Support and raise a claim to confirm whether this product is eligible for listing.\nThis step will help ensure that all necessary requirements and approvals are addressed before proceeding with the sale, and prevent any future compliance issues."
            ),
            'Suspected counterfeit Jerseys': (
                '1000030 - Suspected Counterfeit/Fake Product.Please Contact Seller Support By Raising A Claim , For Questions & Inquiries (Not Authorized)',
                "This product is suspected to be counterfeit or fake and is not authorized for sale on our platform.\n\nPlease contact Seller Support to raise a claim and initiate the necessary verification process.\nIf you have any questions or need further assistance, don't hesitate to reach out to Seller Support."
            ),
            'Suspected Fake product': (
                '1000030 - Suspected Counterfeit/Fake Product.Please Contact Seller Support By Raising A Claim , For Questions & Inquiries (Not Authorized)',
                "This product is suspected to be counterfeit or fake and is not authorized for sale on our platform.\n\nPlease contact Seller Support to raise a claim and initiate the necessary verification process.\nIf you have any questions or need further assistance, don't hesitate to reach out to Seller Support."
            ),
            'Product Warranty': (
                '1000013 - Kindly Provide Product Warranty Details',
                "For listing this type of product requires a valid warranty as per our platform guidelines.\nTo proceed, please ensure the warranty details are clearly mentioned in:\n\nProduct Description tab\n\nWarranty Tab.\n\nThis helps build customer trust and ensures your listing complies with Jumia's requirements."
            ),
            'Sensitive words': (
                '1000001 - Brand NOT Allowed',
                "Your listing was rejected because it includes brands that are not allowed on Jumia, such as Chanel, Rolex, and My Salat Mat. These brands are banned from being sold on our platform."
            ),
        }
        return flag_mapping
    except Exception:
        return {}

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
        'duplicate_exempt_codes': load_txt_file('duplicate_exempt.txt'),
    }
    return files

@st.cache_data(ttl=3600)
def compile_regex_patterns(words: List[str]) -> re.Pattern:
    if not words:
        return None
    words = sorted(words, key=len, reverse=True)
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
        if df.empty:
            return df
        if 'Status' not in df.columns:
            df['Status'] = 'Approved'
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
    # Improvement: Memory Optimization
    for col in ['ACTIVE_STATUS_COUNTRY', 'CATEGORY_CODE', 'BRAND', 'TAX_CLASS']:
        if col in df.columns:
            df[col] = df[col].astype('category')
    return df

def validate_input_schema(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    errors = []
    required = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'ACTIVE_STATUS_COUNTRY']
    for field in required:
        if field not in df.columns:
            errors.append(f"Missing: {field}")
    return len(errors) == 0, errors

def filter_by_country(df: pd.DataFrame, country_validator: CountryValidator, source: str) -> pd.DataFrame:
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns:
        return df
    df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.strip().str.upper()
    mask = df['ACTIVE_STATUS_COUNTRY'] == country_validator.code
    filtered = df[mask].copy()
    if filtered.empty:
        st.error(f"No {country_validator.code} rows left in {source}")
        st.stop()
    return filtered

def propagate_metadata(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    cols_to_propagate = ['COLOR_FAMILY', 'PRODUCT_WARRANTY', 'WARRANTY_DURATION', 'WARRANTY_ADDRESS', 'WARRANTY_TYPE']
    for col in cols_to_propagate:
        if col not in df.columns:
            df[col] = pd.NA
    for col in cols_to_propagate:
        df[col] = df.groupby('PRODUCT_SET_SID')[col].transform(lambda x: x.ffill().bfill())
    return df

# --- Validation Logic Functions ---

def check_refurb_seller_approval(data: pd.DataFrame, approved_sellers_ke: List[str], approved_sellers_ug: List[str], country_code: str) -> pd.DataFrame:
    if country_code == 'KE': approved_sellers = set(approved_sellers_ke)
    elif country_code == 'UG': approved_sellers = set(approved_sellers_ug)
    else: return pd.DataFrame(columns=data.columns)
    
    if not {'NAME', 'BRAND', 'SELLER_NAME', 'PRODUCT_SET_SID'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    
    data = data.copy()
    refurb_words = r'\b(refurb|refurbished|renewed)\b'
    data['NAME_LOWER'] = data['NAME'].astype(str).str.strip().str.lower()
    data['SELLER_LOWER'] = data['SELLER_NAME'].astype(str).str.strip().str.lower()
    
    trigger_mask = data['NAME_LOWER'].str.contains(refurb_words, regex=True, na=False) | (data['BRAND'].astype(str).str.lower() == 'renewed')
    triggered_data = data[trigger_mask].copy()
    
    if triggered_data.empty: return pd.DataFrame(columns=data.columns)
    
    flagged = triggered_data[~triggered_data['SELLER_LOWER'].isin(approved_sellers)]
    return flagged.drop(columns=['NAME_LOWER', 'SELLER_LOWER']).drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_unnecessary_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None:
        return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    # Improvement: Detailed Comment
    data.loc[mask, 'Comment_Detail'] = "Matched keyword in Name"
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_product_warranty(data: pd.DataFrame, warranty_category_codes: List[str]) -> pd.DataFrame:
    for col in ['PRODUCT_WARRANTY', 'WARRANTY_DURATION']:
        if col not in data.columns: data[col] = ""
        data[col] = data[col].astype(str).fillna('').str.strip()
    
    if not warranty_category_codes: return pd.DataFrame(columns=data.columns)
    
    # Clean codes
    data['CAT_CLEAN'] = data['CATEGORY_CODE'].apply(clean_category_code)
    target_cats = [clean_category_code(c) for c in warranty_category_codes]
    target_data = data[data['CAT_CLEAN'].isin(target_cats)].copy()
    
    if target_data.empty: return pd.DataFrame(columns=data.columns)
    
    def is_present(series):
        s = series.astype(str).str.strip().str.lower()
        return (s != 'nan') & (s != '') & (s != 'none') & (s != 'nat') & (s != 'n/a')
    
    mask = ~(is_present(target_data['PRODUCT_WARRANTY']) | is_present(target_data['WARRANTY_DURATION']))
    flagged = target_data[mask]
    if 'CAT_CLEAN' in flagged.columns: flagged = flagged.drop(columns=['CAT_CLEAN'])
    return flagged.drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_missing_color(data: pd.DataFrame, pattern: re.Pattern, color_categories: List[str], country_code: str) -> pd.DataFrame:
    required = ['CATEGORY_CODE', 'NAME']
    if not all(c in data.columns for c in required) or pattern is None:
        return pd.DataFrame(columns=data.columns)
    
    # Fuzzy Match Category Code
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    config_cats = set(clean_category_code(c) for c in color_categories)
    
    target = data[data_cats.isin(config_cats)].copy()
    if target.empty: return pd.DataFrame(columns=data.columns)
        
    has_color_col = 'COLOR' in data.columns
    
    def is_color_missing(row):
        name_val = str(row['NAME'])
        if pattern.search(name_val): return False
        
        if has_color_col:
            color_val = str(row['COLOR'])
            if color_val.strip().lower() not in ['nan', '', 'none', 'null']: return False
        return True

    mask = target.apply(is_color_missing, axis=1)
    # Add trigger comment
    target.loc[mask, 'Comment_Detail'] = "Color not found in Name or Color column"
    return target[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_sensitive_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_brand_in_name(data: pd.DataFrame) -> pd.DataFrame:
    if not {'BRAND','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    mask = data.apply(lambda r: str(r['BRAND']).strip().lower() in str(r['NAME']).strip().lower()
                      if pd.notna(r['BRAND']) and pd.notna(r['NAME']) else False, axis=1)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_duplicate_products(data: pd.DataFrame, use_image_hash: bool = True, similarity_threshold: float = 0.85, exempt_categories: List[str] = None) -> pd.DataFrame:
    data_to_check = data.copy()
    if exempt_categories and 'CATEGORY_CODE' in data_to_check.columns:
        cats_to_check = data_to_check['CATEGORY_CODE'].apply(clean_category_code)
        exempt_set = set(clean_category_code(c) for c in exempt_categories)
        data_to_check = data_to_check[~cats_to_check.isin(exempt_set)]

    if data_to_check.empty: return pd.DataFrame(columns=data.columns)

    result, stats = check_duplicate_products_enhanced(
        data_to_check,
        use_image_hash=False,
        similarity_threshold=similarity_threshold,
        max_images_to_hash=0
    )
    
    if 'duplicate_stats' not in st.session_state:
        st.session_state.duplicate_stats = {}
    st.session_state.duplicate_stats = stats
    return result

def check_seller_approved_for_books(data: pd.DataFrame, book_category_codes: List[str], approved_book_sellers: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    book_cats = set(clean_category_code(c) for c in book_category_codes)
    
    books = data[data_cats.isin(book_cats)]
    if books.empty: return pd.DataFrame(columns=data.columns)
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_category_codes: List[str], approved_perfume_sellers: List[str], sensitive_perfume_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME','BRAND','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    perfume_cats = set(clean_category_code(c) for c in perfume_category_codes)
    
    perfume_data = data[data_cats.isin(perfume_cats)].copy()
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
    if not {'CATEGORY_CODE', 'NAME', 'BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    sneaker_cats = set(clean_category_code(c) for c in sneaker_category_codes)
    
    sneaker_data = data[data_cats.isin(sneaker_cats)].copy()
    if sneaker_data.empty: return pd.DataFrame(columns=data.columns)
    
    brand_lower = sneaker_data['BRAND'].astype(str).str.strip().str.lower()
    name_lower = sneaker_data['NAME'].astype(str).str.strip().str.lower()
    
    fake_brand_mask = brand_lower.isin(['generic', 'fashion'])
    name_contains_brand = name_lower.apply(lambda x: any(brand in x for brand in sneaker_sensitive_brands))
    
    return sneaker_data[fake_brand_mask & name_contains_brand].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_suspected_fake_products(data: pd.DataFrame, suspected_fake_df: pd.DataFrame, fx_rate: float = 132.0) -> pd.DataFrame:
    required_cols = ['CATEGORY_CODE', 'BRAND', 'GLOBAL_SALE_PRICE', 'GLOBAL_PRICE']
    if not all(c in data.columns for c in required_cols) or suspected_fake_df.empty:
        return pd.DataFrame(columns=data.columns)
    
    try:
        ref_data = suspected_fake_df.copy()
        brand_cols = [col for col in ref_data.columns if col not in ['Unnamed: 0', 'Brand', 'Price'] and pd.notna(col)]
        brand_category_price = {}
        for brand in brand_cols:
            try:
                price_threshold = pd.to_numeric(ref_data[brand].iloc[0], errors='coerce')
                if pd.isna(price_threshold) or price_threshold <= 0: continue
            except: continue
            categories = ref_data[brand].iloc[1:].dropna()
            brand_lower = brand.strip().lower()
            for cat in categories:
                cat_str = str(cat).strip()
                cat_base = cat_str.split('.')[0]
                if cat_base and cat_base.lower() != 'nan':
                    key = (brand_lower, cat_base)
                    brand_category_price[key] = price_threshold
        
        if not brand_category_price: return pd.DataFrame(columns=data.columns)
        
        check_data = data.copy()
        check_data['price_to_use'] = check_data['GLOBAL_SALE_PRICE'].where(
            (check_data['GLOBAL_SALE_PRICE'].notna()) & (pd.to_numeric(check_data['GLOBAL_SALE_PRICE'], errors='coerce') > 0),
            check_data['GLOBAL_PRICE']
        )
        check_data['price_to_use'] = pd.to_numeric(check_data['price_to_use'], errors='coerce').fillna(0)
        check_data['price_usd'] = check_data['price_to_use']
        check_data['BRAND_LOWER'] = check_data['BRAND'].astype(str).str.strip().str.lower()
        check_data['CAT_BASE'] = check_data['CATEGORY_CODE'].apply(clean_category_code)
        
        def is_suspected_fake(row):
            key = (row['BRAND_LOWER'], row['CAT_BASE'])
            if key in brand_category_price:
                threshold = brand_category_price[key]
                if row['price_usd'] < threshold: return True
            return False
        
        check_data['is_fake'] = check_data.apply(is_suspected_fake, axis=1)
        flagged = check_data[check_data['is_fake'] == True].copy()
        return flagged[data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])
    
    except Exception as e:
        logger.error(f"Error in suspected fake: {e}")
        return pd.DataFrame(columns=data.columns)

def check_single_word_name(data: pd.DataFrame, book_category_codes: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    book_cats = set(clean_category_code(c) for c in book_category_codes)
    non_books = data[~data_cats.isin(book_cats)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_generic_brand_issues(data: pd.DataFrame, valid_category_codes_fas: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    fas_cats = set(clean_category_code(c) for c in valid_category_codes_fas)
    return data[data_cats.isin(fas_cats) & (data['BRAND']=='Generic')].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    req = ['CATEGORY_CODE', 'NAME', 'SELLER_NAME']
    if not all(c in data.columns for c in req) or jerseys_df.empty: return pd.DataFrame(columns=data.columns)
    
    jersey_cats = [clean_category_code(c) for c in jerseys_df['Categories'].astype(str).unique() if c.lower() != 'nan']
    keywords = [w for w in jerseys_df['Checklist'].astype(str).str.strip().str.lower().unique() if w and w!='nan']
    exempt = [s for s in jerseys_df['Exempted'].astype(str).str.strip().unique() if s and s.lower()!='nan']
    
    if not jersey_cats or not keywords: return pd.DataFrame(columns=data.columns)
    regex = re.compile('|'.join(r'\b' + re.escape(w) + r'\b' for w in keywords), re.IGNORECASE)
    
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    jerseys = data[data_cats.isin(jersey_cats)].copy()
    if jerseys.empty: return pd.DataFrame(columns=data.columns)
    
    target = jerseys[~jerseys['SELLER_NAME'].isin(exempt)].copy()
    mask = target['NAME'].astype(str).str.strip().str.lower().str.contains(regex, na=False)
    return target[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

# -------------------------------------------------
# Master validation runner
# -------------------------------------------------
def validate_products(data: pd.DataFrame, support_files: Dict, country_validator: CountryValidator, data_has_warranty_cols: bool, common_sids: Optional[set] = None):
    flags_mapping = support_files['flags_mapping']
    
    validations = [
        ("Suspected Fake product", check_suspected_fake_products, {'suspected_fake_df': support_files['suspected_fake'], 'fx_rate': FX_RATE}),
        ("Seller Not approved to sell Refurb", check_refurb_seller_approval, {
            'approved_sellers_ke': support_files['approved_refurb_sellers_ke'],
            'approved_sellers_ug': support_files['approved_refurb_sellers_ug'],
            'country_code': country_validator.code
        }),
        ("Product Warranty", check_product_warranty, {'warranty_category_codes': support_files['warranty_category_codes']}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': support_files['book_category_codes'], 'approved_book_sellers': support_files['approved_book_sellers']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'perfume_category_codes': support_files['perfume_category_codes'], 'approved_perfume_sellers': support_files['approved_perfume_sellers'], 'sensitive_perfume_brands': support_files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'sneaker_category_codes': support_files['sneaker_category_codes'], 'sneaker_sensitive_brands': support_files['sneaker_sensitive_brands']}),
        ("Suspected counterfeit Jerseys", check_counterfeit_jerseys, {'jerseys_df': support_files['jerseys_config']}),
        ("Prohibited products", check_prohibited_products, {'pattern': compile_regex_patterns(country_validator.load_prohibited_products())}),
        ("Unnecessary words in NAME", check_unnecessary_words, {'pattern': compile_regex_patterns(support_files['unnecessary_words'])}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': support_files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': compile_regex_patterns(support_files['colors']), 'color_categories': support_files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {'exempt_categories': support_files.get('duplicate_exempt_codes', [])}),
    ]
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    results = {}
    
    duplicate_groups = {}
    cols_for_dup = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    if len(cols_for_dup) == 4:
        data_temp = data.copy()
        data_temp['dup_key'] = data_temp[cols_for_dup].apply(
            lambda r: tuple(str(v).strip().lower() for v in r), axis=1
        )
        dup_counts = data_temp.groupby('dup_key')['PRODUCT_SET_SID'].apply(list).to_dict()
        for dup_key, sid_list in dup_counts.items():
            if len(sid_list) > 1:
                for sid in sid_list:
                    duplicate_groups[sid] = sid_list
    
    # IMPROVEMENT: Generalized Restricted Keys Container
    restricted_issue_keys = {}

    for i, (name, func, kwargs) in enumerate(validations):
        if name != "Seller Not approved to sell Refurb" and country_validator.should_skip_validation(name):
            if name == "Sensitive words": continue
            if name == "Product Warranty" and country_validator.code == 'UG': continue
            if name == "Seller Approve to sell books" and country_validator.code == 'UG': continue
            if name == "Seller Approved to Sell Perfume" and country_validator.code == 'UG': continue
            if name == "Counterfeit Sneakers" and country_validator.code == 'UG': continue
            if country_validator.should_skip_validation(name): continue
        
        ckwargs = {'data': data, **kwargs}
        
        if name == "Product Warranty":
            if not data_has_warranty_cols: continue
            check_data = data.copy()
            if common_sids is not None and len(common_sids) > 0:
                check_data = check_data[check_data['PRODUCT_SET_SID'].isin(common_sids)]
            if check_data.empty: continue
            ckwargs = {'data': check_data, **kwargs}
        
        elif name == "Missing COLOR":
            if common_sids is not None and len(common_sids) > 0:
                check_data = data[data['PRODUCT_SET_SID'].isin(common_sids)].copy()
                if check_data.empty: continue
                ckwargs = {'data': check_data, **kwargs}
        
        status_text.text(f"Running: {name}")
        
        if name == "Generic BRAND Issues":
            fas = support_files.get('category_fas', pd.DataFrame())
            ckwargs['valid_category_codes_fas'] = fas['ID'].astype(str).tolist() if not fas.empty and 'ID' in fas.columns else []
        elif name == "Missing COLOR":
            ckwargs['country_code'] = country_validator.code
        
        try:
            res = func(**ckwargs)
            if name != "Duplicate product" and not res.empty and 'PRODUCT_SET_SID' in res.columns:
                # Capture keys for Restricted Categories to propagate later
                if name in ["Seller Approve to sell books", "Seller Approved to Sell Perfume", "Counterfeit Sneakers", "Seller Not approved to sell Refurb"]:
                    res['match_key'] = res.apply(create_match_key, axis=1)
                    if name not in restricted_issue_keys: restricted_issue_keys[name] = set()
                    restricted_issue_keys[name].update(res['match_key'].unique())

                flagged_sids = set(res['PRODUCT_SET_SID'].unique())
                expanded_sids = set()
                for sid in flagged_sids:
                    if sid in duplicate_groups:
                        expanded_sids.update(duplicate_groups[sid])
                    else:
                        expanded_sids.add(sid)
                res = data[data['PRODUCT_SET_SID'].isin(expanded_sids)].copy()
            
            results[name] = res if not res.empty else pd.DataFrame(columns=data.columns)
        except Exception as e:
            logger.error(f"Error in {name}: {e}\n{traceback.format_exc()}")
            results[name] = pd.DataFrame(columns=data.columns)
        
        progress_bar.progress((i + 1) / len(validations))
    
    # IMPROVEMENT: Apply Propagation for ALL restricted categories
    if restricted_issue_keys:
        data['match_key'] = data.apply(create_match_key, axis=1)
        for flag_name, keys in restricted_issue_keys.items():
            extra_rows = data[data['match_key'].isin(keys)].copy()
            if flag_name in results:
                existing = results[flag_name]
                combined = pd.concat([existing, extra_rows]).drop_duplicates(subset=['PRODUCT_SET_SID'])
                results[flag_name] = combined
            else:
                results[flag_name] = extra_rows

    status_text.text("Finalizing...")
    rows = []
    processed = set()
    
    for name, _, _ in validations:
        if name not in results or results[name].empty:
            continue
        res = results[name]
        if 'PRODUCT_SET_SID' not in res.columns:
            continue
        
        map_name = name
        if name == "Seller Not approved to sell Refurb":
            reason_info = flags_mapping.get(name, ("1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim", f"Flagged by {name}"))
        else:
            reason_info = flags_mapping.get(name, ("1000007 - Other Reason", f"Flagged by {name}"))
        
        flagged = pd.merge(res[['PRODUCT_SET_SID']].drop_duplicates(), data, on='PRODUCT_SET_SID', how='left')
        
        for _, r in flagged.iterrows():
            sid = r['PRODUCT_SET_SID']
            if sid in processed:
                continue
            processed.add(sid)
            rows.append({
                'ProductSetSid': sid,
                'ParentSKU': r.get('PARENTSKU', ''),
                'Status': 'Rejected',
                'Reason': reason_info[0],
                # Use detailed comment if available, else default
                'Comment': r.get('Comment_Detail', reason_info[1]),
                'FLAG': name,
                'SellerName': r.get('SELLER_NAME', '')
            })
    
    approved = data[~data['PRODUCT_SET_SID'].isin(processed)]
    for _, r in approved.iterrows():
        if r['PRODUCT_SET_SID'] not in processed:
            rows.append({
                'ProductSetSid': r['PRODUCT_SET_SID'],
                'ParentSKU': r.get('PARENTSKU', ''),
                'Status': 'Approved',
                'Reason': "",
                'Comment': "",
                'FLAG': "",
                'SellerName': r.get('SELLER_NAME', '')
            })
            processed.add(r['PRODUCT_SET_SID'])
    
    progress_bar.empty()
    status_text.empty()
    return country_validator.ensure_status_column(pd.DataFrame(rows)), results

# -------------------------------------------------
# Export Logic
# -------------------------------------------------
def to_excel_base(df, sheet, cols, writer, format_rules=False):
    df_p = df.copy()
    for c in cols:
        if c not in df_p.columns:
            df_p[c] = pd.NA
    
    df_to_write = df_p[[c for c in cols if c in df_p.columns]]
    df_to_write.to_excel(writer, index=False, sheet_name=sheet)
    
    # IMPROVEMENT: Conditional Formatting
    if format_rules:
        workbook = writer.book
        worksheet = writer.sheets[sheet]
        
        red_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        green_fmt = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        
        if 'Status' in df_to_write.columns:
            status_idx = df_to_write.columns.get_loc('Status')
            # Check range length (header is row 0)
            worksheet.conditional_format(1, status_idx, len(df_to_write), status_idx,
                                         {'type': 'cell', 'criteria': 'equal', 'value': '"Rejected"', 'format': red_fmt})
            worksheet.conditional_format(1, status_idx, len(df_to_write), status_idx,
                                         {'type': 'cell', 'criteria': 'equal', 'value': '"Approved"', 'format': green_fmt})

def to_excel_full_data(data_df, final_report_df):
    try:
        output = BytesIO()
        d_cp = data_df.copy()
        r_cp = final_report_df.copy()
        d_cp['PRODUCT_SET_SID'] = d_cp['PRODUCT_SET_SID'].astype(str).str.strip()
        r_cp['ProductSetSid'] = r_cp['ProductSetSid'].astype(str).str.strip()
        
        merged = pd.merge(d_cp, r_cp[["ProductSetSid", "Status", "Reason", "Comment", "FLAG", "SellerName"]],
                          left_on="PRODUCT_SET_SID", right_on="ProductSetSid", how='left')
        
        if 'ProductSetSid_y' in merged.columns:
            merged.drop(columns=['ProductSetSid_y'], inplace=True)
        if 'ProductSetSid_x' in merged.columns:
            merged.rename(columns={'ProductSetSid_x': 'PRODUCT_SET_SID'}, inplace=True)
        
        export_cols = FULL_DATA_COLS + [c for c in ["Status", "Reason", "Comment", "FLAG", "SellerName"] if c not in FULL_DATA_COLS]
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            to_excel_base(merged, "ProductSets", export_cols, writer, format_rules=True)
            
            wb = writer.book
            ws = wb.add_worksheet('Sellers Data')
            fmt = wb.add_format({'bold': True, 'bg_color': '#E6F0FA', 'border': 1, 'align': 'center'})
            
            if 'SELLER_RATING' in merged.columns:
                merged['Rejected_Count'] = (merged['Status'] == 'Rejected').astype(int)
                merged['Approved_Count'] = (merged['Status'] == 'Approved').astype(int)
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
    except Exception:
        return BytesIO()

def to_excel(report_df, reasons_config_df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(report_df, "ProductSets", PRODUCTSETS_COLS, writer, format_rules=True)
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
        with open('validation_audit.jsonl', 'a') as f:
            f.write(json.dumps(entry)+'\n')
    except:
        pass

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
                
                data_has_warranty_cols = all(col in data.columns for col in ['PRODUCT_WARRANTY', 'WARRANTY_DURATION'])
                
                for col in ['NAME', 'BRAND', 'COLOR', 'SELLER_NAME', 'CATEGORY_CODE']:
                    if col in data.columns:
                        data[col] = data[col].astype(str).fillna('')
                
                if 'COLOR_FAMILY' not in data.columns:
                    data['COLOR_FAMILY'] = ""
                
                with st.spinner("Running validations..."):
                    common_sids_to_pass = intersection_sids if intersection_count > 0 else None
                    final_report, flag_dfs = validate_products(
                        data, support_files, country_validator, data_has_warranty_cols, common_sids_to_pass
                    )
                
                approved_df = final_report[final_report['Status'] == 'Approved']
                rejected_df = final_report[final_report['Status'] == 'Rejected']
                
                log_validation_run(country, "Multi-Upload", len(data), len(approved_df), len(rejected_df))
                
                st.sidebar.header("Seller Options")
                seller_opts = ['All Sellers'] + (data['SELLER_NAME'].dropna().unique().tolist() if 'SELLER_NAME' in data.columns else [])
                sel_sellers = st.sidebar.multiselect("Select Sellers", seller_opts, default=['All Sellers'])
                
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
                display_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'COLOR', 'PARENTSKU', 'SELLER_NAME']
                for title, df_flagged in flag_dfs.items():
                    with st.expander(f"{title} ({len(df_flagged)})"):
                        if not df_flagged.empty:
                            # 1. Prepare Display Data
                            df_display = df_flagged[[c for c in display_cols if c in df_flagged.columns]].copy()
                            
                            # 2. Add Best Designer Filters (Side-by-Side)
                            col1, col2 = st.columns([1, 1])
                            with col1:
                                search_term = st.text_input(f"🔍 Search {title}", placeholder="Name, Brand, or SKU...", key=f"search_{title}")
                            with col2:
                                all_sellers = sorted(df_display['SELLER_NAME'].astype(str).unique())
                                seller_filter = st.multiselect(f"🏪 Filter Seller ({title})", all_sellers, key=f"filter_{title}")
                            
                            # 3. Apply Filters
                            if search_term:
                                mask = df_display.apply(lambda x: x.astype(str).str.contains(search_term, case=False).any(), axis=1)
                                df_display = df_display[mask]
                            if seller_filter:
                                df_display = df_display[df_display['SELLER_NAME'].isin(seller_filter)]
                            
                            # 4. Interactive Counter
                            if len(df_display) != len(df_flagged):
                                st.caption(f"Showing {len(df_display)} of {len(df_flagged)} rows")

                            # 5. Interactive Table
                            st.dataframe(df_display, use_container_width=True, hide_index=True)
                            
                            # 6. Export Button
                            st.download_button(f"📥 Export {title}", to_excel_flag_data(df_flagged, title), f"{file_prefix}_{title}.xlsx")
                        else:
                            st.success("✅ No issues found.")
                
                st.markdown("---")
                st.header("Overall Exports")
                c1, c2, c3, c4 = st.columns(4)
                c1.download_button("Final Report", to_excel(final_report, support_files['reasons']), f"{file_prefix}_Final_Report_{current_date}.xlsx")
                c2.download_button("Rejected", to_excel(rejected_df, support_files['reasons']), f"{file_prefix}_Rejected_{current_date}.xlsx")
                c3.download_button("Approved", to_excel(approved_df, support_files['reasons']), f"{file_prefix}_Approved_{current_date}.xlsx")
                c4.download_button("Full Data", to_excel_full_data(data, final_report), f"{file_prefix}_Full_Data_{current_date}.xlsx")
            else:
                for e in errors:
                    st.error(e)
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
                st.subheader("Seller Trust Score (Top 10)")
                if not combined_df.empty and 'SELLER_NAME' in combined_df.columns:
                    seller_stats = combined_df.groupby('SELLER_NAME').agg(
                        Total=('PRODUCT_SET_SID', 'count'),
                        Rejected=('Status', lambda x: (x == 'Rejected').sum())
                    )
                    seller_stats['Trust Score'] = 100 - (seller_stats['Rejected'] / seller_stats['Total'] * 100)
                    seller_stats = seller_stats.sort_values('Rejected', ascending=False).head(10).reset_index()
                    
                    chart = alt.Chart(seller_stats).mark_bar().encode(
                        x=alt.X('SELLER_NAME', sort='-y', title='Seller'),
                        y=alt.Y('Trust Score', title='Trust Score (%)', scale=alt.Scale(domain=[0, 100])),
                        color=alt.Color('Trust Score', scale=alt.Scale(scheme='redyellowgreen')),
                        tooltip=['SELLER_NAME', 'Total', 'Rejected', 'Trust Score']
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
        if file.name.endswith('.jsonl'):
            df = pd.read_json(file, lines=True)
        elif file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        st.dataframe(df.head(50))
    else:
        try:
            st.dataframe(pd.read_json('validation_audit.jsonl', lines=True).tail(50))
        except:
            st.info("No audit log found.")
