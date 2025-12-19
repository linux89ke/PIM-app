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
    # This is the base mapping. It will be updated by the Reason Editor in Session State.
    flag_mapping = {
        'Seller Not approved to sell Refurb': ('1000028 - Contact SS', "Confirm refurb possibility."),
        'BRAND name repeated in NAME': ('1000002 - Brand Repeat', "Don't repeat brand in name."),
        'Missing COLOR': ('1000005 - Confirm Color', "Mention color in title and tab."),
        'Duplicate product': ('1000007 - Other', "Avoid duplicate SKUs."),
        'Prohibited products': ('1000024 - No License', "Product unauthorized."),
        'Single-word NAME': ('1000008 - Improve Description', "Format: Name - Type - Color."),
        'Unnecessary words in NAME': ('1000008 - Improve Description', "Avoid unnecessary words."),
        'Generic BRAND Issues': ('1000014 - Brand Creation', "Request brand creation."),
        'Counterfeit Sneakers': ('1000030 - Counterfeit', "Suspected fake sneakers."),
        'Seller Approve to sell books': ('1000028 - Contact SS', "Confirm book sale eligibility."),
        'Seller Approved to Sell Perfume': ('1000028 - Contact SS', "Confirm perfume sale eligibility."),
        'Suspected counterfeit Jerseys': ('1000030 - Counterfeit', "Suspected fake jerseys."),
        'Suspected Fake product': ('1000030 - Counterfeit', "Price too low, suspected fake."),
        'Product Warranty': ('1000013 - Missing Warranty', "Provide warranty details."),
        'Sensitive words': ('1000001 - Brand NOT Allowed', "Restricted brand used.")
    }
    return flag_mapping

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
# Helper Logic
# -------------------------------------------------
def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
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

def compile_regex_patterns(words: List[str]) -> re.Pattern:
    if not words: return None
    pattern = '|'.join(r'\b' + re.escape(w) + r'\b' for w in words)
    return re.compile(pattern, re.IGNORECASE)

# --- Validation Functions (Truncated for brevity, assuming existing logic) ---
def check_refurb_seller_approval(data, approved_sellers_ke, approved_sellers_ug, country_code):
    approved = set(approved_sellers_ke) if country_code == 'KE' else set(approved_sellers_ug)
    refurb_words = r'\b(refurb|refurbished|renewed)\b'
    mask = data['NAME'].str.contains(refurb_words, case=False, na=False) | (data['BRAND'].str.lower() == 'renewed')
    flagged = data[mask & ~data['SELLER_NAME'].str.lower().isin(approved)]
    return flagged

def check_unnecessary_words(data, pattern):
    if pattern is None: return pd.DataFrame()
    mask = data['NAME'].str.contains(pattern, na=False)
    return data[mask]

def check_product_warranty(data, warranty_category_codes):
    data['CAT_CLEAN'] = data['CATEGORY_CODE'].astype(str).str.split('.').str[0]
    mask = data['CAT_CLEAN'].isin(warranty_category_codes)
    no_w = (data['PRODUCT_WARRANTY'].isna() | (data['PRODUCT_WARRANTY'] == "")) & \
           (data['WARRANTY_DURATION'].isna() | (data['WARRANTY_DURATION'] == ""))
    return data[mask & no_w]

def check_missing_color(data, pattern, color_categories, country_code):
    data_f = data[data['CATEGORY_CODE'].isin(color_categories)].copy()
    name_check = data_f['NAME'].str.contains(pattern, na=False)
    color_check = data_f['COLOR'].str.contains(pattern, na=False)
    return data_f[~(name_check | color_check)]

def check_brand_in_name(data):
    mask = data.apply(lambda r: str(r['BRAND']).lower() in str(r['NAME']).lower(), axis=1)
    return data[mask]

def check_duplicate_products(data):
    cols = ['NAME','BRAND','SELLER_NAME','COLOR']
    return data[data.duplicated(subset=cols, keep=False)]

def check_prohibited_products(data, pattern):
    if pattern is None: return pd.DataFrame()
    return data[data['NAME'].str.contains(pattern, na=False)]

def check_suspected_fake_products(data, suspected_fake_df, fx_rate):
    # Simplified placeholder for brevity
    return pd.DataFrame(columns=data.columns)

def check_seller_approved_for_books(data, book_category_codes, approved_book_sellers):
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)]

