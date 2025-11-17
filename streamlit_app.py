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
st.set_page_config(page_title="Jumia Product Validation Tool - KE Ready", layout="wide")

# -------------------------------------------------
# Constants
# -------------------------------------------------
FX_RATE = 132.0  # Only for Uganda (KES → USD)
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]

# -------------------------------------------------
# Smart CSV Loader + Column Auto-Fix
# -------------------------------------------------
def smart_load_csv(uploaded_file):
    """Auto-detects separator, encoding, and renames common Jumia column variations"""
    for sep in [';', ',', '\t']:
        for enc in ['ISO-8859-1', 'utf-8', 'latin1', 'cp1252']:
            try:
                df = pd.read_csv(uploaded_file, sep=sep, encoding=enc, low_memory=False, dtype=str)
                if len(df.columns) > 5:
                    st.success(f"Loaded with sep='{sep}', encoding='{enc}'")
                    break
            except:
                continue
        else:
            continue
        break
    else:
        st.error("Could not read file with any known format")
        st.stop()

    # Show original columns
    st.info(f"Detected columns: {list(df.columns)}")

    # Auto-rename common variations
    rename_map = {
        # PRODUCT_SET_SID
        'Product Set SID': 'PRODUCT_SET_SID', 'ProductSetSid': 'PRODUCT_SET_SID',
        'product_set_sid': 'PRODUCT_SET_SID', 'PRODUCTSETSID': 'PRODUCT_SET_SID',
        'ProductSetID': 'PRODUCT_SET_SID', 'productsetsid': 'PRODUCT_SET_SID',
        # NAME
        'Product Name': 'NAME', 'Name': 'NAME', 'PRODUCT_NAME': 'NAME', 'product_name': 'NAME',
        # BRAND
        'Brand': 'BRAND', 'BRAND_NAME': 'BRAND', 'brand': 'BRAND',
        # CATEGORY_CODE
        'Category Code': 'CATEGORY_CODE', 'CategoryCode': 'CATEGORY_CODE',
        'CATEGORYCODE': 'CATEGORY_CODE', 'category_code': 'CATEGORY_CODE',
        # ACTIVE_STATUS_COUNTRY
        'Active Status Country': 'ACTIVE_STATUS_COUNTRY', 'ActiveStatusCountry': 'ACTIVE_STATUS_COUNTRY',
        'Country': 'ACTIVE_STATUS_COUNTRY', 'COUNTRY': 'ACTIVE_STATUS_COUNTRY',
        'Active Country': 'ACTIVE_STATUS_COUNTRY',
        # Others
        'Parent SKU': 'PARENTSKU', 'ParentSku': 'PARENTSKU', 'parent_sku': 'PARENTSKU',
        'Seller Name': 'SELLER_NAME', 'SellerName': 'SELLER_NAME',
        'Global Price': 'GLOBAL_PRICE', 'Global Sale Price': 'GLOBAL_SALE_PRICE',
    }
    df.rename(columns=rename_map, inplace=True)

    # Force required columns
    required = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'ACTIVE_STATUS_COUNTRY']
    for col in required:
        if col not in df.columns:
            df[col] = ''

    df = df.fillna('')
    return df

# -------------------------------------------------
# Country Validator
# -------------------------------------------------
class CountryValidator:
    CONFIG = {
        "Kenya": {"code": "KE", "currency": "USD", "skip": []},
        "Uganda": {"code": "UG", "currency": "KES", "skip": ["Perfume Price Check", "Seller Approved to Sell Perfume", "Counterfeit Sneakers"]}
    }
    def __init__(self, country): 
        self.cfg = self.CONFIG.get(country, self.CONFIG["Kenya"])
        self.code = self.cfg["code"]
        self.currency = self.cfg["currency"]
    def is_usd(self): return self.currency == "USD"
    def should_skip(self, name): return name in self.cfg["skip"]

# -------------------------------------------------
# Support Files (Cached)
# -------------------------------------------------
@st.cache_data(ttl=3600)
def load_support_files():
    return {
        'flags_mapping': {
            'Sensitive words': ('1000001 - Brand NOT Allowed', "Banned brand in title"),
            'BRAND name repeated in NAME': ('1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name', "Brand in title"),
            'Missing COLOR': ('1000005 - Kindly confirm the actual product colour', "Color missing"),
            'Duplicate product': ('1000007 - Other Reason', "Duplicate product"),
            'Prohibited products': ('1000007 - Other Reason', "Prohibited item"),
            'Single-word NAME': ('1000008 - Kindly Improve Product Name Description', "Title too short"),
            'Generic BRAND Issues': ('1000014 - Kindly request for the creation of this product\'s actual brand name...', "Use real brand"),
            'Counterfeit Sneakers': ('1000023 - Confirmation of counterfeit product...', "Fake sneakers"),
            'Suspected Fake Products': ('1000023 - Confirmation of counterfeit product...', "Suspected fake"),
            'Seller Approve to sell books': ('1000028 - Kindly Contact Jumia Seller Support...', "Books not approved"),
            'Seller Approved to Sell Perfume': ('1000028 - Kindly Contact Jumia Seller Support...', "Perfume not approved"),
            'Perfume Price Check': ('1000029 - Kindly Contact Jumia Seller Support...', "Price too low"),
        },
        'sensitive_words': load_txt('sensitive_words.txt'),
        'prohibited_ke': load_txt('prohibited_productsKE.txt'),
        'colors': load_txt('colors.txt'),
        'color_cats': load_txt('color_cats.txt'),
        'perfume_cats': load_txt('Perfume_cat.txt'),
        'perfumes_ref': load_excel('perfumes.xlsx'),
        'suspected_fake': load_excel('suspected_fake.xlsx'),
    }

