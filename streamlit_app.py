import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import logging
import traceback
import json
from typing import Dict, List, Tuple, Optional

# -------------------------------------------------
# Logging
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
        st.warning(f"{filename} not found – check disabled.")
        return []
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        st.error(f"Error loading {filename}")
        return []

@st.cache_data(ttl=3600)
def load_excel_file(filename: str, column: Optional[str] = None):
    try:
        df = pd.read_excel(filename)
        df.columns = df.columns.str.strip()
        if column and column in df.columns:
            return df[column].astype(str).str.strip().tolist()
        return df
    except FileNotFoundError:
        st.warning(f"{filename} not found")
        return [] if column else pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading {filename}: {e}")
        return [] if column else pd.DataFrame()

@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    try:
        flag_mapping = {
            'Sensitive words': ('1000001 - Brand NOT Allowed', "Your listing includes banned brands like Chanel, Rolex..."),
            'BRAND name repeated in NAME': ('1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name', "..."),
            'Missing COLOR': ('1000005 - Kindly confirm the actual product colour', "..."),
            'Duplicate product': ('1000007 - Other Reason', "Duplicate product"),
            'Prohibited products': ('1000007 - Other Reason', "Product not allowed on Jumia..."),
            'Single-word NAME': ('1000008 - Kindly Improve Product Name Description', "..."),
            'Generic BRAND Issues': ('1000014 - Kindly request for the creation of this product\'s actual brand name...', "..."),
            'Counterfeit Sneakers': ('1000023 - Confirmation of counterfeit product...', "..."),
            'Seller Approve to sell books': ('1000028 - Kindly Contact Jumia Seller Support...', "..."),
            'Seller Approved to Sell Perfume': ('1000028 - Kindly Contact Jumia Seller Support...', "..."),
            'Perfume Price Check': ('1000029 - Kindly Contact Jumia Seller Support To Verify Authenticity...', "..."),
            'Suspected counterfeit Jerseys': (
                '1000030 - Suspected Counterfeit/Fake Product.Please Contact Seller Support By Raising A Claim , For Questions & Inquiries (Not Authorized)',
                "This product is suspected to be a counterfeit or fake jersey and is not authorized for sale on our platform.\n\n"
                "Please contact Seller Support to raise a claim and initiate the necessary verification process.\n"
                "If you have any questions, please reach out to Seller Support."
            ),
        }
        st.success(f"Loaded {len(flag_mapping)} validation rules")
        return flag_mapping
    except:
        st.error("flags.xlsx mapping failed")
        return {}

@st.cache_data(ttl=3600)
def load_all_support_files() -> Dict:
    return {
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
        'category_fas': load_excel_file('category_FAS.xlsx'),
        'perfumes': load_excel_file('perfumes.xlsx'),
        'reasons': load_excel_file('reasons.xlsx'),
        'flags_mapping': load_flags_mapping(),
        'jerseys': load_excel_file('Jerseys.xlsx'),  # ← NEW
    }

@st.cache_data(ttl=3600)
def compile_regex_patterns(words: List[str]) -> Optional[re.Pattern]:
    if not words: return None
    pattern = '|'.join(r'\b' + re.escape(w) + r'\b' for w in words)
    return re.compile(pattern, re.IGNORECASE)

