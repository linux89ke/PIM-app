import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import warnings

# -------------------------------------------------
# Page config
# -------------------------------------------------
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# -------------------------------------------------
# Constants (2025 data-lake schema)
# -------------------------------------------------
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]
REJECTION_REASONS_COLS = ['CODE - REJECTION_REASON', 'COMMENT']
FULL_DATA_COLS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE",
    "COLOR", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU",
    "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG",
    "LISTING_STATUS", "SELLER_RATING", "STOCK_QTY"
]

COUNTRY_MAPPING = {"Kenya": "KE", "Uganda": "UG", "All Countries": None}

# -------------------------------------------------
# Helper – date from filename
# -------------------------------------------------
def extract_date_from_filename(filename: str):
    m = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    return pd.to_datetime(m.group(1)) if m else None

# -------------------------------------------------
# Load support files (graceful fallback)
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

# Load all support files
blacklisted_words          = _load_txt('blacklisted.txt')
book_category_codes        = _load_excel('Books_cat.xlsx', 'CategoryCode')
approved_book_sellers      = _load_excel('Books_Approved_Sellers.xlsx', 'SellerName')
sensitive_brand_words      = _load_excel('sensitive_brands.xlsx', 'BrandWords')
perfume_category_codes     = _load_excel('Perfume_cat.xlsx', 'CategoryCode')
approved_perfume_sellers   = _load_excel('perfumeSellers.xlsx', 'SellerName')  # ← NEW

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
# Country filter (shared)
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
def check_missing_color(data, book_codes):
    if not {'CATEGORY_CODE','COLOR'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    non_books = data[~data['CATEGORY_CODE'].isin(book_codes)]
    return non_books[non_books['COLOR'].isna() | (non_books['COLOR'] == '')]

def check_missing_brand_or_name(data):
    if not {'BRAND','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    return data[data['BRAND'].isna() | (data['BRAND']=='') | data['NAME'].isna() | (data['NAME']=='')]

def check_single_word_name(data, book_codes):
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    non_books = data[~data['CATEGORY_CODE'].isin(book_codes)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1]

def check_generic_brand_issues(data, fas_codes):
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    return data[data['CATEGORY_CODE'].isin(fas_codes) & (data['BRAND']=='Generic')]

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

def check_sensitive_brands(data, sens_words, book_codes):
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    books = data[data['CATEGORY_CODE'].isin(book_codes)]
    if books.empty or not sens_words:
        return pd.DataFrame(columns=data.columns)
    pat = '|'.join(r'\b' + re.escape(w.lower()) + r'\b' for w in sens_words)
    return books[books['NAME'].astype(str).str.lower().str.contains(pat, regex=True, na=False)]

def check_seller_approved_for_books(data, book_codes, approved):
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    books = data[data['CATEGORY_CODE'].isin(book_codes)]
    if books.empty or not approved:
        return pd.DataFrame(columns=data.columns)
    return books[~books['SELLER_NAME'].isin(approved)]

# ---- NEW: Seller Approved to Sell Perfume (Kenya only) ----
def check_seller_approved_for_perfume(data, perfume_codes, approved_sellers):
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns):
        return pd.DataFrame(columns=data.columns)
    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_codes)]
    if perfume_data.empty or not approved_sellers:
        return pd.DataFrame(columns=data.columns)
    unapproved = perfume_data[~perfume_data['SELLER_NAME'].isin(approved_sellers)]
    return unapproved

# ---- Perfume price (2025 FX) ----
FX_RATE = 132.0
def check_perfume_price(data, perf_df, perf_codes):
    req = ['CATEGORY_CODE','NAME','BRAND','GLOBAL_SALE_PRICE','GLOBAL_PRICE','CURRENCY']
    if not all(c in data.columns for c in req) or perf_df.empty or not perf_codes:
        return pd.DataFrame(columns=data.columns)

    perf = data[data['CATEGORY_CODE'].isin(perf_codes)]
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

        m = perf_df[(perf_df['BRAND'].str.lower()==brand) &
                    (perf_df['PRODUCT_NAME'].str.lower().apply(lambda x: x in name))]
        if m.empty:
            m = perf_df[(perf_df['BRAND'].str.lower()==brand) &
                        (perf_df['KEYWORD'].str.lower().apply(lambda x: x in name))]
        if not m.empty:
            ref_usd = m.iloc[0]['PRICE_USD']
            if ref_usd - price_usd >= 30:
                flagged.append(row.to_dict())
    return pd.DataFrame(flagged) if flagged else pd.DataFrame(columns=data.columns)