def check_seller_approved_for_perfume(data, perfume_category_codes, approved_perfume_sellers, sensitive_perfume_brands):
    perfumes = data[data['CATEGORY_CODE'].isin(perfume_category_codes)]
    mask = perfumes['BRAND'].str.lower().isin(sensitive_perfume_brands)
    return perfumes[mask & ~perfumes['SELLER_NAME'].isin(approved_perfume_sellers)]

def check_counterfeit_sneakers(data, sneaker_category_codes, sneaker_sensitive_brands):
    sneakers = data[data['CATEGORY_CODE'].isin(sneaker_category_codes)]
    mask = sneakers['NAME'].str.lower().apply(lambda x: any(b in x for b in sneaker_sensitive_brands))
    generic = sneakers['BRAND'].str.lower().isin(['generic', 'fashion'])
    return sneakers[mask & generic]

def check_counterfeit_jerseys(data, jerseys_df):
    return pd.DataFrame(columns=data.columns) # Placeholder

def check_single_word_name(data, book_category_codes):
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['NAME'].str.split().str.len() == 1]

def check_generic_brand_issues(data, valid_category_codes_fas):
    return data[data['CATEGORY_CODE'].isin(valid_category_codes_fas) & (data['BRAND'] == 'Generic')]

# --- Master Runner ---
def validate_products(data, support_files, country_validator, data_has_warranty_cols):
    flags_mapping = support_files['flags_mapping']
    validations = [
        ("Suspected Fake product", check_suspected_fake_products, {'suspected_fake_df': support_files['suspected_fake'], 'fx_rate': FX_RATE}),
        ("Seller Not approved to sell Refurb", check_refurb_seller_approval, {'approved_sellers_ke': support_files['approved_refurb_sellers_ke'], 'approved_sellers_ug': support_files['approved_refurb_sellers_ug'], 'country_code': country_validator.code}),
        ("Product Warranty", check_product_warranty, {'warranty_category_codes': support_files['warranty_category_codes']}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': support_files['book_category_codes'], 'approved_book_sellers': support_files['approved_book_sellers']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'perfume_category_codes': support_files['perfume_category_codes'], 'approved_perfume_sellers': support_files['approved_perfume_sellers'], 'sensitive_perfume_brands': support_files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'sneaker_category_codes': support_files['sneaker_category_codes'], 'sneaker_sensitive_brands': support_files['sneaker_sensitive_brands']}),
        ("Suspected counterfeit Jerseys", check_counterfeit_jerseys, {'jerseys_df': support_files['jerseys_config']}),
        ("Prohibited products", check_prohibited_products, {'pattern': compile_regex_patterns(country_validator.load_prohibited_products())}),
        ("Unnecessary words in NAME", check_unnecessary_words, {'pattern': compile_regex_patterns(support_files['unnecessary_words'])}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': support_files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {'valid_category_codes_fas': support_files['category_fas']['ID'].astype(str).tolist() if 'ID' in support_files['category_fas'].columns else []}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': compile_regex_patterns(support_files['colors']), 'color_categories': support_files['color_categories'], 'country_code': country_validator.code}),
        ("Duplicate product", check_duplicate_products, {}),
    ]
    
    results = {}
    processed_sids = set()
    rows = []

    for name, func, kwargs in validations:
        if country_validator.should_skip_validation(name): continue
        res = func(data=data, **kwargs)
        if not res.empty:
            flagged_sids = res['PRODUCT_SET_SID'].unique()
            results[name] = data[data['PRODUCT_SET_SID'].isin(flagged_sids)]
            for sid in flagged_sids:
                if sid not in processed_sids:
                    reason_info = flags_mapping.get(name, ("Other", "Flagged"))
                    row = data[data['PRODUCT_SET_SID'] == sid].iloc[0]
                    rows.append({
                        'ProductSetSid': sid, 'ParentSKU': row.get('PARENTSKU', ''), 'Status': 'Rejected',
                        'Reason': reason_info[0], 'Comment': reason_info[1], 'FLAG': name, 'SellerName': row.get('SELLER_NAME', '')
                    })
                    processed_sids.add(sid)

    approved = data[~data['PRODUCT_SET_SID'].isin(processed_sids)]
    for _, r in approved.iterrows():
        rows.append({
            'ProductSetSid': r['PRODUCT_SET_SID'], 'ParentSKU': r.get('PARENTSKU', ''), 'Status': 'Approved',
            'Reason': "", 'Comment': "", 'FLAG': "", 'SellerName': r.get('SELLER_NAME', '')
        })
    
    return pd.DataFrame(rows), results