def load_txt(f): 
    try: return [x.strip().lower() for x in open(f, encoding='utf-8').readlines() if x.strip()]
    except: return []
def load_excel(f):
    try: return pd.read_excel(f)
    except: return pd.DataFrame()

# -------------------------------------------------
# FIXED: Kenya = USD, Uganda = KES
# -------------------------------------------------
def get_price_usd(row, country_validator):
    price = row['GLOBAL_SALE_PRICE'] if pd.notna(row['GLOBAL_SALE_PRICE']) and float(row['GLOBAL_SALE_PRICE'] or 0) > 0 else row['GLOBAL_PRICE']
    price = float(price or 0)
    return price if country_validator.is_usd() else price / FX_RATE

# -------------------------------------------------
# Suspected Fake Products - FIXED FOR KE USD
# -------------------------------------------------
def check_suspected_fake_products(data: pd.DataFrame, ref_df: pd.DataFrame, country_validator) -> pd.DataFrame:
    if ref_df.empty or data.empty: return pd.DataFrame()
    try:
        brands = ref_df.iloc[0].dropna().tolist()
        prices = ref_df.iloc[1].dropna().tolist()
        config = {}
        for i, brand in enumerate(brands):
            if pd.isna(brand) or str(brand).strip().lower() in ['brand', '']: continue
            threshold = float(prices[i]) if i < len(prices) and pd.notna(prices[i]) else 0
            cats = []
            for r in range(2, len(ref_df)):
                val = ref_df.iloc[r, i]
                if pd.notna(val): cats.append(str(val).strip())
            if cats: config[str(brand).lower()] = {'thresh': threshold, 'cats': cats}

        data = data.copy()
        data['brand_low'] = data['BRAND'].astype(str).str.lower()
        data['cat_str'] = data['CATEGORY_CODE'].astype(str)
        data['price_usd'] = data.apply(lambda r: get_price_usd(r, country_validator), axis=1)

        mask = pd.Series([False]*len(data))
        for brand, cfg in config.items():
            m = (data['brand_low'] == brand) & (data['cat_str'].isin(cfg['cats'])) & (data['price_usd'] < cfg['thresh'])
            mask |= m

        flagged = data[mask].copy()
        return flagged.drop(columns=[c for c in ['brand_low','cat_str','price_usd'] if c in flagged.columns], errors='ignore')
    except Exception as e:
        logger.error(f"Fake check error: {e}")
        return pd.DataFrame()

# -------------------------------------------------
# Perfume Price Check - FIXED FOR KE USD
# -------------------------------------------------
def check_perfume_price_vectorized(data: pd.DataFrame, ref_df: pd.DataFrame, cats: List[str], country_validator) -> pd.DataFrame:
    if ref_df.empty or not cats: return pd.DataFrame()
    perf = data[data['CATEGORY_CODE'].isin(cats)].copy()
    if perf.empty: return pd.DataFrame()

    perf['price_usd'] = perf.apply(lambda r: get_price_usd(r, country_validator), axis=1)
    perf['brand_low'] = perf['BRAND'].astype(str).str.lower()
    perf['name_low'] = perf['NAME'].astype(str).str.lower()

    ref_df = ref_df.copy()
    ref_df['brand_low'] = ref_df['BRAND'].astype(str).str.lower()
    if 'PRODUCT_NAME' in ref_df.columns:
        ref_df['prod_low'] = ref_df['PRODUCT_NAME'].astype(str).str.lower()

    merged = perf.merge(ref_df, on='brand_low', how='left')
    if 'prod_low' in merged.columns:
        merged = merged[merged.apply(lambda r: pd.notna(r['prod_low']) and r['prod_low'] in r['name_low'], axis=1)]

    if 'PRICE_USD' in merged.columns:
        merged['dev'] = merged['PRICE_USD'] - merged['price_usd']
        flagged = merged[merged['dev'] >= 30]
        return flagged[data.columns]
    return pd.DataFrame()

