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
def load_excel_file(filename: str, column: Optional[str] = None):
    try:
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
    try:
        flags_df = pd.read_excel('flags.xlsx')
        flags_df.columns = flags_df.columns.str.strip()

        flag_mapping = {
            'Sensitive words': (
                '1000001 - Brand NOT Allowed',
                "Your listing was rejected because it includes brands that are not allowed on Jumia..."
            ),
            'BRAND name repeated in NAME': (
                '1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name',
                "Please do not write the brand name in the Product Name field..."
            ),
            'Missing COLOR': (
                '1000005 - Kindly confirm the actual product colour',
                "Please make sure that the product color is clearly mentioned..."
            ),
            'Duplicate product': (
                '1000007 - Other Reason',
                "kindly note product was rejected because its a duplicate product"
            ),
            'Prohibited products': (
                '1000007 - Other Reason',
                "Kindly note this product is not allowed for listing on Jumia..."
            ),
            'Single-word NAME': (
                '1000008 - Kindly Improve Product Name Description',
                "Kindly update the product title using this format..."
            ),
            'Generic BRAND Issues': (
                '1000014 - Kindly request for the creation of this product\'s actual brand name...',
                "To create the actual brand name..."
            ),
            'Counterfeit Sneakers': (
                '1000023 - Confirmation of counterfeit product by Jumia technical team (Not Authorized)',
                "Your listing has been rejected as Jumia's technical team has confirmed..."
            ),
            'Seller Approve to sell books': (
                '1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale...',
                "Please contact Jumia Seller Support and raise a claim..."
            ),
            'Seller Approved to Sell Perfume': (
                '1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale...',
                "Please contact Jumia Seller Support and raise a claim..."
            ),
            'Perfume Price Check': (
                '1000029 - Kindly Contact Jumia Seller Support To Verify This Product\'s Authenticity...',
                "Please contact Jumia Seller Support to raise a claim..."
            ),
            'Suspected counterfeit Jerseys': (
                '1000030 - Suspected Counterfeit/Fake Product.Please Contact Seller Support By Raising A Claim , For Questions & Inquiries (Not Authorized)',
                "This product is suspected to be a counterfeit or fake jersey and is not authorized for sale on our platform.\n\n"
                "Please contact Seller Support to raise a claim and initiate the necessary verification process.\n"
                "If you have any questions or need further assistance, don't hesitate to reach out to Seller Support."
            ),
        }

        logger.info(f"Loaded {len(flag_mapping)} flag mappings")
        st.success(f"Loaded {len(flag_mapping)} validation flag mappings")
        return flag_mapping

    except FileNotFoundError:
        logger.error("flags.xlsx not found")
        st.error("flags.xlsx not found. This file is required for validation.")
        return {}
    except Exception as e:
        logger.error(f"Error loading flags.xlsx: {e}", exc_info=True)
        st.error(f"Error loading flags.xlsx: {e}")
        return {}

@st.cache_data(ttl=3600)
def load_all_support_files() -> Dict:
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
        'jerseys': load_excel_file('Jerseys.xlsx'),  # ← NEW: Jersey rules
    }
    logger.info("All support files loaded successfully")
    return files

@st.cache_data(ttl=3600)
def compile_regex_patterns(words: List[str]) -> re.Pattern:
    if not words:
        return None
    pattern = '|'.join(r'\b' + re.escape(w) + r'\b' for w in words)
    return re.compile(pattern, re.IGNORECASE)

