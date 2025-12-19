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

# Front-end requested columns
VISIBLE_COLUMNS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", 
    "CATEGORY", "CATEGORY_CODE", "COLOR", "MAIN_IMAGE", 
    "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU"
]

FX_RATE = 132.0 

# Robust Case-Insensitive Mapping
NEW_FILE_MAPPING = {
    'product_set_sid': 'PRODUCT_SET_SID',
    'product_set_id': 'PRODUCT_SET_SID',
    'cod_productset_sid': 'PRODUCT_SET_SID',
    'dsc_name': 'NAME',
    'name': 'NAME',
    'dsc_brand_name': 'BRAND',
    'brand': 'BRAND',
    'cod_category_code': 'CATEGORY_CODE',
    'category_code': 'CATEGORY_CODE',
    'dsc_category_name': 'CATEGORY',
    'category': 'CATEGORY',
    'dsc_shop_seller_name': 'SELLER_NAME',
    'seller_name': 'SELLER_NAME',
    'dsc_shop_active_country': 'ACTIVE_STATUS_COUNTRY',
    'active_status_country': 'ACTIVE_STATUS_COUNTRY',
    'cod_parent_sku': 'PARENTSKU',
    'parentsku': 'PARENTSKU',
    'color': 'COLOR',
    'image1': 'MAIN_IMAGE',
    'main_image': 'MAIN_IMAGE',
    'list_seller_skus': 'SELLER_SKU',
    'seller_sku': 'SELLER_SKU',
    'product_warranty': 'PRODUCT_WARRANTY',
    'warranty_duration': 'WARRANTY_DURATION',
    'warranty_address': 'WARRANTY_ADDRESS',
    'warranty_type': 'WARRANTY_TYPE'
}

# -------------------------------------------------
# DATA NORMALIZATION
# -------------------------------------------------
def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Force lowercase headers to ensure mapping works regardless of input case
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.rename(columns=NEW_FILE_MAPPING)
    
    if 'ACTIVE_STATUS_COUNTRY' in df.columns:
        df['ACTIVE_STATUS_COUNTRY'] = (
            df['ACTIVE_STATUS_COUNTRY'].astype(str).str.lower()
            .str.replace('jumia-', '', regex=False).str.strip().str.upper()
        )
    return df

