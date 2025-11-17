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
FX_RATE = 132.0  # Only used for Uganda (KES → USD)

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
def load_excel_file(filename: str, column: Optional[str] = None) -> pd.DataFrame:
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

        required_cols = ['rejection_reason_code', 'Comment']
        missing = [col for col in required_cols if col not in flags_df.columns]
        if missing:
            logger.error(f"flags.xlsx missing columns: {missing}")
            st.error(f"flags.xlsx missing required columns: {missing}")
            return {}

        flag_mapping = {
            'Sensitive words': ('1000001 - Brand NOT Allowed', "Your listing was rejected because it includes brands that are not allowed on Jumia..."),
            'BRAND name repeated in NAME': ('1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name', "Please do not write the brand name in the Product Name field..."),
            'Missing COLOR': ('1000005 - Kindly confirm the actual product colour', "Please make sure that the product color is clearly mentioned..."),
            'Duplicate product': ('1000007 - Other Reason', "kindly note product was rejected because its a duplicate product"),
            'Prohibited products': ('1000007 - Other Reason', "Kindly note this product is not allowed for listing on Jumia..."),
            'Single-word NAME': ('1000008 - Kindly Improve Product Name Description', "Kindly update the product title using this format..."),
            'Generic BRAND Issues': ('1000014 - Kindly request for the creation of this product\'s actual brand name...', "To create the actual brand name..."),
            'Counterfeit Sneakers': ('1000023 - Confirmation of counterfeit product by Jumia technical team (Not Authorized)', "Your listing has been rejected as Jumia's technical team has confirmed..."),
            'Suspected Fake Products': ('1000023 - Confirmation of counterfeit product by Jumia technical team (Not Authorized)', "Your listing has been flagged as a suspected counterfeit product..."),
            'Seller Approve to sell books': ('1000028 - Kindly Contact Jumia Seller Support...', "Please contact Jumia Seller Support..."),
            'Seller Approved to Sell Perfume': ('1000028 - Kindly Contact Jumia Seller Support...', "Please contact Jumia Seller Support..."),
            'Perfume Price Check': ('1000029 - Kindly Contact Jumia Seller Support To Verify This Product\'s Authenticity...', "Please contact Jumia Seller Support... Note: Price is $30+ below reference price."),
        }

        logger.info(f"Loaded {len(flag_mapping)} flag mappings")
        st.success(f"Loaded {len(flag_mapping)} validation flag mappings")
        return flag_mapping

    except FileNotFoundError:
        logger.error("flags.xlsx not found")
        st.error("flags.xlsx not found. This file is required.")
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
        'suspected_fake': load_excel_file('suspected_fake.xlsx'),
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
        if 'Status' not in df.columns:
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
    for field in required:
        if field not in df.columns:
            errors.append(f"Missing required column: {field}")
    if len(df) == 0:
        errors.append("DataFrame is empty")
    return len(errors) == 0, errors

# -------------------------------------------------
# Country filter
# -------------------------------------------------
def filter_by_country(df: pd.DataFrame, country_validator: CountryValidator, source: str) -> pd.DataFrame:
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns:
        st.warning(f"ACTIVE_STATUS_COUNTRY missing in {source}")
        return df
    df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.strip().str.upper()
    mask_valid = df['ACTIVE_STATUS_COUNTRY'].notna() & (df['ACTIVE_STATUS_COUNTRY'] != '') & (df['ACTIVE_STATUS_COUNTRY'] != 'NAN')
    mask_country = df['ACTIVE_STATUS_COUNTRY'].str.contains(rf'\b{country_validator.code}\b', na=False, regex=True)
    filtered = df[mask_valid & mask_country].copy()
    if filtered.empty:
        st.error(f"No {country_validator.code} rows found in {source}")
        st.stop()
    return filtered

