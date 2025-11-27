import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import logging
import traceback
from typing import Dict, List, Optional

# -------------------------------------------------
# Logging & Config
# -------------------------------------------------
logging.basicConfig(filename=f'validation_{datetime.now().strftime("%Y%m%d")}.log', level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Product Validation Tool", layout="centered")

PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]
REJECTION_REASONS_COLS = ['CODE - REJECTION_REASON', 'COMMENT']
FULL_DATA_COLS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE",
    "COLOR", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU",
    "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG", "LISTING_STATUS", "SELLER_RATING", "STOCK_QTY"
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
    except:
        return []

@st.cache_data(ttl=255600)
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
def load_flags_mapping() -> Dict[str, tuple]:
    return {
        'Sensitive words': ('1000001 - Brand NOT Allowed', "Banned brand"),
        'BRAND name repeated in NAME': ('1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name', "Brand repeated"),
        'Missing COLOR': ('1000005 - Kindly confirm the actual product colour', "Color missing"),
        'Duplicate product': ('1000007 - Other Reason', "Duplicate"),
        'Prohibited products': ('1000007 - Other Reason', "Not allowed"),
        'Single-word NAME': ('1000008 - Kindly Improve Product Name Description', "Single word name"),
        'Generic BRAND Issues': ('1000014 - Kindly request for the creation of this product\'s actual brand name...', "Generic brand"),
        'Counterfeit Sneakers': ('1000023 - Confirmation of counterfeit product...', "Counterfeit sneakers"),
        'Seller Approve to sell books': ('1000028 - Kindly Contact Jumia Seller Support...', "Books seller not approved"),
        'Seller Approved to Sell Perfume': ('1000028 - Kindly Contact Jumia Seller Support...', "Perfume seller not approved"),
        'Perfume Price Check': ('1000029 - Kindly Contact Jumia Seller Support To Verify Authenticity...', "Price too low"),
        'Suspected counterfeit Jerseys': ('1000030 - Suspected Counterfeit/Fake Product', "Suspected fake jersey"),
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
        'jerseys': load_excel_file('Jerseys.xlsx'),
    }

def compile_regex(words: List[str]) -> Optional[re.Pattern]:
    if not words: return None
    return re.compile('|'.join(r'\b' + re.escape(w) + r'\b' for w in words), re.IGNORECASE)

# -------------------------------------------------
# Country Validator (FIXED)
# -------------------------------------------------
class CountryValidator:
    def __init__(self, country: str):
        self.code = "KE" if country == "Kenya" else "UG"
        uganda_skips = ["Seller Approve to sell books", "Perfume Price Check", "Seller Approved to Sell Perfume", "Counterfeit Sneakers"]
        self.skip_list = uganda_skips if country == "Uganda" else []
    def skip_validation(self, name: str) -> bool:
        return name in self.skip_list

# -------------------------------------------------
# VALIDATION FUNCTIONS (ALL FIXED & SAFE)
# -------------------------------------------------
def check_sensitive_words(data, pattern): 
    if not pattern: return pd.DataFrame(columns=data.columns)
    return data[data['NAME'].astype(str).str.lower().str.contains(pattern, na=False)]

def check_prohibited_products(data, pattern): 
    if not pattern: return pd.DataFrame(columns=data.columns)
    return data[data['NAME'].astype(str).str.lower().str.contains(pattern, na=False)]

def check_missing_color(data, pattern, cats):
    if not pattern or not cats: return pd.DataFrame(columns=data.columns)
    df = data[data['CATEGORY_CODE'].isin(cats)]
    has_color = df['NAME'].str.lower().str.contains(pattern, na=False) | df['COLOR'].str.lower().str.contains(pattern, na=False)
    return df[~has_color]

def check_brand_in_name(data):
    mask = data.apply(lambda r: str(r['BRAND']).strip().lower() in str(r['NAME']).lower(), axis=1)
    return data[mask]

def check_duplicate_products(data):
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    return data[data.duplicated(subset=cols, keep=False)] if cols else pd.DataFrame(columns=data.columns)

def check_seller_approved_for_books(data, cats, sellers):
    df = data[data['CATEGORY_CODE'].isin(cats)]
    return df[~df['SELLER_NAME'].isin(sellers)] if sellers else pd.DataFrame(columns=data.columns)

def check_seller_approved_for_perfume(data, cats, sellers, brands):
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty or not sellers: return pd.DataFrame(columns=data.columns)
    df['B'] = df['BRAND'].str.lower()
    df['N'] = df['NAME'].str.lower()
    mask = ((df['B'].isin(brands)) | 
            (df['B'].isin(['designers collection','smart collection','generic','original','designer','fashion']) & 
             df['N'].apply(lambda x: any(b in x for b in brands)))) & (~df['SELLER_NAME'].isin(sellers))
    return df[mask]

