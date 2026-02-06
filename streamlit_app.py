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

# -------------------------------------------------
# CONSTANTS & MAPPING
# -------------------------------------------------
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]
REJECTION_REASONS_COLS = ['CODE - REJECTION_REASON', 'COMMENT']

FULL_DATA_COLS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE",
    "COLOR", "COLOR_FAMILY", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU",
    "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG", "LISTING_STATUS", 
    "PRODUCT_WARRANTY", "WARRANTY_DURATION", "WARRANTY_ADDRESS", "WARRANTY_TYPE"
]
FX_RATE = 132.0
SPLIT_LIMIT = 9998 

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

# Logger setup
logger = logging.getLogger(__name__)

# -------------------------------------------------
# UTILITIES
# -------------------------------------------------
def clean_category_code(code) -> str:
    try:
        if pd.isna(code): return ""
        s = str(code).strip()
        if s.replace('.', '', 1).isdigit() and '.' in s:
            return str(int(float(s)))
        return s
    except:
        return str(code).strip()

def normalize_text(text: str) -> str:
    if pd.isna(text): return ""
    text = str(text).lower().strip()
    noise = r'\b(new|sale|original|genuine|authentic|official|premium|quality|best|hot|2024|2025)\b'
    text = re.sub(noise, '', text)
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', '', text)
    return text

def create_match_key(row: pd.Series) -> str:
    name = normalize_text(row.get('NAME', ''))
    brand = normalize_text(row.get('BRAND', ''))
    color = normalize_text(row.get('COLOR', ''))
    return f"{brand}|{name}|{color}"

# -------------------------------------------------
# ATTRIBUTE EXTRACTION
# -------------------------------------------------
from dataclasses import dataclass

COLOR_PATTERNS = {
    'red': ['red', 'crimson', 'scarlet', 'maroon', 'burgundy', 'wine', 'ruby'],
    'blue': ['blue', 'navy', 'royal', 'sky', 'azure', 'cobalt', 'sapphire'],
    'green': ['green', 'lime', 'olive', 'emerald', 'mint', 'forest', 'jade'],
    'black': ['black', 'onyx', 'ebony', 'jet', 'charcoal', 'midnight'],
    'white': ['white', 'ivory', 'cream', 'pearl', 'snow', 'alabaster'],
    'gray': ['gray', 'grey', 'silver', 'slate', 'ash', 'graphite'],
    'yellow': ['yellow', 'gold', 'golden', 'amber', 'lemon', 'mustard'],
    'orange': ['orange', 'tangerine', 'peach', 'coral', 'apricot'],
    'pink': ['pink', 'rose', 'magenta', 'fuchsia', 'salmon', 'blush'],
    'purple': ['purple', 'violet', 'lavender', 'plum', 'mauve', 'lilac'],
    'brown': ['brown', 'tan', 'beige', 'khaki', 'chocolate', 'coffee', 'bronze'],
    'multicolor': ['multicolor', 'multicolour', 'multi-color', 'rainbow', 'mixed']
}

COLOR_VARIANT_TO_BASE = {}
for base_color, variants in COLOR_PATTERNS.items():
    for variant in variants:
        COLOR_VARIANT_TO_BASE[variant] = base_color

@dataclass
class ProductAttributes:
    base_name: str
    colors: Set[str]
    sizes: Set[str]
    storage: Set[str]
    memory: Set[str]
    quantities: Set[str]
    raw_name: str
    
    def get_variant_key(self) -> str:
        parts = [self.base_name]
        if self.colors: parts.append("_color_" + "_".join(sorted(self.colors)))
        if self.sizes: parts.append("_size_" + "_".join(sorted(self.sizes)))
        if self.storage: parts.append("_storage_" + "_".join(sorted(self.storage)))
        if self.memory: parts.append("_memory_" + "_".join(sorted(self.memory)))
        if self.quantities: parts.append("_qty_" + "_".join(sorted(self.quantities)))
        return "|".join(parts).lower()
    
    def get_base_key(self) -> str:
        return self.base_name.lower()

