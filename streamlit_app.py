import streamlit as st
import pandas as pd
import io
import base64
import re
from datetime import datetime

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

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
    
    # Clean and split colors into individual components
    def clean_color(color):
        if pd.isna(color) or color == '':
            return []
        color = color.lower().strip()
        return [c.strip() for c in re.split(r'[/\s-]+', color) if c.strip()]
    
    non_book_data['COLOR_CLEAN'] = non_book_data['COLOR'].apply(clean_color)
    non_book_data['COLOR_FAMILY_CLEAN'] = non_book_data['COLOR_FAMILY'].apply(clean_color)
    
    # Check if any cleaned color matches valid_colors
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

# Initialize app
st.title("Product Validation Tool")

# Load configuration files
config_data = load_config_files()
book_category_codes = config_data.get('books_cat', pd.DataFrame())['CategoryCode'].astype(str).tolist() if not config_data.get('books_cat', pd.DataFrame()).empty else []
sensitive_brand_words = config_data.get('sensitive_brands', pd.DataFrame())['BrandWords'].astype(str).tolist() if not config_data.get('sensitive_brands', pd.DataFrame()).empty else []
approved_book_sellers = config_data.get('approved_sellers', pd.DataFrame())['SellerName'].astype(str).tolist() if not config_data.get('approved_sellers', pd.DataFrame()).empty else []
perfume_category_codes = config_data.get('perfume_cat', [])
reasons_df = config_data.get('reasons', pd.DataFrame())

# Debug: Show valid colors
st.write("Valid colors from colors.txt:", config_data.get('valid_colors', []))

# Tabs
tab1, tab2, tab3 = st.tabs(["Daily Validation", "Weekly Analysis", "Data Lake"])

# SKU overlap tracking
if 'daily_data' not in st.session_state:
    st.session_state['daily_data'] = None
if 'lake_data' not in st.session_state:
    st.session_state['lake_data'] = None

