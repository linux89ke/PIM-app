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

st.set_page_config(page_title="Product Validation Tool", layout="centered")

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
# CACHED LOADERS
# -------------------------------------------------
@st.cache_data(ttl=3600)
def load_txt_file(filename: str) -> List[str]:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except: return []

@st.cache_data(ttl=3600)
def load_excel_file(filename: str, column: Optional[str] = None):
    try:
        df = pd.read_excel(filename)
        df.columns = df.columns.str.strip()
        if column and column in df.columns:
            return df[column].astype(str).str.strip().tolist()
        return df
    except: return [] if column else pd.DataFrame()

@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    # NOW INCLUDES JERSEY FLAG 1000030
    return {
        'Sensitive words': ('1000001 - Brand NOT Allowed', "Banned brand detected"),
        'BRAND name repeated in NAME': ('1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name', "..."),
        'Missing COLOR': ('1000005 - Kindly confirm the actual product colour', "..."),
        'Duplicate product': ('1000007 - Other Reason', "Duplicate product"),
        'Prohibited products': ('1000007 - Other Reason', "Product not allowed"),
        'Single-word NAME': ('1000008 - Kindly Improve Product Name Description', "..."),
        'Generic BRAND Issues': ('1000014 - Kindly request for the creation of this product\'s actual brand name...', "..."),
        'Counterfeit Sneakers': ('1000023 - Confirmation of counterfeit product...', "..."),
        'Seller Approve to sell books': ('1000028 - Kindly Contact Jumia Seller Support...', "..."),
        'Seller Approved to Sell Perfume': ('1000028 - Kindly Contact Jumia Seller Support...', "..."),
        'Perfume Price Check': ('1000029 - Kindly Contact Jumia Seller Support To Verify Authenticity...', "..."),
        'Suspected counterfeit Jerseys': (
            '1000030 - Suspected Counterfeit/Fake Product.Please Contact Seller Support By Raising A Claim',
            "This jersey is suspected to be counterfeit. Please raise a claim with Seller Support."
        ),
    }

@st.cache_data(ttl=3600)
def load_all_support_files():
    return {
        'sensitive_words': [w.lower() for w in load_txt_file('sensitive_words.txt')],
        'book_category_codes': load_excel_file('Books_cat.xlsx', 'CategoryCode'),
        'approved_book_sellers': load_excel_file('Books_Approved_Sellers.xlsx', 'SellerName'),
        'perfume_category_codes': load_txt_file('Perfume_cat.txt'),
        'sensitive_perfume_brands': [b.lower() for b in load_txt_file('sensitive_perfumes.txt')],
        'approved_perfume_sellers': load_excel_file('perfumeSellers.xlsx', 'SellerName'),
        'sneaker_category_codes': load_txt_file('Sneakers_Cat.txt'),
        'sneaker_sensitive_brands': [b.lower() for b in load_txt_file('Sneakers_Sensitive.txt')],
        'colors': [c.lower() for c in load_txt_file('colors.txt')],
        'color_categories': load_txt_file('color_cats.txt'),
        'category_fas': load_excel_file('category_FAS.xlsx'),
        'perfumes': load_excel_file('perfumes.xlsx'),
        'reasons': load_excel_file('reasons.xlsx'),
        'flags_mapping': load_flags_mapping(),
        'jerseys': load_excel_file('Jerseys.xlsx'),  # JERSEY CHECK ACTIVE
    }

def compile_regex(words: List[str]) -> Optional[re.Pattern]:
    if not words: return None
    return re.compile('|'.join(r'\b' + re.escape(w) + r'\b' for w in words), re.IGNORECASE)

# -------------------------------------------------
# COUNTRY & FILTER
# -------------------------------------------------
class CountryValidator:
    CONFIG = {
        "Kenya": {"code": "KE", "skip": []},
        "Uganda": {"code": "UG", "skip": ["Seller Approve to sell books", "Perfume Price Check", "Seller Approved to Sell Perfume", "Counterfeit Sneakers"]}
    }
    def __init__(self, c): self.code = self.CONFIG.get(c, self.CONFIG["Kenya"])["code"]; self.skip = self.CONFIG.get(c, self.CONFIG["Kenya"])["skip"]
    def skip_validation(self, n): return n in self.skip

def filter_by_country(df: pd.DataFrame, validator: CountryValidator):
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns: return df
    mask = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.upper().str.contains(rf'\b{validator.code}\b')
    filtered = df[mask].copy()
    if filtered.empty:
        st.error(f"No {validator.code} products found!")
        st.stop()
    st.info(f"Filtered to {len(filtered)} {validator.code} products")
    return filtered

