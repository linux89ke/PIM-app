import pandas as pd
import io
import base64
import re
from datetime import datetime
import streamlit as st

# Constants for column names
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG"]
REJECTION_REASONS_COLS = ['CODE - REJECTION_REASON', 'COMMENT']
FULL_DATA_COLS = ["PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE", "COLOR", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU", "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG"]

# Country mapping for Data Lake tab
COUNTRY_MAPPING = {
    "Kenya": "jumia-ke",
    "Uganda": "jumia-ug",
    "All Countries": None
}

# Function to extract date from filename
def extract_date_from_filename(filename):
    pattern = r'(\d{4}-\d{2}-\d{2})'
    match = re.search(pattern, filename)
    return pd.to_datetime(match.group(1)) if match else None

# Function to load configuration files
def load_config_files():
    config_files = {
        'check_variation': 'check_variation.xlsx',
        'category_fas': 'category_FAS.xlsx',
        'perfumes': 'perfumes.xlsx',
        'reasons': 'reasons.xlsx',
        'books_cat': 'Books_cat.xlsx',
        'sensitive_brands': 'sensitive_brands.xlsx',
        'approved_sellers': 'Books_Approved_Sellers.xlsx',
        'perfume_cat': 'Perfume_cat.txt',
        'valid_colors': 'colors.txt'
    }
    data = {}
    for key, filename in config_files.items():
        try:
            if filename.endswith('.txt'):
                with open(filename, 'r') as f:
                    data[key] = [line.strip().lower() for line in f.readlines() if line.strip()]
                if key == 'valid_colors' and not data[key]:
                    st.warning("colors.txt is empty; all colors will be considered invalid.")
            else:
                df = pd.read_excel(filename).rename(columns=lambda x: x.strip())
                data[key] = df
        except FileNotFoundError:
            st.warning(f"{filename} not found, related functionality will be limited.")
            data[key] = pd.DataFrame() if filename.endswith('.xlsx') else []
        except Exception as e:
            st.error(f"Error loading {filename}: {e}")
            data[key] = pd.DataFrame() if filename.endswith('.xlsx') else []
    return data

# Validation check functions
def check_missing_color(data, book_category_codes):
    """Used for Daily Validation tab"""
    if 'CATEGORY_CODE' not in data.columns or 'COLOR' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_book_data[non_book_data['COLOR'].isna() | (non_book_data['COLOR'] == '')]

def check_missing_color_data_lake(data, book_category_codes, valid_colors):
    """Used for Data Lake tab: checks color against colors.txt, falls back to color_family"""
    if 'CATEGORY_CODE' not in data.columns or 'COLOR' not in data.columns or 'COLOR_FAMILY' not in data.columns:
        st.error("Required columns missing: CATEGORY_CODE, COLOR, or COLOR_FAMILY")
        return pd.DataFrame(columns=data.columns)
    
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    
    def clean_color(color):
        if pd.isna(color) or color == '':
            return []
        color = color.lower().strip()
        return [c.strip() for c in re.split(r'[/\s-]+', color) if c.strip()]
    
    non_book_data['COLOR_CLEAN'] = non_book_data['COLOR'].apply(clean_color)
    non_book_data['COLOR_FAMILY_CLEAN'] = non_book_data['COLOR_FAMILY'].apply(clean_color)
    
    valid_color = non_book_data[
        non_book_data['COLOR_CLEAN'].apply(lambda x: any(c in valid_colors for c in x)) &
        pd.notna(non_book_data['COLOR']) & (non_book_data['COLOR'] != '')
    ]
    valid_color_family = non_book_data[
        (~non_book_data['COLOR_CLEAN'].apply(lambda x: any(c in valid_colors for c in x)) | 
         non_book_data['COLOR'].isna() | (non_book_data['COLOR'] == '')) &
        non_book_data['COLOR_FAMILY_CLEAN'].apply(lambda x: any(c in valid_colors for c in x)) &
        pd.notna(non_book_data['COLOR_FAMILY']) & (non_book_data['COLOR_FAMILY'] != '')
    ]
    invalid_color_values = non_book_data[
        ~non_book_data['COLOR_CLEAN'].apply(lambda x: any(c in valid_colors for c in x)) &
        pd.notna(non_book_data['COLOR']) & (non_book_data['COLOR'] != '')
    ]['COLOR'].unique()
    flagged_data = non_book_data[
        (~non_book_data['COLOR_CLEAN'].apply(lambda x: any(c in valid_colors for c in x)) & 
         non_book_data['COLOR'].isna() | (non_book_data['COLOR'] == '')) &
        (~non_book_data['COLOR_FAMILY_CLEAN'].apply(lambda x: any(c in valid_colors for c in x)) & 
         non_book_data['COLOR_FAMILY'].isna() | (non_book_data['COLOR_FAMILY'] == ''))
    ][['COLOR', 'COLOR_FAMILY']]
    
    st.write(f"Debug: {len(valid_color)}/{len(non_book_data)} non-book products have valid COLOR")
    st.write(f"Debug: {len(valid_color_family)}/{len(non_book_data)} non-book products have invalid COLOR but valid COLOR_FAMILY")
    st.write("Invalid COLOR values:", invalid_color_values.tolist())
    st.write("Flagged products' COLOR and COLOR_FAMILY:", flagged_data.to_dict(orient='records') if not flagged_data.empty else "None")
    
    return flagged_data

def check_multicolour_non_watches(data):
    if 'CATEGORY' not in data.columns or 'COLOR' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    return data[~data['CATEGORY'].isin(['Wrist Watches', 'Smart Watches']) & (data['COLOR'].str.lower() == 'multicolour')]

def check_missing_brand_or_name(data):
    if 'BRAND' not in data.columns or 'NAME' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    return data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]