# -------------------------------------------------
# Country-Specific Configuration
# -------------------------------------------------
class CountryValidator:
    COUNTRY_CONFIG = {
        "Kenya": {"code": "KE", "skip_validations": [], "prohibited_products_file": "prohibited_productsKE.txt"},
        "Uganda": {"code": "UG", "skip_validations": [
            "Seller Approve to sell books", "Perfume Price Check",
            "Seller Approved to Sell Perfume", "Counterfeit Sneakers"
        ], "prohibited_products_file": "prohibited_productsUG.txt"}
    }

    def __init__(self, country: str):
        self.country = country
        self.config = self.COUNTRY_CONFIG.get(country, self.COUNTRY_CONFIG["Kenya"])
        self.code = self.config["code"]
        self.skip_validations = self.config["skip_validations"]

    def should_skip_validation(self, validation_name: str) -> bool:
        return validation_name in self.skip_validations

    def ensure_status_column(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or 'Status' in df.columns:
            return df
        df['Status'] = 'Approved'
        return df

    @st.cache_data(ttl=3600)
    def load_prohibited_products(_self) -> List[str]:
        filename = _self.config["prohibited_products_file"]
        return [w.lower() for w in load_txt_file(filename)]

# -------------------------------------------------
# Input Validation
# -------------------------------------------------
def validate_input_schema(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    errors = []
    required = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'ACTIVE_STATUS_COUNTRY']
    for col in required:
        if col not in df.columns:
            errors.append(f"Missing required column: {col}")
    if df['PRODUCT_SET_SID'].isna().all():
        errors.append("PRODUCT_SET_SID column is empty")
    if df['NAME'].isna().all():
        errors.append("NAME column is empty")
    if len(df) == 0:
        errors.append("File is empty")
    return len(errors) == 0, errors

# -------------------------------------------------
# Country Filter
# -------------------------------------------------
def filter_by_country(df: pd.DataFrame, country_validator: CountryValidator, source: str) -> pd.DataFrame:
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns:
        st.warning(f"ACTIVE_STATUS_COUNTRY missing in {source}")
        return df
    df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.upper().str.strip()
    mask = df['ACTIVE_STATUS_COUNTRY'].str.contains(rf'\b{country_validator.code}\b', na=False)
    filtered = df[mask].copy()
    if filtered.empty:
        st.error(f"No {country_validator.code} products found!")
        st.stop()
    return filtered

# -------------------------------------------------
# VECTORIZED VALIDATION CHECKS
# -------------------------------------------------
def check_sensitive_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None:
        return pd.DataFrame(columns=data.columns)
    data = data.copy()
    data['NAME_LOWER'] = data['NAME'].astype(str).str.lower()
    return data[data['NAME_LOWER'].str.contains(pattern, na=False)].drop(columns=['NAME_LOWER'])

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None:
        return pd.DataFrame(columns=data.columns)
    data = data.copy()
    data['NAME_LOWER'] = data['NAME'].astype(str).str.lower()
    return data[data['NAME_LOWER'].str.contains(pattern, na=False)].drop(columns=['NAME_LOWER'])

def check_missing_color(data: pd.DataFrame, pattern: re.Pattern, color_categories: List[str]) -> pd.DataFrame:
    if not {'NAME', 'COLOR', 'CATEGORY_CODE'}.issubset(data.columns) or not pattern or not color_categories:
        return pd.DataFrame(columns=data.columns)
    data = data[data['CATEGORY_CODE'].isin(color_categories)].copy()
    if data.empty: return pd.DataFrame(columns=data.columns)
    data['NAME_LOWER'] = data['NAME'].astype(str).str.lower()
    data['COLOR_LOWER'] = data['COLOR'].astype(str).str.lower()
    mask = ~(data['NAME_LOWER'].str.contains(pattern, na=False) | data['COLOR_LOWER'].str.contains(pattern, na=False))
    return data[mask].drop(columns=['NAME_LOWER', 'COLOR_LOWER'])

def check_brand_in_name(data: pd.DataFrame) -> pd.DataFrame:
    if not {'BRAND', 'NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    data = data.copy()
    data['BRAND_L'] = data['BRAND'].astype(str).str.strip().str.lower()
    data['NAME_L'] = data['NAME'].astype(str).str.strip().str.lower()
    mask = data.apply(lambda x: x['BRAND_L'] in x['NAME_L'] if x['BRAND_L'] and x['NAME_L'] else False, axis=1)
    return data[mask].drop(columns=['BRAND_L', 'NAME_L'])

def check_duplicate_products(data: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    return data[data.duplicated(subset=cols, keep=False)] if len(cols) >= 3 else pd.DataFrame(columns=data.columns)

def check_seller_approved_for_books(data: pd.DataFrame, book_category_codes: List[str], approved_book_sellers: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)] if not books.empty and approved_book_sellers else pd.DataFrame(columns=data.columns)

# FIXED: Missing comma in fake_brands list
def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_category_codes: List[str],
                                     approved_perfume_sellers: List[str], sensitive_perfume_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME','BRAND','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    perf = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perf.empty or not approved_perfume_sellers: return pd.DataFrame(columns=data.columns)

    perf['BRAND_L'] = perf['BRAND'].astype(str).str.lower()
    perf['NAME_L'] = perf['NAME'].astype(str).str.lower()

    sensitive = perf['BRAND_L'].isin(sensitive_perfume_brands)
    fake_brands = ['designers collection', 'smart collection', 'generic', 'original', 'designer', 'fashion']  # ← FIXED!
    fake_brand = perf['BRAND_L'].isin(fake_brands)
    name_has_sensitive = perf['NAME_L'].apply(lambda x: any(b in x for b in sensitive_perfume_brands))

    mask = (sensitive | (fake_brand & name_has_sensitive)) & (~perf['SELLER_NAME'].isin(approved_perfume_sellers))
    return perf[mask].drop(columns=['BRAND_L', 'NAME_L'])

def check_counterfeit_sneakers(data: pd.DataFrame, sneaker_category_codes: List[str], sneaker_sensitive_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'NAME', 'BRAND'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    sneaker = data[data['CATEGORY_CODE'].isin(sneaker_category_codes)].copy()
    if sneaker.empty or not sneaker_sensitive_brands: return pd.DataFrame(columns=data.columns)
    sneaker['NAME_L'] = sneaker['NAME'].astype(str).str.lower()
    sneaker['BRAND_L'] = sneaker['BRAND'].astype(str).str.lower()
    fake = sneaker['BRAND_L'].isin(['generic', 'fashion'])
    name_has = sneaker['NAME_L'].apply(lambda x: any(b in x for b in sneaker_sensitive_brands))
    return sneaker[fake & name_has].drop(columns=['NAME_L', 'BRAND_L'])

# NEW: Suspected counterfeit Jerseys
def check_suspected_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'NAME', 'SELLER_NAME'}.issubset(data.columns) or jerseys_df.empty:
        return pd.DataFrame(columns=data.columns)

    req = ['Categories', 'Checklist', 'Exempted']
    if not all(c in jerseys_df.columns for c in req):
        st.warning("Jerseys.xlsx missing required columns: Categories, Checklist, Exempted")
        return pd.DataFrame(columns=data.columns)

    cats = jerseys_df['Categories'].dropna().astype(str).str.strip().tolist()
    keywords = [k.strip().lower() for k in jerseys_df['Checklist'].dropna().astype(str) if k.strip()]
    exempt = jerseys_df['Exempted'].dropna().astype(str).str.strip().tolist()

    if not cats or not keywords:
        return pd.DataFrame(columns=data.columns)

    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty: return pd.DataFrame(columns=data.columns)
    if exempt:
        df = df[~df['SELLER_NAME'].isin(exempt)]

    df['NAME_L'] = df['NAME'].astype(str).str.lower()
    pattern = re.compile('|'.join(r'\b' + re.escape(k) + r'\b' for k in keywords), re.IGNORECASE)
    flagged = df[df['NAME_L'].str.contains(pattern, na=False)]
    return flagged.drop(columns=['NAME_L'])

# ... (rest of validation functions remain unchanged)

def check_perfume_price_vectorized(...):  # unchanged – already correct
    # ... (your original function)

def check_single_word_name(data: pd.DataFrame, book_category_codes: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1]

def check_generic_brand_issues(data: pd.DataFrame, valid_category_codes_fas: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    return data[data['CATEGORY_CODE'].isin(valid_category_codes_fas) & (data['BRAND'] == 'Generic')]

# -------------------------------------------------
# MASTER VALIDATION RUNNER
# -------------------------------------------------
def validate_products(data: pd.DataFrame, support_files: Dict, country_validator: CountryValidator):
    flags_mapping = support_files['flags_mapping']
    if not flags_mapping:
        st.error("Cannot proceed without flags.xlsx")
        st.stop()

    sensitive_pattern = compile_regex_patterns(support_files['sensitive_words'])
    prohibited_pattern = compile_regex_patterns(country_validator.load_prohibited_products())
    color_pattern = compile_regex_patterns(support_files['colors'])

    validations = [
        ("Sensitive words", check_sensitive_words, {'pattern': sensitive_pattern}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {
            'book_category_codes': support_files['book_category_codes'],
            'approved_book_sellers': support_files['approved_book_sellers']
        }),
        ("Perfume Price Check", check_perfume_price_vectorized, {
            'perfumes_df': support_files['perfumes'],
            'perfume_category_codes': support_files['perfume_category_codes']
        }),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {
            'perfume_category_codes': support_files['perfume_category_codes'],
            'approved_perfume_sellers': support_files['approved_perfume_sellers'],
            'sensitive_perfume_brands': support_files['sensitive_perfume_brands']
        }),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {
            'sneaker_category_codes': support_files['sneaker_category_codes'],
            'sneaker_sensitive_brands': support_files['sneaker_sensitive_brands']
        }),
        ("Suspected counterfeit Jerseys", check_suspected_counterfeit_jerseys, {'jerseys_df': support_files['jerseys']}),  # ← NEW
        ("Prohibited products", check_prohibited_products, {'pattern': prohibited_pattern}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': support_files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {
            'valid_category_codes_fas': support_files['category_fas'].get('ID', []).astype(str).tolist() if 'ID' in support_files['category_fas'].columns else []
        }),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {
            'pattern': color_pattern, 'color_categories': support_files['color_categories']
        }),
        ("Duplicate product", check_duplicate_products, {}),
    ]

    validations = [v for v in validations if not country_validator.should_skip_validation(v[0])]

    # ... rest of your validate_products function (unchanged)

