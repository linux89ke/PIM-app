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
import altair as alt # Added for charts

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
st.set_page_config(page_title="Product Validation Tool", layout="wide") # Changed to wide layout for dashboards

# -------------------------------------------------
# Constants & Mapping
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

# MAPPING: New File Columns -> Script Internal Columns
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
    'list_seller_skus': 'SELLER_SKU',
    'image1': 'MAIN_IMAGE',
    'dsc_status': 'LISTING_STATUS',
    'dsc_shop_email': 'SELLER_EMAIL'
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
        # Manual mapping for demonstration/fallback
        flag_mapping = {
            'Sensitive words': ('1000001 - Brand NOT Allowed', "Your listing was rejected because it includes brands that are not allowed on Jumia..."),
            'BRAND name repeated in NAME': ('1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name', "Please do not write the brand name in the Product Name field..."),
            'Missing COLOR': ('1000005 - Kindly confirm the actual product colour', "Please make sure that the product color is clearly mentioned..."),
            'Duplicate product': ('1000007 - Other Reason', "kindly note product was rejected because its a duplicate product"),
            'Prohibited products': ('1000007 - Other Reason', "Kindly note this product is not allowed for listing on Jumia..."),
            'Single-word NAME': ('1000008 - Kindly Improve Product Name Description', "Kindly update the product title using this format..."),
            'Generic BRAND Issues': ('1000014 - Kindly request for the creation of this product\'s actual brand name...', "To create the actual brand name for this product..."),
            'Counterfeit Sneakers': ('1000023 - Confirmation of counterfeit product by Jumia technical team...', "Your listing has been rejected as Jumia's technical team has confirmed..."),
            'Seller Approve to sell books': ('1000028 - Kindly Contact Jumia Seller Support...', "Please contact Jumia Seller Support and raise a claim..."),
            'Seller Approved to Sell Perfume': ('1000028 - Kindly Contact Jumia Seller Support...', "Please contact Jumia Seller Support and raise a claim..."),
            'Perfume Price Check': ('1000029 - Kindly Contact Jumia Seller Support To Verify This Product\'s Authenticity...', "Please contact Jumia Seller Support to raise a claim..."),
            'Suspected counterfeit Jerseys': ('1000030 - Suspected Counterfeit Product', "Your listing has been rejected as it is suspected to be a counterfeit jersey..."),
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
        'colors': [c.lower() for c in load_txt_file('colors.txt')],
        'color_categories': load_txt_file('color_cats.txt'),
        'check_variation': load_excel_file('check_variation.xlsx'),
        'category_fas': load_excel_file('category_FAS.xlsx'),
        'perfumes': load_excel_file('perfumes.xlsx'),
        'reasons': load_excel_file('reasons.xlsx'),
        'flags_mapping': load_flags_mapping(),
        'jerseys_config': load_excel_file('Jerseys.xlsx'),
    }
    return files

@st.cache_data(ttl=3600)
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
        if 'Status' not in df.columns: df['Status'] = 'Approved'
        return df
    @st.cache_data(ttl=3600)
    def load_prohibited_products(_self) -> List[str]:
        filename = _self.config["prohibited_products_file"]
        return [w.lower() for w in load_txt_file(filename)]

# -------------------------------------------------
# Data Loading & Validation Functions
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

def filter_by_country(df: pd.DataFrame, country_validator: CountryValidator, source: str) -> pd.DataFrame:
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns: return df
    df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.strip().str.upper()
    mask = df['ACTIVE_STATUS_COUNTRY'] == country_validator.code
    filtered = df[mask].copy()
    if filtered.empty:
        st.error(f"No {country_validator.code} rows left in {source}")
        st.stop()
    return filtered

# --- Validation Logic Functions (Same as before) ---
def check_sensitive_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    return data[mask]

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    return data[mask]