def check_single_word_name(data, book_category_codes):
    if 'CATEGORY_CODE' not in data.columns or 'NAME' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_book_data[non_book_data['NAME'].astype(str).str.split().str.len() == 1]

def check_generic_brand_issues(data, valid_category_codes_fas):
    if 'CATEGORY_CODE' not in data.columns or 'BRAND' not in data.columns or not valid_category_codes_fas:
        return pd.DataFrame(columns=data.columns)
    return data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]

def check_brand_in_name(data):
    if 'BRAND' not in data.columns or 'NAME' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    return data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

def check_duplicate_products(data):
    subset_cols = [col for col in ['NAME', 'BRAND', 'SELLER_NAME', 'COLOR'] if col in data.columns]
    if len(subset_cols) < 4:
        return pd.DataFrame(columns=data.columns)
    return data[data.duplicated(subset=subset_cols, keep=False)]

def check_sensitive_brands(data, sensitive_brand_words, book_category_codes):
    if 'CATEGORY_CODE' not in data.columns or 'NAME' not in data.columns or not sensitive_brand_words:
        return pd.DataFrame(columns=data.columns)
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if book_data.empty:
        return pd.DataFrame(columns=data.columns)
    sensitive_regex_words = [r'\b' + re.escape(word.lower()) + r'\b' for word in sensitive_brand_words]
    sensitive_brands_regex = '|'.join(sensitive_regex_words)
    return book_data[book_data['NAME'].astype(str).str.lower().str.contains(sensitive_brands_regex, regex=True, na=False)]

def check_seller_approved_for_books(data, book_category_codes, approved_book_sellers):
    if 'CATEGORY_CODE' not in data.columns or 'SELLER_NAME' not in data.columns or not approved_book_sellers:
        return pd.DataFrame(columns=data.columns)
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    return book_data[~book_data['SELLER_NAME'].isin(approved_book_sellers)]

def check_perfume_price(data, perfumes_df, perfume_category_codes):
    required_cols = ['CATEGORY_CODE', 'NAME', 'BRAND', 'GLOBAL_SALE_PRICE', 'GLOBAL_PRICE']
    if not all(col in data.columns for col in required_cols) or perfumes_df.empty or not perfume_category_codes:
        return pd.DataFrame(columns=data.columns)
    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)]
    if perfume_data.empty:
        return pd.DataFrame(columns=data.columns)
    flagged_perfumes = []
    for _, row in perfume_data.iterrows():
        seller_price = row['GLOBAL_SALE_PRICE'] if pd.notna(row['GLOBAL_SALE_PRICE']) and row['GLOBAL_SALE_PRICE'] > 0 else row['GLOBAL_PRICE']
        if not pd.notna(seller_price) or seller_price <= 0:
            continue
        matched = perfumes_df[
            (perfumes_df['BRAND'].str.lower() == str(row['BRAND']).lower()) &
            (perfumes_df['PRODUCT_NAME'].str.lower().isin(str(row['NAME']).lower()) |
             perfumes_df['KEYWORD'].str.lower().isin(str(row['NAME']).lower()))
        ]
        if not matched.empty:
            price_diff = matched['PRICE'].iloc[0] - (seller_price / 129)
            if price_diff >= 30:
                flagged_perfumes.append(row)
    return pd.DataFrame(flagged_perfumes) if flagged_perfumes else pd.DataFrame(columns=data.columns)