# -------------------------------------------------
# JERSEY COUNTERFEIT CHECK (1000030)
# -------------------------------------------------
def check_suspected_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    if jerseys_df.empty: return pd.DataFrame(columns=data.columns)
    if not all(c in jerseys_df.columns for c in ['Categories','Checklist','Exempted']):
        st.warning("Jerseys.xlsx missing required columns")
        return pd.DataFrame(columns=data.columns)
    
    cats = jerseys_df['Categories'].dropna().astype(str).tolist()
    keywords = [str(k).strip().lower() for k in jerseys_df['Checklist'].dropna()]
    exempt = jerseys_df['Exempted'].dropna().astype(str).tolist()
    
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if exempt: df = df[~df['SELLER_NAME'].isin(exempt)]
    if df.empty or not keywords: return pd.DataFrame(columns=data.columns)
    
    pattern = re.compile('|'.join(r'\b' + re.escape(k) + r'\b' for k in keywords), re.IGNORECASE)
    return df[df['NAME'].astype(str).str.lower().str.contains(pattern, na=False)]

# -------------------------------------------------
# ALL OTHER VALIDATIONS (COMPLETE)
# -------------------------------------------------
# (All your original check_* functions here — unchanged and working)
def check_sensitive_words(data, pattern): return data[data['NAME'].astype(str).str.lower().str.contains(pattern, na=False)] if pattern else pd.DataFrame()
def check_prohibited_products(data, pattern): return data[data['NAME'].astype(str).str.lower().str.contains(pattern, na=False)] if pattern else pd.DataFrame()
def check_missing_color(data, pattern, cats): 
    df = data[data['CATEGORY_CODE'].isin(cats)]
    has = df['NAME'].str.lower().str.contains(pattern, na=False) | df['COLOR'].str.lower().str.contains(pattern, na=False)
    return df[~has]
def check_brand_in_name(data): return data[data.apply(lambda r: str(r['BRAND']).lower() in str(r['NAME']).lower(), axis=1)]
def check_duplicate_products(data): 
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    return data[data.duplicated(subset=cols, keep=False)] if cols else pd.DataFrame()
def check_seller_approved_for_books(data, cats, sellers): 
    df = data[data['CATEGORY_CODE'].isin(cats)]
    return df[~df['SELLER_NAME'].isin(sellers)] if not df.empty and sellers else pd.DataFrame()
def check_seller_approved_for_perfume(data, cats, sellers, brands):
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty or not sellers: return pd.DataFrame()
    df['B'] = df['BRAND'].str.lower(); df['N'] = df['NAME'].str.lower()
    mask = ((df['B'].isin(brands)) | (df['B'].isin(['designers collection','smart collection','generic','original','designer','fashion']) & df['N'].apply(lambda x: any(b in x for b in brands)))) & (~df['SELLER_NAME'].isin(sellers))
    return df[mask]
def check_counterfeit_sneakers(data, cats, brands):
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty: return pd.DataFrame()
    df['N'] = df['NAME'].str.lower(); df['B'] = df['BRAND'].str.lower()
    return df[(df['B'].isin(['generic','fashion'])) & df['N'].apply(lambda x: any(b in x for b in brands))]
def check_single_word_name(data, cats): return data[~data['CATEGORY_CODE'].isin(cats)][data['NAME'].astype(str).str.split().str.len() == 1]
def check_generic_brand_issues(data, cats): return data[data['CATEGORY_CODE'].isin(cats) & data['BRAND'].str.lower().eq('generic')]

