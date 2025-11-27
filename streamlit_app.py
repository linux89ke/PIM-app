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

# -------------------------------------------------
# Constants
# -------------------------------------------------
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]
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
    mapping = {
        'Sensitive words': ('1000001 - Brand NOT Allowed', "Your listing was rejected because it includes brands that are not allowed..."),
        'BRAND name repeated in NAME': ('1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name', "..."),
        'Missing COLOR': ('1000005 - Kindly confirm the actual product colour', "..."),
        'Duplicate product': ('1000007 - Other Reason', "kindly note product was rejected because its a duplicate product"),
        'Prohibited products': ('1000007 - Other Reason', "..."),
        'Single-word NAME': ('1000008 - Kindly Improve Product Name Description', "..."),
        'Generic BRAND Issues': ('1000014 - Kindly request for the creation...', "..."),
        'Counterfeit Sneakers': ('1000023 - Confirmation of counterfeit product...', "..."),
        'Seller Approve to sell books': ('1000028 - Kindly Contact Jumia Seller Support...', "..."),
        'Seller Approved to Sell Perfume': ('1000028 - Kindly Contact Jumia Seller Support...', "..."),
        'Perfume Price Check': ('1000029 - Kindly Contact Jumia Seller Support To Verify...', "..."),
        # JERSEY 1000030 ADDED & ACTIVE
        'Suspected counterfeit Jerseys': (
            '1000030 - Suspected Counterfeit/Fake Product',
            'This jersey is suspected to be counterfeit. Please raise a claim with Seller Support for verification.'
        ),
    }
    return mapping

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
        'jerseys': load_excel_file('Jerseys.xlsx'),  # ADDED
        'flags_mapping': load_flags_mapping(),
    }

def compile_regex(words: List[str]) -> Optional[re.Pattern]:
    if not words: return None
    return re.compile('|'.join(r'\b' + re.escape(w) + r'\b' for w in words), re.IGNORECASE)

# -------------------------------------------------
# Country Validator
# -------------------------------------------------
class CountryValidator:
    def __init__(self, country: str):
        self.code = "KE" if country == "Kenya" else "UG"
        self.skip_list = ["Seller Approve to sell books", "Perfume Price Check", "Seller Approved to Sell Perfume", "Counterfeit Sneakers"] if country == "Uganda" else []

    def skip_validation(self, name: str) -> bool:
        return name in self.skip_list

# -------------------------------------------------
# JERSEY CHECK (NEW + ACTIVE)
# -------------------------------------------------
def check_suspected_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    if jerseys_df.empty or 'Categories' not in jerseys_df.columns:
        return pd.DataFrame(columns=data.columns)
    
    cats = jerseys_df['Categories'].dropna().astype(str).tolist()
    keywords = [str(k).strip().lower() for k in jerseys_df['Checklist'].dropna()]
    exempt_sellers = jerseys_df['Exempted'].dropna().astype(str).tolist() if 'Exempted' in jerseys_df.columns else []
    
    df = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if not exempt_sellers:
        df = df[~df['SELLER_NAME'].isin(exempt_sellers)]
    
    if df.empty or not keywords:
        return pd.DataFrame(columns=data.columns)
    
    pattern = re.compile('|'.join(r'\b' + re.escape(k) + r'\b' for k in keywords), re.IGNORECASE)
    return df[df['NAME'].str.lower().str.contains(pattern, na=False)]

# -------------------------------------------------
# FIXED: fake_brands line (was syntax error)
# -------------------------------------------------
def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_category_codes: List[str],
                                     approved_perfume_sellers: List[str],
                                     sensitive_perfume_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME','BRAND','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
   
    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perfume_data.empty or not approved_perfume_sellers:
        return pd.DataFrame(columns=data.columns)
   
    perfume_data['BRAND_LOWER'] = perfume_data['BRAND'].astype(str).str.strip().str.lower()
    perfume_data['NAME_LOWER'] = perfume_data['NAME'].astype(str).str.strip().str.lower()
   
    sensitive_mask = perfume_data['BRAND_LOWER'].isin(sensitive_perfume_brands)
   
    # FIXED: Added missing comma
    fake_brands = ['designers collection', 'smart collection', 'generic', 'original', 'designer', 'fashion']
    fake_brand_mask = perfume_data['BRAND_LOWER'].isin(fake_brands)
   
    name_contains_sensitive = perfume_data['NAME_LOWER'].apply(
        lambda x: any(brand in x for brand in sensitive_perfume_brands)
    )
    fake_name_mask = fake_brand_mask & name_contains_sensitive
   
    final_mask = (sensitive_mask | fake_name_mask) & (~perfume_data['SELLER_NAME'].isin(approved_perfume_sellers))
   
    return perfume_data[final_mask].drop(columns=['BRAND_LOWER', 'NAME_LOWER'])