def check_missing_color(data: pd.DataFrame, pattern: re.Pattern, color_categories: List[str]) -> pd.DataFrame:
    if not {'NAME', 'COLOR', 'CATEGORY_CODE'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    data = data[data['CATEGORY_CODE'].isin(color_categories)].copy()
    if data.empty: return pd.DataFrame(columns=data.columns)
    mask = ~(data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False) | 
             data['COLOR'].astype(str).str.strip().str.lower().str.contains(pattern, na=False))
    return data[mask]

def check_brand_in_name(data: pd.DataFrame) -> pd.DataFrame:
    if not {'BRAND','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    mask = data.apply(lambda r: str(r['BRAND']).strip().lower() in str(r['NAME']).strip().lower() 
                      if pd.notna(r['BRAND']) and pd.notna(r['NAME']) else False, axis=1)
    return data[mask]

def check_duplicate_products(data: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    if len(cols) < 4: return pd.DataFrame(columns=data.columns)
    return data[data.duplicated(subset=cols, keep=False)]

def check_seller_approved_for_books(data: pd.DataFrame, book_category_codes: List[str], approved_book_sellers: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if books.empty: return pd.DataFrame(columns=data.columns)
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)]

def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_category_codes: List[str], approved_perfume_sellers: List[str], sensitive_perfume_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME','BRAND','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perfume_data.empty: return pd.DataFrame(columns=data.columns)
    brand_lower = perfume_data['BRAND'].astype(str).str.strip().str.lower()
    name_lower = perfume_data['NAME'].astype(str).str.strip().str.lower()
    sensitive_mask = brand_lower.isin(sensitive_perfume_brands)
    fake_brands = ['designers collection', 'smart collection', 'generic', 'original', 'fashion']
    fake_brand_mask = brand_lower.isin(fake_brands)
    name_contains_sensitive = name_lower.apply(lambda x: any(brand in x for brand in sensitive_perfume_brands))
    final_mask = (sensitive_mask | (fake_brand_mask & name_contains_sensitive)) & (~perfume_data['SELLER_NAME'].isin(approved_perfume_sellers))
    return perfume_data[final_mask]

def check_counterfeit_sneakers(data: pd.DataFrame, sneaker_category_codes: List[str], sneaker_sensitive_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'NAME', 'BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    sneaker_data = data[data['CATEGORY_CODE'].isin(sneaker_category_codes)].copy()
    if sneaker_data.empty: return pd.DataFrame(columns=data.columns)
    brand_lower = sneaker_data['BRAND'].astype(str).str.strip().str.lower()
    name_lower = sneaker_data['NAME'].astype(str).str.strip().str.lower()
    fake_brand_mask = brand_lower.isin(['generic', 'fashion'])
    name_contains_brand = name_lower.apply(lambda x: any(brand in x for brand in sneaker_sensitive_brands))
    return sneaker_data[fake_brand_mask & name_contains_brand]

def check_perfume_price_vectorized(data: pd.DataFrame, perfumes_df: pd.DataFrame, perfume_category_codes: List[str]) -> pd.DataFrame:
    req = ['CATEGORY_CODE','NAME','BRAND','GLOBAL_SALE_PRICE','GLOBAL_PRICE']
    if not all(c in data.columns for c in req) or perfumes_df.empty: return pd.DataFrame(columns=data.columns)
    perf = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perf.empty: return pd.DataFrame(columns=data.columns)
    
    perf['price_to_use'] = perf['GLOBAL_SALE_PRICE'].where((perf['GLOBAL_SALE_PRICE'].notna()) & (perf['GLOBAL_SALE_PRICE'] > 0), perf['GLOBAL_PRICE'])
    currency = perf.get('CURRENCY', pd.Series(['KES'] * len(perf)))
    perf['price_usd'] = perf['price_to_use'].where(currency.astype(str).str.upper() != 'KES', perf['price_to_use'] / FX_RATE)
    
    perf['BRAND_LOWER'] = perf['BRAND'].astype(str).str.strip().str.lower()
    perf['NAME_LOWER'] = perf['NAME'].astype(str).str.strip().str.lower()
    perfumes_df = perfumes_df.copy()
    perfumes_df['BRAND_LOWER'] = perfumes_df['BRAND'].astype(str).str.strip().str.lower()
    if 'PRODUCT_NAME' in perfumes_df.columns:
        perfumes_df['PRODUCT_NAME_LOWER'] = perfumes_df['PRODUCT_NAME'].astype(str).str.strip().str.lower()
    
    merged = perf.merge(perfumes_df, on='BRAND_LOWER', how='left', suffixes=('', '_ref'))
    if 'PRODUCT_NAME_LOWER' in merged.columns:
        merged = merged[merged.apply(lambda r: r['PRODUCT_NAME_LOWER'] in r['NAME_LOWER'] if pd.notna(r['PRODUCT_NAME_LOWER']) else False, axis=1)]
    
    if 'PRICE_USD' in merged.columns:
        flagged = merged[merged['PRICE_USD'] - merged['price_usd'] >= 30]
        return flagged[data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])
    return pd.DataFrame(columns=data.columns)

