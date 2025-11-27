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
# Logging & Config
# -------------------------------------------------
logging.basicConfig(
    filename=f'validation_{datetime.now().strftime("%Y%m%d")}.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Product Validation Tool", layout="centered")

FX_RATE = 132.0

# -------------------------------------------------
# File Loaders
# -------------------------------------------------
@st.cache_data(ttl=3600)
def load_txt_file(filename: str) -> List[str]:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        st.warning(f"{filename} not found")
        return []
    except Exception:
        return []

@st.cache_data(ttl=3600)
def load_excel_file(filename: str, column: Optional[str] = None):
    try:
        df = pd.read_excel(filename)
        df.columns = df.columns.str.strip()
        if column and column in df.columns:
            return df[column].astype(str).str.strip().tolist()
        return df
    except:
        return [] if column else pd.DataFrame()

@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    return {
        'Sensitive words': ('1000001 - Brand NOT Allowed', "Banned brand"),
        'BRAND name repeated in NAME': ('1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name', "..."),
        'Missing COLOR': ('1000005 - Kindly confirm the actual product colour', "..."),
        'Duplicate product': ('1000007 - Other Reason', "Duplicate"),
        'Prohibited products': ('1000007 - Other Reason', "Not allowed"),
        'Single-word NAME': ('1000008 - Kindly Improve Product Name Description', "..."),
        'Generic BRAND Issues': ('1000014 - Kindly request for the creation of this product\'s actual brand name...', "..."),
        'Counterfeit Sneakers': ('1000023 - Confirmation of counterfeit product...', "..."),
        'Seller Approve to sell books': ('1000028 - Kindly Contact Jumia Seller Support...', "..."),
        'Seller Approved to Sell Perfume': ('1000028 - Kindly Contact Jumia Seller Support...', "..."),
        'Perfume Price Check': ('1000029 - Kindly Contact Jumia Seller Support To Verify Authenticity...', "..."),
        'Suspected counterfeit Jerseys': (
            '1000030 - Suspected Counterfeit/Fake Product.Please Contact Seller Support By Raising A Claim',
            "Suspected fake jersey – please contact Seller Support"
        ),
    }

@st.cache_data(ttl=3600)
def load_all_support_files() -> Dict:
    return {
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
        'flags_mapping': load_flags_mapping(),
        'jerseys': load_excel_file('Jerseys.xlsx'),  # ACTIVE
    }

@st.cache_data(ttl=3600)
def compile_regex(words: List[str]) -> Optional[re.Pattern]:
    if not words: return None
    return re.compile('|'.join(r'\b' + re.escape(w) + r'\b' for w in words), re.IGNORECASE)

# -------------------------------------------------
# Country Handler
# -------------------------------------------------
class CountryValidator:
    CONFIG = {
        "Kenya": {"code": "KE", "skip": []},
        "Uganda": {"code": "UG", "skip": ["Seller Approve to sell books", "Perfume Price Check", "Seller Approved to Sell Perfume", "Counterfeit Sneakers"]}
    }
    def __init__(self, country: str):
        cfg = self.CONFIG.get(country, self.CONFIG["Kenya"])
        self.code = cfg["code"]
        self.skip = cfg["skip"]
    def skip_validation(self, name: str): return name in self.skip

# -------------------------------------------------
# Country Filter (NOW INCLUDED!)
# -------------------------------------------------
def filter_by_country(df: pd.DataFrame, validator: CountryValidator) -> pd.DataFrame:
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns:
        st.warning("Missing ACTIVE_STATUS_COUNTRY")
        return df
    df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.upper()
    mask = df['ACTIVE_STATUS_COUNTRY'].str.contains(rf'\b{validator.code}\b')
    filtered = df[mask].copy()
    if filtered.empty:
        st.error(f"No {validator.code} products found")
        st.stop()
    st.info(f"Filtered: {len(filtered)} {validator.code} products")
    return filtered

# -------------------------------------------------
# ALL VALIDATION FUNCTIONS (COMPLETE)
# -------------------------------------------------
def check_sensitive_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not pattern or 'NAME' not in data.columns: return pd.DataFrame(columns=data.columns)
    return data[data['NAME'].astype(str).str.lower().str.contains(pattern, na=False)]

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not pattern or 'NAME' not in data.columns: return pd.DataFrame(columns=data.columns)
    return data[data['NAME'].astype(str).str.lower().str.contains(pattern, na=False)]

def check_missing_color(data: pd.DataFrame, pattern: re.Pattern, cats: List[str]) -> pd.DataFrame:
    if not pattern or not cats: return pd.DataFrame(columns=data.columns)
    df = data[data['CATEGORY_CODE'].isin(cats)]
    has_color = df['NAME'].str.lower().str.contains(pattern, na=False) | df['COLOR'].str.lower().str.contains(pattern, na=False)
    return df[~has_color]

def check_brand_in_name(data: pd.DataFrame) -> pd.DataFrame:
    mask = data.apply(lambda r: str(r['BRAND']).strip().lower() in str(r['NAME']).lower(), axis=1)
    return data[mask]

def check_duplicate_products(data: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    return data[data.duplicated(subset=cols, keep=False)] if cols else pd.DataFrame()

def check_seller_approved_for_books(data: pd.DataFrame, cats: List[str], sellers: List[str]) -> pd.DataFrame:
    df = data[data['CATEGORY_CODE'].isin(cats)]
    return df[~df['SELLER_NAME'].isin(sellers)] if not df.empty and sellers else pd.DataFrame()

def check_seller_approved_for_perfume(data: pd.DataFrame, cats: List[str], sellers: List[str], brands: List[str]) -> pd.DataFrame:
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty or not sellers: return pd.DataFrame()
    df['B'] = df['BRAND'].str.lower()
    df['N'] = df['NAME'].str.lower()
    sensitive = df['B'].isin(brands)
    fake = df['B'].isin(['designers collection','smart collection','generic','original','designer','fashion'])
    name_has = df['N'].apply(lambda x: any(b in x for b in brands))
    mask = (sensitive | (fake & name_has)) & (~df['SELLER_NAME'].isin(sellers))
    return df[mask].drop(columns=['B','N'])

def check_counterfeit_sneakers(data: pd.DataFrame, cats: List[str], brands: List[str]) -> pd.DataFrame:
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty: return pd.DataFrame()
    df['N'] = df['NAME'].str.lower()
    df['B'] = df['BRAND'].str.lower()
    mask = df['B'].isin(['generic','fashion']) & df['N'].apply(lambda x: any(b in x for b in brands))
    return df[mask].drop(columns=['N','B'])

def check_suspected_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    if jerseys_df.empty or not {'CATEGORY_CODE','NAME','SELLER_NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    if not all(c in jerseys_df.columns for c in ['Categories','Checklist','Exempted']):
        st.warning("Jerseys.xlsx missing columns")
        return pd.DataFrame()
    cats = jerseys_df['Categories'].dropna().astype(str).tolist()
    keywords = [str(k).strip().lower() for k in jerseys_df['Checklist'].dropna()]
    exempt = jerseys_df['Exempted'].dropna().astype(str).tolist()
    if not cats or not keywords: return pd.DataFrame()
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if exempt:
        df = df[~df['SELLER_NAME'].isin(exempt)]
    pattern = re.compile('|'.join(r'\b' + re.escape(k) + r'\b' for k in keywords), re.IGNORECASE)
    return df[df['NAME'].str.lower().str.contains(pattern, na=False)]

def check_perfume_price_vectorized(data: pd.DataFrame, ref_df: pd.DataFrame, cats: List[str]) -> pd.DataFrame:
    if ref_df.empty or not cats: return pd.DataFrame()
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty: return pd.DataFrame()
    df['price'] = df['GLOBAL_SALE_PRICE'].fillna(df['GLOBAL_PRICE'])
    df['usd'] = pd.to_numeric(df['price'], errors='coerce') / FX_RATE
    df['B'] = df['BRAND'].str.lower()
    ref_df['B'] = ref_df['BRAND'].astype(str).str.lower()
    merged = df.merge(ref_df[['B','PRICE_USD','PRODUCT_NAME']], on='B', how='left')
    merged['match'] = merged.apply(lambda r: pd.notna(r['PRODUCT_NAME']) and str(r['PRODUCT_NAME']) in str(r['NAME']), axis=1)
    flagged = merged[merged['match'] & (merged['PRICE_USD'] - merged['usd'] >= 30)]
    return flagged[data.columns]

def check_single_word_name(data: pd.DataFrame, book_cats: List[str]) -> pd.DataFrame:
    df = data[~data['CATEGORY_CODE'].isin(book_cats)]
    return df[df['NAME'].astype(str).str.split().str.len() == 1]

def check_generic_brand_issues(data: pd.DataFrame, fas_cats: List[str]) -> pd.DataFrame:
    return data[data['CATEGORY_CODE'].isin(fas_cats) & data['BRAND'].str.lower().eq('generic')]

# -------------------------------------------------
# MAIN VALIDATION ENGINE (ALL CHECKS INCLUDED)
# -------------------------------------------------
def validate_products(data: pd.DataFrame, files: Dict, country: CountryValidator):
    flags = files['flags_mapping']
    sensitive_p = compile_regex(files['sensitive_words'])
    prohibited_p = compile_regex([w.lower() for w in load_txt_file(f"prohibited_products{country.code}.txt")])
    color_p = compile_regex(files['colors'])

    validations = [
        ("Sensitive words", check_sensitive_words, {'pattern': sensitive_p}),
        ("Seller Approve to sell books", check_seller_approved_for_books,
         {'cats': files['book_category_codes'], 'sellers': files['approved_book_sellers']}),
        ("Perfume Price Check", check_perfume_price_vectorized,
         {'ref_df': files['perfumes'], 'cats': files['perfume_category_codes']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume,
         {'cats': files['perfume_category_codes'], 'sellers': files['approved_perfume_sellers'], 'brands': files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers,
         {'cats': files['sneaker_category_codes'], 'brands': files['sneaker_sensitive_brands']}),
        ("Suspected counterfeit Jerseys", check_suspected_counterfeit_jerseys,
         {'jerseys_df': files['jerseys']}),
        ("Prohibited products", check_prohibited_products, {'pattern': prohibited_p}),
        ("Single-word NAME", check_single_word_name, {'book_cats': files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues,
         {'fas_cats': [str(x) for x in files['category_fas'].get('ID',[])]}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': color_p, 'cats': files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
    ]

    validations = [v for v in validations if not country.skip_validation(v[0])]

    results = {}
    for name, func, kwargs in validations:
        try:
            results[name] = func(data, **kwargs)
        except Exception as e:
            st.error(f"Error in {name}")
            results[name] = pd.DataFrame()

    rejected_sids = set()
    report = []

    for name, df in results.items():
        if df.empty or 'PRODUCT_SET_SID' not in df.columns: continue
        reason, comment = flags.get(name, ("1000007 - Other Reason", name))
        for sid in df['PRODUCT_SET_SID'].unique():
            if sid in rejected_sids: continue
            rejected_sids.add(sid)
            report.append({
                'ProductSetSid': sid,
                'Status': 'Rejected',
                'Reason': reason,
                'Comment': comment,
                'FLAG': name
            })

    approved = data[~data['PRODUCT_SET_SID'].isin(rejected_sids)]
    for _, r in approved.iterrows():
        report.append({
            'ProductSetSid': r['PRODUCT_SET_SID'],
            'Status': 'Approved',
            'Reason': '', 'Comment': '', 'FLAG': ''
        })

    return pd.DataFrame(report), results

# -------------------------------------------------
# UI
# -------------------------------------------------
st.title("Product Validation Tool – Jersey Check ACTIVE")

support_files = load_all_support_files()

with st.tabs(["Daily Validation"])[0]:
    country = st.selectbox("Country", ["Kenya", "Uganda"])
    validator = CountryValidator(country)
    uploaded = st.file_uploader("Upload CSV (semicolon)", type="csv")

    if uploaded:
        try:
            df = pd.read_csv(uploaded, sep=';', encoding='ISO-8859-1', dtype=str).fillna('')
            df = filter_by_country(df, validator)
            report, details = validate_products(df, support_files, validator)

            st.success(f"Complete! Approved: {len(report[report['Status']=='Approved'])} | Rejected: {len(report[report['Status']=='Rejected'])}")

            def to_excel(df):
                out = BytesIO()
                with pd.ExcelWriter(out, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                return out.getvalue()

            st.download_button("Download Report", data=to_excel(report), file_name="validation_report.xlsx")

            for name, df_flag in details.items():
                if not df_flag.empty:
                    with st.expander(f"{name} – {len(df_flag)} items"):
                        st.dataframe(df_flag[['PRODUCT_SET_SID','NAME','BRAND','SELLER_NAME','CATEGORY_CODE']])

        except Exception as e:
            st.error("Upload failed")
            st.code(traceback.format_exc())

st.sidebar.success("Suspected counterfeit Jerseys (Flag 1000030) is FULLY ACTIVE")