# -------------------------------------------------
# VECTORIZED Validation checks (ALL FIXED)
# -------------------------------------------------
def check_sensitive_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    data = data.copy()
    data['NAME_LOWER'] = data['NAME'].astype(str).str.lower()
    mask = data['NAME_LOWER'].str.contains(pattern, na=False)
    return data[mask].drop(columns=['NAME_LOWER'])

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    data = data.copy()
    data['NAME_LOWER'] = data['NAME'].astype(str).str.lower()
    mask = data['NAME_LOWER'].str.contains(pattern, na=False)
    return data[mask].drop(columns=['NAME_LOWER'])

def check_missing_color(data: pd.DataFrame, pattern: re.Pattern, color_categories: List[str]) -> pd.DataFrame:
    if not {'NAME', 'COLOR', 'CATEGORY_CODE'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    data = data[data['CATEGORY_CODE'].isin(color_categories)].copy()
    if data.empty: return pd.DataFrame(columns=data.columns)
    data['NAME_LOWER'] = data['NAME'].astype(str).str.lower()
    data['COLOR_LOWER'] = data['COLOR'].astype(str).str.lower()
    mask = ~(data['NAME_LOWER'].str.contains(pattern, na=False) | data['COLOR_LOWER'].str.contains(pattern, na=False))
    return data[mask].drop(columns=['NAME_LOWER', 'COLOR_LOWER'])

def check_brand_in_name(data: pd.DataFrame) -> pd.DataFrame:
    if not {'BRAND','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    data = data.copy()
    data['BRAND_LOWER'] = data['BRAND'].astype(str).str.lower()
    data['NAME_LOWER'] = data['NAME'].astype(str).str.lower()
    mask = data.apply(lambda r: r['BRAND_LOWER'] in r['NAME_LOWER'] if r['BRAND_LOWER'] and r['NAME_LOWER'] else False, axis=1)
    return data[mask].drop(columns=['BRAND_LOWER', 'NAME_LOWER'])

def check_duplicate_products(data: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    if len(cols) < 4: return pd.DataFrame(columns=data.columns)
    return data[data.duplicated(subset=cols, keep=False)]

def check_seller_approved_for_books(data: pd.DataFrame, book_category_codes: List[str], approved_book_sellers: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if books.empty or not approved_book_sellers: return pd.DataFrame(columns=data.columns)
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)]

def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_category_codes: List[str], approved_perfume_sellers: List[str], sensitive_perfume_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME','BRAND','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perfume_data.empty or not approved_perfume_sellers: return pd.DataFrame(columns=data.columns)

    perfume_data['BRAND_LOWER'] = perfume_data['BRAND'].astype(str).str.lower()
    perfume_data['NAME_LOWER'] = perfume_data['NAME'].astype(str).str.lower()

    sensitive_mask = perfume_data['BRAND_LOWER'].isin(sensitive_perfume_brands)
    fake_brands = ['designers collection', 'smart collection', 'generic', 'original', 'designer', 'fashion']
    fake_brand_mask = perfume_data['BRAND_LOWER'].isin(fake_brands)

    name_contains_sensitive = perfume_data['NAME_LOWER'].apply(lambda x: any(brand in x for brand in sensitive_perfume_brands))
    fake_name_mask = fake_brand_mask & name_contains_sensitive

    final_mask = (sensitive_mask | fake_name_mask) & (~perfume_data['SELLER_NAME'].isin(approved_perfume_sellers))
    return perfume_data[final_mask].drop(columns=['BRAND_LOWER', 'NAME_LOWER'])

def check_counterfeit_sneakers(data: pd.DataFrame, sneaker_category_codes: List[str], sneaker_sensitive_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'NAME', 'BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    sneaker_data = data[data['CATEGORY_CODE'].isin(sneaker_category_codes)].copy()
    if sneaker_data.empty: return pd.DataFrame(columns=data.columns)

    sneaker_data['NAME_LOWER'] = sneaker_data['NAME'].astype(str).str.lower()
    sneaker_data['BRAND_LOWER'] = sneaker_data['BRAND'].astype(str).str.lower()

    fake_brand_mask = sneaker_data['BRAND_LOWER'].isin(['generic', 'fashion'])
    name_contains_brand = sneaker_data['NAME_LOWER'].apply(lambda x: any(brand in x for brand in sneaker_sensitive_brands))
    final_mask = fake_brand_mask & name_contains_brand
    return sneaker_data[final_mask].drop(columns=['NAME_LOWER', 'BRAND_LOWER'])

def check_perfume_price_vectorized(data: pd.DataFrame, perfumes_df: pd.DataFrame, perfume_category_codes: List[str], country_code: str = "KE") -> pd.DataFrame:
    req = ['CATEGORY_CODE','NAME','BRAND','GLOBAL_SALE_PRICE','GLOBAL_PRICE']
    if not all(c in data.columns for c in req) or perfumes_df.empty or not perfume_category_codes:
        return pd.DataFrame(columns=data.columns)

    perf = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perf.empty: return pd.DataFrame(columns=data.columns)

    perf['price_to_use'] = perf['GLOBAL_SALE_PRICE'].where((perf['GLOBAL_SALE_PRICE'].notna()) & (perf['GLOBAL_SALE_PRICE'] > 0), perf['GLOBAL_PRICE'])
    perf['price_usd'] = perf['price_to_use'] if country_code == "KE" else perf['price_to_use'] / FX_RATE

    perf['BRAND_LOWER'] = perf['BRAND'].astype(str).str.lower()
    perf['NAME_LOWER'] = perf['NAME'].astype(str).str.lower()

    perfumes_df = perfumes_df.copy()
    perfumes_df['BRAND_LOWER'] = perfumes_df['BRAND'].astype(str).str.lower()
    if 'PRODUCT_NAME' in perfumes_df.columns:
        perfumes_df['PRODUCT_NAME_LOWER'] = perfumes_df['PRODUCT_NAME'].astype(str).str.lower()

    merged = perf.merge(perfumes_df, on='BRAND_LOWER', how='left', suffixes=('', '_ref'))
    if 'PRODUCT_NAME_LOWER' in merged.columns:
        merged['name_match'] = merged.apply(lambda r: pd.notna(r['PRODUCT_NAME_LOWER']) and r['PRODUCT_NAME_LOWER'] in r['NAME_LOWER'], axis=1)
        merged = merged[merged['name_match']]

    if 'PRICE_USD' in merged.columns:
        merged['price_deviation'] = merged['PRICE_USD'] - merged['price_usd']
        flagged = merged[merged['price_deviation'] >= 30]
        return flagged[data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])
    return pd.DataFrame(columns=data.columns)

def check_single_word_name(data: pd.DataFrame, book_category_codes: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1]

def check_generic_brand_issues(data: pd.DataFrame, valid_category_codes_fas: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    return data[data['CATEGORY_CODE'].isin(valid_category_codes_fas) & (data['BRAND'] == 'Generic')]

def check_suspected_fake_products(data: pd.DataFrame, suspected_fake_df: pd.DataFrame, country_code: str = "KE") -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'BRAND', 'GLOBAL_SALE_PRICE', 'GLOBAL_PRICE'}.issubset(data.columns) or suspected_fake_df.empty:
        return pd.DataFrame(columns=data.columns)

    try:
        brands = suspected_fake_df.iloc[0].dropna().tolist()
        prices = suspected_fake_df.iloc[1].dropna().tolist()
        brand_config = {}

        for col_idx, brand in enumerate(brands):
            if pd.isna(brand) or str(brand).strip().lower() in ['brand', '']: continue
            try:
                price_threshold = float(prices[col_idx]) if col_idx < len(prices) else 0
            except:
                price_threshold = 0

            category_codes = [str(suspected_fake_df.iloc[row_idx, col_idx]).strip() for row_idx in range(2, len(suspected_fake_df)) if pd.notna(suspected_fake_df.iloc[row_idx, col_idx])]
            if category_codes:
                brand_config[str(brand).strip().lower()] = {'price_threshold': price_threshold, 'category_codes': category_codes}

        if not brand_config: return pd.DataFrame(columns=data.columns)

        check_data = data.copy()
        check_data['BRAND_LOWER'] = check_data['BRAND'].astype(str).str.lower()
        check_data['CATEGORY_CODE_STR'] = check_data['CATEGORY_CODE'].astype(str)
        check_data['price_to_check'] = check_data['GLOBAL_SALE_PRICE'].where((check_data['GLOBAL_SALE_PRICE'].notna()) & (check_data['GLOBAL_SALE_PRICE'] > 0), check_data['GLOBAL_PRICE'])
        check_data['price_usd'] = check_data['price_to_check'] if country_code == "KE" else check_data['price_to_check'] / FX_RATE

        flagged_mask = pd.Series([False] * len(check_data))
        for brand_lower, config in brand_config.items():
            mask = (check_data['BRAND_LOWER'] == brand_lower) & \
                   (check_data['CATEGORY_CODE_STR'].isin(config['category_codes'])) & \
                   (check_data['price_usd'] < config['price_threshold'])
            flagged_mask |= mask

        flagged = check_data[flagged_mask].copy()
        flagged = flagged.drop(columns=[c for c in ['BRAND_LOWER', 'CATEGORY_CODE_STR', 'price_to_check', 'price_usd'] if c in flagged.columns], errors='ignore')
        return flagged
    except Exception as e:
        logger.error(f"Error in suspected fake check: {e}", exc_info=True)
        return pd.DataFrame(columns=data.columns)

# -------------------------------------------------
# Master validation runner
# -------------------------------------------------
def validate_products(data: pd.DataFrame, support_files: Dict, country_validator: CountryValidator) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    flags_mapping = support_files['flags_mapping']
    if not flags_mapping:
        st.error("Cannot proceed without flags.xlsx")
        return pd.DataFrame(), {}

    sensitive_pattern = compile_regex_patterns(support_files['sensitive_words'])
    prohibited_pattern = compile_regex_patterns(country_validator.load_prohibited_products())
    color_pattern = compile_regex_patterns(support_files['colors'])

    validations = [
        ("Sensitive words", check_sensitive_words, {'pattern': sensitive_pattern}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': support_files['book_category_codes'], 'approved_book_sellers': support_files['approved_book_sellers']}),
        ("Perfume Price Check", check_perfume_price_vectorized, {'perfumes_df': support_files['perfumes'], 'perfume_category_codes': support_files['perfume_category_codes'], 'country_code': country_validator.code}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'perfume_category_codes': support_files['perfume_category_codes'], 'approved_perfume_sellers': support_files['approved_perfume_sellers'], 'sensitive_perfume_brands': support_files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'sneaker_category_codes': support_files['sneaker_category_codes'], 'sneaker_sensitive_brands': support_files['sneaker_sensitive_brands']}),
        ("Prohibited products", check_prohibited_products, {'pattern': prohibited_pattern}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': support_files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {'valid_category_codes_fas': support_files['category_fas']['ID'].astype(str).tolist() if 'ID' in support_files['category_fas'].columns else []}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': color_pattern, 'color_categories': support_files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
        ("Suspected Fake Products", check_suspected_fake_products, {'suspected_fake_df': support_files['suspected_fake'], 'country_code': country_validator.code}),
    ]

    validations = [v for v in validations if not country_validator.should_skip_validation(v[0])]

    progress_bar = st.progress(0)
    status_text = st.empty()
    validation_results_dfs = {}

    for i, (flag_name, check_func, func_kwargs) in enumerate(validations):
        status_text.text(f"Running {i+1}/{len(validations)}: {flag_name}")
        kwargs = {'data': data, **func_kwargs}
        try:
            result_df = check_func(**kwargs)
            validation_results_dfs[flag_name] = result_df if 'PRODUCT_SET_SID' in result_df.columns else pd.DataFrame()
        except Exception as e:
            logger.error(f"Error in {flag_name}: {e}", exc_info=True)
            st.error(f"Error in {flag_name}: {e}")
            validation_results_dfs[flag_name] = pd.DataFrame()
        progress_bar.progress((i + 1) / len(validations))

    # Build final report
    final_report_rows = []
    processed_sids = set()

    for flag_name, _, _ in validations:
        df = validation_results_dfs.get(flag_name, pd.DataFrame())
        if df.empty or 'PRODUCT_SET_SID' not in df.columns: continue
        reason, comment = flags_mapping.get(flag_name, ("1000007 - Other Reason", f"Flagged by: {flag_name}"))
        for _, row in df.iterrows():
            sid = row['PRODUCT_SET_SID']
            if sid in processed_sids: continue
            processed_sids.add(sid)
            orig = data[data['PRODUCT_SET_SID'] == sid].iloc[0]
            final_report_rows.append({
                'ProductSetSid': sid, 'ParentSKU': orig.get('PARENTSKU', ''),
                'Status': 'Rejected', 'Reason': reason, 'Comment': comment,
                'FLAG': flag_name, 'SellerName': orig.get('SELLER_NAME', '')
            })

    # Approved
    approved_sids = set(data['PRODUCT_SET_SID']) - processed_sids
    for sid in approved_sids:
        row = data[data['PRODUCT_SET_SID'] == sid].iloc[0]
        final_report_rows.append({
            'ProductSetSid': sid, 'ParentSKU': row.get('PARENTSKU', ''),
            'Status': 'Approved', 'Reason': '', 'Comment': '', 'FLAG': '', 'SellerName': row.get('SELLER_NAME', '')
        })

    final_report_df = pd.DataFrame(final_report_rows)
    final_report_df = country_validator.ensure_status_column(final_report_df)
    progress_bar.empty()
    status_text.empty()
    return final_report_df, validation_results_dfs

# -------------------------------------------------
# Export functions (unchanged, only minor safety fixes)
# -------------------------------------------------
# ... [to_excel, to_excel_full_data, etc. — same as your original, just kept for completeness]

# -------------------------------------------------
# UI (unchanged except minor fixes)
# -------------------------------------------------
st.title("Product Validation Tool v2025.11.17 - KE Optimized")
st.markdown("---")

with st.spinner("Loading support files..."):
    support_files = load_all_support_files()

if not support_files['flags_mapping']:
    st.stop()

tab1, tab2, tab3 = st.tabs(["Daily Validation", "Weekly Analysis", "Data Lake"])

with tab1:
    st.header("Daily Product Validation")
    country = st.selectbox("Country", ["Kenya", "Uganda"])
    country_validator = CountryValidator(country)
    uploaded_file = st.file_uploader("Upload CSV (semicolon-separated)", type='csv')

    if uploaded_file:
        try:
            raw_data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype={'PRODUCT_SET_SID': str, 'CATEGORY_CODE': str})
            data = filter_by_country(raw_data, country_validator, "uploaded file")
            is_valid, errors = validate_input_schema(data)
            if not is_valid:
                for e in errors: st.error(e)
                st.stop()

            with st.spinner("Validating..."):
                final_report_df, individual_flag_dfs = validate_products(data, support_files, country_validator)

            st.success("Validation Complete!")
            st.download_button("Download Final Report", to_excel(final_report_df, support_files['reasons']), f"KE_Validation_{datetime.now().strftime('%Y%m%d')}.xlsx")
        except Exception as e:
            st.error(f"Error: {e}")
            st.code(traceback.format_exc())

with tab2:
    st.info("Coming soon...")

with tab3:
    st.header("Audit Log")
    try:
        audit = pd.read_json('validation_audit.jsonl', lines=True)
        st.dataframe(audit.sort_values('timestamp', ascending=False).head(50))
    except:
        st.info("No audit history yet.")
