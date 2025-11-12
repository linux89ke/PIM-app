import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import os

# -------------------------------------------------
# Page config
# -------------------------------------------------
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# -------------------------------------------------
# Constants
# -------------------------------------------------
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]
REJECTION_REASONS_COLS = ['CODE - REJECTION_REASON', 'COMMENT']
FULL_DATA_COLS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE",
    "COLOR", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU",
    "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG",
    "LISTING_STATUS", "SELLER_RATING", "STOCK_QTY"
]

# -------------------------------------------------
# Helper – date from filename
# -------------------------------------------------
def extract_date_from_filename(filename: str):
    m = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    return pd.to_datetime(m.group(1)) if m else None

# -------------------------------------------------
# Load support files
# -------------------------------------------------
def _load_txt(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return [ln.strip() for ln in f if ln.strip()]
    except FileNotFoundError:
        st.warning(f"{path} not found – related check disabled.")
        return []

def _load_excel(path, col):
    try:
        df = pd.read_excel(path)
        return df[col].astype(str).str.strip().tolist()
    except FileNotFoundError:
        st.warning(f"{path} not found – related check disabled.")
        return []
    except Exception as e:
        st.error(f"Error reading {path}: {e}")
        return []

# Load perfume category codes from TXT
def load_perfume_category_codes_txt():
    try:
        with open('Perfume_cat.txt', 'r', encoding='utf-8') as f:
            codes = [line.strip() for line in f if line.strip()]
        st.success(f"Loaded {len(codes)} perfume category codes from Perfume_cat.txt")
        return codes
    except FileNotFoundError:
        st.warning("Perfume_cat.txt not found – perfume checks disabled.")
        return []
    except Exception as e:
        st.error(f"Error reading Perfume_cat.txt: {e}")
        return []

# Load sensitive perfume brands from TXT
def load_sensitive_perfume_brands():
    try:
        with open('sensitive_perfumes.txt', 'r', encoding='utf-8') as f:
            brands = [line.strip().lower() for line in f if line.strip()]
        st.success(f"Loaded {len(brands)} sensitive perfume brands from sensitive_perfumes.txt")
        return brands
    except FileNotFoundError:
        st.warning("sensitive_perfumes.txt not found – perfume brand check disabled.")
        return []
    except Exception as e:
        st.error(f"Error reading sensitive_perfumes.txt: {e}")
        return []

# Load all support files
blacklisted_words          = _load_txt('blacklisted.txt')
book_category_codes        = _load_excel('Books_cat.xlsx', 'CategoryCode')
approved_book_sellers      = _load_excel('Books_Approved_Sellers.xlsx', 'SellerName')
sensitive_brand_words      = _load_excel('sensitive_brands.xlsx', 'BrandWords')
perfume_category_codes     = load_perfume_category_codes_txt()
sensitive_perfume_brands   = load_sensitive_perfume_brands()  # ← NEW
approved_perfume_sellers   = _load_excel('perfumeSellers.xlsx', 'SellerName')

def load_config_files():
    files = {
        'check_variation': 'check_variation.xlsx',
        'category_fas'   : 'category_FAS.xlsx',
        'perfumes'       : 'perfumes.xlsx',
        'reasons'        : 'reasons.xlsx',
    }
    out = {}
    for key, fn in files.items():
        try:
            df = pd.read_excel(fn).rename(columns=str.strip)
            out[key] = df
        except FileNotFoundError:
            st.warning(f"{fn} missing – functionality limited.")
            out[key] = pd.DataFrame()
        except Exception as e:
            st.error(f"Error loading {fn}: {e}")
            out[key] = pd.DataFrame()
    return out

config_data = load_config_files()
reasons_df  = config_data.get('reasons', pd.DataFrame())

# -------------------------------------------------
# Country filter
# -------------------------------------------------
def filter_ke_ug_only(df, src):
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns:
        st.warning(f"ACTIVE_STATUS_COUNTRY missing in {src}")
        return df
    df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.strip().str.upper()
    mask_valid = df['ACTIVE_STATUS_COUNTRY'].notna() & (df['ACTIVE_STATUS_COUNTRY'] != '') & (df['ACTIVE_STATUS_COUNTRY'] != 'NAN')
    mask_keug  = df['ACTIVE_STATUS_COUNTRY'].str.contains(r'\b(KE|UG)\b', na=False, regex=True)
    keug = df[mask_valid & mask_keug].copy()
    excl = len(df[mask_valid]) - len(keug)
    if excl:
        others = ', '.join(sorted(df[mask_valid & ~mask_keug]['ACTIVE_STATUS_COUNTRY'].unique())[:5])
        if len(df[mask_valid & ~mask_keug]['ACTIVE_STATUS_COUNTRY'].unique()) > 5:
            others += f" (+{len(df[mask_valid & ~mask_keug]['ACTIVE_STATUS_COUNTRY'].unique())-5} more)"
        st.warning(f"Excluded {excl} non-KE/UG rows from {src}: {others}")
    else:
        st.info(f"All valid rows in {src} are KE/UG")
    if keug.empty:
        st.error(f"No KE/UG rows left in {src}")
        st.stop()
    return keug

# -------------------------------------------------
# Validation checks
# -------------------------------------------------
def check_missing_brand_or_name(data):
    if not {'BRAND','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    return data[data['BRAND'].isna() | (data['BRAND']=='') | data['NAME'].isna() | (data['NAME']=='')]

def check_brand_in_name(data):
    if not {'BRAND','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    return data[
        data.apply(lambda r: isinstance(r['BRAND'],str) and isinstance(r['NAME'],str) and
                   r['BRAND'].lower() in r['NAME'].lower(), axis=1)
    ]

def check_duplicate_products(data):
    cols = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    if len(cols) < 4:
        return pd.DataFrame(columns=data.columns)
    return data[data.duplicated(subset=cols, keep=False)]

def check_sensitive_brands(data, sensitive_brand_words, book_category_codes):
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if books.empty or not sensitive_brand_words:
        return pd.DataFrame(columns=data.columns)
    pat = '|'.join(r'\b' + re.escape(w.lower()) + r'\b' for w in sensitive_brand_words)
    return books[books['NAME'].astype(str).str.lower().str.contains(pat, regex=True, na=False)]

def check_seller_approved_for_books(data, book_category_codes, approved_book_sellers):
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    books = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if books.empty or not approved_book_sellers:
        return pd.DataFrame(columns=data.columns)
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)]