def propagate_metadata(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    cols_to_propagate = ['COLOR_FAMILY', 'PRODUCT_WARRANTY', 'WARRANTY_DURATION', 'WARRANTY_ADDRESS', 'WARRANTY_TYPE']
    for col in cols_to_propagate:
        if col not in df.columns: df[col] = pd.NA
    for col in cols_to_propagate:
        df[col] = df.groupby('PRODUCT_SET_SID')[col].transform(lambda x: x.ffill().bfill())
    return df

# -------------------------------------------------
# CACHED FILE LOADING
# -------------------------------------------------
@st.cache_data(ttl=3600)
def load_txt_file(filename: str) -> List[str]:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = [line.strip() for line in f if line.strip()]
        return data
    except Exception: return []

@st.cache_data(ttl=3600)
def load_excel_file(filename: str, column: Optional[str] = None) -> pd.DataFrame:
    try:
        df = pd.read_excel(filename, engine='openpyxl', dtype=str)
        df.columns = df.columns.str.strip()
        if column and column in df.columns:
            return df[column].astype(str).str.strip().tolist()
        return df
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    # Baseline Rejection Reasons (Your Original List)
    return {
        'Seller Not approved to sell Refurb': ('1000028 - Contact SS', "Please contact Jumia Seller Support to confirm possibility of sale for Refurbished products."),
        'BRAND name repeated in NAME': ('1000002 - Brand Repeat', "Ensure Brand Name is not repeated in Product Name."),
        'Missing COLOR': ('1000005 - Confirm Color', "Ensure product color is clearly mentioned in title and color tab."),
        'Duplicate product': ('1000007 - Other Reason', "Kindly avoid creating duplicate SKUs."),
        'Prohibited products': ('1000024 - No License', "Rejected due to absence of required license."),
        'Single-word NAME': ('1000008 - Improve Name', "Format: Name – Type – Color."),
        'Unnecessary words in NAME': ('1000008 - Improve Name', "Avoid unnecessary filler words in title."),
        'Generic BRAND Issues': ('1000014 - Brand Form', "Request brand creation: https://bit.ly/2kpjja8"),
        'Counterfeit Sneakers': ('1000030 - Suspected Fake', "Suspected counterfeit sneaker product."),
        'Seller Approve to sell books': ('1000028 - Contact SS', "Confirm book sale eligibility."),
        'Seller Approved to Sell Perfume': ('1000028 - Contact SS', "Confirm perfume sale eligibility."),
        'Suspected counterfeit Jerseys': ('1000030 - Suspected Fake', "Suspected counterfeit jersey product."),
        'Suspected Fake product': ('1000030 - Suspected Fake', "Price logic indicates suspected fake."),
        'Product Warranty': ('1000013 - Missing Warranty', "Listing requires a valid warranty in description and warranty tab."),
        'Sensitive words': ('1000001 - Brand Banned', "Includes brands not allowed on Jumia (e.g. Chanel, Rolex).")
    }

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

# -------------------------------------------------
# ORIGINAL VALIDATION LOGIC FUNCTIONS
# -------------------------------------------------
def check_refurb_seller_approval(data, approved_sellers_ke, approved_sellers_ug, country_code):
    approved = set(approved_sellers_ke) if country_code == 'KE' else set(approved_sellers_ug)
    refurb_words = r'\b(refurb|refurbished|renewed)\b'
    mask = (data['NAME'].str.contains(refurb_words, case=False, na=False)) | (data['BRAND'].str.lower() == 'renewed')
    return data[mask & ~data['SELLER_NAME'].str.lower().isin(approved)]

def check_unnecessary_words(data, pattern):
    if pattern is None: return pd.DataFrame()
    return data[data['NAME'].str.contains(pattern, na=False)]

def check_product_warranty(data, warranty_category_codes):
    data['CAT_CLEAN'] = data['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
    target = data[data['CAT_CLEAN'].isin(warranty_category_codes)].copy()
    no_w = (target['PRODUCT_WARRANTY'].isna() | (target['PRODUCT_WARRANTY'] == "")) & \
           (target['WARRANTY_DURATION'].isna() | (target['WARRANTY_DURATION'] == ""))
    return target[no_w]

def check_missing_color(data, pattern, color_categories):
    target = data[data['CATEGORY_CODE'].isin(color_categories)].copy()
    name_check = target['NAME'].str.contains(pattern, na=False)
    color_check = target['COLOR'].str.contains(pattern, na=False)
    return target[~(name_check | color_check)]

def check_brand_in_name(data):
    mask = data.apply(lambda r: str(r['BRAND']).lower() in str(r['NAME']).lower() if pd.notna(r['BRAND']) and pd.notna(r['NAME']) else False, axis=1)
    return data[mask]

def check_duplicate_products(data):
    cols = ['NAME','BRAND','SELLER_NAME','COLOR']
    return data[data.duplicated(subset=cols, keep=False)]

def check_seller_approved_for_books(data, book_category_codes, approved_book_sellers):
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)]

def check_seller_approved_for_perfume(data, perfume_category_codes, approved_perfume_sellers, sensitive_perfume_brands):
    perfumes = data[data['CATEGORY_CODE'].isin(perfume_category_codes)]
    mask = perfumes['BRAND'].str.lower().isin(sensitive_perfume_brands)
    return perfumes[mask & ~perfumes['SELLER_NAME'].isin(approved_perfume_sellers)]