def check_counterfeit_sneakers(data, cats, brands):
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty: return pd.DataFrame(columns=data.columns)
    mask = df['BRAND'].str.lower().isin(['generic','fashion']) & df['NAME'].str.lower().apply(lambda x: any(b in x for b in brands))
    return df[mask]

def check_perfume_price_vectorized(data, ref_df, cats):
    if ref_df.empty or not cats: return pd.DataFrame(columns=data.columns)
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if df.empty: return pd.DataFrame(columns=data.columns)
    df['price'] = pd.to_numeric(df['GLOBAL_SALE_PRICE'].fillna(df['GLOBAL_PRICE']), errors='coerce')
    df['usd'] = df['price'] / FX_RATE
    df['B'] = df['BRAND'].str.lower()
    if 'PRICE_USD' not in ref_df.columns: return pd.DataFrame(columns=data.columns)
    ref_df['B'] = ref_df['BRAND'].astype(str).str.lower()
    merged = df.merge(ref_df[['B','PRICE_USD','PRODUCT_NAME']], on='B', how='left')
    merged['match'] = merged.apply(lambda r: pd.notna(r['PRODUCT_NAME']) and str(r['PRODUCT_NAME']) in str(r['NAME']), axis=1)
    flagged = merged[merged['match'] & (merged['PRICE_USD'] - merged['usd'] >= 30)]
    return flagged[data.columns] if not flagged.empty else pd.DataFrame(columns=data.columns)

def check_suspected_counterfeit_jerseys(data, jerseys_df):
    if jerseys_df.empty or 'Categories' not in jerseys_df.columns or 'Checklist' not in jerseys_df.columns:
        return pd.DataFrame(columns=data.columns)
    cats = jerseys_df['Categories'].dropna().astype(str).tolist()
    keywords = [str(k).strip().lower() for k in jerseys_df['Checklist'].dropna()]
    exempt = jerseys_df['Exempted'].dropna().astype(str).tolist() if 'Exempted' in jerseys_df.columns else []
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if exempt and 'SELLER_NAME' in df.columns:
        df = df[~df['SELLER_NAME'].isin(exempt)]
    if df.empty or not keywords: return pd.DataFrame(columns=data.columns)
    pattern = re.compile('|'.join(r'\b' + re.escape(k) + r'\b' for k in keywords), re.IGNORECASE)
    return df[df['NAME'].str.lower().str.contains(pattern, na=False)]

def check_single_word_name(data, book_cats):
    return data[~data['CATEGORY_CODE'].isin(book_cats)][data['NAME'].astype(str).str.split().str.len() == 1]

def check_generic_brand_issues(data, fas_cats):
    return data[data['CATEGORY_CODE'].isin(fas_cats) & data['BRAND'].str.lower().eq('generic')]