# NEW: Perfume seller check with sensitive brands + fake brand in name
def check_seller_approved_for_perfume(data, perfume_category_codes, approved_perfume_sellers, sensitive_perfume_brands):
    if not {'CATEGORY_CODE','SELLER_NAME','BRAND','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)

    # Filter by perfume category
    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)].copy()
    if perfume_data.empty or not approved_perfume_sellers:
        return pd.DataFrame(columns=data.columns)

    # Normalize
    perfume_data['BRAND_LOWER'] = perfume_data['BRAND'].astype(str).str.strip().str.lower()
    perfume_data['NAME_LOWER'] = perfume_data['NAME'].astype(str).str.strip().str.lower()

    # Condition 1: BRAND is sensitive
    sensitive_mask = perfume_data['BRAND_LOWER'].isin(sensitive_perfume_brands)

    # Condition 2: Fake brand + sensitive brand in NAME
    fake_brands = ['designers collection', 'smart collection', 'generic', 'designer', 'fashion']
    fake_brand_mask = perfume_data['BRAND_LOWER'].isin(fake_brands)
    name_contains_sensitive = perfume_data['NAME_LOWER'].apply(
        lambda x: any(brand in x for brand in sensitive_perfume_brands)
    )
    fake_name_mask = fake_brand_mask & name_contains_sensitive

    # Final: (sensitive OR fake name) AND not approved
    final_mask = (sensitive_mask | fake_name_mask) & (~perfume_data['SELLER_NAME'].isin(approved_perfume_sellers))

    return perfume_data[final_mask].drop(columns=['BRAND_LOWER', 'NAME_LOWER'])