# -------------------------------------------------
# Country Validator
# -------------------------------------------------
class CountryValidator:
    COUNTRY_CONFIG = {
        "Kenya": {"code": "KE", "skip_validations": []},
        "Uganda": {"code": "UG", "skip_validations": ["Seller Approve to sell books", "Perfume Price Check", "Seller Approved to Sell Perfume", "Counterfeit Sneakers"]}
    }
    def __init__(self, country: str):
        self.country = country
        self.config = self.COUNTRY_CONFIG.get(country, self.COUNTRY_CONFIG["Kenya"])
        self.code = self.config["code"]
        self.skip_validations = self.config["skip_validations"]
    def should_skip_validation(self, name: str): return name in self.skip_validations
    def ensure_status_column(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or 'Status' in df.columns: return df
        df['Status'] = 'Approved'
        return df

# -------------------------------------------------
# Validation Functions
# -------------------------------------------------
def check_sensitive_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not pattern or 'NAME' not in data.columns: return pd.DataFrame()
    mask = data['NAME'].astype(str).str.lower().str.contains(pattern, na=False)
    return data[mask]

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not pattern or 'NAME' not in data.columns: return pd.DataFrame()
    mask = data['NAME'].astype(str).str.lower().str.contains(pattern, na=False)
    return data[mask]

def check_missing_color(data: pd.DataFrame, pattern: re.Pattern, color_cats: List[str]) -> pd.DataFrame:
    if not pattern or not color_cats: return pd.DataFrame()
    df = data[data['CATEGORY_CODE'].isin(color_cats)].copy()
    if df.empty: return pd.DataFrame()
    has_color = df['NAME'].astype(str).str.lower().str.contains(pattern) | df['COLOR'].astype(str).str.lower().str.contains(pattern)
    return df[~has_color]

def check_brand_in_name(data: pd.DataFrame) -> pd.DataFrame:
    if not {'BRAND','NAME'}.issubset(data.columns): return pd.DataFrame()
    mask = data.apply(lambda r: str(r['BRAND']).strip().lower() in str(r['NAME']).lower(), axis=1)
    return data[mask]

def check_duplicate_products(data: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    return data[data.duplicated(subset=cols, keep=False)] if cols else pd.DataFrame()

def check_seller_approved_for_books(data, cats, sellers): 
    if not cats or not sellers: return pd.DataFrame()
    df = data[data['CATEGORY_CODE'].isin(cats)]
    return df[~df['SELLER_NAME'].isin(sellers)]

# FIXED: perfume fake brands list
def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_cats: List[str], approved_sellers: List[str], sensitive_brands: List[str]) -> pd.DataFrame:
    if 'CATEGORY_CODE' not in data.columns: return pd.DataFrame()
    df = data[data['CATEGORY_CODE'].isin(perfume_cats)].copy()
    if df.empty or not approved_sellers: return pd.DataFrame()

    df['B'] = df['BRAND'].astype(str).str.lower()
    df['N'] = df['NAME'].astype(str).str.lower()

    sensitive = df['B'].isin(sensitive_brands)
    fake = df['B'].isin(['designers collection', 'smart collection', 'generic', 'original', 'designer', 'fashion'])
    name_has = df['N'].apply(lambda x: any(b in x for b in sensitive_brands))

    mask = (sensitive | (fake & name_has)) & (~df['SELLER_NAME'].isin(approved_sellers))
    return df[mask].drop(columns=['B','N'])

def check_counterfeit_sneakers(data, cats, brands):
    if not cats or not brands: return pd.DataFrame()
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    df['N'] = df['NAME'].astype(str).str.lower()
    df['B'] = df['BRAND'].astype(str).str.lower()
    mask = df['B'].isin(['generic','fashion']) & df['N'].apply(lambda x: any(b in x for b in brands))
    return df[mask].drop(columns=['N','B'])

# NEW: Suspected Counterfeit Jerseys
def check_suspected_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    if jerseys_df.empty or not {'CATEGORY_CODE','NAME','SELLER_NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)

    if not all(c in jerseys_df.columns for c in ['Categories','Checklist','Exempted']):
        st.warning("Jerseys.xlsx must have columns: Categories, Checklist, Exempted")
        return pd.DataFrame(columns=data.columns)

    cats = jerseys_df['Categories'].dropna().astype(str).tolist()
    keywords = [str(k).strip().lower() for k in jerseys_df['Checklist'].dropna() if str(k).strip()]
    exempt = jerseys_df['Exempted'].dropna().astype(str).str.strip().tolist()

    if not cats or not keywords: return pd.DataFrame()

    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty: return pd.DataFrame()
    if exempt:
        df = df[~df['SELLER_NAME'].isin(exempt)]
        if df.empty: return pd.DataFrame()

    pattern = re.compile('|'.join(r'\b' + re.escape(k) + r'\b' for k in keywords), re.IGNORECASE)
    mask = df['NAME'].astype(str).str.lower().str.contains(pattern, na=False)
    return df[mask]

def check_perfume_price_vectorized(data: pd.DataFrame, perfumes_df: pd.DataFrame, perfume_cats: List[str]) -> pd.DataFrame:
    if perfumes_df.empty or not perfume_cats: return pd.DataFrame()
    df = data[data['CATEGORY_CODE'].isin(perfume_cats)].copy()
    if df.empty: return pd.DataFrame()

    df['price'] = df['GLOBAL_SALE_PRICE'].fillna(df['GLOBAL_PRICE'])
    df['usd'] = df['price'] / FX_RATE

    df['B'] = df['BRAND'].astype(str).str.lower()
    perfumes_df['B'] = perfumes_df['BRAND'].astype(str).str.lower()

    merged = df.merge(perfumes_df[['B','PRICE_USD','PRODUCT_NAME']], on='B', how='left')
    merged['name_match'] = merged.apply(lambda r: str(r['PRODUCT_NAME']) in str(r['NAME']) if pd.notna(r['PRODUCT_NAME']) else False, axis=1)
    merged = merged[merged['name_match']]
    flagged = merged[merged['PRICE_USD'] - merged['usd'] >= 30]
    return flagged[data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_single_word_name(data: pd.DataFrame, book_cats: List[str]) -> pd.DataFrame:
    non_books = data[~data['CATEGORY_CODE'].isin(book_cats)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1]

def check_generic_brand_issues(data: pd.DataFrame, fas_cats: List[str]) -> pd.DataFrame:
    return data[data['CATEGORY_CODE'].isin(fas_cats) & (data['BRAND'] == 'Generic')]

# -------------------------------------------------
# MAIN VALIDATION ENGINE
# -------------------------------------------------
def validate_products(data: pd.DataFrame, files: Dict, country: CountryValidator):
    flags = files['flags_mapping']
    if not flags:
        st.error("No flag mappings!")
        st.stop()

    sensitive_p = compile_regex_patterns(files['sensitive_words'])
    prohibited_p = compile_regex_patterns(country.load_prohibited_products())
    color_p = compile_regex_patterns(files['colors'])

    validations = [
        ("Sensitive words", check_sensitive_words, {'pattern': sensitive_p}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': files['book_category_codes'], 'approved_book_sellers': files['approved_book_sellers']}),
        ("Perfume Price Check", check_perfume_price_vectorized, {'perfumes_df': files['perfumes'], 'perfume_category_codes': files['perfume_category_codes']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'perfume_category_codes': files['perfume_category_codes'], 'approved_perfume_sellers': files['approved_perfume_sellers'], 'sensitive_perfume_brands': files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'sneaker_category_codes': files['sneaker_category_codes'], 'sneaker_sensitive_brands': files['sneaker_sensitive_brands']}),
        ("Suspected counterfeit Jerseys", check_suspected_counterfeit_jerseys, {'jerseys_df': files['jerseys']}),  # ← NEW
        ("Prohibited products", check_prohibited_products, {'pattern': prohibited_p}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {'valid_category_codes_fas': files['category_fas'].get('ID',[]).astype(str).tolist()}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': color_p, 'color_categories': files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
    ]

    validations = [v for v in validations if not country.should_skip_validation(v[0])]

    results = {}
    progress = st.progress(0)
    for i, (name, func, kwargs) in enumerate(validations):
        st.write(f"Running: {name}...")
        kwargs['data'] = data
        if name == "Generic BRAND Issues":
            kwargs['valid_category_codes_fas'] = files['category_fas'].get('ID',[]).astype(str).tolist()
        try:
            results[name] = func(**kwargs)
        except Exception as e:
            results[name] = pd.DataFrame()
            st.error(f"Error in {name}: {e}")
        progress.progress((i+1)/len(validations))

    # Build final report
    report = []
    used = set()
    for name, df in results.items():
        if df.empty or 'PRODUCT_SET_SID' not in df.columns: continue
        reason, comment = flags.get(name, ("1000007 - Other Reason", f"Flagged by: {name}"))
        for sid in df['PRODUCT_SET_SID']:
            if sid in used: continue
            used.add(sid)
            report.append({'ProductSetSid': sid, 'Status': 'Rejected', 'Reason': reason, 'Comment': comment, 'FLAG': name})

    approved = data[~data['PRODUCT_SET_SID'].isin(used)]
    for _, r in approved.iterrows():
        report.append({'ProductSetSid': r['PRODUCT_SET_SID'], 'Status': 'Approved', 'Reason': '', 'Comment': '', 'FLAG': ''})

    final_df = pd.DataFrame(report)
    final_df = country.ensure_status_column(final_df)
    return final_df, results

# -------------------------------------------------
# UI
# -------------------------------------------------
st.title("Product Validation Tool – Now with Jersey Check")
st.markdown("---")

support_files = load_all_support_files()
if not support_files['flags_mapping']:
    st.stop()

tab1, tab2, tab3 = st.tabs(["Daily Validation", "Weekly", "Data Lake"])

with tab1:
    st.header("Daily Validation")
    country = st.selectbox("Country", ["Kenya", "Uganda"])
    validator = CountryValidator(country)
    file = st.file_uploader("Upload CSV", type="csv")

    if file:
        try:
            df = pd.read_csv(file, sep=';', encoding='ISO-8859-1', dtype=str, keep_default_na=False)
            df = filter_by_country(df, validator, "upload")
            final_report, flag_results = validate_products(df, support_files, validator)

            st.success(f"Done! Approved: {len(final_report[final_report['Status']=='Approved'])} | Rejected: {len(final_report[final_report['Status']=='Rejected'])}")

            st.download_button("Download Final Report", data=to_excel(final_report, support_files['reasons']).getvalue(), file_name="report.xlsx")

            for flag_name, flagged_df in flag_results.items():
                if not flagged_df.empty:
                    with st.expander(f"{flag_name} ({len(flagged_df)})"):
                        st.dataframe(flagged_df[['PRODUCT_SET_SID','NAME','BRAND','SELLER_NAME']])

        except Exception as e:
            st.error(f"Error: {e}")
            st.code(traceback.format_exc())

st.sidebar.success("Jersey Counterfeit Detection Active")