def extract_colors(text: str, explicit_color: Optional[str] = None) -> Set[str]:
    colors = set()
    if not text: text = ""
    text_lower = str(text).lower()
    if explicit_color and pd.notna(explicit_color):
        color_lower = str(explicit_color).lower().strip()
        for variant, base in COLOR_VARIANT_TO_BASE.items():
            if variant in color_lower: colors.add(base)
    for variant, base in COLOR_VARIANT_TO_BASE.items():
        if re.search(r'\b' + re.escape(variant) + r'\b', text_lower):
            colors.add(base)
    return colors

def extract_sizes(text: str) -> Set[str]:
    if not text: return set()
    sizes = set()
    text_lower = str(text).lower()
    size_map = {
        r'\bxxs\b|2xs': 'xxs', r'\bxs\b|xsmall|extra small': 'xs', r'\bs\b|small': 'small',
        r'\bm\b|medium': 'medium', r'\bl\b|large': 'large', r'\bxl\b|xlarge|extra large': 'xl',
        r'\bxxl\b|2xl': 'xxl', r'\bxxxl\b|3xl': 'xxxl'
    }
    for pattern, size in size_map.items():
        if re.search(pattern, text_lower): sizes.add(size)
    for match in re.finditer(r'\b(\d+(?:\.\d+)?)\s*(?:inch|inches|")\b', text_lower):
        sizes.add(f"{match.group(1)}inch")
    return sizes

def extract_storage(text: str) -> Set[str]:
    if not text: return set()
    storage = set()
    for match in re.finditer(r'\b(\d+)\s*(?:gb|tb)\b', str(text).lower()):
        value, unit = match.group(1), match.group(0)
        storage.add(f"{value}{'tb' if 'tb' in unit else 'gb'}")
    return storage

def extract_memory(text: str) -> Set[str]:
    if not text: return set()
    memory = set()
    for match in re.finditer(r'\b(\d+)\s*(?:gb|mb)\s*(?:ram|memory|ddr)\b', str(text).lower()):
        value = match.group(1)
        if 2 <= int(value) <= 128: memory.add(f"{value}gb")
    return memory

def extract_quantities(text: str) -> Set[str]:
    if not text: return set()
    quantities = set()
    patterns = [r'\b(\d+)[- ]?pack\b', r'\bpack\s+of\s+(\d+)\b', r'\b(\d+)[- ]?(?:pieces?|pcs?)\b']
    text_lower = str(text).lower()
    for pattern in patterns:
        for match in re.finditer(pattern, text_lower):
            quantities.add(f"{match.group(1)}pack")
    return quantities

def remove_attributes(text: str) -> str:
    if not text: return ""
    base = str(text).lower()
    for variant in COLOR_VARIANT_TO_BASE.keys():
        base = re.sub(r'\b' + re.escape(variant) + r'\b', '', base)
    base = re.sub(r'\b(?:xxs|xs|small|medium|large|xl|xxl|xxxl)\b', '', base)
    base = re.sub(r'\b\d+\s*(?:gb|tb|inch|inches|"|ram|memory|ddr|pack|piece|pcs)\b', '', base)
    noise = ['new', 'original', 'genuine', 'authentic', 'official', 'premium', 'quality', 'best', 'hot', 'sale', 'promo', 'deal']
    for word in noise:
        base = re.sub(r'\b' + word + r'\b', '', base)
    base = re.sub(r'[^\w\s]', ' ', base)
    base = re.sub(r'\s+', ' ', base)
    return base.strip()

def extract_product_attributes(name: str, explicit_color: Optional[str] = None, brand: Optional[str] = None) -> ProductAttributes:
    if not name or pd.isna(name): name = ""
    name_str = str(name).strip()
    colors = extract_colors(name_str, explicit_color)
    sizes = extract_sizes(name_str)
    storage = extract_storage(name_str)
    memory = extract_memory(name_str)
    quantities = extract_quantities(name_str)
    attrs = ProductAttributes(base_name="", colors=colors, sizes=sizes, storage=storage, memory=memory, quantities=quantities, raw_name=name_str)
    base_name = remove_attributes(name_str)
    if brand and pd.notna(brand):
        brand_lower = str(brand).lower().strip()
        if brand_lower not in base_name and brand_lower not in ['generic', 'fashion']:
            base_name = f"{brand_lower} {base_name}"
    attrs.base_name = base_name.strip()
    return attrs