# Daily Validation Tab
with tab1:
    st.header("Daily Validation")
    country = st.selectbox("Select Country", ["Kenya", "Uganda"], key="daily_country")
    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"], key="daily_file")
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype={'PRODUCT_SET_SID': str, 'CATEGORY_CODE': str, 'PARENTSKU': str})
            st.session_state['daily_data'] = df
            required_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'CATEGORY_CODE', 'COLOR', 'SELLER_NAME', 'PARENTSKU']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                st.error(f"Missing columns: {', '.join(missing_cols)}")
            else:
                df = df[df['ACTIVE_STATUS_COUNTRY'] == country[:2]]
                if df.empty:
                    st.error(f"No data for {country}")
                else:
                    # Check SKU overlap
                    if st.session_state['lake_data'] is not None:
                        overlap = set(df['PRODUCT_SET_SID']).intersection(set(st.session_state['lake_data']['cod_productset_sid']))
                        if overlap:
                            st.warning(f"Found {len(overlap)} overlapping SKUs with Data Lake file.")
                    
                    final_report, validation_results = validate_products(df, config_data, book_category_codes, sensitive_brand_words, approved_book_sellers, perfume_category_codes, country)
                    approved_df = final_report[final_report['Status'] == 'Approved']
                    rejected_df = final_report[final_report['Status'] == 'Rejected']
                    
                    st.write(f"Total Products: {len(df)}")
                    st.write(f"Approved: {len(approved_df)}")
                    st.write(f"Rejected: {len(rejected_df)}")
                    
                    # Seller filtering
                    seller_options = ['All Sellers'] + list(df['SELLER_NAME'].dropna().unique())
                    selected_sellers = st.sidebar.multiselect("Select Sellers", seller_options, default=['All Sellers'], key="daily_sellers")
                    if 'All Sellers' not in selected_sellers:
                        filtered_df = df[df['SELLER_NAME'].isin(selected_sellers)]
                        filtered_report = final_report[final_report['ProductSetSid'].isin(filtered_df['PRODUCT_SET_SID'])]
                        seller_label = "_".join(s.replace(" ", "_") for s in selected_sellers)
                    else:
                        filtered_df = df
                        filtered_report = final_report
                        seller_label = "All_Sellers"
                    
                    # Downloads
                    file_prefix = country[:2]
                    current_date = datetime.now().strftime("%Y-%m-%d")
                    final_excel = to_excel(filtered_report, reasons_df)
                    rejected_excel = to_excel(filtered_report[filtered_report['Status'] == 'Rejected'], reasons_df)
                    approved_excel = to_excel(filtered_report[final_report['Status'] == 'Approved'], reasons_df)
                    full_excel = to_excel_full_data(filtered_df, filtered_report)
                    
                    st.markdown(get_download_link(final_excel, f"{file_prefix}_Final_Report_{current_date}_{seller_label}.xlsx", "Download Final Report"), unsafe_allow_html=True)
                    st.markdown(get_download_link(rejected_excel, f"{file_prefix}_Rejected_{current_date}_{seller_label}.xlsx", "Download Rejected Report"), unsafe_allow_html=True)
                    st.markdown(get_download_link(approved_excel, f"{file_prefix}_Approved_{current_date}_{seller_label}.xlsx", "Download Approved Report"), unsafe_allow_html=True)
                    st.markdown(get_download_link(full_excel, f"{file_prefix}_Full_Data_{current_date}_{seller_label}.xlsx", "Download Full Data"), unsafe_allow_html=True)
                    
                    for title, df_flagged in validation_results.items():
                        with st.expander(f"{title} ({len(df_flagged)} products)"):
                            st.dataframe(df_flagged)
                            flag_excel = to_excel_flag_data(df_flagged, title)
                            st.markdown(get_download_link(flag_excel, f"{file_prefix}_{title.replace(' ', '_')}_{current_date}.xlsx", f"Download {title} Data"), unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error processing CSV: {e}")

# Weekly Analysis Tab
with tab2:
    st.header("Weekly Analysis")
    uploaded_files = st.file_uploader("Upload Excel files", type=['xlsx'], accept_multiple_files=True, key="weekly_files")
    
    if uploaded_files:
        all_sellers, all_categories, all_reasons, dates = [], [], [], []
        for file in uploaded_files:
            date = extract_date_from_filename(file.name)
            if date:
                try:
                    sellers_sheet = pd.read_excel(file, sheet_name='Sellers Data', header=None)
                    sellers_df, categories_df, reasons_df = parse_sellers_data_sheet(sellers_sheet, date)
                    if not sellers_df.empty:
                        all_sellers.append(sellers_df)
                    if not categories_df.empty:
                        all_categories.append(categories_df)
                    if not reasons_df.empty:
                        all_reasons.append(reasons_df)
                    dates.append(date)
                except Exception as e:
                    st.error(f"Error reading {file.name}: {e}")
        
        if all_sellers or all_categories or all_reasons:
            st.success(f"Parsed {len(dates)} files: {sorted(set(dates))}")
            
            if all_sellers:
                weekly_sellers = pd.concat(all_sellers).groupby('Seller')['Rejected Products'].sum().reset_index()
                weekly_sellers = weekly_sellers.sort_values('Rejected Products', ascending=False).head(5)
                weekly_sellers['Percentage'] = (weekly_sellers['Rejected Products'] / weekly_sellers['Rejected Products'].sum() * 100).round(1)
                st.subheader("Top 5 Sellers by Rejected Products")
                st.dataframe(weekly_sellers)
                st.markdown("**Chart: Top 5 Sellers**")
                st.json({
                    "type": "bar",
                    "data": {
                        "labels": weekly_sellers['Seller'].tolist(),
                        "datasets": [{
                            "label": "Rejected Products",
                            "data": weekly_sellers['Rejected Products'].tolist(),
                            "backgroundColor": ["#4CAF50", "#2196F3", "#FFC107", "#F44336", "#9C27B0"],
                            "borderColor": ["#388E3C", "#1976D2", "#FFA000", "#D32F2F", "#7B1FA2"],
                            "borderWidth": 1
                        }]
                    },
                    "options": {
                        "scales": {
                            "y": {"beginAtZero": True, "title": {"display": True, "text": "Rejected Products"}},
                            "x": {"title": {"display": True, "text": "Seller"}}
                        }
                    }
                }, expanded=False)
            
            if all_categories:
                weekly_categories = pd.concat(all_categories).groupby('Category')['Rejected Products'].sum().reset_index()
                weekly_categories = weekly_categories.sort_values('Rejected Products', ascending=False).head(5)
                weekly_categories['Percentage'] = (weekly_categories['Rejected Products'] / weekly_categories['Rejected Products'].sum() * 100).round(1)
                st.subheader("Top 5 Categories by Rejected Products")
                st.dataframe(weekly_categories)
                st.markdown("**Chart: Top 5 Categories**")
                st.json({
                    "type": "bar",
                    "data": {
                        "labels": weekly_categories['Category'].tolist(),
                        "datasets": [{
                            "label": "Rejected Products",
                            "data": weekly_categories['Rejected Products'].tolist(),
                            "backgroundColor": ["#4CAF50", "#2196F3", "#FFC107", "#F44336", "#9C27B0"],
                            "borderColor": ["#388E3C", "#1976D2", "#FFA000", "#D32F2F", "#7B1FA2"],
                            "borderWidth": 1
                        }]
                    },
                    "options": {
                        "scales": {
                            "y": {"beginAtZero": True, "title": {"display": True, "text": "Rejected Products"}},
                            "x": {"title": {"display": True, "text": "Category"}}
                        }
                    }
                }, expanded=False)
            
            if all_reasons:
                weekly_reasons = pd.concat(all_reasons).groupby('Rejection Reason')['Rejected Products'].sum().reset_index()
                weekly_reasons = weekly_reasons.sort_values('Rejected Products', ascending=False).head(5)
                weekly_reasons['Percentage'] = (weekly_reasons['Rejected Products'] / weekly_reasons['Rejected Products'].sum() * 100).round(1)
                st.subheader("Top 5 Rejection Reasons")
                st.dataframe(weekly_reasons)
                st.markdown("**Chart: Top 5 Rejection Reasons**")
                st.json({
                    "type": "bar",
                    "data": {
                        "labels": weekly_reasons['Rejection Reason'].tolist(),
                        "datasets": [{
                            "label": "Rejected Products",
                            "data": weekly_reasons['Rejected Products'].tolist(),
                            "backgroundColor": ["#4CAF50", "#2196F3", "#FFC107", "#F44336", "#9C27B0"],
                            "borderColor": ["#388E3C", "#1976D2", "#FFA000", "#D32F2F", "#7B1FA2"],
                            "borderWidth": 1
                        }]
                    },
                    "options": {
                        "scales": {
                            "y": {"beginAtZero": True, "title": {"display": True, "text": "Rejected Products"}},
                            "x": {"title": {"display": True, "text": "Rejection Reason"}}
                        }
                    }
                }, expanded=False)
            
            if len(set(dates)) > 1 and all_sellers:
                daily_trend = pd.concat(all_sellers).groupby('Date')['Rejected Products'].sum().reset_index()
                st.subheader("Daily Rejection Trend")
                st.json({
                    "type": "line",
                    "data": {
                        "labels": daily_trend['Date'].astype(str).tolist(),
                        "datasets": [{
                            "label": "Rejected Products",
                            "data": daily_trend['Rejected Products'].tolist(),
                            "fill": False,
                            "borderColor": "#2196F3",
                            "tension": 0.1
                        }]
                    },
                    "options": {
                        "scales": {
                            "y": {"beginAtZero": True, "title": {"display": True, "text": "Rejected Products"}},
                            "x": {"title": {"display": True, "text": "Date"}}
                        }
                    }
                }, expanded=False)
            
            st.subheader("Deep Analysis")
            total_rejections = pd.concat(all_sellers)['Rejected Products'].sum() if all_sellers else 0
            if total_rejections:
                avg_daily_rej = total_rejections / len(set(dates))
                st.metric("Total Weekly Rejections", total_rejections)
                st.metric("Average Daily Rejections", f"{avg_daily_rej:.1f}")
                if not weekly_sellers.empty:
                    st.info(f"Top seller '{weekly_sellers.iloc[0]['Seller']}' accounts for {weekly_sellers.iloc[0]['Percentage']}% of rejections.")
                if not weekly_categories.empty:
                    st.info(f"Top category '{weekly_categories.iloc[0]['Category']}' has {weekly_categories.iloc[0]['Percentage']}% of rejections.")
                if not weekly_reasons.empty:
                    st.info(f"Top reason '{weekly_reasons.iloc[0]['Rejection Reason']}' drives {weekly_reasons.iloc[0]['Percentage']}% of issues.")
            
            st.subheader("Recommendations")
            recs = []
            if not weekly_sellers.empty:
                recs.append(f"Train top sellers ({', '.join(weekly_sellers.head(3)['Seller'])}) on listing practices.")
            if not weekly_categories.empty:
                recs.append(f"Create guidelines for categories ({', '.join(weekly_categories.head(3)['Category'])}).")
            if not weekly_reasons.empty:
                recs.append(f"Automate checks for '{weekly_reasons.iloc[0]['Rejection Reason']}'.")
            if total_rejections > 0 and avg_daily_rej > 50:
                recs.append("High rejection rate (>50/day); conduct platform audit.")
            else:
                recs.append("Rejections stable; focus on seller support.")
            for rec in recs:
                st.write(f"• {rec}")
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                if not weekly_sellers.empty:
                    weekly_sellers.to_excel(writer, sheet_name='Top Sellers', index=False)
                if not weekly_categories.empty:
                    weekly_categories.to_excel(writer, sheet_name='Top Categories', index=False)
                if not weekly_reasons.empty:
                    weekly_reasons.to_excel(writer, sheet_name='Top Reasons', index=False)
            output.seek(0)
            st.download_button(
                label="Download Weekly Report",
                data=output,
                file_name=f"Weekly_Analysis_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# Data Lake Tab
with tab3:
    st.header("Data Lake")
    country = st.selectbox("Select Country", ["All Countries", "Kenya", "Uganda"], index=1, key="data_lake_country")  # Default to Kenya
    uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx"], key="data_lake_file")
    
    if uploaded_file:
        try:
            raw_data = pd.read_excel(uploaded_file, sheet_name="Sheet1")
            st.session_state['lake_data'] = raw_data
            st.write("Unique countries:", raw_data['dsc_shop_active_country'].dropna().unique().tolist())
            
            column_mapping = {
                'image1': 'MAIN_IMAGE',
                'cod_category_code': 'CATEGORY_CODE',
                'dsc_shop_tax_class': 'TAX_CLASS',
                'dsc_shop_active_country': 'ACTIVE_STATUS_COUNTRY',
                'cod_productset_sid': 'PRODUCT_SET_SID',
                'cod_parent_sku': 'PARENTSKU',
                'dsc_shop_seller_name': 'SELLER_NAME',
                'dsc_brand_name': 'BRAND',
                'dsc_name': 'NAME',
                'dsc_category_name': 'CATEGORY',
                'color': 'COLOR',
                'color_family': 'COLOR_FAMILY',
                'list_variations': 'VARIATION',
                'list_seller_skus': 'SELLER_SKU'
            }
            df = raw_data.rename(columns=column_mapping)
            df['COLOR'] = df['COLOR'].astype(str).replace('nan', '')
            df['COLOR_FAMILY'] = df['COLOR_FAMILY'].astype(str).replace('nan', '')
            
            required_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'CATEGORY_CODE', 'COLOR', 'COLOR_FAMILY', 'SELLER_NAME', 'PARENTSKU']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                st.error(f"Missing columns: {', '.join(missing_cols)}")
            else:
                if country != "All Countries":
                    country_code = COUNTRY_MAPPING[country]
                    df = df[df['ACTIVE_STATUS_COUNTRY'] == country_code]
                    if df.empty:
                        st.error(f"No data for {country} ({country_code})")
                        st.stop()
                
                # Check SKU overlap
                if st.session_state['daily_data'] is not None:
                    overlap = set(df['PRODUCT_SET_SID']).intersection(set(st.session_state['daily_data']['PRODUCT_SET_SID']))
                    if overlap:
                        st.warning(f"Found {len(overlap)} overlapping SKUs with Daily Validation file.")
                
                final_report, validation_results = validate_products(df, config_data, book_category_codes, sensitive_brand_words, approved_book_sellers, perfume_category_codes, country, is_data_lake=True)
                approved_df = final_report[final_report['Status'] == 'Approved']
                rejected_df = final_report[final_report['Status'] == 'Rejected']
                
                st.write(f"Total Products: {len(df)}")
                st.write(f"Approved: {len(approved_df)}")
                st.write(f"Rejected: {len(rejected_df)}")
                
                # Seller filtering
                seller_options = ['All Sellers'] + list(df['SELLER_NAME'].dropna().unique())
                selected_sellers = st.sidebar.multiselect("Select Sellers", seller_options, default=['All Sellers'], key="lake_sellers")
                if 'All Sellers' not in selected_sellers:
                    filtered_df = df[df['SELLER_NAME'].isin(selected_sellers)]
                    filtered_report = final_report[final_report['ProductSetSid'].isin(filtered_df['PRODUCT_SET_SID'])]
                    seller_label = "_".join(s.replace(" ", "_") for s in selected_sellers)
                else:
                    filtered_df = df
                    filtered_report = final_report
                    seller_label = "All_Sellers"
                
                # Downloads
                file_prefix = country[:2] if country != "All Countries" else "ALL"
                current_date = datetime.now().strftime("%Y-%m-%d")
                final_excel = to_excel(filtered_report, reasons_df)
                rejected_excel = to_excel(filtered_report[filtered_report['Status'] == 'Rejected'], reasons_df)
                approved_excel = to_excel(filtered_report[final_report['Status'] == 'Approved'], reasons_df)
                full_excel = to_excel_full_data(filtered_df, filtered_report)
                
                st.markdown(get_download_link(final_excel, f"{file_prefix}_Final_Report_{current_date}_{seller_label}.xlsx", "Download Final Report"), unsafe_allow_html=True)
                st.markdown(get_download_link(rejected_excel, f"{file_prefix}_Rejected_{current_date}_{seller_label}.xlsx", "Download Rejected Report"), unsafe_allow_html=True)
                st.markdown(get_download_link(approved_excel, f"{file_prefix}_Approved_{current_date}_{seller_label}.xlsx", "Download Approved Report"), unsafe_allow_html=True)
                st.markdown(get_download_link(full_excel, f"{file_prefix}_Full_Data_{current_date}_{seller_label}.xlsx", "Download Full Data"), unsafe_allow_html=True)
                
                for title, df_flagged in validation_results.items():
                    with st.expander(f"{title} ({len(df_flagged)} products)"):
                        st.dataframe(df_flagged)
                        flag_excel = to_excel_flag_data(df_flagged, title)
                        st.markdown(get_download_link(flag_excel, f"{file_prefix}_{title.replace(' ', '_')}_{current_date}.xlsx", f"Download {title} Data"), unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error processing Excel: {e}")