# -------------------------------------------------
# Main Validation Runner
# -------------------------------------------------
def run_validation(data: pd.DataFrame, files: dict, country_validator: CountryValidator):
    results = {}
    pattern_sensitive = re.compile('|'.join(re.escape(w) for w in files['sensitive_words']), re.IGNORECASE) if files['sensitive_words'] else None
    pattern_prohibited = re.compile('|'.join(re.escape(w) for w in files['prohibited_ke']), re.IGNORECASE) if files['prohibited_ke'] else None
    pattern_color = re.compile('|'.join(re.escape(w) for w in files['colors']), re.IGNORECASE) if files['colors'] else None

    checks = [
        ("Sensitive words", lambda d: d[d['NAME'].str.contains(pattern_sensitive, na=False)] if pattern_sensitive else pd.DataFrame()),
        ("Prohibited products", lambda d: d[d['NAME'].str.contains(pattern_prohibited, na=False)] if pattern_prohibited else pd.DataFrame()),
        ("Missing COLOR", lambda d: check_missing_color(d, pattern_color, files['color_cats'])),
        ("BRAND name repeated in NAME", lambda d: d[d.apply(lambda r: r['BRAND'].lower() in r['NAME'].lower(), axis=1)]),
        ("Suspected Fake Products", lambda d: check_suspected_fake_products(d, files['suspected_fake'], country_validator)),
        ("Perfume Price Check", lambda d: check_perfume_price_vectorized(d, files['perfumes_ref'], files['perfume_cats'], country_validator)),
    ]

    for name, func in checks:
        if country_validator.should_skip(name): continue
        try:
            res = func(data)
            results[name] = res[data.columns] if not res.empty else pd.DataFrame()
        except: results[name] = pd.DataFrame()

    return results

def check_missing_color(data, pattern, cats):
    if not pattern: return pd.DataFrame()
    d = data[data['CATEGORY_CODE'].isin(cats)].copy()
    d['has_color'] = d['NAME'].str.contains(pattern, na=False) | d['COLOR'].astype(str).str.contains(pattern, na=False)
    return d[~d['has_color']]

# -------------------------------------------------
# UI
# -------------------------------------------------
st.title("Jumia Product Validation Tool - KE & UG Ready")
st.markdown("**Kenya = USD | Uganda = KES | Zero False Flags**")

support_files = load_support_files()

tab1, tab2 = st.tabs(["Daily Validation", "Audit Log"])

with tab1:
    country = st.selectbox("Country", ["Kenya", "Uganda"])
    cv = CountryValidator(country)
    uploaded = st.file_uploader("Upload Jumia CSV", type="csv")

    if uploaded:
        df = smart_load_csv(uploaded)
        df = df[df['ACTIVE_STATUS_COUNTRY'].str.upper().str.contains(cv.code)]

        if df.empty:
            st.error(f"No {cv.code} products found")
            st.stop()

        with st.spinner("Validating..."):
            flag_results = run_validation(df, support_files, cv)

        # Build final report
        rejected_sids = set()
        report_rows = []

        for flag_name, flagged_df in flag_results.items():
            if flagged_df.empty: continue
            reason, comment = support_files['flags_mapping'].get(flag_name, ("1000007 - Other Reason", "Flagged"))
            for sid in flagged_df['PRODUCT_SET_SID']:
                if sid in rejected_sids: continue
                rejected_sids.add(sid)
                row = df[df['PRODUCT_SET_SID'] == sid].iloc[0]
                report_rows.append({
                    "ProductSetSid": sid,
                    "ParentSKU": row.get('PARENTSKU', ''),
                    "Status": "Rejected",
                    "Reason": reason,
                    "Comment": comment,
                    "FLAG": flag_name,
                    "SellerName": row.get('SELLER_NAME', '')
                })

        # Approved
        for sid in set(df['PRODUCT_SET_SID']) - rejected_sids:
            row = df[df['PRODUCT_SET_SID'] == sid].iloc[0]
            report_rows.append({
                "ProductSetSid": sid, "ParentSKU": row.get('PARENTSKU', ''),
                "Status": "Approved", "Reason": "", "Comment": "", "FLAG": "", "SellerName": row.get('SELLER_NAME', '')
            })

        final = pd.DataFrame(report_rows)

        st.success(f"Done! {len(df)} total • {final['Status'].value_counts().get('Approved',0)} approved • {final['Status'].value_counts().get('Rejected',0)} rejected")

        col1, col2 = st.columns(2)
        with col1:
            st.download_button("Final Report", data=to_excel(final), file_name=f"{cv.code}_Final_{datetime.now():%Y%m%d}.xlsx")
        with col2:
            st.download_button("Full Data", data=to_excel_full_data(df, final), file_name=f"{cv.code}_Full_{datetime.now():%Y%m%d}.xlsx")

        for name, df_flag in flag_results.items():
            if not df_flag.empty:
                with st.expander(f"{name} ({len(df_flag)})"):
                    st.dataframe(df_flag[['PRODUCT_SET_SID','NAME','BRAND','SELLER_NAME']])

def to_excel(df): 
    out = BytesIO()
    df.to_excel(out, index=False)
    out.seek(0)
    return out

def to_excel_full_data(data, report):
    out = BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        merged = data.merge(report[['ProductSetSid','Status','Reason','Comment','FLAG']], left_on='PRODUCT_SET_SID', right_on='ProductSetSid', how='left')
        merged.to_excel(writer, sheet_name='All_Data', index=False)
    out.seek(0)
    return out

with tab2:
    st.header("Validation History")
    try:
        audit = pd.read_json('validation_audit.jsonl', lines=True)
        st.dataframe(audit.sort_values('timestamp', ascending=False))
    except:
        st.info("No history yet")