def check_single_word_name(data: pd.DataFrame, book_category_codes: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1]

def check_generic_brand_issues(data: pd.DataFrame, valid_category_codes_fas: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    return data[data['CATEGORY_CODE'].isin(valid_category_codes_fas) & (data['BRAND']=='Generic')]

def check_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    req = ['CATEGORY_CODE', 'NAME', 'SELLER_NAME']
    if not all(c in data.columns for c in req) or jerseys_df.empty: return pd.DataFrame(columns=data.columns)
    
    jersey_cats = jerseys_df['Categories'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().unique().tolist()
    jersey_cats = [c for c in jersey_cats if c.lower() != 'nan']
    keywords = [w for w in jerseys_df['Checklist'].astype(str).str.strip().str.lower().unique().tolist() if w and w!='nan']
    exempt = [s for s in jerseys_df['Exempted'].astype(str).str.strip().unique().tolist() if s and s.lower()!='nan']
    
    if not jersey_cats or not keywords: return pd.DataFrame(columns=data.columns)
    
    regex = re.compile('|'.join(r'\b' + re.escape(w) + r'\b' for w in keywords), re.IGNORECASE)
    
    data['CAT_STR'] = data['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
    jerseys = data[data['CAT_STR'].isin(jersey_cats)].copy()
    
    if jerseys.empty: return pd.DataFrame(columns=data.columns)
    
    target = jerseys[~jerseys['SELLER_NAME'].isin(exempt)].copy()
    if target.empty: return pd.DataFrame(columns=data.columns)
    
    mask = target['NAME'].astype(str).str.strip().str.lower().str.contains(regex, na=False)
    flagged = target[mask]
    
    return flagged.drop(columns=['CAT_STR']) if 'CAT_STR' in flagged.columns else flagged

# -------------------------------------------------
# Master validation runner
# -------------------------------------------------
def validate_products(data: pd.DataFrame, support_files: Dict, country_validator: CountryValidator):
    flags_mapping = support_files['flags_mapping']
    
    validations = [
        ("Sensitive words", check_sensitive_words, {'pattern': compile_regex_patterns(support_files['sensitive_words'])}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': support_files['book_category_codes'], 'approved_book_sellers': support_files['approved_book_sellers']}),
        ("Perfume Price Check", check_perfume_price_vectorized, {'perfumes_df': support_files['perfumes'], 'perfume_category_codes': support_files['perfume_category_codes']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'perfume_category_codes': support_files['perfume_category_codes'], 'approved_perfume_sellers': support_files['approved_perfume_sellers'], 'sensitive_perfume_brands': support_files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'sneaker_category_codes': support_files['sneaker_category_codes'], 'sneaker_sensitive_brands': support_files['sneaker_sensitive_brands']}),
        ("Suspected counterfeit Jerseys", check_counterfeit_jerseys, {'jerseys_df': support_files['jerseys_config']}),
        ("Prohibited products", check_prohibited_products, {'pattern': compile_regex_patterns(country_validator.load_prohibited_products())}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': support_files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': compile_regex_patterns(support_files['colors']), 'color_categories': support_files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
    ]
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    results = {}
    
    for i, (name, func, kwargs) in enumerate(validations):
        if country_validator.should_skip_validation(name): continue
        status_text.text(f"Running: {name}")
        ckwargs = {'data': data, **kwargs}
        if name == "Generic BRAND Issues":
             fas = support_files.get('category_fas', pd.DataFrame())
             ckwargs['valid_category_codes_fas'] = fas['ID'].astype(str).tolist() if not fas.empty and 'ID' in fas.columns else []
        
        try:
            res = func(**ckwargs)
            results[name] = res if not res.empty else pd.DataFrame(columns=data.columns)
        except Exception:
            results[name] = pd.DataFrame(columns=data.columns)
        progress_bar.progress((i + 1) / len(validations))
    
    status_text.text("Finalizing...")
    rows = []
    processed = set()
    
    for name, _, _ in validations:
        if name not in results or results[name].empty: continue
        res = results[name]
        if 'PRODUCT_SET_SID' not in res.columns: continue
        
        reason_info = flags_mapping.get(name, ("1000007 - Other Reason", f"Flagged by {name}"))
        flagged = pd.merge(res[['PRODUCT_SET_SID']].drop_duplicates(), data, on='PRODUCT_SET_SID', how='left')
        
        for _, r in flagged.iterrows():
            sid = r['PRODUCT_SET_SID']
            if sid in processed: continue
            processed.add(sid)
            rows.append({
                'ProductSetSid': sid, 'ParentSKU': r.get('PARENTSKU', ''), 'Status': 'Rejected',
                'Reason': reason_info[0], 'Comment': reason_info[1], 'FLAG': name, 'SellerName': r.get('SELLER_NAME', '')
            })
    
    approved = data[~data['PRODUCT_SET_SID'].isin(processed)]
    for _, r in approved.iterrows():
        rows.append({
            'ProductSetSid': r['PRODUCT_SET_SID'], 'ParentSKU': r.get('PARENTSKU', ''), 'Status': 'Approved',
            'Reason': "", 'Comment': "", 'FLAG': "", 'SellerName': r.get('SELLER_NAME', '')
        })
    
    progress_bar.empty()
    status_text.empty()
    return country_validator.ensure_status_column(pd.DataFrame(rows)), results

# -------------------------------------------------
# Export Logic
# -------------------------------------------------
def to_excel_base(df, sheet, cols, writer):
    df_p = df.copy()
    for c in cols: 
        if c not in df_p.columns: df_p[c] = pd.NA
    df_p[[c for c in cols if c in df_p.columns]].to_excel(writer, index=False, sheet_name=sheet)

def to_excel_full_data(data_df, final_report_df):
    try:
        output = BytesIO()
        d_cp = data_df.copy()
        r_cp = final_report_df.copy()
        
        # Merge logic
        d_cp['PRODUCT_SET_SID'] = d_cp['PRODUCT_SET_SID'].astype(str).str.strip()
        r_cp['ProductSetSid'] = r_cp['ProductSetSid'].astype(str).str.strip()
        merged = pd.merge(d_cp, r_cp[["ProductSetSid", "Status", "Reason", "Comment", "FLAG", "SellerName"]],
                          left_on="PRODUCT_SET_SID", right_on="ProductSetSid", how='left')
        
        if 'ProductSetSid_y' in merged.columns: merged.drop(columns=['ProductSetSid_y'], inplace=True)
        if 'ProductSetSid_x' in merged.columns: merged.rename(columns={'ProductSetSid_x': 'PRODUCT_SET_SID'}, inplace=True)
        
        export_cols = FULL_DATA_COLS + [c for c in ["Status", "Reason", "Comment", "FLAG", "SellerName"] if c not in FULL_DATA_COLS]
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            to_excel_base(merged, "ProductSets", export_cols, writer)
            
            # Helper for summary sheets
            wb = writer.book
            ws = wb.add_worksheet('Sellers Data')
            fmt = wb.add_format({'bold': True, 'bg_color': '#E6F0FA', 'border': 1, 'align': 'center'})
            
            # Sellers Summary
            if 'SELLER_RATING' in merged.columns:
                merged['Rejected_Count'] = (merged['Status'] == 'Rejected').astype(int)
                merged['Approved_Count'] = (merged['Status'] == 'Approved').astype(int)
                summ = merged.groupby('SELLER_NAME').agg(
                    Rejected=('Rejected_Count', 'sum'), Approved=('Approved_Count', 'sum'),
                    AvgRating=('SELLER_RATING', 'mean'), TotalStock=('STOCK_QTY', 'sum')
                ).reset_index().sort_values('Rejected', ascending=False)
                summ.insert(0, 'Rank', range(1, len(summ) + 1))
                
                ws.write(0, 0, "Sellers Summary", fmt)
                summ.to_excel(writer, sheet_name='Sellers Data', startrow=1, index=False)
                row_cursor = len(summ) + 4
            else:
                row_cursor = 1

            # Category Summary
            if 'CATEGORY' in merged.columns:
                cat_summ = merged[merged['Status']=='Rejected'].groupby('CATEGORY').size().reset_index(name='Rejected Products').sort_values('Rejected Products', ascending=False)
                cat_summ.insert(0, 'Rank', range(1, len(cat_summ) + 1))
                ws.write(row_cursor, 0, "Categories Summary", fmt)
                cat_summ.to_excel(writer, sheet_name='Sellers Data', startrow=row_cursor+1, index=False)
                row_cursor += len(cat_summ) + 4
            
            # Reasons Summary
            if 'Reason' in merged.columns:
                rsn_summ = merged[merged['Status']=='Rejected'].groupby('Reason').size().reset_index(name='Rejected Products').sort_values('Rejected Products', ascending=False)
                rsn_summ.insert(0, 'Rank', range(1, len(rsn_summ) + 1))
                ws.write(row_cursor, 0, "Rejection Reasons Summary", fmt)
                rsn_summ.to_excel(writer, sheet_name='Sellers Data', startrow=row_cursor+1, index=False)
        
        output.seek(0)
        return output
    except Exception: return BytesIO()

def to_excel(report_df, reasons_config_df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(report_df, "ProductSets", PRODUCTSETS_COLS, writer)
        if not reasons_config_df.empty:
            to_excel_base(reasons_config_df, "RejectionReasons", REJECTION_REASONS_COLS, writer)
    output.seek(0)
    return output

def to_excel_flag_data(flag_df, flag_name):
    output = BytesIO()
    df_copy = flag_df.copy()
    df_copy['FLAG'] = flag_name
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(df_copy, "ProductSets", FULL_DATA_COLS, writer)
    output.seek(0)
    return output

def log_validation_run(country, file, total, app, rej):
    try:
        entry = {'timestamp': datetime.now().isoformat(), 'country': country, 'file': file, 'total': total, 'approved': app, 'rejected': rej}
        with open('validation_audit.jsonl', 'a') as f: f.write(json.dumps(entry)+'\n')
    except: pass

# -------------------------------------------------
# UI
# -------------------------------------------------
st.title("Product Validation Tool")
st.markdown("---")

with st.spinner("Loading configuration files..."):
    support_files = load_all_support_files()

if not support_files['flags_mapping']:
    st.error("Critical: flags.xlsx could not be loaded.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Daily Validation", "Weekly Analysis", "Data Lake"])

# -------------------------------------------------
# TAB 1: DAILY VALIDATION
# -------------------------------------------------
with tab1:
    st.header("Daily Product Validation")
    country = st.selectbox("Select Country", ["Kenya", "Uganda"], key="daily_country")
    country_validator = CountryValidator(country)
    
    uploaded_file = st.file_uploader("Upload your file", type=['csv', 'xlsx'], key="daily_file")
    
    if uploaded_file:
        try:
            current_date = datetime.now().strftime('%Y-%m-%d')
            file_prefix = country_validator.code
            
            # Smart Load
            try:
                if uploaded_file.name.endswith('.xlsx'):
                     raw_data = pd.read_excel(uploaded_file, engine='openpyxl', dtype=str)
                else:
                    try: 
                        raw_data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype=str)
                        if len(raw_data.columns) <= 1:
                            uploaded_file.seek(0)
                            raw_data = pd.read_csv(uploaded_file, sep=',', encoding='ISO-8859-1', dtype=str)
                    except:
                        uploaded_file.seek(0)
                        raw_data = pd.read_csv(uploaded_file, sep=',', encoding='ISO-8859-1', dtype=str)
            except Exception as e:
                st.error(f"Failed to read file: {e}")
                st.stop()
            
            raw_data = standardize_input_data(raw_data)
            st.success(f"Loaded {len(raw_data)} rows from {uploaded_file.name}")
            
            is_valid, errors = validate_input_schema(raw_data)
            
            if is_valid:
                data = filter_by_country(raw_data, country_validator, "Uploaded File")
                for col in ['NAME', 'BRAND', 'COLOR', 'SELLER_NAME', 'CATEGORY_CODE']:
                    if col in data.columns: data[col] = data[col].astype(str).fillna('')
                
                with st.spinner("Running validations..."):
                    final_report, flag_dfs = validate_products(data, support_files, country_validator)
                
                approved_df = final_report[final_report['Status'] == 'Approved']
                rejected_df = final_report[final_report['Status'] == 'Rejected']
                log_validation_run(country, uploaded_file.name, len(data), len(approved_df), len(rejected_df))
                
                # Side Panel
                st.sidebar.header("Seller Options")
                seller_opts = ['All Sellers'] + (data['SELLER_NAME'].dropna().unique().tolist() if 'SELLER_NAME' in data.columns else [])
                sel_sellers = st.sidebar.multiselect("Select Sellers", seller_opts, default=['All Sellers'])
                
                # Filter Logic
                filt_data = data.copy()
                filt_report = final_report.copy()
                lbl = "All_Sellers"
                
                if 'All Sellers' not in sel_sellers and sel_sellers:
                    filt_data = data[data['SELLER_NAME'].isin(sel_sellers)]
                    filt_report = final_report[final_report['ProductSetSid'].isin(filt_data['PRODUCT_SET_SID'])]
                    lbl = "Selected_Sellers"
                
                filt_rej = filt_report[filt_report['Status']=='Rejected']
                filt_app = filt_report[filt_report['Status']=='Approved']
                
                # Dashboard
                st.markdown("---")
                st.header("Overall Results")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total", len(data))
                c2.metric("Approved", len(approved_df))
                c3.metric("Rejected", len(rejected_df))
                rt = (len(rejected_df)/len(data)*100) if len(data)>0 else 0
                c4.metric("Rate", f"{rt:.1f}%")
                
                st.subheader("Validation Results by Flag")
                for title, df_flagged in flag_dfs.items():
                    with st.expander(f"{title} ({len(df_flagged)})"):
                        if not df_flagged.empty:
                            st.dataframe(df_flagged)
                            st.download_button(f"Export {title}", to_excel_flag_data(df_flagged, title), f"{file_prefix}_{title}.xlsx")
                        else:
                            st.success("No issues found.")
                
                st.markdown("---")
                st.header("Overall Exports")
                c1, c2, c3, c4 = st.columns(4)
                c1.download_button("Final Report", to_excel(final_report, support_files['reasons']), f"{file_prefix}_Final_Report_{current_date}.xlsx")
                c2.download_button("Rejected", to_excel(rejected_df, support_files['reasons']), f"{file_prefix}_Rejected_{current_date}.xlsx")
                c3.download_button("Approved", to_excel(approved_df, support_files['reasons']), f"{file_prefix}_Approved_{current_date}.xlsx")
                c4.download_button("Full Data", to_excel_full_data(data, final_report), f"{file_prefix}_Full_Data_{current_date}.xlsx")
            else:
                for e in errors: st.error(e)
        except Exception as e:
            st.error(f"Error: {e}")
            st.code(traceback.format_exc())

# -------------------------------------------------
# TAB 2: WEEKLY ANALYSIS
# -------------------------------------------------
with tab2:
    st.header("Weekly Analysis Dashboard")
    st.info("Upload multiple 'Full Data' files exported from the Daily tab to see aggregated trends.")
    
    weekly_files = st.file_uploader("Upload Full Data Files (XLSX/CSV)", accept_multiple_files=True, type=['xlsx', 'csv'], key="weekly_files")
    
    if weekly_files:
        combined_df = pd.DataFrame()
        
        with st.spinner("Aggregating files..."):
            for f in weekly_files:
                try:
                    # Logic to read "ProductSets" sheet if available, else standard read
                    if f.name.endswith('.xlsx'):
                        try:
                            # Try reading ProductSets sheet directly
                            df = pd.read_excel(f, sheet_name='ProductSets', engine='openpyxl', dtype=str)
                        except:
                            # Fallback to first sheet
                            f.seek(0)
                            df = pd.read_excel(f, engine='openpyxl', dtype=str)
                    else:
                        df = pd.read_csv(f, dtype=str)
                    
                    # Ensure standard names
                    df = standardize_input_data(df)
                    combined_df = pd.concat([combined_df, df], ignore_index=True)
                except Exception as e:
                    st.error(f"Error reading {f.name}: {e}")
        
        if not combined_df.empty:
            # Check for required analysis columns
            if 'Status' not in combined_df.columns:
                # If Status is missing, it might be raw data, try to look for Listing Status or map it
                st.warning("Column 'Status' (Approved/Rejected) not found. Attempting to use available data.")
                # Fallback logic if needed, or stop
            
            # Clean up
            combined_df = combined_df.drop_duplicates(subset=['PRODUCT_SET_SID'])
            rejected = combined_df[combined_df['Status'] == 'Rejected'].copy()
            
            # --- METRICS ROW ---
            st.markdown("### Key Metrics")
            m1, m2, m3, m4 = st.columns(4)
            total = len(combined_df)
            rej_count = len(rejected)
            rej_rate = (rej_count/total * 100) if total else 0
            
            m1.metric("Total Products Checked", f"{total:,}")
            m2.metric("Total Rejected", f"{rej_count:,}")
            m3.metric("Rejection Rate", f"{rej_rate:.1f}%")
            m4.metric("Unique Sellers", f"{combined_df['SELLER_NAME'].nunique():,}")
            
            st.markdown("---")
            
            # --- CHARTS ROW 1 ---
            c1, c2 = st.columns(2)
            
            # Chart 1: Top Rejection Reasons
            with c1:
                st.subheader("Top Rejection Reasons")
                if not rejected.empty and 'Reason' in rejected.columns:
                    reason_counts = rejected['Reason'].value_counts().reset_index()
                    reason_counts.columns = ['Reason', 'Count']
                    
                    chart = alt.Chart(reason_counts.head(10)).mark_bar().encode(
                        x=alt.X('Count', title='Number of Products'),
                        y=alt.Y('Reason', sort='-x', title=None),
                        color=alt.value('#FF6B6B'),
                        tooltip=['Reason', 'Count']
                    ).interactive()
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.info("No rejection reasons data found.")

            # Chart 2: Top Rejected Categories
            with c2:
                st.subheader("Top Rejected Categories")
                if not rejected.empty and 'CATEGORY' in rejected.columns:
                    cat_counts = rejected['CATEGORY'].value_counts().reset_index()
                    cat_counts.columns = ['Category', 'Count']
                    
                    chart = alt.Chart(cat_counts.head(10)).mark_bar().encode(
                        x=alt.X('Count', title='Number of Rejections'),
                        y=alt.Y('Category', sort='-x', title=None),
                        color=alt.value('#4ECDC4'),
                        tooltip=['Category', 'Count']
                    ).interactive()
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.info("No category data found.")

            # --- CHARTS ROW 2 ---
            c3, c4 = st.columns(2)

            # Chart 3: Top Rejected Sellers
            with c3:
                st.subheader("Top 10 Rejected Sellers")
                if not rejected.empty and 'SELLER_NAME' in rejected.columns:
                    seller_counts = rejected['SELLER_NAME'].value_counts().reset_index()
                    seller_counts.columns = ['Seller', 'Count']
                    
                    chart = alt.Chart(seller_counts.head(10)).mark_bar().encode(
                        x=alt.X('Seller', sort='-y', axis=alt.Axis(labelAngle=-45)),
                        y=alt.Y('Count', title='Rejections'),
                        color=alt.value('#FFE66D'),
                        tooltip=['Seller', 'Count']
                    ).interactive()
                    st.altair_chart(chart, use_container_width=True)

            # Chart 4: Seller vs Reason Heatmap (Aggregated)
            with c4:
                st.subheader("Seller vs. Reason Breakdown (Top 5)")
                if not rejected.empty and 'SELLER_NAME' in rejected.columns and 'Reason' in rejected.columns:
                    # Get top 5 sellers
                    top_sellers = rejected['SELLER_NAME'].value_counts().head(5).index.tolist()
                    filtered_rej = rejected[rejected['SELLER_NAME'].isin(top_sellers)]
                    
                    if not filtered_rej.empty:
                        # Prepare data for stacked bar
                        breakdown = filtered_rej.groupby(['SELLER_NAME', 'Reason']).size().reset_index(name='Count')
                        
                        chart = alt.Chart(breakdown).mark_bar().encode(
                            x=alt.X('SELLER_NAME', title='Seller'),
                            y=alt.Y('Count', title='Count'),
                            color=alt.Color('Reason', legend=alt.Legend(title="Rejection Reason", orient="bottom")),
                            tooltip=['SELLER_NAME', 'Reason', 'Count']
                        ).interactive()
                        st.altair_chart(chart, use_container_width=True)
                    else:
                        st.info("Not enough data for breakdown.")

            # --- DATA TABLES ---
            with st.expander("View Detailed Data Tables"):
                t1, t2 = st.tabs(["Top Rejected Sellers", "Category Breakdown"])
                
                with t1:
                    if not rejected.empty:
                        st.dataframe(rejected['SELLER_NAME'].value_counts().reset_index(name='Rejections').rename(columns={'index':'Seller'}))
                
                with t2:
                     if not rejected.empty:
                        st.dataframe(rejected['CATEGORY'].value_counts().reset_index(name='Rejections').rename(columns={'index':'Category'}))

# -------------------------------------------------
# TAB 3: DATA LAKE
# -------------------------------------------------
with tab3:
    st.header("Data Lake Audit")
    file = st.file_uploader("Upload audit file", type=['jsonl','csv','xlsx'], key="audit_file")
    if file:
        if file.name.endswith('.jsonl'): df = pd.read_json(file, lines=True)
        elif file.name.endswith('.csv'): df = pd.read_csv(file)
        else: df = pd.read_excel(file)
        st.dataframe(df.head(50))
    else:
        try:
            st.dataframe(pd.read_json('validation_audit.jsonl', lines=True).tail(50))
        except:
            st.info("No audit log found.")
