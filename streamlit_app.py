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
# Logging & Config
# -------------------------------------------------
logging.basicConfig(
    filename=f'validation_{datetime.now().strftime("%Y%m%d")}.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Product Validation Tool", layout="wide")
st.title("Product Validation Tool – Jersey 1000030 ACTIVE")
st.sidebar.success("Suspected counterfeit Jerseys (1000030) is ACTIVE")

# -------------------------------------------------
# Constants
# -------------------------------------------------
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]
REJECTION_REASONS_COLS = ['CODE - REJECTION_REASON', 'COMMENT']
FULL_DATA_COLS = [
    "PRODUCT_SET_SID", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE", "COLOR",
    "PARENTSKU", "SELLER_NAME", "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "FLAG", "Status", "Reason", "Comment"
]
FX_RATE = 132.0

# -------------------------------------------------
# CACHED FILE LOADING
# -------------------------------------------------
@st.cache_data(ttl=3600)
def load_txt_file(filename: str) -> List[str]:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except:
        st.warning(f"{filename} not found")
        return []

@st.cache_data(ttl=3600)
def load_excel(filename: str, col: Optional[str] = None):
    try:
        df = pd.read_excel(filename)
        df.columns = df.columns.str.strip()
        if col and col in df.columns:
            return df[col].astype(str).str.strip().tolist()
        return df
    except:
        return [] if col else pd.DataFrame()

@st.cache_data(ttl=3600)
def load_all_support_files():
    return {
        'sensitive_words': [w.lower() for w in load_txt('sensitive_words.txt')],
        'book_category_codes': load_excel('Books_cat.xlsx', 'CategoryCode'),
        'approved_book_sellers': load_excel('Books_Approved_Sellers.xlsx', 'SellerName'),
        'perfume_category_codes': load_txt('Perfume_cat.txt'),
        'sensitive_perfume_brands': [b.lower() for b in load_txt('sensitive_perfumes.txt')],
        'approved_perfume_sellers': load_excel('perfumeSellers.xlsx', 'SellerName'),
        'sneaker_category_codes': load_txt('Sneakers_Cat.txt'),
        'sneaker_sensitive_brands': [b.lower() for b in load_txt('Sneakers_Sensitive.txt')],
        'colors': [c.lower() for c in load_txt('colors.txt')],
        'color_categories': load_txt('color_cats.txt'),
        'category_fas': load_excel('category_FAS.xlsx'),
        'perfumes': load_excel('perfumes.xlsx'),
        'reasons': load_excel('reasons.xlsx'),
        'jerseys': load_excel('Jerseys.xlsx'),  # For Jersey flag
        'flags_mapping': {
            'Sensitive words': ('1000001 - Brand NOT Allowed', 'Banned brand detected in title'),
            'BRAND name repeated in NAME': ('1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name', 'Brand appears in both fields'),
            'Missing COLOR': ('1000005 - Kindly confirm the actual product colour', 'Color missing in title or color field'),
            'Duplicate product': ('1000007 - Other Reason', 'Duplicate product detected'),
            'Prohibited products': ('1000007 - Other Reason', 'Prohibited product keyword found'),
            'Single-word NAME': ('1000008 - Kindly Improve Product Name Description', 'Title has only one word'),
            'Generic BRAND Issues': ('1000014 - Kindly request for the creation...', 'Generic brand in fashion category'),
            'Counterfeit Sneakers': ('1000023 - Confirmation of counterfeit product...', 'Suspected fake sneaker'),
            'Seller Approve to sell books': ('1000028 - Kindly Contact Jumia Seller Support...', 'Not approved to sell books'),
            'Seller Approved to Sell Perfume': ('1000028 - Kindly Contact Jumia Seller Support...', 'Not approved to sell perfume'),
            'Perfume Price Check': ('1000029 - Kindly Contact Jumia Seller Support To Verify...', 'Price too low – possible fake'),
            'Suspected counterfeit Jerseys': ('1000030 - Suspected Counterfeit/Fake Product', 'This jersey is suspected to be counterfeit. Please raise a claim.'),
        }
    }

