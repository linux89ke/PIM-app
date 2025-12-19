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
            'Duplicate product': (
                '1000007 - Other Reason',
                "Kindly avoid creating duplicate SKUs"
            ),
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
                "To create the actual brand name for this product, please fill out the form at: https://bit.ly/2kpjja8.\nYou will receive an email within the coming 48 working hours the result of your request — whether it’s approved or rejected, along with the reason..Avoid using Generic for fashion items"
            ),
            'Counterfeit Sneakers': (
                '1000030 - Suspected Counterfeit/Fake Product.Please Contact Seller Support By Raising A Claim , For Questions & Inquiries (Not Authorized)',
                "This product is suspected to be counterfeit or fake and is not authorized for sale on our platform.\n\nPlease contact Seller Support to raise a claim and initiate the necessary verification process.\nIf you have any questions or need further assistance, don’t hesitate to reach out to Seller Support."
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
                "This product is suspected to be counterfeit or fake and is not authorized for sale on our platform.\n\nPlease contact Seller Support to raise a claim and initiate the necessary verification process.\nIf you have any questions or need further assistance, don’t hesitate to reach out to Seller Support."
            ),
            'Suspected Fake product': (
                '1000030 - Suspected Counterfeit/Fake Product.Please Contact Seller Support By Raising A Claim , For Questions & Inquiries (Not Authorized)',
                "This product is suspected to be counterfeit or fake and is not authorized for sale on our platform.\n\nPlease contact Seller Support to raise a claim and initiate the necessary verification process.\nIf you have any questions or need further assistance, don’t hesitate to reach out to Seller Support."
            ),
            'Product Warranty': (
                '1000013 - Kindly Provide Product Warranty Details',
                "For listing this type of product requires a valid warranty as per our platform guidelines.\nTo proceed, please ensure the warranty details are clearly mentioned in:\n\nProduct Description tab\n\nWarranty Tab.\n\nThis helps build customer trust and ensures your listing complies with Jumia’s requirements."
            ),
            'Sensitive words': (
                '1000001 - Brand NOT Allowed', 
                "Your listing was rejected because it includes brands that are not allowed on Jumia, such as Chanel, Rolex, and My Salat Mat. These brands are banned from being sold on our platform."
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
# Data Loading & Validation Logic
# -------------------------------------------------
def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Normalize headers to lowercase to match NEW_FILE_MAPPING keys
    df.columns = [str(c).strip().lower() for c in df.columns]
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
    if df.empty: return df
    cols_to_propagate = ['COLOR_FAMILY', 'PRODUCT_WARRANTY', 'WARRANTY_DURATION', 'WARRANTY_ADDRESS', 'WARRANTY_TYPE']
    for col in cols_to_propagate:
        if col not in df.columns: df[col] = pd.NA
    for col in cols_to_propagate:
        df[col] = df.groupby('PRODUCT_SET_SID')[col].transform(lambda x: x.ffill().bfill())
    return df

# --- RESTORED ORIGINAL VALIDATION LOGIC FUNCTIONS ---

def check_refurb_seller_approval(data: pd.DataFrame, approved_sellers_ke: List[str], approved_sellers_ug: List[str], country_code: str) -> pd.DataFrame:
    if country_code == 'KE':
        approved_sellers = set(approved_sellers_ke)
    elif country_code == 'UG':
        approved_sellers = set(approved_sellers_ug)
    else:
        return pd.DataFrame(columns=data.columns)

    if not {'NAME', 'BRAND', 'SELLER_NAME', 'PRODUCT_SET_SID'}.issubset(data.columns): 
        return pd.DataFrame(columns=data.columns)
    
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
    if triggered_data.empty:
        return pd.DataFrame(columns=data.columns)
    seller_not_approved_mask = ~triggered_data['SELLER_LOWER'].isin(approved_sellers)
    flagged = triggered_data[seller_not_approved_mask]
    columns_to_drop = ['NAME_LOWER', 'BRAND_LOWER', 'SELLER_LOWER']
    flagged = flagged.drop(columns=[col for col in columns_to_drop if col in flagged.columns])
    return flagged.drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_unnecessary_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_product_warranty(data: pd.DataFrame, warranty_category_codes: List[str]) -> pd.DataFrame:
    for col in ['PRODUCT_WARRANTY', 'WARRANTY_DURATION']:
        if col not in data.columns:  
            data[col] = ""
        data[col] = data[col].astype(str).fillna('').str.strip()
    if not warranty_category_codes:  
        return pd.DataFrame(columns=data.columns)
    data['CAT_CLEAN'] = data['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
    target_cats = [str(c).strip() for c in warranty_category_codes]
    target_data = data[data['CAT_CLEAN'].isin(target_cats)].copy()
    if target_data.empty:  
        return pd.DataFrame(columns=data.columns)
    def is_present(series):
        s = series.astype(str).str.strip().str.lower()
        return (s != 'nan') & (s != '') & (s != 'none') & (s != 'nat') & (s != 'n/a')
    has_product_warranty = is_present(target_data['PRODUCT_WARRANTY'])
    has_duration = is_present(target_data['WARRANTY_DURATION'])
    has_any_warranty = has_product_warranty | has_duration
    mask = ~has_any_warranty
    flagged = target_data[mask]
    if 'CAT_CLEAN' in flagged.columns:  
        flagged = flagged.drop(columns=['CAT_CLEAN'])
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

def check_duplicate_products(data: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    if len(cols) < 4: return pd.DataFrame(columns=data.columns)
    return data[data.duplicated(subset=cols, keep=False)].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_seller_approved_for_books(data: pd.DataFrame, book_category_codes: List[str], approved_book_sellers: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if books.empty: return pd.DataFrame(columns=data.columns)
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)].drop_duplicates(subset=['PRODUCT_SET_SID'])

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
    return perfume_data[final_mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_counterfeit_sneakers(data: pd.DataFrame, sneaker_category_codes: List[str], sneaker_sensitive_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'NAME', 'BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    sneaker_data = data[data['CATEGORY_CODE'].isin(sneaker_category_codes)].copy()
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
            return pd.DataFrame(columns=data.columns)
        check_data = data.copy()
        check_data['price_to_use'] = check_data['GLOBAL_SALE_PRICE'].where(
            (check_data['GLOBAL_SALE_PRICE'].notna()) & 
            (pd.to_numeric(check_data['GLOBAL_SALE_PRICE'], errors='coerce') > 0),
            check_data['GLOBAL_PRICE']
        )
        check_data['price_to_use'] = pd.to_numeric(check_data['price_to_use'], errors='coerce').fillna(0)
        check_data['price_usd'] = check_data['price_to_use']
        check_data['BRAND_LOWER'] = check_data['BRAND'].astype(str).str.strip().str.lower()
        check_data['CAT_BASE'] = check_data['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
        def is_suspected_fake(row):
            key = (row['BRAND_LOWER'], row['CAT_BASE'])
            if key in brand_category_price:
                threshold = brand_category_price[key]
                if row['price_usd'] < threshold:
                    return True
            return False
        check_data['is_fake'] = check_data.apply(is_suspected_fake, axis=1)
        flagged = check_data[check_data['is_fake'] == True].copy()
        columns_to_drop = ['price_to_use', 'price_usd', 'BRAND_LOWER', 'CAT_BASE', 'is_fake']
        flagged = flagged.drop(columns=[col for col in columns_to_drop if col in flagged.columns])
        return flagged[data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])
    except Exception as e:
        logger.error(f"Error in suspected fake product check: {e}")
        return pd.DataFrame(columns=data.columns)

def check_single_word_name(data: pd.DataFrame, book_category_codes: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_generic_brand_issues(data: pd.DataFrame, valid_category_codes_fas: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    return data[data['CATEGORY_CODE'].isin(valid_category_codes_fas) & (data['BRAND']=='Generic')].drop_duplicates(subset=['PRODUCT_SET_SID'])

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
    return flagged.drop(columns=['CAT_STR']).drop_duplicates(subset=['PRODUCT_SET_SID'])

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
        ("Duplicate product", check_duplicate_products, {}),
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
    
    for i, (name, func, kwargs) in enumerate(validations):
        if name != "Seller Not approved to sell Refurb" and country_validator.should_skip_validation(name): 
             continue
        
        ckwargs = {'data': data, **kwargs}
        if name == "Product Warranty":
            if not data_has_warranty_cols: continue
            check_data = data.copy()
            if common_sids:
                check_data = check_data[check_data['PRODUCT_SET_SID'].isin(common_sids)]
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
            if name != "Duplicate product" and not res.empty:
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
            logger.error(f"Error in {name}: {e}")
            results[name] = pd.DataFrame(columns=data.columns)
        progress_bar.progress((i + 1) / len(validations))
    
    status_text.text("Finalizing...")
    rows = []
    processed = set()
    
    for name, _, _ in validations:
        if name not in results or results[name].empty: continue
        res = results[name]
        reason_info = flags_mapping.get(name, ("1000007 - Other Reason", f"Flagged by {name}"))
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
        if r['PRODUCT_SET_SID'] not in processed:
             rows.append({
                'ProductSetSid': r['PRODUCT_SET_SID'], 'ParentSKU': r.get('PARENTSKU', ''), 'Status': 'Approved',
                'Reason': "", 'Comment': "", 'FLAG': "", 'SellerName': r.get('SELLER_NAME', '')
            })
             processed.add(r['PRODUCT_SET_SID'])
    
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
            else: row_cursor = 1
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
if 'manual_approvals' not in st.session_state:
    st.session_state.manual_approvals = set()

st.title("Product Validation Tool")
st.markdown("---")

with st.spinner("Loading configuration files..."):
    support_files = load_all_support_files()

if not support_files['flags_mapping']:
    st.error("Critical configuration files missing.")
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
                        f_bytes = uploaded_file.read()
                        uploaded_file.seek(0)
                        try:
                            raw_data = pd.read_csv(BytesIO(f_bytes), sep=';', encoding='ISO-8859-1', dtype=str)
                            if len(raw_data.columns) <= 1:
                                raw_data = pd.read_csv(BytesIO(f_bytes), sep=',', encoding='ISO-8859-1', dtype=str)
                        except:
                            raw_data = pd.read_csv(BytesIO(f_bytes), sep=',', encoding='ISO-8859-1', dtype=str)
                    
                    std_data = standardize_input_data(raw_data)
                    if 'PRODUCT_SET_SID' in std_data.columns:
                        file_sids_sets.append(set(std_data['PRODUCT_SET_SID'].unique()))
                    all_dfs.append(std_data)
                except Exception as e:
                    st.error(f"Failed to read file {uploaded_file.name}: {e}")
                    st.stop()
            
            if not all_dfs: st.stop()
            merged_data = pd.concat(all_dfs, ignore_index=True)
            st.success(f"Loaded total {len(merged_data)} rows.")
            
            intersection_sids = set.intersection(*file_sids_sets) if len(file_sids_sets) > 1 else set()
            intersection_count = len(intersection_sids)
            data_prop = propagate_metadata(merged_data)
            is_valid, errors = validate_input_schema(data_prop)
            
            if is_valid:
                data_filtered = filter_by_country(data_prop, country_validator, "Uploaded Files")
                data = data_filtered.drop_duplicates(subset=['PRODUCT_SET_SID'], keep='first')
                data_has_warranty_cols = all(col in data.columns for col in ['PRODUCT_WARRANTY', 'WARRANTY_DURATION'])
                for col in ['NAME', 'BRAND', 'COLOR', 'SELLER_NAME', 'CATEGORY_CODE']:
                    if col in data.columns: data[col] = data[col].astype(str).fillna('')
                if 'COLOR_FAMILY' not in data.columns: data['COLOR_FAMILY'] = ""
                
                with st.spinner("Running validations..."):
                    final_report, flag_dfs = validate_products(data, support_files, country_validator, data_has_warranty_cols, intersection_sids)
                
                # Apply Overrides
                final_report.loc[final_report['ProductSetSid'].isin(st.session_state.manual_approvals), 'Status'] = 'Approved'
                
                approved_df = final_report[final_report['Status'] == 'Approved']
                rejected_df = final_report[final_report['Status'] == 'Rejected']
                log_validation_run(country, "Multi-Upload", len(data), len(approved_df), len(rejected_df))
                
                # Global Search UI
                st.markdown("---")
                search_query = st.text_input("🔍 Global Search", placeholder="Search SID, Name, or Seller...").lower()
                
                # Dashboard Metrics
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Total", len(data))
                c2.metric("Approved", len(approved_df))
                c3.metric("Rejected", len(rejected_df))
                c4.metric("Rej Rate", f"{(len(rejected_df)/len(data)*100):.1f}%")
                c5.metric("Common SKUs", intersection_count)

                # Results Display
                st.subheader("Validation Results by Flag")
                for title, df_flagged in flag_dfs.items():
                    # Filter items already manually approved
                    df_remaining = df_flagged[~df_flagged['PRODUCT_SET_SID'].isin(st.session_state.manual_approvals)]
                    
                    if search_query:
                        mask = df_remaining.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
                        display_df = df_remaining[mask].copy()
                    else:
                        display_df = df_remaining.copy()

                    with st.expander(f"{title} ({len(display_df)})"):
                        if not display_df.empty:
                            display_df.insert(0, "Override Approve", False)
                            cols_to_show = ["Override Approve"] + [c for c in VISIBLE_COLUMNS if c in display_df.columns]
                            
                            edited_df = st.data_editor(
                                display_df[cols_to_show],
                                column_config={
                                    "Override Approve": st.column_config.CheckboxColumn("Approve?"),
                                    "MAIN_IMAGE": st.column_config.ImageColumn("Image")
                                },
                                disabled=[c for c in cols_to_show if c != "Override Approve"],
                                hide_index=True,
                                key=f"editor_{title}_{len(display_df)}"
                            )
                            
                            newly_approved = edited_df[edited_df["Override Approve"] == True]["PRODUCT_SET_SID"].tolist()
                            if newly_approved and st.button(f"Confirm Bulk Approval for {title}", key=f"btn_{title}"):
                                st.session_state.manual_approvals.update(newly_approved)
                                st.rerun()

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
    weekly_files = st.file_uploader("Upload Full Data Files", accept_multiple_files=True, type=['xlsx', 'csv'], key="weekly_files")
    if weekly_files:
        combined_df = pd.DataFrame()
        for f in weekly_files:
            try:
                if f.name.endswith('.xlsx'):
                    df = pd.read_excel(f, sheet_name='ProductSets', engine='openpyxl', dtype=str)
                else:
                    df = pd.read_csv(f, dtype=str)
                df.columns = df.columns.str.strip()
                df = standardize_input_data(df)
                combined_df = pd.concat([combined_df, df], ignore_index=True)
            except Exception as e: st.error(f"Error reading {f.name}: {e}")
        
        if not combined_df.empty:
            combined_df = combined_df.drop_duplicates(subset=['PRODUCT_SET_SID'])
            rejected = combined_df[combined_df['Status'] == 'Rejected'].copy()
            st.markdown("### Key Metrics")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Products", f"{len(combined_df):,}")
            m2.metric("Total Rejected", f"{len(rejected):,}")
            m3.metric("Rej Rate", f"{(len(rejected)/len(combined_df)*100):.1f}%")
            m4.metric("Unique Sellers", f"{combined_df['SELLER_NAME'].nunique():,}")

# -------------------------------------------------
# TAB 3: DATA LAKE
# -------------------------------------------------
with tab3:
    st.header("Data Lake Audit")
    try:
        df_audit = pd.read_json('validation_audit.jsonl', lines=True).tail(50)
        st.dataframe(df_audit)
    except:
        st.info("No audit log found.")