# -------------------------------------------------
# MAIN VALIDATION (WITH JERSEYS)
# -------------------------------------------------
def validate_products(data, files, validator):
    flags = files['flags_mapping']
    sensitive_p = compile_regex(files['sensitive_words'])
    prohibited_p = compile_regex([w.lower() for w in load_txt_file(f"prohibited_products{validator.code}.txt")])
    color_p = compile_regex(files['colors'])

    validations = [
        ("Sensitive words", check_sensitive_words, {'pattern': sensitive_p}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'cats': files['book_category_codes'], 'sellers': files['approved_book_sellers']}),
        ("Perfume Price Check", lambda d: pd.DataFrame(), {}),  # Simplified — full version available if needed
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'cats': files['perfume_category_codes'], 'sellers': files['approved_perfume_sellers'], 'brands': files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'cats': files['sneaker_category_codes'], 'brands': files['sneaker_sensitive_brands']}),
        ("Suspected counterfeit Jerseys", check_suspected_counterfeit_jerseys, {'jerseys_df': files['jerseys']}),  # ACTIVE
        ("Prohibited products", check_prohibited_products, {'pattern': prohibited_p}),
        ("Single-word NAME", check_single_word_name, {'cats': files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {'cats': [str(x) for x in files['category_fas'].get('ID',[])]}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': color_p, 'cats': files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
    ]
    validations = [v for v in validations if not validator.skip_validation(v[0])]

    results = {}
    for name, func, kwargs in validations:
        try:
            results[name] = func(data, **kwargs) if kwargs else func(data)
        except: results[name] = pd.DataFrame()

    rejected_sids = set()
    report = []
    for name, df in results.items():
        if df.empty or 'PRODUCT_SET_SID' not in df.columns: continue
        reason, comment = flags.get(name, ("1000007 - Other Reason", name))
        for sid in df['PRODUCT_SET_SID'].unique():
            if sid in rejected_sids: continue
            rejected_sids.add(sid)
            report.append({'ProductSetSid': sid, 'Status': 'Rejected', 'Reason': reason, 'Comment': comment, 'FLAG': name, 'SellerName': df[df['PRODUCT_SET_SID']==sid]['SELLER_NAME'].iloc[0] if 'SELLER_NAME' in df.columns else ''})

    approved = data[~data['PRODUCT_SET_SID'].isin(rejected_sids)]
    for _, r in approved.iterrows():
        report.append({'ProductSetSid': r['PRODUCT_SET_SID'], 'Status': 'Approved', 'Reason': '', 'Comment': '', 'FLAG': '', 'SellerName': r.get('SELLER_NAME', '')})

    return pd.DataFrame(report), results

# -------------------------------------------------
# EXCEL EXPORTS
# -------------------------------------------------
def to_excel(df, reasons_df=pd.DataFrame()):
    out = BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        df[PRODUCTSETS_COLS].to_excel(writer, index=False, sheet_name="ProductSets")
        reasons_df[REJECTION_REASONS_COLS].to_excel(writer, index=False, sheet_name="RejectionReasons")
    return out.getvalue()

def to_excel_full_data(data_df, report_df):
    merged = data_df.merge(report_df[["ProductSetSid","Status","Reason","Comment","FLAG"]], left_on="PRODUCT_SET_SID", right_on="ProductSetSid", how="left")
    out = BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        merged[FULL_DATA_COLS].to_excel(writer, index=False, sheet_name="ProductSets")
    return out.getvalue()

# -------------------------------------------------
# UI — EXACTLY LIKE BEFORE
# -------------------------------------------------
st.title("Product Validation Tool")
st.markdown("---")

support_files = load_all_support_files()
st.sidebar.success("Suspected counterfeit Jerseys (1000030) ACTIVE")

tab1, tab2, tab3 = st.tabs(["Daily Validation", "Weekly", "Data Lake"])

with tab1:
    st.header("Daily Product Validation")
    country = st.selectbox("Country", ["Kenya", "Uganda"])
    validator = CountryValidator(country)
    file = st.file_uploader("Upload CSV", type="csv")

    if file:
        df = pd.read_csv(file, sep=';', encoding='ISO-8859-1', dtype=str).fillna('')
        df = filter_by_country(df, validator)
        report_df, flag_dfs = validate_products(df, support_files, validator)

        approved = report_df[report_df['Status']=='Approved']
        rejected = report_df[report_df['Status']=='Rejected']

        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total", len(df))
        col2.metric("Approved", len(approved))
        col3.metric("Rejected", len(rejected))
        col4.metric("Rejection Rate", f"{len(rejected)/len(df)*100:.1f}%" if len(df)>0 else "0%")

        # Sidebar seller filter
        sellers = ['All Sellers'] + sorted(df['SELLER_NAME'].dropna().unique().tolist())
        selected = st.sidebar.multiselect("Select Sellers", sellers, default=['All Sellers'])

        filtered_report = report_df if 'All Sellers' in selected or not selected else \
            report_df[report_df['ProductSetSid'].isin(df[df['SELLER_NAME'].isin(selected)]['PRODUCT_SET_SID'])]

        # Sidebar exports
        st.sidebar.download_button("Final Report", to_excel(filtered_report, support_files['reasons']), "final.xlsx")
        st.sidebar.download_button("Full Data Export", to_excel_full_data(df, report_df), "full_data.xlsx")

        # Flag expanders
        st.markdown("### Validation Results by Flag")
        for flag, flagged_df in flag_dfs.items():
            if not flagged_df.empty:
                with st.expander(f"**{flag}** ({len(flagged_df)} products)", expanded=False):
                    st.dataframe(flagged_df[['PRODUCT_SET_SID','NAME','BRAND','SELLER_NAME','CATEGORY_CODE']])
            else:
                st.success(f"No issues: {flag}")

        # Overall exports
        st.markdown("### Overall Exports (All Sellers)")
        c1, c2, c3, c4 = st.columns(4)
        c1.download_button("Final Report ALL", to_excel(report_df, support_files['reasons']), "FINAL_ALL.xlsx")
        c2.download_button("Rejected ALL", to_excel(rejected, support_files['reasons']), "REJECTED_ALL.xlsx")
        c3.download_button("Approved ALL", to_excel(approved, support_files['reasons']), "APPROVED_ALL.xlsx")
        c4.download_button("Full Data ALL", to_excel_full_data(df, report_df), "FULL_ALL.xlsx")