def validate_products(data, config_data, book_category_codes, sensitive_brand_words, approved_book_sellers, perfume_category_codes, country, is_data_lake=False):
    valid_colors = config_data.get('valid_colors', [])
    validations = [
        ("Missing or Invalid COLOR", check_missing_color_data_lake if is_data_lake else check_missing_color, 
         {'book_category_codes': book_category_codes, 'valid_colors': valid_colors} if is_data_lake else {'book_category_codes': book_category_codes}),
        ("Multicolour Non-Watches", check_multicolour_non_watches, {}),
        ("Missing BRAND or NAME", check_missing_brand_or_name, {}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': book_category_codes}),
        ("Generic BRAND Issues", check_generic_brand_issues, {'valid_category_codes_fas': config_data.get('category_fas', pd.DataFrame())['ID'].astype(str).tolist() if not config_data.get('category_fas', pd.DataFrame()).empty else []}),
        ("BRAND in NAME", check_brand_in_name, {}),
        ("Duplicate Products", check_duplicate_products, {}),
        ("Sensitive Brand Issues", check_sensitive_brands, {'sensitive_brand_words': sensitive_brand_words, 'book_category_codes': book_category_codes}),
        ("Unapproved Book Sellers", check_seller_approved_for_books, {'book_category_codes': book_category_codes, 'approved_book_sellers': approved_book_sellers}),
        ("Perfume Price Issues", check_perfume_price, {'perfumes_df': config_data.get('perfumes', pd.DataFrame()), 'perfume_category_codes': perfume_category_codes}),
    ]
    if country == "Uganda":
        validations = [v for v in validations if v[0] not in ["Sensitive Brand Issues", "Unapproved Book Sellers", "Perfume Price Issues"]]
    
    flag_reason_comment = {
        "Missing or Invalid COLOR": ("1000005 - Missing or Invalid Color", "Add a valid color from the approved list or update color_family"),
        "Multicolour Non-Watches": ("1000006 - Invalid Color", "Multicolour not allowed for non-watch categories"),
        "Missing BRAND or NAME": ("1000001 - Missing Brand/Name", "Brand or Name field is empty"),
        "Single-word NAME": ("1000008 - Improve Name Description", "Update product title with format: Name – Type – Color"),
        "Generic BRAND Issues": ("1000001 - Brand NOT Allowed", "Use Fashion as brand for Fashion items"),
        "BRAND in NAME": ("1000002 - Brand Repeated in Name", "Do not include brand in product name"),
        "Duplicate Products": ("1000003 - Duplicate Product", "Product is a duplicate"),
        "Sensitive Brand Issues": ("1000023 - Counterfeit Product", "Contact vendor support for authorization"),
        "Unapproved Book Sellers": ("1000024 - Unapproved Seller", "Contact Jumia Seller Support for eligibility"),
        "Perfume Price Issues": ("1000029 - Verify Authenticity", "Contact Jumia Seller Support to verify product authenticity")
    }
    
    validation_results = {}
    for flag_name, check_func, kwargs in validations:
        try:
            result_df = check_func(data, **kwargs)
            validation_results[flag_name] = result_df
        except Exception as e:
            st.error(f"Error in validation '{flag_name}': {e}")
            validation_results[flag_name] = pd.DataFrame(columns=data.columns)
    
    final_report = []
    processed_sids = set()
    for flag_name, _, _ in validations:
        df = validation_results.get(flag_name, pd.DataFrame())
        if df.empty or 'PRODUCT_SET_SID' not in df.columns:
            continue
        reason, comment = flag_reason_comment.get(flag_name, ("Unknown", "No comment"))
        for _, row in df.iterrows():
            sid = row['PRODUCT_SET_SID']
            if sid not in processed_sids:
                processed_sids.add(sid)
                final_report.append({
                    'ProductSetSid': sid,
                    'ParentSKU': row.get('PARENTSKU', ''),
                    'Status': 'Rejected',
                    'Reason': reason,
                    'Comment': comment,
                    'FLAG': flag_name
                })
    
    approved_sids = set(data['PRODUCT_SET_SID']) - processed_sids
    for sid in approved_sids:
        row = data[data['PRODUCT_SET_SID'] == sid].iloc[0]
        final_report.append({
            'ProductSetSid': sid,
            'ParentSKU': row.get('PARENTSKU', ''),
            'Status': 'Approved',
            'Reason': '',
            'Comment': '',
            'FLAG': ''
        })
    
    return pd.DataFrame(final_report), validation_results

# Export functions
def to_excel_base(df, sheet_name, columns, writer):
    df_prepared = df.copy()
    for col in columns:
        if col not in df_prepared.columns:
            df_prepared[col] = pd.NA
    df_prepared[columns].to_excel(writer, index=False, sheet_name=sheet_name)

def to_excel_full_data(data_df, final_report_df):
    output = io.BytesIO()
    merged_df = pd.merge(
        data_df,
        final_report_df[['ProductSetSid', 'Status', 'Reason', 'Comment', 'FLAG']],
        left_on='PRODUCT_SET_SID',
        right_on='ProductSetSid',
        how='left'
    ).drop(columns=['ProductSetSid'], errors='ignore')
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(merged_df, "ProductSets", FULL_DATA_COLS, writer)
        workbook = writer.book
        worksheet = workbook.add_worksheet('Sellers Data')
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
        cell_format = workbook.add_format({'border': 1})
        number_format = workbook.add_format({'border': 1, 'align': 'right'})
        
        start_row = 0
        if 'SELLER_NAME' in merged_df.columns:
            seller_rejections = merged_df[merged_df['Status'] == 'Rejected'].groupby('SELLER_NAME').size().reset_index(name='Rejected Products')
            seller_rejections = seller_rejections.sort_values('Rejected Products', ascending=False)
            seller_rejections.insert(0, 'Rank', range(1, len(seller_rejections) + 1))
            worksheet.write(start_row, 0, 'Sellers Summary', header_format)
            start_row += 1
            for col_num, col_name in enumerate(['Rank', 'Seller', 'Rejected Products']):
                worksheet.write(start_row, col_num, col_name, header_format)
            for row_num, row_data in enumerate(seller_rejections.values, start=start_row + 1):
                for col_num, value in enumerate(row_data):
                    worksheet.write(row_num, col_num, value, number_format if col_num > 0 else cell_format)
            start_row += len(seller_rejections) + 2
        
        if 'CATEGORY' in merged_df.columns:
            category_rejections = merged_df[merged_df['Status'] == 'Rejected'].groupby('CATEGORY').size().reset_index(name='Rejected Products')
            category_rejections = category_rejections.sort_values('Rejected Products', ascending=False)
            category_rejections.insert(0, 'Rank', range(1, len(category_rejections) + 1))
            worksheet.write(start_row, 0, 'Categories Summary', header_format)
            start_row += 1
            for col_num, col_name in enumerate(['Rank', 'Category', 'Rejected Products']):
                worksheet.write(start_row, col_num, col_name, header_format)
            for row_num, row_data in enumerate(category_rejections.values, start=start_row + 1):
                for col_num, value in enumerate(row_data):
                    worksheet.write(row_num, col_num, value, number_format if col_num > 0 else cell_format)
            start_row += len(category_rejections) + 2
        
        if 'Reason' in merged_df.columns:
            reason_rejections = merged_df[merged_df['Status'] == 'Rejected'].groupby('Reason').size().reset_index(name='Rejected Products')
            reason_rejections = reason_rejections.sort_values('Rejected Products', ascending=False)
            reason_rejections.insert(0, 'Rank', range(1, len(reason_rejections) + 1))
            worksheet.write(start_row, 0, 'Rejection Reasons Summary', header_format)
            start_row += 1
            for col_num, col_name in enumerate(['Rank', 'Rejection Reason', 'Rejected Products']):
                worksheet.write(start_row, col_num, col_name, header_format)
            for row_num, row_data in enumerate(reason_rejections.values, start=start_row + 1):
                for col_num, value in enumerate(row_data):
                    worksheet.write(row_num, col_num, value, number_format if col_num > 0 else cell_format)
        
        worksheet.set_column('A:A', 30)
        worksheet.set_column('B:B', 10)
        worksheet.set_column('C:C', 20)
    output.seek(0)
    return output

def to_excel_flag_data(df, flag_name):
    output = io.BytesIO()
    df['FLAG'] = flag_name
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(df, "ProductSets", FULL_DATA_COLS, writer)
    output.seek(0)
    return output

def to_excel(report_df, reasons_df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(report_df, "ProductSets", PRODUCTSETS_COLS, writer)
        to_excel_base(reasons_df, "RejectionReasons", REJECTION_REASONS_COLS, writer)
    output.seek(0)
    return output

def get_download_link(data, filename, text):
    b64 = base64.b64encode(data.getvalue()).decode()
    return f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}">{text}</a>'

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
        if header_idx:
            data_rows = sellers_sheet.iloc[header_idx + 1:end, [0, 1, 2]].dropna(how='all')
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
        if header_idx:
            data_rows = sellers_sheet.iloc[header_idx + 1:end, [0, 1, 2]].dropna(how='all')
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
        if header_idx:
            data_rows = sellers_sheet.iloc[header_idx + 1:end, [0, 1, 2]].dropna(how='all')
            if not data_rows.empty:
                data_rows.columns = ['Rank', 'Rejection Reason', 'Rejected Products']
                data_rows['Date'] = date
                data_rows['Rejected Products'] = pd.to_numeric(data_rows['Rejected Products'], errors='coerce')
                all_reasons.append(data_rows)
    
    return (pd.concat(all_sellers, ignore_index=True) if all_sellers else pd.DataFrame(),
            pd.concat(all_categories, ignore_index=True) if all_categories else pd.DataFrame(),
            pd.concat(all_reasons, ignore_index=True) if all_reasons else pd.DataFrame())