# -------------------------------------------------
# HELPER & LOADING FUNCTIONS
# -------------------------------------------------

def load_txt_file(filename: str) -> List[str]:
    try:
        full_path = os.path.abspath(filename)
        if not os.path.exists(full_path):
            st.warning(f"File Not Found: {filename} (looked in {os.getcwd()})")
            return []
        with open(filename, 'r', encoding='utf-8') as f:
            data = [line.strip() for line in f if line.strip()]
        if not data:
            st.warning(f"File is Empty: {filename}")
        return data
    except UnicodeDecodeError:
        st.error(f"Encoding Error: '{filename}' is not UTF-8.")
        return []
    except Exception as e:
        st.error(f"Error reading {filename}: {e}")
        return []

@st.cache_data(ttl=3600)
def load_excel_file(filename: str, column: Optional[str] = None):
    try:
        if not os.path.exists(filename): return [] if column else pd.DataFrame()
        df = pd.read_excel(filename, engine='openpyxl', dtype=str)
        df.columns = df.columns.str.strip()
        if column and column in df.columns:
            return df[column].apply(clean_category_code).tolist()
        return df
    except Exception as e:
        logger.error(f"Error reading {filename}: {e}")
        return [] if column else pd.DataFrame()

@st.cache_data(ttl=3600)
def load_restricted_brands_config(filename: str) -> Dict:
    config = {}
    try:
        if not os.path.exists(filename): return {}
        df1 = pd.read_excel(filename, sheet_name=0, engine='openpyxl', dtype=str)
        df1.columns = df1.columns.str.strip()
        try:
            df2 = pd.read_excel(filename, sheet_name=1, engine='openpyxl', dtype=str)
            df2.columns = df2.columns.str.strip()
        except: df2 = pd.DataFrame()

        for _, row in df1.iterrows():
            brand_raw = str(row.get('Brand', '')).strip()
            if not brand_raw or brand_raw.lower() == 'nan': continue
            brand_key = brand_raw.lower()
            sellers = set()
            if 'Sellers' in row and pd.notna(row['Sellers']):
                s = str(row['Sellers']).strip()
                if s.lower() != 'nan': sellers.add(s.lower())
            for col in df1.columns:
                if 'Unnamed' in col or col == 'Sellers':
                    val = str(row[col]).strip()
                    if val and val.lower() != 'nan' and col != 'Brand' and col != 'check name': sellers.add(val.lower())
            config[brand_key] = {'sellers': sellers, 'categories': None}

        if not df2.empty:
            for col in df2.columns:
                brand_header_key = str(col).strip().lower()
                if brand_header_key in config:
                    cats = df2[col].dropna().astype(str).apply(clean_category_code).tolist()
                    if cats: config[brand_header_key]['categories'] = set(cats)
        return config
    except Exception as e:
        logger.error(f"Error loading restricted brands: {e}")
        return {}