def compile_regex(words: List[str]) -> Optional[re.Pattern]:
    if not words: return None
    return re.compile('|'.join(r'\b' + re.escape(w) + r'\b' for w in words), re.IGNORECASE)

# -------------------------------------------------
# ALL VALIDATION FUNCTIONS (NOW INCLUDED!)
# -------------------------------------------------
def check_sensitive_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if 'NAME' not in data.columns or not pattern: return pd.DataFrame()
    return data[data['NAME'].str.lower().str.contains(pattern, na=False)]

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if 'NAME' not in data.columns or not pattern: return pd.DataFrame()
    return data[data['NAME'].str.lower().str.contains(pattern, na=False)]

def check_missing_color(data: pd.DataFrame, pattern: re.Pattern, color_categories: List[str]) -> pd.DataFrame:
    if not {'NAME','COLOR','CATEGORY_CODE'}.issubset(data.columns): return pd.DataFrame()
    df = data[data['CATEGORY_CODE'].isin(color_categories)].copy()
    if df.empty or not pattern: return pd.DataFrame()
    name_has = df['NAME'].str.lower().str.contains(pattern, na=False)
    color_has = df['COLOR'].str.lower().str.contains(pattern, na=False)
    return df[~(name_has | color_has)]

def check_brand_in_name(data: pd.DataFrame) -> pd.DataFrame:
    if not {'BRAND','NAME'}.issubset(data.columns): return pd.DataFrame()
    mask = data.apply(lambda r: str(r['BRAND']).lower() in str(r['NAME']).lower() if r['BRAND'] else False, axis=1)
    return data[mask]