# -------------------------------------------------
# UI - MAIN APP
# -------------------------------------------------
# Initialize Session State
if 'manual_approvals' not in st.session_state:
    st.session_state.manual_approvals = set()

with st.spinner("Loading configuration files..."):
    support_files = load_all_support_files()

st.title("Product Validation Tool")

tab1, tab2 = st.tabs(["Daily Validation", "Weekly Analysis"])

with tab1:
    col_l, col_r = st.columns([1, 1])
    country = col_l.selectbox("Select Country", ["Kenya", "Uganda"])
    country_validator = CountryValidator(country)
    
    uploaded_files = st.file_uploader("Upload files", type=['csv', 'xlsx'], accept_multiple_files=True)
    
    # REJECTION REASON EDITOR
    with st.expander("⚙️ Edit Rejection Reasons & Comments"):
        for flag_name, (reason, comment) in support_files['flags_mapping'].items():
            c1, c2 = st.columns([1, 2])
            new_r = c1.text_input(f"Reason: {flag_name}", value=reason, key=f"r_{flag_name}")
            new_c = c2.text_area(f"Comment: {flag_name}", value=comment, key=f"c_{flag_name}", height=68)
            support_files['flags_mapping'][flag_name] = (new_r, new_c)

    if uploaded_files:
        all_dfs = [standardize_input_data(pd.read_excel(f) if f.name.endswith('.xlsx') else pd.read_csv(f, encoding='ISO-8859-1')) for f in uploaded_files]
        merged_data = pd.concat(all_dfs).drop_duplicates(subset=['PRODUCT_SET_SID'])
        
        final_report, flag_dfs = validate_products(merged_data, support_files, country_validator, True)
        
        # Apply Overrides to Report
        final_report.loc[final_report['ProductSetSid'].isin(st.session_state.manual_approvals), 'Status'] = 'Approved'
        final_report.loc[final_report['ProductSetSid'].isin(st.session_state.manual_approvals), 'Comment'] = 'Manual QC Pass'

        # Global Search
        search_query = st.text_input("🔍 Global Search", placeholder="Search SID, Name, or Seller...").lower()
        
        # Results Loop
        st.subheader("Validation Results by Flag")
        for title, df_flagged in flag_dfs.items():
            # Filter manually approved items and apply search
            df_remaining = df_flagged[~df_flagged['PRODUCT_SET_SID'].isin(st.session_state.manual_approvals)]
            if search_query:
                mask = df_remaining.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
                df_display = df_remaining[mask].copy()
            else:
                df_display = df_remaining.copy()

            with st.expander(f"{title} ({len(df_display)})"):
                if not df_display.empty:
                    df_display.insert(0, "Override Approval", False)
                    cols = ["Override Approval"] + [c for c in VISIBLE_COLUMNS if c in df_display.columns]
                    
                    edited_df = st.data_editor(
                        df_display[cols],
                        column_config={"Override Approval": st.column_config.CheckboxColumn("Approve?"), "MAIN_IMAGE": st.column_config.ImageColumn("Preview")},
                        disabled=[c for c in cols if c != "Override Approval"],
                        hide_index=True, key=f"ed_{title}"
                    )
                    
                    new_approvals = edited_df[edited_df["Override Approval"] == True]["PRODUCT_SET_SID"].tolist()
                    if new_approvals and st.button(f"Confirm Overrides for {title}", key=f"btn_conf_{title}"):
                        st.session_state.manual_approvals.update(new_approvals)
                        st.rerun()
                else:
                    st.success("Clear!")

        # Final Exports
        st.divider()
        st.header("Overall Exports")
        c1, c2, c3 = st.columns(3)
        rej_df = final_report[final_report['Status'] == 'Rejected']
        app_df = final_report[final_report['Status'] == 'Approved']
        
        c1.download_button("Download Final Report", final_report.to_csv(index=False), "Report.csv")
        c2.download_button("Download Approved", app_df.to_csv(index=False), "Approved.csv")
        c3.download_button("Download Rejected", rej_df.to_csv(index=False), "Rejected.csv")