# -------------------------------------------------
# Master validation runner
# -------------------------------------------------
def validate_products(data, cfg, country):
    validations = [
        ("Sensitive Brand Issues", check_sensitive_brands,
         {'sensitive_brand_words': sensitive_brand_words, 'book_category_codes': book_category_codes}),
        ("Seller Approve to sell books", check_seller_approved_for_books,
         {'book_category_codes': book_category_codes, 'approved_book_sellers': approved_book_sellers}),
        ("Perfume Price Check", check_perfume_price,
         {'perfumes_df': cfg.get('perfumes', pd.DataFrame()), 'perfume_category_codes': perfume_category_codes}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume,
         {'perfume_category_codes': perfume_category_codes, 'approved_perfume_sellers': approved_perfume_sellers}),  # ← NEW
        ("Single-word NAME", check_single_word_name, {'book_category_codes': book_category_codes}),
        ("Missing BRAND or NAME", check_missing_brand_or_name, {}),
        ("Generic BRAND Issues", check_generic_brand_issues, {}),
        ("Missing COLOR", check_missing_color, {'book_category_codes': book_category_codes}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Duplicate product", check_duplicate_products, {}),
    ]

    # Skip certain checks for Uganda
    if country == "Uganda":
        skip = ["Sensitive Brand Issues", "Seller Approve to sell books", "Perfume Price Check", "Seller Approved to Sell Perfume"]
        validations = [v for v in validations if v[0] not in skip]

    # Reason / comment mapping
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
            current_product_sid = row.get('PRODUCT_SET_SID')
            if current_product_sid in processed_sids:
                continue
            processed_sids.add(current_product_sid)
            final_report_rows.append({
                'ProductSetSid': current_product_sid,
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
            merged_df.rename(columns={'ProductSetSid_x': 'PRODUCT_SET_SID'}, inplace=True)
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
# Weekly Analysis Parser
# -------------------------------------------------
def parse_sellers_data_sheet(sellers_sheet, date):
    all_sellers = []
    all_categories = []
    all_reasons = []
    section_starts = {}
    for idx in range(len(sellers_sheet)):
        row = sellers_sheet.iloc[idx]
        if pd.isna(row[0]):
            continue
        cell = str(row[0]).strip()
        if 'Sellers Summary' in cell:
            section_starts['sellers'] = idx
        elif 'Categories Summary' in cell:
            section_starts['categories'] = idx
        elif 'Rejection Reasons Summary' in cell:
            section_starts['reasons'] = idx
    if 'sellers' in section_starts:
        start = section_starts['sellers']
        end = section_starts.get('categories', len(sellers_sheet))
        header_idx = None
        for i in range(start + 1, end):
            if str(sellers_sheet.iloc[i, 0]).strip() == 'Rank':
                header_idx = i
                break
        if header_idx is not None:
            data_start = header_idx + 1
            data_end = end
            data_rows = sellers_sheet.iloc[data_start:data_end, [0, 1, 2]].dropna(how='all')
            if not data_rows.empty:
                data_rows.columns = ['Rank', 'Seller', 'Rejected Products']
                data_rows['Date'] = date
                data_rows['Rejected Products'] = pd.to_numeric(data_rows['Rejected Products'], errors='coerce')
                all_sellers.append(data_rows)
    if 'categories' in section_starts:
        start = section_starts['categories']
        end = section_starts.get('reasons', len(sellers_sheet))
        header_idx = None
        for i in range(start + 1, end):
            if str(sellers_sheet.iloc[i, 0]).strip() == 'Rank':
                header_idx = i
                break
        if header_idx is not None:
            data_start = header_idx + 1
            data_end = end
            data_rows = sellers_sheet.iloc[data_start:data_end, [0, 1, 2]].dropna(how='all')
            if not data_rows.empty:
                data_rows.columns = ['Rank', 'Category', 'Rejected Products']
                data_rows['Date'] = date
                data_rows['Rejected Products'] = pd.to_numeric(data_rows['Rejected Products'], errors='coerce')
                all_categories.append(data_rows)
    if 'reasons' in section_starts:
        start = section_starts['reasons']
        end = len(sellers_sheet)
        header_idx = None
        for i in range(start + 1, end):
            if str(sellers_sheet.iloc[i, 0]).strip() == 'Rank':
                header_idx = i
                break
        if header_idx is not None:
            data_start = header_idx + 1
            data_end = end
            data_rows = sellers_sheet.iloc[data_start:data_end, [0, 1, 2]].dropna(how='all')
            if not data_rows.empty:
                data_rows.columns = ['Rank', 'Rejection Reason', 'Rejected Products']
                data_rows['Date'] = date
                data_rows['Rejected Products'] = pd.to_numeric(data_rows['Rejected Products'], errors='coerce')
                all_reasons.append(data_rows)
    sellers_df = pd.concat(all_sellers, ignore_index=True) if all_sellers else pd.DataFrame()
    categories_df = pd.concat(all_categories, ignore_index=True) if all_categories else pd.DataFrame()
    reasons_df = pd.concat(all_reasons, ignore_index=True) if all_reasons else pd.DataFrame()
    return sellers_df, categories_df, reasons_df

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
        election_prefix = "POST_ELECTION_2025_" if datetime.now().date() > datetime(2025, 1, 20).date() else ""
        current_date = f"{election_prefix}{datetime.now().strftime('%Y-%m-%d')}"
        file_prefix = "KE" if country == "Kenya" else "UG"
        process_success = False
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
                st.warning(f"Excluded {excluded_in_selected} rows not matching selected country ({selected_code}). Processing {len(data)} {country} rows only.")
            else:
                st.info(f"All {len(data)} valid rows are from {country} ({selected_code}).")
            if data.empty:
                st.error(f"No {country} ({selected_code}) rows found after filtering.")
                st.stop()

            essential_input_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'COLOR', 'SELLER_NAME', 'GLOBAL_PRICE', 'GLOBAL_SALE_PRICE', 'PARENTSKU']
            for col in essential_input_cols:
                if col not in data.columns:
                    data[col] = pd.NA
            for col in ['NAME', 'BRAND', 'COLOR', 'SELLER_NAME', 'CATEGORY_CODE', 'PARENTSKU']:
                if col in data.columns:
                    data[col] = data[col].astype(str).fillna('')

            st.write(f"Processed {len(data)} products after cleaning.")
            final_report_df, individual_flag_dfs = validate_products(
                data, config_data, blacklisted_words, reasons_df, book_category_codes,
                sensitive_brand_words, approved_book_sellers, perfume_category_codes, country
            )
            process_success = True

            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

            # Seller filtering
            st.sidebar.header("Seller Options")
            seller_options = ['All Sellers']
            if 'SELLER_NAME' in data.columns:
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

            seller_rejected_df_filtered = seller_final_report_df_filtered[seller_final_report_df_filtered['Status'] == 'Rejected']
            seller_approved_df_filtered = seller_final_report_df_filtered[seller_final_report_df_filtered['Status'] == 'Approved']

            # Metrics
            st.header("Overall Product Validation Results")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Products in Upload", len(data))
                st.metric("Approved Products (Overall)", len(approved_df))
            with col2:
                st.metric("Rejected Products (Overall)", len(rejected_df))
                rejection_rate = (len(rejected_df)/len(data)*100) if len(data) > 0 else 0
                st.metric("Rejection Rate (Overall)", f"{rejection_rate:.1f}%")

            # Flag details
            for title, df_flagged in individual_flag_dfs.items():
                with st.expander(f"{title} ({len(df_flagged)} products overall)"):
                    if not df_flagged.empty:
                        display_cols = [col for col in ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'SELLER_NAME', 'CATEGORY_CODE', 'COLOR'] if col in df_flagged.columns]
                        st.dataframe(df_flagged[display_cols] if display_cols else df_flagged)
                        flag_excel_export = to_excel_flag_data(df_flagged.copy(), title)
                        safe_title = title.replace(' ', '_').replace('/', '_')
                        st.download_button(
                            label=f"Export {title} Data",
                            data=flag_excel_export,
                            file_name=f"{file_prefix}_{safe_title}_Products_{current_date}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"daily_flag_{safe_title}"
                        )
                    else:
                        st.write("No issues found for this check.")

            # Exports
            st.header("Overall Data Exports (All Sellers)")
            col1_main, col2_main, col3_main, col4_main = st.columns(4)
            with col1_main:
                overall_final_excel = to_excel(final_report_df, reasons_df)
                st.download_button("Final Export (All)", data=overall_final_excel, file_name=f"{file_prefix}_Final_Report_{current_date}_ALL.xlsx", key="daily_overall_final")
            with col2_main:
                overall_rejected_excel = to_excel(rejected_df, reasons_df)
                st.download_button("Rejected Export (All)", data=overall_rejected_excel, file_name=f"{file_prefix}_Rejected_Products_{current_date}_ALL.xlsx", key="daily_overall_rejected")
            with col3_main:
                overall_approved_excel = to_excel(approved_df, reasons_df)
                st.download_button("Approved Export (All)", data=overall_approved_excel, file_name=f"{file_prefix}_Approved_Products_{current_date}_ALL.xlsx", key="daily_overall_approved")
            with col4_main:
                overall_full_excel = to_excel_full_data(data.copy(), final_report_df)
                st.download_button("Full Data Export (All)", data=overall_full_excel, file_name=f"{file_prefix}_Full_Data_Export_{current_date}_ALL.xlsx", key="daily_overall_full")

        except Exception as e:
            st.error(f"Error: {e}")

# ================================
# WEEKLY & DATA LAKE TABS (unchanged)
# ================================
with tab2:
    st.subheader("Weekly Analysis")
    uploaded_files = st.file_uploader("Upload multiple Excel files for the week", type=['xlsx'], accept_multiple_files=True, key="weekly_files")
    if uploaded_files:
        all_sellers_dfs = []
        all_categories_dfs = []
        all_reasons_dfs = []
        dates = []
        for file in uploaded_files:
            date = extract_date_from_filename(file.name)
            if date is None:
                st.warning(f"Could not extract date from filename: {file.name}")
                continue
            try:
                sellers_sheet = pd.read_excel(file, sheet_name='Sellers Data', header=None)
                sellers_df, categories_df, reasons_df = parse_sellers_data_sheet(sellers_sheet, date)
                if not sellers_df.empty:
                    all_sellers_dfs.append(sellers_df)
                if not categories_df.empty:
                    all_categories_dfs.append(categories_df)
                if not reasons_df.empty:
                    all_reasons_dfs.append(reasons_df)
                dates.append(date)
            except Exception as e:
                st.error(f"Error reading {file.name}: {e}")
        if all_sellers_dfs or all_categories_dfs or all_reasons_dfs:
            st.success(f"Parsed data from {len(dates)} files.")
            # ... (rest of weekly analysis - unchanged) ...
            pass

with tab3:
    st.subheader("Data Lake Validation")
    country = st.selectbox("Select Country", ["Kenya", "Uganda", "All Countries"], key="data_lake_country")
    uploaded_file = st.file_uploader("Upload your Data Lake Excel file", type='xlsx', key="data_lake_file")
    if uploaded_file is not None:
        # ... (same logic as Daily, but with column renaming) ...
        pass