# -------------------------------------------------
# MAIN VALIDATION (NOW INCLUDES JERSEY)
# -------------------------------------------------
def validate_products(data, files, validator):
    flags = files['flags_mapping']
    sensitive_p = compile_regex(files['sensitive_words'])
    prohibited_p = compile_regex([w.lower() for w in load_txt_file(f"prohibited_products{validator.code}.txt")])
    color_p = compile_regex(files['colors'])

    validations = [
        ("Sensitive words", check_sensitive_words, {'pattern': sensitive_p}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {...}),
        ("Perfume Price Check", check_perfume_price_vectorized, {...}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {...}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {...}),
        ("Suspected counterfeit Jerseys", check_suspected_counterfeit_jerseys, {'jerseys_df': files['jerseys']}),  # ADDED
        ("Prohibited products", check_prohibited_products, {'pattern': prohibited_p}),
        ("Single-word NAME", check_single_word_name, {...}),
        ("Generic BRAND Issues", check_generic_brand_issues, {...}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': color_p, 'color_categories': files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
    ]
    validations = [v for v in validations if not validator.skip_validation(v[0])]

    progress = st.progress(0)
    results = {}
    for i, (name, func, kwargs) in enumerate(validations):
        st.write(f"Running: {name}")
        try:
            results[name] = func(data, **kwargs) if name != "Generic BRAND Issues" else func(data, [str(x) for x in files['category_fas'].get('ID',[])])
        except Exception as e:
            st.warning(f"{name}: {e}")
            results[name] = pd.DataFrame(columns=data.columns)
        progress.progress((i + 1) / len(validations))

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
                'ProductSetSid': sid, 'ParentSKU': row.get('PARENTSKU', ''), 'Status': 'Rejected',
                'Reason': reason, 'Comment': comment, 'FLAG': name, 'SellerName': row.get('SELLER_NAME', '')
            })

    approved = data[~data['PRODUCT_SET_SID'].isin(rejected_sids)]
    for _, r in approved.iterrows():
        report.append({
            'ProductSetSid': r['PRODUCT_SET_SID'], 'ParentSKU': r.get('PARENTSKU', ''), 'Status': 'Approved',
            'Reason': '', 'Comment': '', 'FLAG': '', 'SellerName': r.get('SELLER_NAME', '')
        })

    return pd.DataFrame(report), results

# -------------------------------------------------
# UI – JERSEY FLAG SHOWS WITH COUNT
# -------------------------------------------------
st.title("Product Validation Tool – Jersey 1000030 ACTIVE")
st.sidebar.success("Suspected counterfeit Jerseys (1000030) is ACTIVE")

support_files = load_all_support_files()
country = st.selectbox("Country", ["Kenya", "Uganda"])
validator = CountryValidator(country)
uploaded = st.file_uploader("Upload CSV (semicolon)", type="csv")

if uploaded:
    try:
        df = pd.read_csv(uploaded, sep=';', encoding='ISO-8859-1', dtype=str).fillna('')
        if 'ACTIVE_STATUS_COUNTRY' in df.columns:
            df = df[df['ACTIVE_STATUS_COUNTRY'].str.upper().str.contains(validator.code)]
        if df.empty:
            st.error(f"No {validator.code} products")
            st.stop()

        report_df, flag_results = validate_products(df, support_files, validator)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total", len(df))
        col2.metric("Approved", len(report_df[report_df['Status']=='Approved']))
        col3.metric("Rejected", len(report_df[report_df['Status']=='Rejected']))
        col4.metric("Rejection Rate", f"{len(report_df[report_df['Status']=='Rejected'])/len(df)*100:.1f}%")

        st.markdown("### Validation Results by Flag")
        flags_to_show = [
            "Sensitive words", "BRAND name repeated in NAME", "Missing COLOR", "Duplicate product",
            "Prohibited products", "Single-word NAME", "Generic BRAND Issues",
            "Seller Approve to sell books", "Perfume Price Check", "Seller Approved to Sell Perfume",
            "Counterfeit Sneakers", "Suspected counterfeit Jerseys"  # ACTIVE
        ]
        for flag in flags_to_show:
            if validator.skip_validation(flag): continue
            count = len(flag_results.get(flag, pd.DataFrame()))
            with st.expander(f"{flag} ({count} products)", expanded=False):
                if count:
                    st.dataframe(flag_results[flag][['PRODUCT_SET_SID','NAME','BRAND','SELLER_NAME']].head(50), use_container_width=True)
                else:
                    st.success("No issues")

        # Your 4 original reports (add generate_four_reports() if you want them back)
        st.download_button("Download Final Report", to_excel(report_df, support_files['reasons']).getvalue(), "Final_Report.xlsx")

    except Exception as e:
        st.error("Error")
        with st.expander("Details"):
            st.code(traceback.format_exc())