@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    try:
        return {
            'Restricted brands': (
                '1000024 - Product does not have a license to be sold via Jumia (Not Authorized)',
                "Your product listing has been rejected due to the absence of a required license for this item.\nAs a result, the product cannot be authorized for sale on Jumia.\n\nPlease ensure that you obtain and submit the necessary license(s) before attempting to relist the product.\nFor further assistance or clarification, Please raise a claim via Vendor Center."
            ),
            'Suspected Fake product': (
                '1000023 - Confirmation of counterfeit product by Jumia technical team (Not Authorized)',
                "Your listing has been rejected as Jumia’s technical team has confirmed the product is counterfeit.\nAs a result, this item cannot be sold on the platform.\n\nPlease ensure that all products listed are 100% authentic to comply with Jumia’s policies and protect customer trust.\n\nIf you believe this decision is incorrect or need further clarification, please contact the Seller Support team"
            ),
            'Seller Not approved to sell Refurb': (
                '1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim',
                "Please contact Jumia Seller Support and raise a claim to confirm whether this refurbished product is eligible for listing.\nThis step will help ensure that all necessary requirements and approvals are addressed before proceeding with the sale, and prevent any future compliance issues."
            ),
            'Product Warranty': (
                '1000013 - Kindly Provide Product Warranty Details',
                "For listing this type of product requires a valid warranty as per our platform guidelines.\nTo proceed, please ensure the warranty details are clearly mentioned in:\n\nProduct Description tab\n\nWarranty Tab.\n\nThis helps build customer trust and ensures your listing complies with Jumia’s requirements."
            ),
            'Seller Approve to sell books': (
                '1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim',
                "Please contact Jumia Seller Support and raise a claim to confirm whether this book is eligible for listing.\nThis step will help ensure that all necessary requirements and approvals are addressed before proceeding with the sale, and prevent any future compliance issues."
            ),
            'Seller Approved to Sell Perfume': (
                '1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim',
                "Please contact Jumia Seller Support and raise a claim to confirm whether this perfume is eligible for listing.\nThis step will help ensure that all necessary requirements and approvals are addressed before proceeding with the sale, and prevent any future compliance issues."
            ),
            'Counterfeit Sneakers': (
                '1000023 - Confirmation of counterfeit product by Jumia technical team (Not Authorized)',
                "Your listing has been rejected as Jumia’s technical team has confirmed the product is counterfeit.\nAs a result, this item cannot be sold on the platform.\n\nPlease ensure that all products listed are 100% authentic to comply with Jumia’s policies and protect customer trust.\n\nIf you believe this decision is incorrect or need further clarification, please contact the Seller Support team"
            ),
            'Suspected counterfeit Jerseys': (
                '1000023 - Confirmation of counterfeit product by Jumia technical team (Not Authorized)',
                "Your listing has been rejected as Jumia’s technical team has confirmed the product is counterfeit.\nAs a result, this item cannot be sold on the platform.\n\nPlease ensure that all products listed are 100% authentic to comply with Jumia’s policies and protect customer trust.\n\nIf you believe this decision is incorrect or need further clarification, please contact the Seller Support team"
            ),
            'Prohibited products': (
                '1000007 - Other Reason',
                "Please note listing of this product is prohibited … Please contact Jumia Seller Support and raise a claim"
            ),
            'Unnecessary words in NAME': (
                '1000008 - Kindly Improve Product Name Description',
                "Kindly update the product title using this format: Name – Type of the Products – Color.avoid unnecesary words"
            ),
            'Single-word NAME': (
                '1000008 - Kindly Improve Product Name Description',
                "Kindly update the product title using this format: Name – Type of the Products – Color.\nIf available, please also add key details such as weight, capacity, type, and warranty to make the title clear and complete for customers."
            ),
            'Generic BRAND Issues': (
                '1000007 - Other Reason',
                "Please use the correct brand for Fashion items or use Fashion ..To create the actual brand name for this product, please fill out the form at: https://bit.ly/2kpjja8.\nYou will receive an email within the coming 48 working hours the result of your request — whether it’s approved or rejected, along with the reason"
            ),
            'Fashion brand issues': (
                '1000007 - Other Reason',
                "Please use the correct brand for this item instead of Fashion use Generic ..To create the actual brand name for this product, please fill out the form at: https://bit.ly/2kpjja8.\nYou will receive an email within the coming 48 working hours the result of your request — whether it’s approved or rejected, along with the reason"
            ),
            'BRAND name repeated in NAME': (
                '1000007 - Other Reason',
                "Please note that brand name should not be repeated in product name"
            ),
            'Generic branded products with genuine brands': (
                '1000007 - Other Reason',
                "Kindly use the displayed brand on the product instead of Generic"
            ),
            'Missing COLOR': (
                '1000005 - Kindly confirm the actual product colour',
                "Please make sure that the product color is clearly mentioned in both the title and in the color tab.\nAlso, the images you upload must match the exact color being sold in this specific listing.\nAvoid including pictures of other colors, as this may confuse customers and lead to order cancellations."
            ),
            'Duplicate product': (
                '1000007 - Other Reason',
                "Please note this product is a duplicate"
            ),
        }
    except Exception:
        return {}