def check_counterfeit_sneakers(data, sneaker_category_codes, sneaker_sensitive_brands):
    sneakers = data[data['CATEGORY_CODE'].isin(sneaker_category_codes)]
    name_lower = sneakers['NAME'].str.lower()
    mask = (sneakers['BRAND'].str.lower().isin(['generic', 'fashion'])) & (name_lower.apply(lambda x: any(b in x for b in sneaker_sensitive_brands)))
    return sneakers[mask]

def check_suspected_fake_products(data, suspected_fake_df):
    # Placeholder for price logic comparison
    return pd.DataFrame(columns=data.columns)

def check_single_word_name(data, book_category_codes):
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['NAME'].str.split().str.len() == 1]

def check_generic_brand_issues(data, valid_category_codes_fas):
    return data[data['CATEGORY_CODE'].isin(valid_category_codes_fas) & (data['BRAND'] == 'Generic')]

def check_prohibited_products(data, pattern):
    if pattern is None: return pd.DataFrame()
    return data[data['NAME'].str.contains(pattern, na=False)]

def compile_regex(words):
    if not words: return None
    return re.compile('|'.join(r'\b' + re.escape(w) + r'\b' for w in words), re.IGNORECASE)

# -------------------------------------------------
# MASTER VALIDATION RUNNER
# -------------------------------------------------
def validate_products(data, support_files, country_code):
    flags_mapping = support_files['flags_mapping']
    
    validations = [
        ("Suspected Fake product", check_suspected_fake_products, {'suspected_fake_df': support_files['suspected_fake']}),
        ("Seller Not approved to sell Refurb", check_refurb_seller_approval, {'approved_sellers_ke': support_files['approved_refurb_sellers_ke'], 'approved_sellers_ug': support_files['approved_refurb_sellers_ug'], 'country_code': country_code}),
        ("Product Warranty", check_product_warranty, {'warranty_category_codes': support_files['warranty_category_codes']}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': support_files['book_category_codes'], 'approved_book_sellers': support_files['approved_book_sellers']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'perfume_category_codes': support_files['perfume_category_codes'], 'approved_perfume_sellers': support_files['approved_perfume_sellers'], 'sensitive_perfume_brands': support_files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'sneaker_category_codes': support_files['sneaker_category_codes'], 'sneaker_sensitive_brands': support_files['sneaker_sensitive_brands']}),
        ("Prohibited products", check_prohibited_products, {'pattern': compile_regex(support_files['blacklisted_words'])}),
        ("Unnecessary words in NAME", check_unnecessary_words, {'pattern': compile_regex(support_files['unnecessary_words'])}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': support_files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {'valid_category_codes_fas': support_files['category_fas']['ID'].astype(str).tolist() if not support_files['category_fas'].empty else []}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': compile_regex(support_files['colors']), 'color_categories': support_files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {}),
    ]

    results = {}
    rows = []
    processed = set()

    for name, func, kwargs in validations:
        res = func(data=data, **kwargs)
        if not res.empty:
            flagged_sids = res['PRODUCT_SET_SID'].unique()
            results[name] = data[data['PRODUCT_SET_SID'].isin(flagged_sids)]
            reason_info = flags_mapping.get(name, ("Other", "Flagged"))
            for sid in flagged_sids:
                if sid not in processed:
                    r = data[data['PRODUCT_SET_SID'] == sid].iloc[0]
                    rows.append({
                        'ProductSetSid': sid, 'Status': 'Rejected', 'Reason': reason_info[0], 
                        'Comment': reason_info[1], 'FLAG': name, 'SellerName': r.get('SELLER_NAME', '')
                    })
                    processed.add(sid)

    approved = data[~data['PRODUCT_SET_SID'].isin(processed)]
    for _, r in approved.iterrows():
        rows.append({'ProductSetSid': r['PRODUCT_SET_SID'], 'Status': 'Approved', 'Reason': "", 'Comment': "", 'FLAG': "", 'SellerName': r.get('SELLER_NAME', '')})

    return pd.DataFrame(rows), results

# -------------------------------------------------
# EXPORT HELPERS
# -------------------------------------------------
def to_excel_full(data_df, report_df):
    output = BytesIO()
    merged = pd.merge(data_df, report_df, left_on="PRODUCT_SET_SID", right_on="ProductSetSid", how='left')
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        merged.to_excel(writer, index=False, sheet_name='ProductSets')
    return output.getvalue()

# -------------------------------------------------
# STREAMLIT UI
# -------------------------------------------------
def main():
    if 'manual_approvals' not in st.session_state: st.session_state.manual_approvals = set()

    with st.spinner("Initializing support files..."):
        support_files = load_all_support_files()

    st.title("Product Validation Tool")
    country = st.sidebar.selectbox("Country", ["Kenya", "Uganda"])
    country_code = "KE" if country == "Kenya" else "UG"
    
    uploaded_files = st.file_uploader("Upload PIM Files", type=['csv', 'xlsx'], accept_multiple_files=True)

    if uploaded_files:
        all_dfs = []
        for f in uploaded_files:
            try:
                if f.name.endswith('.xlsx'): df = pd.read_excel(f, dtype=str)
                else: 
                    f.seek(0)
                    df = pd.read_csv(f, sep=None, engine='python', encoding='ISO-8859-1', dtype=str)
                all_dfs.append(standardize_input_data(df))
            except Exception as e: st.error(f"Error reading {f.name}: {e}")

        if all_dfs:
            raw_data = pd.concat(all_dfs, ignore_index=True)
            
            # THE FIX: Ensure column exists after standardization
            if 'PRODUCT_SET_SID' not in raw_data.columns:
                st.error("❌ Column 'PRODUCT_SET_SID' missing.")
                st.write("Headers found:", list(raw_data.columns))
                st.stop()
            
            data_prop = propagate_metadata(raw_data)
            data = data_prop.drop_duplicates(subset=['PRODUCT_SET_SID'])
            
            report, flag_dfs = validate_products(data, support_files, country_code)
            
            # Apply Manual QC Passes
            report.loc[report['ProductSetSid'].isin(st.session_state.manual_approvals), 'Status'] = 'Approved'

            # --- FRONT END RESULTS ---
            st.divider()
            search = st.text_input("🔍 Global Search", "").lower()
            
            m1, m2 = st.columns(2)
            m1.metric("Total Flags", len(report[report['Status'] == 'Rejected']))
            m2.metric("Manual QC Passes", len(st.session_state.manual_approvals))

            st.subheader("Validation Results by Flag")
            for title, df_flagged in flag_dfs.items():
                df_rem = df_flagged[~df_flagged['PRODUCT_SET_SID'].isin(st.session_state.manual_approvals)]
                if search:
                    mask = df_rem.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)
                    df_disp = df_rem[mask].copy()
                else: df_disp = df_rem.copy()

                with st.expander(f"{title} ({len(df_disp)})"):
                    if not df_disp.empty:
                        df_disp.insert(0, "QC Pass", False)
                        cols = ["QC Pass"] + [c for c in VISIBLE_COLUMNS if c in df_disp.columns]
                        ed = st.data_editor(
                            df_disp[cols], 
                            column_config={"QC Pass": st.column_config.CheckboxColumn("Approve?"), "MAIN_IMAGE": st.column_config.ImageColumn("Image Preview")},
                            disabled=[c for c in cols if c != "QC Pass"],
                            hide_index=True, key=f"ed_{title}"
                        )
                        
                        passed = ed[ed["QC Pass"] == True]["PRODUCT_SET_SID"].tolist()
                        if passed and st.button(f"Confirm Bulk Approval for {title}"):
                            st.session_state.manual_approvals.update(passed)
                            st.rerun()
                    else: st.success("Clear!")

            st.divider()
            st.download_button("📥 Final Full Data Export", to_excel_full(data, report), f"Final_QC_Report_{datetime.now().strftime('%Y%m%d')}.xlsx")
            if st.sidebar.button("Clear QC Memory"): 
                st.session_state.manual_approvals.clear()
                st.rerun()

if __name__ == "__main__":
    main()