# -------------------------------------------------
# MAIN VALIDATION
# -------------------------------------------------
def validate_products(data, files, validator):
    flags = files['flags_mapping']
    sensitive_p = compile_regex(files['sensitive_words'])
    prohibited_p = compile_regex([w.lower() for w in load_txt_file(f"prohibited_products{validator.code}.txt")])
    color_p = compile_regex(files['colors'])

    validations = [
        ("Sensitive words", check_sensitive_words, {'pattern': sensitive_p}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'cats': files['book_category_codes'], 'sellers': files['approved_book_sellers']}),
        ("Perfume Price Check", check_perfume_price_vectorized, {'ref_df': files['perfumes'], 'cats': files['perfume_category_codes']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'cats': files['perfume_category_codes'], 'sellers': files['approved_perfume_sellers'], 'brands': files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'cats': files['sneaker_category_codes'], 'brands': files['sneaker_sensitive_brands']}),
        ("Suspected counterfeit Jerseys", check_suspected_counterfeit_jerseys, {'jerseys_df': files['jerseys']}),
        ("Prohibited products", check_prohibited_products, {'pattern': prohibited_p}),
        ("Single-word NAME", check_single_word_name, {'book_cats': files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {'fas_cats': [str(x) for x in files['category_fas'].get('ID',[])]}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': color_p, 'cats': files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
    ]
    validations = [v for v in validations if not validator.skip_validation(v[0])]

    progress = st.progress(0)
    results = {}
    for i, (name, func, kwargs) in enumerate(validations):
        st.write(f"Running: {name}")
        try:
            results[name] = func(data, **kwargs)
        except Exception as e:
            st.warning(f"Error in {name}: {e}")
            results[name] = pd.DataFrame(columns=data.columns)
        progress.progress((i+1)/len(validations))

    # Build report
    rejected_sids = set()
    report = []
    for name, df in results.items():
        if df.empty or 'PRODUCT_SET_SID' not in df.columns: continue
        reason, comment = flags.get(name, ("1000007 - Other Reason", name))
        for sid in df['PRODUCT_SET_SID'].unique():
            if sid in rejected_sids: continue
            rejected_sids.add(sid)
            row = df[df['PRODUCT_SET_SID'] == sid].iloc[0]
            report.append({
                'ProductSetSid': sid,
                'ParentSKU': row.get('PARENTSKU', ''),
                'Status': 'Rejected',
                'Reason': reason,
                'Comment': comment,
                'FLAG': name,
                'SellerName': row.get('SELLER_NAME', '')
            })

    approved = data[~data['PRODUCT_SET_SID'].isin(rejected_sids)]
    for _, r in approved.iterrows():
        report.append({
            'ProductSetSid': r['PRODUCT_SET_SID'],
            'ParentSKU': r.get('PARENTSKU', ''),
            'Status': 'Approved',
            'Reason': '', 'Comment': '', 'FLAG': '', 'SellerName': r.get('SELLER_NAME', '')
        })

    return pd.DataFrame(report), results

# -------------------------------------------------
# EXPORTS (FIXED)
# -------------------------------------------------
def to_excel(df, reasons_df=pd.DataFrame()):
    out = BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        df[PRODUCTSETS_COLS].to_excel(writer, index=False, sheet_name="ProductSets")
        if not reasons_df.empty:
            cols = [c for c in REJECTION_REASONS_COLS if c in reasons_df.columns]
            if cols:
                reasons_df[cols].to_excel(writer, index=False, sheet_name="RejectionReasons")
    out.seek(0)
    return out.getvalue()

def to_excel_full_data(data_df, report_df):
    merged = data_df.merge(report_df[["ProductSetSid","Status","Reason","Comment","FLAG","SellerName"]], 
                          left_on="PRODUCT_SET_SID", right_on="ProductSetSid", how="left")
    out = BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        merged[FULL_DATA_COLS].to_excel(writer, index=False, sheet_name="ProductSets")
    out.seek(0)
    return out.getvalue()

# -------------------------------------------------
# UI
# -------------------------------------------------
st.title("Product Validation Tool – Jersey Check 100% ACTIVE")
support_files = load_all_support_files()
st.sidebar.success("Suspected counterfeit Jerseys (1000030) is ACTIVE")

country = st.selectbox("Country", ["Kenya", "Uganda"])
validator = CountryValidator(country)

uploaded = st.file_uploader("Upload CSV (semicolon)", type="csv")

if uploaded:
    try:
        df = pd.read_csv(uploaded, sep=';', encoding='ISO-8859-1', dtype=str).fillna('')
        if 'ACTIVE_STATUS_COUNTRY' in df.columns:
            df = df[df['ACTIVE_STATUS_COUNTRY'].astype(str).str.upper().str.contains(validator.code)]
        if df.empty:
            st.error(f"No {validator.code} products found")
            st.stop()

        report_df, flag_results = validate_products(df, support_files, validator)

        approved = report_df[report_df['Status']=='Approved']
        rejected = report_df[report_df['Status']=='Rejected']

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(df))
        c2.metric("Approved", len(approved))
        c3.metric("Rejected", len(rejected))
        c4.metric("Rejection Rate", f"{len(rejected)/len(df)*100:.1f}%" if len(df)>0 else "0%")

        sellers = ['All Sellers'] + sorted(df['SELLER_NAME'].dropna().unique().tolist())
        chosen = st.sidebar.multiselect("Filter by Seller", sellers, default=['All Sellers'])
        display_report = report_df if 'All Sellers' in chosen or not chosen else report_df[report_df['SellerName'].isin(chosen)]

        st.sidebar.download_button("Final Report", to_excel(display_report, support_files['reasons']), "final_report.xlsx")
        st.sidebar.download_button("Full Data Export", to_excel_full_data(df, report_df), "full_data.xlsx")

        for flag_name, flagged_df in flag_results.items():
            if not flagged_df.empty:
                with st.expander(f"{flag_name} – {len(flagged_df)} products", expanded=False):
                    cols = [c for c in ['PRODUCT_SET_SID','NAME','BRAND','SELLER_NAME','CATEGORY_CODE'] if c in flagged_df.columns]
                    st.dataframe(flagged_df[cols])

        st.download_button("Download Final Report (All Sellers)", to_excel(report_df, support_files['reasons']), "FINAL_ALL.xlsx")
        st.download_button("Download Full Data (All Sellers)", to_excel_full_data(df, report_df), "FULL_DATA_ALL.xlsx")

    except Exception as e:
        st.error("Error processing file")
        st.code(traceback.format_exc())