@st.cache_data(ttl=3600)
def load_all_support_files() -> Dict:
    def safe_load_txt(f): return load_txt_file(f) if os.path.exists(f) else []

    files = {
        'blacklisted_words': safe_load_txt('blacklisted.txt'),
        'book_category_codes': load_excel_file('Books_cat.xlsx', 'CategoryCode'),
        'approved_book_sellers': load_excel_file('Books_Approved_Sellers.xlsx', 'SellerName'),
        'perfume_category_codes': safe_load_txt('Perfume_cat.txt'),
        'sensitive_perfume_brands': [b.lower() for b in safe_load_txt('sensitive_perfumes.txt')],
        'approved_perfume_sellers': load_excel_file('perfumeSellers.xlsx', 'SellerName'),
        'sneaker_category_codes': safe_load_txt('Sneakers_Cat.txt'),
        'sneaker_sensitive_brands': [b.lower() for b in safe_load_txt('Sneakers_Sensitive.txt')],
        'sensitive_words': [w.lower() for w in safe_load_txt('sensitive_words.txt')],
        'unnecessary_words': [w.lower() for w in safe_load_txt('unnecessary.txt')],
        'colors': [c.lower() for c in safe_load_txt('colors.txt')],
        'color_categories': safe_load_txt('color_cats.txt'),
        'category_fas': load_excel_file('category_FAS.xlsx'),
        'reasons': load_excel_file('reasons.xlsx'),
        'flags_mapping': load_flags_mapping(),
        'jerseys_config': load_excel_file('Jerseys.xlsx'),
        'warranty_category_codes': safe_load_txt('warranty.txt'),
        'suspected_fake': load_excel_file('suspected_fake.xlsx'),
        'approved_refurb_sellers_ke': [s.lower() for s in safe_load_txt('Refurb_LaptopKE.txt')],
        'approved_refurb_sellers_ug': [s.lower() for s in safe_load_txt('Refurb_LaptopUG.txt')],
        'duplicate_exempt_codes': safe_load_txt('duplicate_exempt.txt'),
        'restricted_brands_config': load_restricted_brands_config('restric_brands.xlsx'),
        'known_brands': safe_load_txt('brands.txt'), 
    }
    return files

@st.cache_data(ttl=3600)
def load_support_files_lazy():
    with st.spinner("Loading configuration files..."):
        support_files = load_all_support_files()
    return support_files

@st.cache_data(ttl=3600)
def compile_regex_patterns(words: List[str]) -> re.Pattern:
    if not words: return None
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
        if df.empty: return df
        if 'Status' not in df.columns: df['Status'] = 'Approved'
        return df
    
    @st.cache_data(ttl=3600)
    def load_prohibited_products(_self) -> List[str]:
        return [w.lower() for w in load_txt_file(_self.config["prohibited_products_file"])]

# -------------------------------------------------
# Data Loading & Validation Functions
# -------------------------------------------------
def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()
    map_lower = {k.lower(): v for k, v in NEW_FILE_MAPPING.items()}
    new_cols = {}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in map_lower:
            new_cols[col] = map_lower[col_lower]
        else:
            new_cols[col] = col.upper()
    df = df.rename(columns=new_cols)
    for col in ['ACTIVE_STATUS_COUNTRY', 'CATEGORY_CODE', 'BRAND', 'TAX_CLASS', 'NAME', 'SELLER_NAME']:
        if col in df.columns:
            df[col] = df[col].astype(str)
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
    cols = ['COLOR_FAMILY', 'PRODUCT_WARRANTY', 'WARRANTY_DURATION', 'WARRANTY_ADDRESS', 'WARRANTY_TYPE']
    for col in cols:
        if col not in df.columns: df[col] = pd.NA
        df[col] = df.groupby('PRODUCT_SET_SID')[col].transform(lambda x: x.ffill().bfill())
    return df

# --- Validation Logic Functions ---