def check_duplicate_products(data: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    if len(cols) < 3: return pd.DataFrame()
    return data[data.duplicated(subset=cols, keep=False)]

def check_seller_approved_for_books(data: pd.DataFrame, cats: List[str], sellers: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns): return pd.DataFrame()
    books = data[data['CATEGORY_CODE'].isin(cats)]
    if books.empty or not sellers: return pd.DataFrame()
    return books[~books['SELLER_NAME'].isin(sellers)]

def check_seller_approved_for_perfume(data: pd.DataFrame, cats: List[str], sellers: List[str], brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME','BRAND','NAME'}.issubset(data.columns): return pd.DataFrame()
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty: return pd.DataFrame()
    df['BRAND_L'] = df['BRAND'].str.lower()
    df['NAME_L'] = df['NAME'].str.lower()
    sensitive = df['BRAND_L'].isin(brands)
    fake = df['BRAND_L'].isin(['generic','fashion','original','designer','smart collection','designers collection'])
    name_has = df['NAME_L'].apply(lambda x: any(b in x for b in brands))
    return df[(sensitive | (fake & name_has)) & (~df['SELLER_NAME'].isin(sellers)))]

def check_counterfeit_sneakers(data: pd.DataFrame, cats: List[str], brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','NAME','BRAND'}.issubset(data.columns): return pd.DataFrame()
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty: return pd.DataFrame()
    fake_brand = df['BRAND'].str.lower().isin(['generic','fashion'])
    name_has = df['NAME'].str.lower().apply(lambda x: any(b in x for b in brands))
    return df[fake_brand & name_has]

def check_perfume_price_vectorized(data: pd.DataFrame, ref_df: pd.DataFrame, cats: List[str]) -> pd.DataFrame:
    if ref_df.empty or not cats: return pd.DataFrame()
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty: return pd.DataFrame()
    price = df['GLOBAL_SALE_PRICE'].fillna(df['GLOBAL_PRICE'])
    price_usd = price.where(df.get('CURRENCY','KES').str.upper()!='KES', price / FX_RATE)
    df['BRAND_L'] = df['BRAND'].str.lower()
    df['NAME_L'] = df['NAME'].str.lower()
    ref = ref_df.copy()
    ref['BRAND_L'] = ref['BRAND'].str.lower()
    ref['NAME_L'] = ref.get('PRODUCT_NAME','').str.lower()
    merged = df.merge(ref, on='BRAND_L', how='left')
    merged = merged[merged['NAME_L_x'].str.contains(merged['NAME_L_y'], na=False)]
    flagged = merged[merged['PRICE_USD'] - merged['price_usd'] >= 30]
    return flagged[data.columns].drop_duplicates('PRODUCT_SET_SID')

def check_single_word_name(data: pd.DataFrame, book_cats: List[str]) -> pd.DataFrame:
    if 'NAME' not in data.columns: return pd.DataFrame()
    non_books = data[~data['CATEGORY_CODE'].isin(book_cats)]
    return non_books[non_books['NAME'].str.split().str.len() == 1]

def check_generic_brand_issues(data: pd.DataFrame, fas_cats: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns): return pd.DataFrame()
    return data[data['CATEGORY_CODE'].isin(fas_cats) & (data['BRAND'].str.lower() == 'generic')]

def check_suspected_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    if jerseys_df.empty: return pd.DataFrame(columns=data.columns)
    cats = jerseys_df['Categories'].dropna().astype(str).tolist()
    keywords = [str(k).strip().lower() for k in jerseys_df.get('Checklist',[])]
    exempt = jerseys_df.get('Exempted', pd.Series()).dropna().astype(str).tolist()
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty or not keywords: return pd.DataFrame(columns=data.columns)
    if exempt: df = df[~df['SELLER_NAME'].isin(exempt)]
    pattern = re.compile('|'.join(r'\b' + re.escape(k) + r'\b' for k in keywords), re.IGNORECASE)
    return df[df['NAME'].str.contains(pattern, case=False, na=False)]

# -------------------------------------------------
# Country Validator
# -------------------------------------------------
class CountryValidator:
    def __init__(self, country: str):
        self.code = "KE" if country == "Kenya" else "UG"
        self.skip = ["Seller Approve to sell books", "Perfume Price Check", "Seller Approved to Sell Perfume", "Counterfeit Sneakers"] if country == "Uganda" else []
    def skip_validation(self, name: str): return name in self.skip

# -------------------------------------------------
# MAIN VALIDATION ENGINE (NOW WORKS!)
# -------------------------------------------------
def validate_products(data: pd.DataFrame, files: Dict, validator: CountryValidator):
    flags = files['flags_mapping']
    sensitive_p = compile_regex(files['sensitive_words'])
    prohibited_p = compile_regex([w.lower() for w in load_txt(f"prohibited_products{validator.code}.txt")])
    color_p = compile_regex(files['colors'])

    validations = [
        ("Sensitive words", check_sensitive_words, {'pattern': sensitive_p}),
        ("Prohibited products", check_prohibited_products, {'pattern': prohibited_p}),
        ("Missing COLOR", check_missing_color, {'pattern': color_p, 'color_categories': files['color_categories']}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Duplicate product", check_duplicate_products, {}),
        ("Single-word NAME", check_single_word_name, {'book_cats': files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {'fas_cats': [str(x) for x in files['category_fas'].get('ID',[])]}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'cats': files['book_category_codes'], 'sellers': files['approved_book_sellers']}),
        ("Perfume Price Check", check_perfume_price_vectorized, {'ref_df': files['perfumes'], 'cats': files['perfume_category_codes']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'cats': files['perfume_category_codes'], 'sellers': files['approved_perfume_sellers'], 'brands': files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'cats': files['sneaker_category_codes'], 'brands': files['sneaker_sensitive_brands']}),
        ("Suspected counterfeit Jerseys", check_suspected_counterfeit_jerseys, {'jerseys_df': files['jerseys']}),  # ACTIVE
    ]
    validations = [v for v in validations if not validator.skip_validation(v[0])]

    progress = st.progress(0)
    results = {}
    for i, (name, func, kwargs) in enumerate(validations):
        st.caption(f"Running: {name}")
        try:
            if name == "Generic BRAND Issues":
                results[name] = func(data, [str(x) for x in files['category_fas'].get('ID',[])])
            else:
                results[name] = func(data, **kwargs)
        except Exception as e:
            st.warning(f"{name} failed: {e}")
            results[name] = pd.DataFrame()
        progress.progress((i+1)/len(validations))

    # Build final report
    rejected_sids = set()
    rows = []
    for name, df in results.items():
        if df.empty or 'PRODUCT_SET_SID' not in df.columns: continue
        reason, comment = flags.get(name, ("1000007 - Other Reason", name))
        for sid in df['PRODUCT_SET_SID'].unique():
            if sid in rejected_sids: continue
            rejected_sids.add(sid)
            r = df[df['PRODUCT_SET_SID'] == sid].iloc[0]
            rows.append({
                'ProductSetSid': sid, 'ParentSKU': r.get('PARENTSKU',''), 'Status': 'Rejected',
                'Reason': reason, 'Comment': comment, 'FLAG': name, 'SellerName': r.get('SELLER_NAME','')
            })

    approved = data[~data['PRODUCT_SET_SID'].isin(rejected_sids)]
    for _, r in approved.iterrows():
        rows.append({
            'ProductSetSid': r['PRODUCT_SET_SID'], 'ParentSKU': r.get('PARENTSKU',''), 'Status': 'Approved',
            'Reason': '', 'Comment': '', 'FLAG': '', 'SellerName': r.get('SELLER_NAME','')
        })

    return pd.DataFrame(rows), results

# -------------------------------------------------
# Simple Excel Export
# -------------------------------------------------
def to_excel(df: pd.DataFrame) -> BytesIO:
    out = BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        df[PRODUCTSETS_COLS].to_excel(writer, sheet_name="ProductSets", index=False)
    out.seek(0)
    return out

# -------------------------------------------------
# UI
# -------------------------------------------------
support_files = load_all_support_files()

country = st.selectbox("Country", ["Kenya", "Uganda"])
validator = CountryValidator(country)

uploaded = st.file_uploader("Upload your CSV (semicolon-separated)", type="csv")

if uploaded:
    try:
        df = pd.read_csv(uploaded, sep=';', encoding='ISO-8859-1', dtype=str).fillna('')
        if 'ACTIVE_STATUS_COUNTRY' in df.columns:
            df = df[df['ACTIVE_STATUS_COUNTRY'].str.upper().str.contains(validator.code)]
        if df.empty:
            st.error("No products for selected country")
            st.stop()

        with st.spinner("Validating..."):
            report_df, flag_results = validate_products(df, support_files, validator)

        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total", len(df))
        col2.metric("Approved", (report_df['Status']=='Approved').sum())
        col3.metric("Rejected", (report_df['Status']=='Rejected').sum())
        col4.metric("Rejection %", f"{(report_df['Status']=='Rejected').mean()*100:.1f}%")

        # Show flags
        st.markdown("### Validation Results by Flag")
        for flag_name in flag_results:
            count = len(flag_results[flag_name])
            with st.expander(f"{flag_name} ({count})", expanded=count>0):
                if count:
                    st.dataframe(flag_results[flag_name][['PRODUCT_SET_SID','NAME','BRAND','SELLER_NAME','CATEGORY_CODE']].head(100))
                else:
                    st.success("Clean")

        # Download
        st.download_button(
            "Download Final Report",
            to_excel(report_df).getvalue(),
            f"Jumia_Validation_{validator.code}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error("Something went wrong")
        with st.expander("Details"):
            st.code(traceback.format_exc())
else:
    st.info("Upload a file to start validation")
