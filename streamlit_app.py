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
    try:
        flag_mapping = {
            'Seller Not approved to sell Refurb': ('1000028 - Contact Support Refurb', "Seller not approved for Refurbished items."),
            'BRAND name repeated in NAME': ('1000002 - Ensure Brand Name Is Not Repeated', "Do not repeat brand in product name."),
            'Missing COLOR': ('1000005 - Confirm actual product colour', "Color missing in title or tab."),
            'Duplicate product': ('1000007 - Other Reason', "Avoid creating duplicate SKUs."),
            'Prohibited products': ('1000024 - Not Authorized', "Prohibited product detected."),
            'Single-word NAME': ('1000008 - Improve Product Name', "Product name too short."),
            'Unnecessary words in NAME': ('1000008 - Improve Product Name', "Remove unnecessary words from name."),
            'Generic BRAND Issues': ('1000014 - Request Brand Name', "Avoid 'Generic' for fashion."),
            'Counterfeit Sneakers': ('1000030 - Suspected Counterfeit', "Suspected fake sneakers."),
            'Seller Approve to sell books': ('1000028 - Contact Support', "Seller not approved for Books."),
            'Seller Approved to Sell Perfume': ('1000028 - Contact Support', "Seller not approved for Perfume."),
            'Suspected counterfeit Jerseys': ('1000030 - Suspected Counterfeit', "Suspected fake jerseys."),
            'Suspected Fake product': ('1000030 - Suspected Counterfeit', "Price suspiciously low for brand."),
            'Product Warranty': ('1000013 - Provide Warranty Details', "Warranty details required for this category."),
            'Sensitive words': ('1000001 - Brand NOT Allowed', "Banned brand detected.")
        }
        return flag_mapping
    except Exception: return {}

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

def compile_regex_patterns(words: List[str]) -> re.Pattern:
    if not words: return None
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
        filename = _self.config["prohibited_products_file"]
        return [w.lower() for w in load_txt_file(filename)]

# -------------------------------------------------
# Logic Helpers
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
    cols_to_propagate = ['COLOR_FAMILY', 'PRODUCT_WARRANTY', 'WARRANTY_DURATION', 'WARRANTY_ADDRESS', 'WARRANTY_TYPE']
    for col in cols_to_propagate:
        if col not in df.columns: df[col] = pd.NA
        df[col] = df.groupby('PRODUCT_SET_SID')[col].transform(lambda x: x.ffill().bfill())
    return df