def check_duplicate_products(
    data: pd.DataFrame,
    exempt_categories: List[str] = None,
    similarity_threshold: float = 0.70,
    known_colors: List[str] = None,
    **kwargs
) -> pd.DataFrame:
    """
    Duplicate Check (Text-Based Only)
    Recognizes color/size/storage variants as DIFFERENT products.
    """
    duplicate_threshold = int(similarity_threshold * 100) if similarity_threshold <= 1 else int(similarity_threshold)
    required_cols = ['NAME', 'SELLER_NAME', 'BRAND']
    if not all(col in data.columns for col in required_cols): return pd.DataFrame(columns=data.columns)
    
    data_to_check = data.copy()
    if exempt_categories and 'CATEGORY_CODE' in data_to_check.columns:
        data_cats = data_to_check['CATEGORY_CODE'].apply(clean_category_code)
        exempt_set = set(clean_category_code(c) for c in exempt_categories)
        data_to_check = data_to_check[~data_cats.isin(exempt_set)]
    
    if data_to_check.empty: return pd.DataFrame(columns=data.columns)
    
    def extract_attrs_row(row):
        return extract_product_attributes(name=row['NAME'], explicit_color=row.get('COLOR'), brand=row.get('BRAND'))
    
    data_to_check['_attributes'] = data_to_check.apply(extract_attrs_row, axis=1)
    data_to_check['_base_key'] = data_to_check['_attributes'].apply(lambda x: x.get_base_key())
    data_to_check['_variant_key'] = data_to_check['_attributes'].apply(lambda x: x.get_variant_key())
    data_to_check['_seller_lower'] = data_to_check['SELLER_NAME'].astype(str).str.strip().str.lower()
    
    rejected_sids = set()
    duplicate_details = {}
    grouped = data_to_check.groupby(['_seller_lower', '_base_key'])
    
    for (seller, base_key), group in grouped:
        if len(group) < 2: continue
        variant_groups = group.groupby('_variant_key')
        
        for variant_key, variant_group in variant_groups:
            if len(variant_group) < 2: continue
            products = variant_group.to_dict('records')
            
            for i in range(len(products)):
                current = products[i]
                current_sid = str(current['PRODUCT_SET_SID'])
                if current_sid in rejected_sids: continue
                potential_duplicates = []
                
                for j in range(i + 1, len(products)):
                    compare = products[j]
                    compare_sid = str(compare['PRODUCT_SET_SID'])
                    if compare_sid in rejected_sids: continue
                    
                    attrs_A = current['_attributes']
                    attrs_B = compare['_attributes']
                    score = 0
                    tokens_A = set(attrs_A.base_name.split())
                    tokens_B = set(attrs_B.base_name.split())
                    if tokens_A and tokens_B:
                        similarity = len(tokens_A & tokens_B) / len(tokens_A | tokens_B)
                        score += similarity * 70
                    if current['_seller_lower'] == compare['_seller_lower']: score += 30
                    
                    if score >= duplicate_threshold:
                        potential_duplicates.append({'sid': compare_sid, 'score': score})
                
                if len(potential_duplicates) >= 2:
                    for dup in potential_duplicates:
                        rejected_sids.add(dup['sid'])
                        attrs = current['_attributes']
                        variant_desc = []
                        if attrs.colors: variant_desc.append(f"Color: {', '.join(attrs.colors)}")
                        if attrs.sizes: variant_desc.append(f"Size: {', '.join(attrs.sizes)}")
                        if attrs.storage: variant_desc.append(f"Storage: {', '.join(attrs.storage)}")
                        duplicate_details[dup['sid']] = {
                            'base': base_key[:40],
                            'variant': ", ".join(variant_desc) if variant_desc else "Same specs",
                            'score': dup['score']
                        }
    
    if not rejected_sids: return pd.DataFrame(columns=data.columns)
    rejected_df = data_to_check[data_to_check['PRODUCT_SET_SID'].astype(str).isin(rejected_sids)].copy()
    
    def add_comment(row):
        sid = str(row['PRODUCT_SET_SID'])
        if sid in duplicate_details:
            details = duplicate_details[sid]
            return f"Duplicate: Base '{details['base']}', {details['variant']}, Confidence: {details['score']:.0f}%"
        return "Duplicate detected"
    
    rejected_df['Comment_Detail'] = rejected_df.apply(add_comment, axis=1)
    cols_to_drop = ['_attributes', '_base_key', '_variant_key', '_seller_lower']
    rejected_df = rejected_df.drop(columns=[c for c in cols_to_drop if c in rejected_df.columns])
    return rejected_df[data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_restricted_brands(data: pd.DataFrame, restricted_config: Dict) -> pd.DataFrame:
    if not all(c in data.columns for c in ['NAME', 'BRAND', 'SELLER_NAME']) or not restricted_config:
        return pd.DataFrame(columns=data.columns)

    data_to_check = data.copy()
    data_to_check['NAME_LOWER'] = data_to_check['NAME'].astype(str).str.lower().str.strip()
    data_to_check['BRAND_LOWER'] = data_to_check['BRAND'].astype(str).str.lower().str.strip()
    data_to_check['SELLER_LOWER'] = data_to_check['SELLER_NAME'].astype(str).str.lower().str.strip()
    data_to_check['CAT_CODE_CLEAN'] = data_to_check['CATEGORY_CODE'].apply(clean_category_code)

    flagged_indices = set()
    for brand_key, rules in restricted_config.items():
        pattern = re.compile(r'\b' + re.escape(brand_key) + r'\b', re.IGNORECASE)
        mask_match = (data_to_check['BRAND_LOWER'].str.contains(pattern, regex=True) |
                      data_to_check['NAME_LOWER'].str.contains(pattern, regex=True))
        potential_rows = data_to_check[mask_match]
        
        if potential_rows.empty: continue
        
        restricted_cats = rules.get('categories')
        if restricted_cats:
            target_rows = potential_rows[potential_rows['CAT_CODE_CLEAN'].isin(restricted_cats)]
        else:
            target_rows = potential_rows
            
        if target_rows.empty: continue

        allowed_sellers = rules.get('sellers', set())
        if not allowed_sellers:
            flagged_indices.update(target_rows.index)
        else:
            mask_unauthorized = ~target_rows['SELLER_LOWER'].isin(allowed_sellers)
            flagged_indices.update(target_rows[mask_unauthorized].index)

    if not flagged_indices: return pd.DataFrame(columns=data.columns)
    return data.loc[list(flagged_indices)].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_refurb_seller_approval(data: pd.DataFrame, approved_sellers_ke: List[str], approved_sellers_ug: List[str], country_code: str) -> pd.DataFrame:
    if country_code == 'KE': approved_sellers = set(approved_sellers_ke)
    elif country_code == 'UG': approved_sellers = set(approved_sellers_ug)
    else: return pd.DataFrame(columns=data.columns)
    
    if not {'NAME', 'BRAND', 'SELLER_NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    
    data = data.copy()
    refurb_words = r'\b(refurb|refurbished|renewed)\b'
    data['NAME_LOWER'] = data['NAME'].astype(str).str.strip().str.lower()
    data['SELLER_LOWER'] = data['SELLER_NAME'].astype(str).str.strip().str.lower()
    
    trigger_mask = data['NAME_LOWER'].str.contains(refurb_words, regex=True, na=False) | (data['BRAND'].astype(str).str.lower() == 'renewed')
    triggered_data = data[trigger_mask].copy()
    if triggered_data.empty: return pd.DataFrame(columns=data.columns)
    
    return triggered_data[~triggered_data['SELLER_LOWER'].isin(approved_sellers)].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_unnecessary_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    data.loc[mask, 'Comment_Detail'] = "Matched keyword in Name"
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_product_warranty(data: pd.DataFrame, warranty_category_codes: List[str]) -> pd.DataFrame:
    for col in ['PRODUCT_WARRANTY', 'WARRANTY_DURATION']:
        if col not in data.columns: data[col] = ""
        data[col] = data[col].astype(str).fillna('').str.strip()
    if not warranty_category_codes: return pd.DataFrame(columns=data.columns)
    
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
    if not {'CATEGORY_CODE', 'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    
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

def check_seller_approved_for_books(data: pd.DataFrame, book_category_codes: List[str], approved_book_sellers: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    book_cats = set(clean_category_code(c) for c in book_category_codes)
    books = data[data_cats.isin(book_cats)]
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_category_codes: List[str], approved_perfume_sellers: List[str], sensitive_perfume_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
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
    if not all(c in data.columns for c in required_cols) or suspected_fake_df.empty: return pd.DataFrame(columns=data.columns)
    
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
        check_data['BRAND_LOWER'] = check_data['BRAND'].astype(str).str.strip().str.lower()
        check_data['CAT_BASE'] = check_data['CATEGORY_CODE'].apply(clean_category_code)
        
        def is_suspected_fake(row):
            key = (row['BRAND_LOWER'], row['CAT_BASE'])
            if key in brand_category_price:
                return row['price_to_use'] < brand_category_price[key]
            return False
        
        check_data['is_fake'] = check_data.apply(is_suspected_fake, axis=1)
        return check_data[check_data['is_fake'] == True][data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])
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

def check_fashion_brand_issues(data: pd.DataFrame, valid_category_codes_fas: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns): 
        return pd.DataFrame(columns=data.columns)
    
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    fas_cats = set(clean_category_code(c) for c in valid_category_codes_fas)
    
    # Check for 'Fashion' case-insensitive
    brand_is_fashion = data['BRAND'].astype(str).str.strip().str.lower() == 'fashion'
    cat_not_in_fas = ~data_cats.isin(fas_cats)
    
    return data[brand_is_fashion & cat_not_in_fas].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'NAME', 'SELLER_NAME'}.issubset(data.columns) or jerseys_df.empty: return pd.DataFrame(columns=data.columns)
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

def check_generic_with_brand_in_name(data: pd.DataFrame, brands_list: List[str]) -> pd.DataFrame:
    if not {'NAME', 'BRAND'}.issubset(data.columns) or not brands_list:
        return pd.DataFrame(columns=data.columns)

    is_generic = data['BRAND'].astype(str).str.strip().str.lower() == 'generic'
    generic_items = data[is_generic].copy()
    
    if generic_items.empty:
        return pd.DataFrame(columns=data.columns)

    sorted_brands = sorted([str(b).strip().lower() for b in brands_list if b], key=len, reverse=True)

    def normalize_text(text):
        text = str(text).lower()
        text = re.sub(r"['\.\-]", ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def detect_brand(name):
        name_clean = normalize_text(name)
        for brand in sorted_brands:
            brand_clean = normalize_text(brand)
            if name_clean.startswith(brand_clean):
                if len(name_clean) > len(brand_clean):
                    next_char = name_clean[len(brand_clean)]
                    if next_char.isalnum(): continue 
                return brand.title()
        return None

    generic_items['Detected_Brand'] = generic_items['NAME'].apply(detect_brand)
    flagged = generic_items[generic_items['Detected_Brand'].notna()].copy()
    
    if not flagged.empty:
        flagged['Comment_Detail'] = "Detected Brand: " + flagged['Detected_Brand']
        
    return flagged.drop_duplicates(subset=['PRODUCT_SET_SID'])

# -------------------------------------------------
# Master validation runner
# -------------------------------------------------
def validate_products(data: pd.DataFrame, support_files: Dict, country_validator: CountryValidator, data_has_warranty_cols: bool, common_sids: Optional[set] = None):
    # Ensure ID match compatibility
    data['PRODUCT_SET_SID'] = data['PRODUCT_SET_SID'].astype(str).str.strip()
    
    flags_mapping = support_files['flags_mapping']
    
    validations = [
        ("Restricted brands", check_restricted_brands, {'restricted_config': support_files['restricted_brands_config']}),
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
        ("Fashion brand issues", check_fashion_brand_issues, {}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Generic branded products with genuine brands", check_generic_with_brand_in_name, {'brands_list': support_files.get('known_brands', [])}),
        ("Missing COLOR", check_missing_color, {'pattern': compile_regex_patterns(support_files['colors']), 'color_categories': support_files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {
            'exempt_categories': support_files.get('duplicate_exempt_codes', []),
            'known_colors': support_files['colors'],
        }),
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
                    duplicate_groups[sid] =