FX_RATE = 132.0
def check_perfume_price(data, perfumes_df, perfume_category_codes):
    req = ['CATEGORY_CODE','NAME','BRAND','GLOBAL_SALE_PRICE','GLOBAL_PRICE','CURRENCY']
    if not all(c in data.columns for c in req) or perfumes_df.empty or not perfume_category_codes:
        return pd.DataFrame(columns=data.columns)

    perf = data[data['CATEGORY_CODE'].isin(perfume_category_codes)]
    if perf.empty:
        return pd.DataFrame(columns=data.columns)

    flagged = []
    for _, row in perf.iterrows():
        price_kes = row['GLOBAL_SALE_PRICE'] if pd.notna(row['GLOBAL_SALE_PRICE']) and row['GLOBAL_SALE_PRICE']>0 else row['GLOBAL_PRICE']
        if not pd.notna(price_kes) or price_kes<=0:
            continue
        cur = str(row.get('CURRENCY','KES')).upper()
        price_usd = price_kes / FX_RATE if cur=='KES' else price_kes

        name = str(row['NAME']).strip().lower()
        brand = str(row['BRAND']).strip().lower()

        m = perfumes_df[(perfumes_df['BRAND'].str.lower()==brand) &
                        (perfumes_df['PRODUCT_NAME'].str.lower().apply(lambda x: x in name))]
        if m.empty:
            m = perfumes_df[(perfumes_df['BRAND'].str.lower()==brand) &
                            (perfumes_df['KEYWORD'].str.lower().apply(lambda x: x in name))]
        if not m.empty:
            ref_usd = m.iloc[0]['PRICE_USD']
            if ref_usd - price_usd >= 30:
                flagged.append(row.to_dict())
    return pd.DataFrame(flagged) if flagged else pd.DataFrame(columns=data.columns)

def check_single_word_name(data, book_category_codes):
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1]

def check_generic_brand_issues(data, valid_category_codes_fas):
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    return data[data['CATEGORY_CODE'].isin(valid_category_codes_fas) & (data['BRAND']=='Generic')]