# -------------------------------------------------
# UI & Rest of App
# -------------------------------------------------
st.title("Product Validation Tool v2.9 – Now with Jersey Check")
st.markdown("---")

with st.spinner("Loading configuration..."):
    support_files = load_all_support_files()

if not support_files['flags_mapping']:
    st.stop()

tab1, tab2, tab3 = st.tabs(["Daily Validation", "Weekly Analysis", "Data Lake"])

with tab1:
    st.header("Daily Product Validation")
    country = st.selectbox("Select Country", ["Kenya", "Uganda"])
    country_validator = CountryValidator(country)

    uploaded_file = st.file_uploader("Upload CSV", type='csv')

    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype={'PRODUCT_SET_SID': str})
            data = filter_by_country(df, country_validator, "uploaded file")

            final_report, flag_dfs = validate_products(data, support_files, country_validator)

            st.success(f"Validation Complete: {len(final_report[final_report['Status']=='Approved'])} Approved | {len(final_report[final_report['Status']=='Rejected'])} Rejected")

            # ... rest of your UI (downloads, metrics, etc.)

        except Exception as e:
            st.error(f"Error: {e}")
            st.code(traceback.format_exc())

st.sidebar.markdown("---")
st.sidebar.caption("Product Validation Tool • 2025 • Now with Jersey Counterfeit Detection")