# -------------------------------------------------
# CHECK FUNCTIONS
# -------------------------------------------------
def check_refurb_seller_approval(data: pd.DataFrame, approved_sellers_ke: List[str], approved_sellers_ug: List[str], country_code: str) -> pd.DataFrame:
    approved_sellers = set(approved_sellers_ke) if country_code == 'KE' else set(approved_sellers_ug)
    refurb_words = r'\b(refurb|refurbished|renewed)\b'
    data_cp = data.copy()
    data_cp['NAME_LOWER'] = data_cp['NAME'].astype(str).str.lower()
    data_cp['BRAND_LOWER'] = data_cp['BRAND'].astype(str).str.lower()
    data_cp['SELLER_LOWER'] = data_cp['SELLER_NAME'].astype(str).str.lower()
    trigger_mask = data_cp['NAME_LOWER'].str.contains(refurb_words, regex=True, na=False) | (data_cp['BRAND_LOWER'] == 'renewed')
    flagged = data_cp[trigger_mask & (~data_cp['SELLER_LOWER'].isin(approved_sellers))]
    return flagged.drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_unnecessary_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.lower().str.contains(pattern, na=False)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_product_warranty(data: pd.DataFrame, warranty_category_codes: List[str]) -> pd.DataFrame:
    data_cp = data.copy()
    for col in ['PRODUCT_WARRANTY', 'WARRANTY_DURATION']:
        if col not in data_cp.columns: data_cp[col] = ""
    data_cp['CAT_CLEAN'] = data_cp['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
    target_data = data_cp[data_cp['CAT_CLEAN'].isin([str(c) for c in warranty_category_codes])]
    def is_missing(s):
        s = s.astype(str).str.strip().str.lower()
        return (s == 'nan') | (s == '') | (s == 'none') | (s == 'n/a')
    mask = is_missing(target_data['PRODUCT_WARRANTY']) & is_missing(target_data['WARRANTY_DURATION'])
    return target_data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_missing_color(data: pd.DataFrame, pattern: re.Pattern, color_categories: List[str], country_code: str = 'KE') -> pd.DataFrame:
    data_cp = data[data['CATEGORY_CODE'].isin(color_categories)].copy()
    if data_cp.empty: return data_cp
    name_check = data_cp['NAME'].astype(str).str.lower().str.contains(pattern, na=False)
    color_check = data_cp['COLOR'].astype(str).str.lower().str.contains(pattern, na=False)
    if country_code == 'KE' and 'COLOR_FAMILY' in data_cp.columns:
        family_check = data_cp['COLOR_FAMILY'].astype(str).str.lower().str.contains(pattern, na=False)
        mask = ~(name_check | color_check | family_check)
    else:
        mask = ~(name_check | color_check)
    return data_cp[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.lower().str.contains(pattern, na=False)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_brand_in_name(data: pd.DataFrame) -> pd.DataFrame:
    mask = data.apply(lambda r: str(r['BRAND']).lower() in str(r['NAME']).lower() if pd.notna(r['BRAND']) and pd.notna(r['NAME']) else False, axis=1)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_duplicate_products(data: pd.DataFrame) -> pd.DataFrame:
    cols = ['NAME','BRAND','SELLER_NAME','COLOR']
    cols = [c for c in cols if c in data.columns]
    return data[data.duplicated(subset=cols, keep=False)].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_seller_approved_for_books(data: pd.DataFrame, book_category_codes: List[str], approved_book_sellers: List[str]) -> pd.DataFrame:
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_category_codes: List[str], approved_perfume_sellers: List[str], sensitive_perfume_brands: List[str]) -> pd.DataFrame:
    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    brand_lower = perfume_data['BRAND'].astype(str).str.lower()
    name_lower = perfume_data['NAME'].astype(str).str.lower()
    sensitive_mask = brand_lower.isin(sensitive_perfume_brands) | name_lower.apply(lambda x: any(b in x for b in sensitive_perfume_brands))
    fake_brand_mask = brand_lower.isin(['designers collection', 'smart collection', 'generic', 'original', 'fashion'])
    final_mask = (sensitive_mask | fake_brand_mask) & (~perfume_data['SELLER_NAME'].isin(approved_perfume_sellers))
    return perfume_data[final_mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_counterfeit_sneakers(data: pd.DataFrame, sneaker_category_codes: List[str], sneaker_sensitive_brands: List[str]) -> pd.DataFrame:
    sneaker_data = data[data['CATEGORY_CODE'].isin(sneaker_category_codes)].copy()
    brand_lower = sneaker_data['BRAND'].astype(str).str.lower()
    name_lower = sneaker_data['NAME'].astype(str).str.lower()
    brand_check = name_lower.apply(lambda x: any(b in x for b in sneaker_sensitive_brands))
    return sneaker_data[brand_lower.isin(['generic', 'fashion']) & brand_check].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_suspected_fake_products(data: pd.DataFrame, suspected_fake_df: pd.DataFrame, fx_rate: float = 132.0) -> pd.DataFrame:
    return pd.DataFrame(columns=data.columns) # Logic placeholder

def check_single_word_name(data: pd.DataFrame, book_category_codes: List[str]) -> pd.DataFrame:
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    mask = non_books['NAME'].astype(str).str.split().str.len() == 1
    return non_books[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_generic_brand_issues(data: pd.DataFrame, valid_category_codes_fas: List[str]) -> pd.DataFrame:
    mask = (data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(columns=data.columns) # Logic placeholder

# -------------------------------------------------
# MASTER VALIDATION RUNNER
# -------------------------------------------------
def validate_products(data: pd.DataFrame, support_files: Dict, country_validator: CountryValidator, data_has_warranty_cols: bool, common_sids: Optional[set] = None):
    flags_mapping = support_files['flags_mapping']
    
    validations = [
        ("Suspected Fake product", check_suspected_fake_products, {'suspected_fake_df': support_files['suspected_fake']}),
        ("Seller Not approved to sell Refurb", check_refurb_seller_approval, {'approved_sellers_ke': support_files['approved_refurb_sellers_ke'], 'approved_sellers_ug': support_files['approved_refurb_sellers_ug'], 'country_code': country_validator.code}),
        ("Product Warranty", check_product_warranty, {'warranty_category_codes': support_files['warranty_category_codes']}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': support_files['book_category_codes'], 'approved_book_sellers': support_files['approved_book_sellers']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'perfume_category_codes': support_files['perfume_category_codes'], 'approved_perfume_sellers': support_files['approved_perfume_sellers'], 'sensitive_perfume_brands': support_files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'sneaker_category_codes': support_files['sneaker_category_codes'], 'sneaker_sensitive_brands': support_files['sneaker_sensitive_brands']}),
        ("Suspected counterfeit Jerseys", check_counterfeit_jerseys, {'jerseys_df': support_files['jerseys_config']}),
        ("Prohibited products", check_prohibited_products, {'pattern': compile_regex_patterns(country_validator.load_prohibited_products())}),
        ("Unnecessary words in NAME", check_unnecessary_words, {'pattern': compile_regex_patterns(support_files['unnecessary_words'])}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': support_files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': compile_regex_patterns(support_files['colors']), 'color_categories': support_files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
    ]
    
    progress_bar = st.progress(0)
    results = {}
    processed_sids = set()
    rows = []

    # Map duplicates
    duplicate_map = {}
    dup_cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    if len(dup_cols) == 4:
        temp = data.copy()
        temp['key'] = temp[dup_cols].astype(str).sum(axis=1)
        groups = temp.groupby('key')['PRODUCT_SET_SID'].apply(list).to_dict()
        for sids in groups.values():
            if len(sids) > 1:
                for sid in sids: duplicate_map[sid] = sids

    for i, (name, func, kwargs) in enumerate(validations):
        if country_validator.should_skip_validation(name): continue
        
        # --- NEW LOGIC FOR INTERSECTION ONLY ---
        check_data = data.copy()
        if name in ["Missing COLOR", "Product Warranty"]:
            if common_sids is not None and len(common_sids) > 0:
                check_data = check_data[check_data['PRODUCT_SET_SID'].isin(common_sids)]
        
        if check_data.empty:
            results[name] = pd.DataFrame(columns=data.columns)
            continue

        ckwargs = {'data': check_data, **kwargs}
        if name == "Generic BRAND Issues":
            fas = support_files.get('category_fas', pd.DataFrame())
            ckwargs['valid_category_codes_fas'] = fas['ID'].astype(str).tolist() if not fas.empty else []
        elif name == "Missing COLOR":
            ckwargs['country_code'] = country_validator.code

        try:
            res = func(**ckwargs)
            if name != "Duplicate product" and not res.empty:
                flagged = set(res['PRODUCT_SET_SID'].unique())
                expanded = set()
                for sid in flagged: expanded.update(duplicate_map.get(sid, [sid]))
                res = data[data['PRODUCT_SET_SID'].isin(expanded)].copy()
            results[name] = res
        except Exception:
            results[name] = pd.DataFrame(columns=data.columns)
        
        progress_bar.progress((i + 1) / len(validations))

    # Build report
    for name, _, _ in validations:
        res = results.get(name, pd.DataFrame())
        if res.empty: continue
        reason_info = flags_mapping.get(name, ("1000007", "Flagged"))
        for sid in res['PRODUCT_SET_SID'].unique():
            if sid not in processed_sids:
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
# Main UI
# -------------------------------------------------
tab1, tab2 = st.tabs(["Daily Validation", "Analysis"])

with tab1:
    country = st.selectbox("Select Country", ["Kenya", "Uganda"])
    cv = CountryValidator(country)
    files = st.file_uploader("Upload Files", accept_multiple_files=True, type=['csv', 'xlsx'])
    
    if files:
        all_dfs = []
        sid_sets = []
        support = load_all_support_files()
        
        for f in files:
            try:
                # RECTIFIED ROBUST LOADER
                if f.name.endswith('.xlsx'):
                    df = pd.read_excel(f, engine='openpyxl', dtype=str)
                else:
                    f.seek(0)
                    try:
                        df = pd.read_csv(f, sep=',', encoding='utf-8', dtype=str)
                        if len(df.columns) <= 1: raise ValueError
                    except:
                        f.seek(0)
                        df = pd.read_csv(f, sep=';', encoding='ISO-8859-1', dtype=str)

                df = standardize_input_data(df)
                all_dfs.append(df)
                sid_sets.append(set(df['PRODUCT_SET_SID'].unique()))
            except Exception as e:
                st.error(f"Error loading {f.name}: {e}")

        if all_dfs:
            merged = pd.concat(all_dfs).drop_duplicates('PRODUCT_SET_SID')
            merged = filter_by_country(merged, cv, "Uploads")
            merged = propagate_metadata(merged)
            
            # Intersection logic
            intersection = set.intersection(*sid_sets) if len(sid_sets) > 1 else None
            
            has_warranty = all(c in merged.columns for c in ['PRODUCT_WARRANTY', 'WARRANTY_DURATION'])
            report, flag_dfs = validate_products(merged, support, cv, has_warranty, intersection)
            
            st.success(f"Processed {len(merged)} products.")
            st.download_button("Download Report", report.to_csv(index=False), "Report.csv")