def check_missing_color(data, book_category_codes):
    if not {'CATEGORY_CODE','COLOR'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    non_books = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_books[non_books['COLOR'].isna() | (non_books['COLOR'] == '')]

# -------------------------------------------------
# Master validation runner
# -------------------------------------------------
def validate_products(
    data,
    cfg,
    blacklisted_words,
    reasons_df,
    book_category_codes,
    sensitive_brand_words,
    approved_book_sellers,
    perfume_category_codes,
    sensitive_perfume_brands,
    country
):
    validations = [
        ("Sensitive Brand Issues", check_sensitive_brands,
         {'sensitive_brand_words': sensitive_brand_words, 'book_category_codes': book_category_codes}),
        ("Seller Approve to sell books", check_seller_approved_for_books,
         {'book_category_codes': book_category_codes, 'approved_book_sellers': approved_book_sellers}),
        ("Perfume Price Check", check_perfume_price,
         {'perfumes_df': cfg.get('perfumes', pd.DataFrame()), 'perfume_category_codes': perfume_category_codes}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume,
         {'perfume_category_codes': perfume_category_codes,
          'approved_perfume_sellers': approved_perfume_sellers,
          'sensitive_perfume_brands': sensitive_perfume_brands}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': book_category_codes}),
        ("Missing BRAND or NAME", check_missing_brand_or_name, {}),
        ("Generic BRAND Issues", check_generic_brand_issues, {}),
        ("Missing COLOR", check_missing_color, {'book_category_codes': book_category_codes}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Duplicate product", check_duplicate_products, {}),
    ]

    if country == "Uganda":
        skip = ["Sensitive Brand Issues", "Seller Approve to sell books", "Perfume Price Check", "Seller Approved to Sell Perfume"]
        validations = [v for v in validations if v[0] not in skip]

    flag_reason_comment_mapping = {
        "Sensitive Brand Issues": ("1000023 - Confirmation of counterfeit product by Jumia technical team (Not Authorized)", "Please contact vendor support for sale of..."),
        "Seller Approve to sell books": ("1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim", """Please contact Jumia Seller Support and raise a claim to confirm whether this product is eligible for listing.
This step will help ensure that all necessary requirements and approvals are addressed before proceeding with the sale, and prevent any future compliance issues."""),
        "Perfume Price Check": ("1000029 - Perfume Price Deviation >= $30", "Price is $30+ below reference. Contact Seller Support with claim #{{CLAIM_ID}} for authenticity verification."),
        "Seller Approved to Sell Perfume": ("1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim", """Please contact Jumia Seller Support and raise a claim to confirm whether this product is eligible for listing.
This step will help ensure that all necessary requirements and approvals are addressed before proceeding with the sale, and prevent any future compliance issues."""),
        "Single-word NAME": ("1000008 - Kindly Improve Product Name Description", """Kindly update the product title using this format: Name – Type of the Products – Color.
If available, please also add key details such as weight, capacity, type, and warranty to make the title clear and complete for customers."""),
        "Missing BRAND or NAME": ("1000001 - Brand NOT Allowed", "Brand NOT Allowed"),
        "Generic BRAND Issues": ("1000001 - Brand NOT Allowed", "Please use Fashion as brand for Fashion items- Kindly request for the creation of this product's actual brand name by filling this form: https://bit.ly/2kpjja8"),
        "Missing COLOR": ("1000005 - Kindly confirm the actual product colour", "Kindly add color on the color field"),
        "BRAND name repeated in NAME": ("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", """Please do not write the brand name in the Product Name field. The brand name should only be written in the Brand field.
If you include it in both fields, it will show up twice in the product title on the website"""),
        "Duplicate product": ("1000007 - Other Reason", "kindly note product was rejected because its a duplicate product"),
    }

    validation_results_dfs = {}
    for flag_name, check_func, func_kwargs in validations:
        current_kwargs = {'data': data}
        if flag_name == "Generic BRAND Issues":
            fas_df = cfg.get('category_fas', pd.DataFrame())
            current_kwargs['valid_category_codes_fas'] = fas_df['ID'].astype(str).tolist() if not fas_df.empty and 'ID' in fas_df.columns else []
        else:
            current_kwargs.update(func_kwargs)
        try:
            result_df = check_func(**current_kwargs)
            if not result_df.empty and 'PRODUCT_SET_SID' not in result_df.columns and 'PRODUCT_SET_SID' in data.columns:
                st.warning(f"Check '{flag_name}' did not return 'PRODUCT_SET_SID'. Results might be incomplete.")
                validation_results_dfs[flag_name] = pd.DataFrame(columns=data.columns)
            else:
                validation_results_dfs[flag_name] = result_df
        except Exception as e:
            st.error(f"Error during validation check '{flag_name}': {e}")
            validation_results_dfs[flag_name] = pd.DataFrame(columns=data.columns)

    final_report_rows = []
    processed_sids = set()
    for flag_name, _, _ in validations:
        validation_df = validation_results_dfs.get(flag_name, pd.DataFrame())
        if validation_df.empty or 'PRODUCT_SET_SID' not in validation_df.columns:
            continue
        rejection_reason, comment = flag_reason_comment_mapping.get(flag_name, ("Unknown Reason", "No comment defined."))
        flagged_sids_df = pd.merge(
            validation_df[['PRODUCT_SET_SID']],
            data,
            on='PRODUCT_SET_SID',
            how='left'
        )
        for _, row in flagged_sids_df.iterrows():
            sid = row.get('PRODUCT_SET_SID')
            if sid in processed_sids:
                continue
            processed_sids.add(sid)
            final_report_rows.append({
                'ProductSetSid': sid,
                'ParentSKU': row.get('PARENTSKU', ''),
                'Status': 'Rejected',
                'Reason': rejection_reason,
                'Comment': comment,
                'FLAG': flag_name,
                'SellerName': row.get('SELLER_NAME', '')
            })

    all_sids = set(data['PRODUCT_SET_SID'].astype(str).unique())
    approved_sids = all_sids - processed_sids
    approved_data = data[data['PRODUCT_SET_SID'].isin(approved_sids)]
    for _, row in approved_data.iterrows():
        final_report_rows.append({
            'ProductSetSid': row.get('PRODUCT_SET_SID'),
            'ParentSKU': row.get('PARENTSKU', ''),
            'Status': 'Approved',
            'Reason': "",
            'Comment': "",
            'FLAG': "",
            'SellerName': row.get('SELLER_NAME', '')
        })

    final_report_df = pd.DataFrame(final_report_rows)
    return final_report_df, validation_results_dfs

# -------------------------------------------------
# Export functions
# -------------------------------------------------
def to_excel_base(df_to_export, sheet_name, columns_to_include, writer):
    df_prepared = df_to_export.copy()
    for col in columns_to_include:
        if col not in df_prepared.columns:
            df_prepared[col] = pd.NA
    df_prepared[columns_to_include].to_excel(writer, index=False, sheet_name=sheet_name)

def to_excel_full_data(data_df, final_report_df):
    try:
        output = BytesIO()
        data_df_copy = data_df.copy()
        final_report_df_copy = final_report_df.copy()
        data_df_copy['PRODUCT_SET_SID'] = data_df_copy['PRODUCT_SET_SID'].astype(str).str.strip()
        final_report_df_copy['ProductSetSid'] = final_report_df_copy['ProductSetSid'].astype(str).str.strip()
        merged_df = pd.merge(
            data_df_copy,
            final_report_df_copy[["ProductSetSid", "Status", "Reason", "Comment", "FLAG", "SellerName"]],
            left_on="PRODUCT_SET_SID",
            right_on="ProductSetSid",
            how='left'
        )
        if merged_df.empty:
            st.error("Merged DataFrame is empty. Verify PRODUCT_SET_SID values match.")
            return output
        if 'ProductSetSid_y' in merged_df.columns:
            merged_df.drop(columns=['ProductSetSid_y'], inplace=True)
        if 'ProductSetSid_x' in merged_df.columns:
            merged_df.rename.web(columns={'ProductSetSid_x': 'PRODUCT_SET_SID'}, inplace=True)
        if 'FLAG' in merged_df.columns:
            merged_df['FLAG'] = merged_df['FLAG'].fillna('')
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            to_excel_base(merged_df, "ProductSets", FULL_DATA_COLS, writer)
            workbook = writer.book
            worksheet = workbook.add_worksheet('Sellers Data')
            header_fmt = workbook.add_format({'bold': True, 'bg_color': '#E6F0FA', 'border': 1, 'align': 'center'})
            red_fill = workbook.add_format({'bg_color': '#FFC7CE', 'border': 1})
            sellers_data_rows = []
            start_row = 0
            sellers_data_rows.append(pd.DataFrame([['', '', '', '']]))
            sellers_data_rows.append(pd.DataFrame([['Sellers Summary', '', '', '']]))
            if 'SELLER_RATING' in merged_df.columns:
                seller_summary = merged_df.groupby('SELLER_NAME').agg(
                    Rejected=('Status', lambda x: (x == 'Rejected').sum()),
                    Approved=('Status', lambda x: (x == 'Approved').sum()),
                    AvgRating=('SELLER_RATING', 'mean'),
                    TotalStock=('STOCK_QTY', 'sum')
                ).reset_index()
                seller_summary['Rejection %'] = (seller_summary['Rejected'] / (seller_summary['Rejected'] + seller_summary['Approved']) * 100).round(1)
                seller_summary = seller_summary.sort_values('Rejected', ascending=False)
                sellers_data_rows.append(seller_summary)
            try:
                if 'CATEGORY' in merged_df.columns and not merged_df['CATEGORY'].isna().all():
                    category_rejections = (merged_df[merged_df['Status'] == 'Rejected'].groupby('CATEGORY').size().reset_index(name='Rejected Products'))
                    category_rejections = category_rejections.sort_values('Rejected Products', ascending=False)
                    category_rejections.insert(0, 'Rank', range(1, len(category_rejections) + 1))
                    sellers_data_rows.append(pd.DataFrame([['', '', '', '']]))
                    sellers_data_rows.append(pd.DataFrame([['Categories Summary', '', '', '']]))
                    sellers_data_rows.append(category_rejections.rename(columns={'CATEGORY': 'Category', 'Rejected Products': 'Number of Rejected Products'}))
            except Exception as e:
                sellers_data_rows.append(pd.DataFrame([['Categories Summary', f'Error: {str(e)}', '', '']]))
            try:
                if 'Reason' in merged_df.columns and not merged_df['Reason'].isna().all():
                    reason_rejections = (merged_df[merged_df['Status'] == 'Rejected'].groupby('Reason').size().reset_index(name='Rejected Products'))
                    reason_rejections = reason_rejections.sort_values('Rejected Products', ascending=False)
                    reason_rejections.insert(0, 'Rank', range(1, len(reason_rejections) + 1))
                    sellers_data_rows.append(pd.DataFrame([['', '', '', '']]))
                    sellers_data_rows.append(pd.DataFrame([['Rejection Reasons Summary', '', '', '']]))
                    sellers_data_rows.append(reason_rejections.rename(columns={'Reason': 'Rejection Reason', 'Rejected Products': 'Number of Rejected Products'}))
            except Exception as e:
                sellers_data_rows.append(pd.DataFrame([['Rejection Reasons Summary', f'Error: {str(e)}', '', '']]))
            for df in sellers_data_rows:
                if df.empty or len(df.columns) < 2:
                    continue
                if 'Rank' in df.columns:
                    for col_num, col_name in enumerate(df.columns):
                        worksheet.write(start_row, col_num, col_name, header_fmt)
                    for row_num, row_data in enumerate(df.values, start=start_row + 1):
                        for col_num, value in enumerate(row_data):
                            fmt = red_fill if col_num == 4 and len(row_data) > 4 and value > 30 else None
                            worksheet.write(row_num, col_num, value, fmt or header_fmt)
                else:
                    worksheet.write(start_row, 0, df.iloc[0, 0], header_fmt)
                start_row += len(df) + 1
            worksheet.set_column('A:A', 30)
            worksheet.set_column('B:B', 10)
            worksheet.set_column('C:C', 20)
        output.seek(0)
        return output
    except Exception as e:
        st.error(f"Error generating Full Data Export: {str(e)}")
        return BytesIO()

def to_excel_flag_data(flag_df, flag_name):
    output = BytesIO()
    df_copy = flag_df.copy()
    df_copy['FLAG'] = flag_name
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(df_copy, "ProductSets", FULL_DATA_COLS, writer)
    output.seek(0)
    return output

def to_excel(report_df, reasons_config_df, sheet1_name="ProductSets", sheet2_name="RejectionReasons"):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(report_df, sheet1_name, PRODUCTSETS_COLS, writer)
        if not reasons_config_df.empty:
            to_excel_base(reasons_config_df, sheet2_name, REJECTION_REASONS_COLS, writer)
        else:
            pd.DataFrame(columns=REJECTION_REASONS_COLS).to_excel(writer, index=False, sheet_name=sheet2_name)
    output.seek(0)
    return output

# -------------------------------------------------
# UI
# -------------------------------------------------
st.title("Product Validation Tool")

tab1, tab2, tab3 = st.tabs(["Daily Validation", "Weekly Analysis", "Data Lake"])

# ================================
# DAILY VALIDATION TAB
# ================================
with tab1:
    country = st.selectbox("Select Country", ["Kenya", "Uganda"], key="daily_country")
    uploaded_file = st.file_uploader("Upload your CSV file", type='csv', key="daily_file")
    if uploaded_file is not None:
        current_date = datetime.now().strftime('%Y-%m-%d')
        file_prefix = "KE" if country == "Kenya" else "UG"
        try:
            dtype_spec = {
                'CATEGORY_CODE': str,
                'PRODUCT_SET_SID': str,
                'PARENTSKU': str,
                'ACTIVE_STATUS_COUNTRY': str,
            }
            raw_data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype=dtype_spec)
            st.write(f"Loaded CSV with {len(raw_data)} rows.")
            data = filter_ke_ug_only(raw_data, "Daily CSV")
            if data.empty:
                st.stop()

            selected_code = "KE" if country == "Kenya" else "UG"
            before_count = len(data)
            data = data[data['ACTIVE_STATUS_COUNTRY'].str.contains(rf'\b{selected_code}\b', na=False, regex=True)]
            excluded_in_selected = before_count - len(data)
            if excluded_in_selected > 0:
                st.warning(f"Excluded {excluded_in_selected} non-{country} rows.")
            else:
                st.info(f"All {len(data)} rows are from {country}.")

            essential_input_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'COLOR', 'SELLER_NAME', 'GLOBAL_PRICE', 'GLOBAL_SALE_PRICE', 'PARENTSKU']
            for col in essential_input_cols:
                if col not in data.columns:
                    data[col] = pd.NA
            for col in ['NAME', 'BRAND', 'COLOR', 'SELLER_NAME', 'CATEGORY_CODE', 'PARENTSKU']:
                if col in data.columns:
                    data[col] = data[col].astype(str).fillna('')

            final_report_df, individual_flag_dfs = validate_products(
                data, config_data, blacklisted_words, reasons_df,
                book_category_codes, sensitive_brand_words,
                approved_book_sellers, perfume_category_codes,
                sensitive_perfume_brands, country
            )

            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

            # --- ORIGINAL SIDEBAR RESTORED ---
            st.sidebar.header("Seller Options")
            seller_options = ['All Sellers']
            if 'SELLER_NAME' in data.columns and 'ProductSetSid' in final_report_df.columns and 'PRODUCT_SET_SID' in data.columns:
                final_report_df_for_join = final_report_df.copy()
                final_report_df_for_join['ProductSetSid'] = final_report_df_for_join['ProductSetSid'].astype(str)
                data_for_join = data[['PRODUCT_SET_SID', 'SELLER_NAME']].copy()
                data_for_join['PRODUCT_SET_SID'] = data_for_join['PRODUCT_SET_SID'].astype(str)
                data_for_join.drop_duplicates(subset=['PRODUCT_SET_SID'], inplace=True)
                report_with_seller = pd.merge(
                    final_report_df_for_join,
                    data_for_join,
                    left_on='ProductSetSid',
                    right_on='PRODUCT_SET_SID',
                    how='left'
                )
                if not report_with_seller.empty:
                    seller_options.extend(list(report_with_seller['SELLER_NAME'].dropna().unique()))
            selected_sellers = st.sidebar.multiselect("Select Sellers", seller_options, default=['All Sellers'], key="daily_sellers")

            seller_data_filtered = data.copy()
            seller_final_report_df_filtered = final_report_df.copy()
            seller_label_filename = "All_Sellers"
            if 'All Sellers' not in selected_sellers and selected_sellers:
                if 'SELLER_NAME' in data.columns:
                    seller_data_filtered = data[data['SELLER_NAME'].isin(selected_sellers)].copy()
                    seller_final_report_df_filtered = final_report_df[final_report_df['ProductSetSid'].isin(seller_data_filtered['PRODUCT_SET_SID'])].copy()
                    seller_label_filename = "_".join(s.replace(" ", "_").replace("/", "_") for s in selected_sellers)
                else:
                    st.sidebar.warning("SELLER_NAME column missing, cannot filter by seller.")

            seller_rejected_df_filtered = seller_final_report_df_filtered[seller_final_report_df_filtered['Status'] == 'Rejected']
            seller_approved_df_filtered = seller_final_report_df_filtered[seller_final_report_df_filtered['Status'] == 'Approved']

            st.sidebar.subheader("Seller SKU Metrics")
            if 'SELLER_NAME' in data.columns and 'report_with_seller' in locals() and not report_with_seller.empty:
                sellers_to_display = selected_sellers if 'All Sellers' not in selected_sellers and selected_sellers else seller_options[1:]
                for seller in sellers_to_display:
                    if seller == 'All Sellers': continue
                    current_seller_data = report_with_seller[report_with_seller['SELLER_NAME'] == seller]
                    rej_count = current_seller_data[current_seller_data['Status'] == 'Rejected'].shape[0]
                    app_count = current_seller_data[current_seller_data['Status'] == 'Approved'].shape[0]
                    st.sidebar.write(f"{seller}: **Rej**: {rej_count}, **App**: {app_count}")
            else:
                st.sidebar.write("Seller metrics unavailable.")

            st.sidebar.subheader(f"Exports for: {seller_label_filename.replace('_', ' ')}")
            st.sidebar.download_button("Seller Final Export", to_excel(seller_final_report_df_filtered, reasons_df), f"{file_prefix}_Final_Report_{current_date}_{seller_label_filename}.xlsx", key="daily_final")
            st.sidebar.download_button("Seller Rejected Export", to_excel(seller_rejected_df_filtered, reasons_df), f"{file_prefix}_Rejected_Products_{current_date}_{seller_label_filename}.xlsx", key="daily_rejected")
            st.sidebar.download_button("Seller Approved Export", to_excel(seller_approved_df_filtered, reasons_df), f"{file_prefix}_Approved_Products_{current_date}_{seller_label_filename}.xlsx", key="daily_approved")
            st.sidebar.download_button("Seller Full Data Export", to_excel_full_data(seller_data_filtered, seller_final_report_df_filtered), f"{file_prefix}_Seller_Data_Export_{current_date}_{seller_label_filename}.xlsx", key="daily_full")

            # Main content
            st.header("Overall Results")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total", len(data))
                st.metric("Approved", len(approved_df))
            with col2:
                st.metric("Rejected", len(rejected_df))
                rate = (len(rejected_df)/len(data)*100) if len(data) > 0 else 0
                st.metric("Rejection Rate", f"{rate:.1f}%")

            for title, df_flagged in individual_flag_dfs.items():
                with st.expander(f"{title} ({len(df_flagged)} products)"):
                    if not df_flagged.empty:
                        cols = [c for c in ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'SELLER_NAME', 'CATEGORY_CODE'] if c in df_flagged.columns]
                        st.dataframe(df_flagged[cols])
                        safe = title.replace(' ', '_').replace('/', '_')
                        st.download_button(f"Export {title}", to_excel_flag_data(df_flagged.copy(), title), f"{file_prefix}_{safe}_{current_date}.xlsx", key=f"flag_{safe}")
                    else:
                        st.write("No issues.")

            st.header("Overall Exports")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.download_button("Final Report", to_excel(final_report_df, reasons_df), f"{file_prefix}_Final_{current_date}_ALL.xlsx")
            with col2:
                st.download_button("Rejected", to_excel(rejected_df, reasons_df), f"{file_prefix}_Rejected_{current_date}_ALL.xlsx")
            with col3:
                st.download_button("Approved", to_excel(approved_df, reasons_df), f"{file_prefix}_Approved_{current_date}_ALL.xlsx")
            with col4:
                st.download_button("Full Data", to_excel_full_data(data.copy(), final_report_df), f"{file_prefix}_Full_{current_date}_ALL.xlsx")

        except Exception as e:
            st.error(f"Error: {e}")

# ================================
# WEEKLY & DATA LAKE TABS (unchanged – same sidebar logic)
# ================================

# ... (rest of Weekly and Data Lake tabs – same as your original, with seller sidebar in Data Lake too)
