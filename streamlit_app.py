import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import os

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# --- Constants for column names ---
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG"]
REJECTION_REASONS_COLS = ['CODE - REJECTION_REASON', 'COMMENT']
FULL_DATA_COLS = ["PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE", "COLOR", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU", "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG"]

# Country mapping for Data Lake tab
COUNTRY_MAPPING = {
    "Kenya": "jumia-ke",
    "Uganda": "jumia-ug",
    "All Countries": None  # None indicates no filtering
}

# Function to extract date from filename
def extract_date_from_filename(filename):
    pattern = r'(\d{4}-\d{2}-\d{2})'
    match = re.search(pattern, filename)
    if match:
        return pd.to_datetime(match.group(1))
    return None

# Function to load blacklisted words from a file
def load_blacklisted_words():
    try:
        with open('blacklisted.txt', 'r') as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        st.error("blacklisted.txt file not found!")
        return []
    except Exception as e:
        st.error(f"Error loading blacklisted words: {e}")
        return []

# Function to load book category codes from file
def load_book_category_codes():
    try:
        book_cat_df = pd.read_excel('Books_cat.xlsx')
        return book_cat_df['CategoryCode'].astype(str).tolist()
    except FileNotFoundError:
        st.warning("Books_cat.xlsx file not found! Book category exemptions will not be applied.")
        return []
    except Exception as e:
        st.error(f"Error loading Books_cat.xlsx: {e}")
        return []

# Function to load sensitive brand words from Excel file
def load_sensitive_brand_words():
    try:
        sensitive_brands_df = pd.read_excel('sensitive_brands.xlsx')
        return sensitive_brands_df['BrandWords'].astype(str).tolist()
    except FileNotFoundError:
        st.warning("sensitive_brands.xlsx file not found! Sensitive brand check will not be applied.")
        return []
    except Exception as e:
        st.error(f"Error loading sensitive_brands.xlsx: {e}")
        return []

# Function to load approved book sellers from Excel file
def load_approved_book_sellers():
    try:
        approved_sellers_df = pd.read_excel('Books_Approved_Sellers.xlsx')
        return approved_sellers_df['SellerName'].astype(str).tolist()
    except FileNotFoundError:
        st.warning("Books_Approved_Sellers.xlsx file not found! Book seller approval check will not be applied.")
        return []
    except Exception as e:
        st.error(f"Error loading Books_Approved_Sellers.xlsx: {e}")
        return []

# Function to load perfume category codes from file
def load_perfume_category_codes():
    try:
        with open('Perfume_cat.txt', 'r') as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        st.warning("Perfume_cat.txt file not found! Perfume price check will not be applied.")
        return []
    except Exception as e:
        st.error(f"Error loading Perfume_cat.txt: {e}")
        return []

# Function to load configuration files
def load_config_files():
    config_files = {
        'check_variation': 'check_variation.xlsx',
        'category_fas': 'category_FAS.xlsx',
        'perfumes': 'perfumes.xlsx',
        'reasons': 'reasons.xlsx'
    }
    data = {}
    for key, filename in config_files.items():
        try:
            df = pd.read_excel(filename).rename(columns=lambda x: x.strip())
            data[key] = df
        except FileNotFoundError:
            st.warning(f"{filename} file not found, functionality related to this file will be limited.")
            data[key] = pd.DataFrame()
        except Exception as e:
            st.error(f"Error loading {filename}: {e}")
            data[key] = pd.DataFrame()
    return data

# Validation check functions
def check_missing_color(data, book_category_codes):
    if 'CATEGORY_CODE' not in data.columns or 'COLOR' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    missing_color_non_books = non_book_data[non_book_data['COLOR'].isna() | (non_book_data['COLOR'] == '')]
    return missing_color_non_books

def check_missing_brand_or_name(data):
    if 'BRAND' not in data.columns or 'NAME' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    return data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]

def check_single_word_name(data, book_category_codes):
    if 'CATEGORY_CODE' not in data.columns or 'NAME' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    flagged_non_book_single_word_names = non_book_data[
        non_book_data['NAME'].astype(str).str.split().str.len() == 1
    ]
    return flagged_non_book_single_word_names

def check_generic_brand_issues(data, valid_category_codes_fas):
    if 'CATEGORY_CODE' not in data.columns or 'BRAND' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    if not valid_category_codes_fas:
        return pd.DataFrame(columns=data.columns)
    return data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]

def check_brand_in_name(data):
    if 'BRAND' not in data.columns or 'NAME' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    return data[data.apply(lambda row:
        isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and
        row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

def check_duplicate_products(data):
    subset_cols = [col for col in ['NAME', 'BRAND', 'SELLER_NAME', 'COLOR'] if col in data.columns]
    if len(subset_cols) < 4:
        return pd.DataFrame(columns=data.columns)
    return data[data.duplicated(subset=subset_cols, keep=False)]

def check_sensitive_brands(data, sensitive_brand_words, book_category_codes):
    if 'CATEGORY_CODE' not in data.columns or 'NAME' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if not sensitive_brand_words or book_data.empty:
        return pd.DataFrame(columns=data.columns)

    sensitive_regex_words = [r'\b' + re.escape(word.lower()) + r'\b' for word in sensitive_brand_words]
    sensitive_brands_regex = '|'.join(sensitive_regex_words)

    mask_name = book_data['NAME'].astype(str).str.lower().str.contains(sensitive_brands_regex, regex=True, na=False)
    return book_data[mask_name]

def check_seller_approved_for_books(data, book_category_codes, approved_book_sellers):
    if 'CATEGORY_CODE' not in data.columns or 'SELLER_NAME' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if book_data.empty or not approved_book_sellers:
        return pd.DataFrame(columns=data.columns)
    unapproved_book_sellers_mask = ~book_data['SELLER_NAME'].isin(approved_book_sellers)
    return book_data[unapproved_book_sellers_mask]

def check_perfume_price(data, perfumes_df, perfume_category_codes):
    required_cols = ['CATEGORY_CODE', 'NAME', 'BRAND', 'GLOBAL_SALE_PRICE', 'GLOBAL_PRICE']
    if not all(col in data.columns for col in required_cols) or \
       perfumes_df.empty or not perfume_category_codes or \
       not all(col in perfumes_df.columns for col in ['BRAND', 'PRODUCT_NAME', 'KEYWORD', 'PRICE']):
        return pd.DataFrame(columns=data.columns)

    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)]
    if perfume_data.empty:
        return pd.DataFrame(columns=data.columns)

    flagged_perfumes_list = []
    for index, row in perfume_data.iterrows():
        seller_product_name = str(row['NAME']).strip().lower()
        seller_brand_name = str(row['BRAND']).strip().lower()
        seller_price = row['GLOBAL_SALE_PRICE'] if pd.notna(row['GLOBAL_SALE_PRICE']) and row['GLOBAL_SALE_PRICE'] > 0 else row['GLOBAL_PRICE']

        if not pd.notna(seller_price) or seller_price <= 0:
            continue

        matched_perfume_row = None
        for _, perfume_row in perfumes_df.iterrows():
            ref_brand = str(perfume_row['BRAND']).strip().lower()
            ref_product_name = str(perfume_row['PRODUCT_NAME']).strip().lower()
            if seller_brand_name == ref_brand and ref_product_name in seller_product_name:
                matched_perfume_row = perfume_row
                break
        if matched_perfume_row is None:
            for _, perfume_row in perfumes_df.iterrows():
                ref_brand = str(perfume_row['BRAND']).strip().lower()
                ref_keyword = str(perfume_row['KEYWORD']).strip().lower()
                ref_product_name = str(perfume_row['PRODUCT_NAME']).strip().lower()
                if seller_brand_name == ref_brand and (ref_keyword in seller_product_name or ref_product_name in seller_product_name):
                    matched_perfume_row = perfume_row
                    break
        if matched_perfume_row is not None:
            reference_price_dollar = matched_perfume_row['PRICE']
            price_difference = reference_price_dollar - (seller_price / 129)
            if price_difference >= 30:
                flagged_perfumes_list.append(row.to_dict())

    if flagged_perfumes_list:
        return pd.DataFrame(flagged_perfumes_list)
    return pd.DataFrame(columns=data.columns)

def validate_products(data, config_data, blacklisted_words, reasons_dict, book_category_codes, sensitive_brand_words, approved_book_sellers, perfume_category_codes, country):
    validations = [
        ("Sensitive Brand Issues", check_sensitive_brands, {'sensitive_brand_words': sensitive_brand_words, 'book_category_codes': book_category_codes}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': book_category_codes, 'approved_book_sellers': approved_book_sellers}),
        ("Perfume Price Check", check_perfume_price, {'perfumes_df': config_data.get('perfumes', pd.DataFrame()), 'perfume_category_codes': perfume_category_codes}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': book_category_codes}),
        ("Missing BRAND or NAME", check_missing_brand_or_name, {}),
        ("Generic BRAND Issues", check_generic_brand_issues, {}),
        ("Missing COLOR", check_missing_color, {'book_category_codes': book_category_codes}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Duplicate product", check_duplicate_products, {}),
    ]

    if country == "Uganda":
        validations_to_skip = ["Sensitive Brand Issues", "Seller Approve to sell books", "Perfume Price Check"]
        validations = [v for v in validations if v[0] not in validations_to_skip]

    flag_reason_comment_mapping = {
        "Sensitive Brand Issues": ("1000023 - Confirmation of counterfeit product by Jumia technical team (Not Authorized)", "Please contact vendor support for sale of..."),
        "Seller Approve to sell books": ("1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim", "Please contact Jumia Seller Support and raise a claim to confirm whether this product is eligible for listing.
This step will help ensure that all necessary requirements and approvals are addressed before proceeding with the sale, and prevent any future compliance issues."),
        "Perfume Price Check": ("1000029 - Kindly Contact Jumia Seller Support To Verify This Product's Authenticity By Raising A Claim", "Please contact Jumia Seller Support to raise a claim and verify the authenticity of this product."),
        "Single-word NAME": ("1000008 - Kindly Improve Product Name Description", "Kindly update the product title using this format: Name – Type of the Products – Color.
If available, please also add key details such as weight, capacity, type, and warranty to make the title clear and complete for customers."),
        "Missing BRAND or NAME": ("1000001 - Brand NOT Allowed", "Brand NOT Allowed"),
        "Generic BRAND Issues": ("1000001 - Brand NOT Allowed", "Please use Fashion as brand for Fashion items- Kindly request for the creation of this product's actual brand name by filling this form: https://bit.ly/2kpjja8"),
        "Missing COLOR": ("1000005 - Kindly confirm the actual product colour", "Kindly add color on the color field"),
        "BRAND name repeated in NAME": ("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", "Please do not write the brand name in the Product Name field. The brand name should only be written in the Brand field.
If you include it in both fields, it will show up twice in the product title on the website"),
        "Duplicate product": ("Duplicate products", "kindly note product was rejected because its a duplicate product"),
    }

    validation_results_dfs = {}
    for flag_name, check_func, func_kwargs in validations:
        current_kwargs = {'data': data}
        if flag_name == "Generic BRAND Issues":
            category_fas_df = config_data.get('category_fas', pd.DataFrame())
            if not category_fas_df.empty and 'ID' in category_fas_df.columns:
                current_kwargs['valid_category_codes_fas'] = category_fas_df['ID'].astype(str).tolist()
            else:
                current_kwargs['valid_category_codes_fas'] = []
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
                'FLAG': flag_name
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
            'FLAG': ""
        })

    final_report_df = pd.DataFrame(final_report_rows)
    return final_report_df, validation_results_dfs

# --- Export functions ---
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
            final_report_df_copy[["ProductSetSid", "Status", "Reason", "Comment", "FLAG"]],
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
            # Write ProductSets sheet
            to_excel_base(merged_df, "ProductSets", FULL_DATA_COLS, writer)

            # Get workbook and worksheet for Sellers Data
            workbook = writer.book
            worksheet = workbook.add_worksheet('Sellers Data')
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#D3D3D3',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True
            })
            cell_format = workbook.add_format({
                'border': 1,
                'align': 'left',
                'valign': 'vcenter'
            })
            number_format = workbook.add_format({
                'border': 1,
                'align': 'right',
                'valign': 'vcenter'
            })
            high_rejection_format = workbook.add_format({
                'bg_color': '#FF9999',
                'border': 1,
                'align': 'right',
                'valign': 'vcenter'
            })

            # Sellers Data sheet
            sellers_data_rows = []
            start_row = 0

            # Sellers Summary
            try:
                if 'SELLER_NAME' in merged_df.columns and not merged_df['SELLER_NAME'].isna().all():
                    seller_rejections = (merged_df[merged_df['Status'] == 'Rejected']
                                        .groupby('SELLER_NAME')
                                        .size()
                                        .reset_index(name='Rejected Products'))
                    seller_rejections = seller_rejections.sort_values('Rejected Products', ascending=False)
                    seller_rejections.insert(0, 'Rank', range(1, len(seller_rejections) + 1))
                    sellers_data_rows.append(pd.DataFrame([['', '', '']]))
                    sellers_data_rows.append(pd.DataFrame([['Sellers Summary', '', '']]))
                    sellers_data_rows.append(seller_rejections.rename(
                        columns={'SELLER_NAME': 'Seller', 'Rejected Products': 'Number of Rejected Products'}))
                else:
                    sellers_data_rows.append(pd.DataFrame([['Sellers Summary', 'No valid SELLER_NAME data available', '']]))
            except Exception as e:
                sellers_data_rows.append(pd.DataFrame([['Sellers Summary', f'Error: {str(e)}', '']]))

            # Categories Summary
            try:
                if 'CATEGORY' in merged_df.columns and not merged_df['CATEGORY'].isna().all():
                    category_rejections = (merged_df[merged_df['Status'] == 'Rejected']
                                         .groupby('CATEGORY')
                                         .size()
                                         .reset_index(name='Rejected Products'))
                    category_rejections = category_rejections.sort_values('Rejected Products', ascending=False)
                    category_rejections.insert(0, 'Rank', range(1, len(category_rejections) + 1))
                    sellers_data_rows.append(pd.DataFrame([['', '', '']]))
                    sellers_data_rows.append(pd.DataFrame([['Categories Summary', '', '']]))
                    sellers_data_rows.append(category_rejections.rename(
                        columns={'CATEGORY': 'Category', 'Rejected Products': 'Number of Rejected Products'}))
                else:
                    sellers_data_rows.append(pd.DataFrame([['Categories Summary', 'No valid CATEGORY data available', '']]))
            except Exception as e:
                sellers_data_rows.append(pd.DataFrame([['Categories Summary', f'Error: {str(e)}', '']]))

            # Rejection Reasons Summary
            try:
                if 'Reason' in merged_df.columns and not merged_df['Reason'].isna().all():
                    reason_rejections = (merged_df[merged_df['Status'] == 'Rejected']
                                        .groupby('Reason')
                                        .size()
                                        .reset_index(name='Rejected Products'))
                    reason_rejections = reason_rejections.sort_values('Rejected Products', ascending=False)
                    reason_rejections.insert(0, 'Rank', range(1, len(reason_rejections) + 1))
                    sellers_data_rows.append(pd.DataFrame([['', '', '']]))
                    sellers_data_rows.append(pd.DataFrame([['Rejection Reasons Summary', '', '']]))
                    sellers_data_rows.append(reason_rejections.rename(
                        columns={'Reason': 'Rejection Reason', 'Rejected Products': 'Number of Rejected Products'}))
                else:
                    sellers_data_rows.append(pd.DataFrame([['Rejection Reasons Summary', 'No valid Reason data available', '']]))
            except Exception as e:
                sellers_data_rows.append(pd.DataFrame([['Rejection Reasons Summary', f'Error: {str(e)}', '']]))

            # Write Sellers Data sheet with formatting
            for df in sellers_data_rows:
                if df.empty or len(df.columns) < 2:
                    continue
                if 'Rank' in df.columns:
                    for col_num, col_name in enumerate(df.columns):
                        worksheet.write(start_row, col_num, col_name, header_format)
                    for row_num, row_data in enumerate(df.values, start=start_row + 1):
                        for col_num, value in enumerate(row_data):
                            format_to_use = number_format if col_num > 0 else cell_format
                            if col_num == 2 and isinstance(value, (int, float)) and value > 10:
                                format_to_use = high_rejection_format
                            worksheet.write(row_num, col_num, value, format_to_use)
                else:
                    worksheet.write(start_row, 0, df.iloc[0, 0], header_format)
                    if len(df.columns) > 1 and pd.notna(df.iloc[0, 1]):
                        worksheet.write(start_row, 1, df.iloc[0, 1], cell_format)
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

def to_excel_seller_data(seller_data_df, seller_final_report_df):
    return to_excel_full_data(seller_data_df, seller_final_report_df)

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

# Function to parse summary tables from Sellers Data sheet
def parse_sellers_data_sheet(sellers_sheet, date):
    # sellers_sheet is pd.read_excel(..., header=None)
    all_sellers = []
    all_categories = []
    all_reasons = []
    
    # Find section headers
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
    
    # Parse Sellers
    if 'sellers' in section_starts:
        start = section_starts['sellers']
        end = section_starts.get('categories', len(sellers_sheet))
        # Find header row with 'Rank'
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
    
    # Parse Categories
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
    
    # Parse Reasons
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

# --- Initialize the app ---
st.title("Product Validation Tool")

# --- Load configuration files (global) ---
config_data = load_config_files()
blacklisted_words = load_blacklisted_words()
book_category_codes = load_book_category_codes()
sensitive_brand_words = load_sensitive_brand_words()
approved_book_sellers = load_approved_book_sellers()
perfume_category_codes = load_perfume_category_codes()

reasons_df_from_config = config_data.get('reasons', pd.DataFrame())
reasons_dict_legacy = {}
if not reasons_df_from_config.empty:
    for _, row in reasons_df_from_config.iterrows():
        reason_text = row.get('CODE - REJECTION_REASON', "")
        comment = row.get('COMMENT', "") if pd.notna(row.get('COMMENT')) else ""
        if isinstance(reason_text, str) and ' - ' in reason_text:
            code, message = reason_text.split(' - ', 1)
            reasons_dict_legacy[f"{code} - {message}"] = (code, message, comment)
        elif isinstance(reason_text, str):
            reasons_dict_legacy[reason_text] = (reason_text, reason_text, comment)

# --- Tabs ---
tab1, tab2, tab3 = st.tabs(["Daily Validation", "Weekly Analysis", "Data Lake"])

with tab1:
    country = st.selectbox("Select Country", ["Kenya", "Uganda"], key="daily_country")
    uploaded_file = st.file_uploader("Upload your CSV file", type='csv', key="daily_file")

    if uploaded_file is not None:
        current_date = datetime.now().strftime("%Y-%m-%d")
        file_prefix = "KE" if country == "Kenya" else "UG"
        process_success = False
        try:
            dtype_spec = {
                'CATEGORY_CODE': str,
                'PRODUCT_SET_SID': str,
                'PARENTSKU': str,
            }
            raw_data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype=dtype_spec)
            st.write(f"Loaded CSV with {len(raw_data)} rows.")
            
            essential_input_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'COLOR', 'SELLER_NAME', 'GLOBAL_PRICE', 'GLOBAL_SALE_PRICE', 'PARENTSKU']
            data = raw_data.copy()
            for col in essential_input_cols:
                if col not in data.columns:
                    data[col] = pd.NA

            for col in ['NAME', 'BRAND', 'COLOR', 'SELLER_NAME', 'CATEGORY_CODE', 'PARENTSKU']:
                if col in data.columns:
                    data[col] = data[col].astype(str).fillna('')

            if data.empty:
                st.error("The uploaded CSV file is empty or became empty after initial processing. Please verify the file contains data and uses the correct format (semicolon-separated, with required columns).")
                st.stop()

            st.write(f"Processed {len(data)} products after cleaning.")

            final_report_df, individual_flag_dfs = validate_products(
                data, config_data, blacklisted_words, reasons_dict_legacy,
                book_category_codes, sensitive_brand_words,
                approved_book_sellers, perfume_category_codes, country
            )
            process_success = True

            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

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
                    if 'All Sellers' not in selected_sellers and selected_sellers and seller in selected_sellers:
                        rej_count = current_seller_data[current_seller_data['Status'] == 'Rejected']['ParentSKU'].count()
                        app_count = current_seller_data[current_seller_data['Status'] == 'Approved']['ParentSKU'].count()
                        st.sidebar.write(f"{seller}: **Rej**: {rej_count}, **App**: {app_count}")
                    elif 'All Sellers' in selected_sellers:
                        rej_count = current_seller_data[current_seller_data['Status'] == 'Rejected']['ParentSKU'].count()
                        app_count = current_seller_data[current_seller_data['Status'] == 'Approved']['ParentSKU'].count()
                        st.sidebar.write(f"{seller}: **Rej**: {rej_count}, **App**: {app_count}")
            else:
                st.sidebar.write("Seller metrics unavailable (SELLER_NAME missing or no products).")

            st.sidebar.subheader(f"Exports for: {seller_label_filename.replace('_', ' ')}")
            seller_final_excel = to_excel(seller_final_report_df_filtered, reasons_df_from_config)
            st.sidebar.download_button(
                label="Seller Final Export",
                data=seller_final_excel,
                file_name=f"{file_prefix}_Final_Report_{current_date}_{seller_label_filename}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="daily_final_export"
            )
            
            seller_rejected_excel = to_excel(seller_rejected_df_filtered, reasons_df_from_config)
            st.sidebar.download_button(
                label="Seller Rejected Export",
                data=seller_rejected_excel,
                file_name=f"{file_prefix}_Rejected_Products_{current_date}_{seller_label_filename}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="daily_rejected_export"
            )

            seller_approved_excel = to_excel(seller_approved_df_filtered, reasons_df_from_config)
            st.sidebar.download_button(
                label="Seller Approved Export",
                data=seller_approved_excel,
                file_name=f"{file_prefix}_Approved_Products_{current_date}_{seller_label_filename}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="daily_approved_export"
            )

            seller_full_excel = to_excel_seller_data(seller_data_filtered, seller_final_report_df_filtered)
            st.sidebar.download_button(
                label="Seller Full Data Export",
                data=seller_full_excel,
                file_name=f"{file_prefix}_Seller_Data_Export_{current_date}_{seller_label_filename}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="daily_full_export"
            )

            st.header("Overall Product Validation Results")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Products in Upload", len(data))
                st.metric("Approved Products (Overall)", len(approved_df))
            with col2:
                st.metric("Rejected Products (Overall)", len(rejected_df))
                rejection_rate = (len(rejected_df)/len(data)*100) if len(data) > 0 else 0
                st.metric("Rejection Rate (Overall)", f"{rejection_rate:.1f}%")

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

            st.header("Overall Data Exports (All Sellers)")
            col1_main, col2_main, col3_main, col4_main = st.columns(4)
            with col1_main:
                overall_final_excel = to_excel(final_report_df, reasons_df_from_config)
                st.download_button(
                    label="Final Export (All)",
                    data=overall_final_excel,
                    file_name=f"{file_prefix}_Final_Report_{current_date}_ALL.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="daily_overall_final"
                )
            with col2_main:
                overall_rejected_excel = to_excel(rejected_df, reasons_df_from_config)
                st.download_button(
                    label="Rejected Export (All)",
                    data=overall_rejected_excel,
                    file_name=f"{file_prefix}_Rejected_Products_{current_date}_ALL.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="daily_overall_rejected"
                )
            with col3_main:
                overall_approved_excel = to_excel(approved_df, reasons_df_from_config)
                st.download_button(
                    label="Approved Export (All)",
                    data=overall_approved_excel,
                    file_name=f"{file_prefix}_Approved_Products_{current_date}_ALL.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="daily_overall_approved"
                )
            with col4_main:
                overall_full_excel = to_excel_full_data(data.copy(), final_report_df)
                st.download_button(
                    label="Full Data Export (All)",
                    data=overall_full_excel,
                    file_name=f"{file_prefix}_Full_Data_Export_{current_date}_ALL.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="daily_overall_full"
                )

        except pd.errors.ParserError as pe:
            process_success = False
            st.error(f"Error parsing the CSV file. Please ensure it's a valid CSV with ';' delimiter and UTF-8 or ISO-8859-1 encoding: {pe}")
        except Exception as e:
            process_success = False
            st.error(f"An unexpected error occurred processing the file: {e}")
            import traceback
            st.error(f"Traceback: {traceback.format_exc()}")

        if not process_success and uploaded_file is not None:
            st.error("File processing failed. Please check the file format, content, console logs (if running locally), and error messages above, then try again.")

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
                # Read Sellers Data sheet with no header to parse manually
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
            st.success(f"Parsed data from {len(dates)} files, covering dates: {sorted(set(dates))}")
            
            # Aggregate Sellers
            if all_sellers_dfs:
                aggregated_sellers = pd.concat(all_sellers_dfs, ignore_index=True)
                weekly_sellers = aggregated_sellers.groupby('Seller')['Rejected Products'].sum().reset_index()
                weekly_sellers = weekly_sellers.sort_values('Rejected Products', ascending=False).head(5)
                weekly_sellers['Percentage'] = (weekly_sellers['Rejected Products'] / weekly_sellers['Rejected Products'].sum() * 100).round(1)
                st.subheader("Top 5 Sellers by Rejected Products (Weekly)")
                st.dataframe(weekly_sellers)
                
                # Create chart
                chart_data = {
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
                            "y": {
                                "beginAtZero": True,
                                "title": {"display": True, "text": "Number of Rejected Products"}
                            },
                            "x": {
                                "title": {"display": True, "text": "Seller"}
                            }
                        }
                    }
                }
                st.markdown("**Chart: Top 5 Sellers by Rejected Products**")
                st.json(chart_data, expanded=False)
            
            else:
                st.warning("No seller data parsed.")
            
            # Aggregate Categories
            if all_categories_dfs:
                aggregated_categories = pd.concat(all_categories_dfs, ignore_index=True)
                weekly_categories = aggregated_categories.groupby('Category')['Rejected Products'].sum().reset_index()
                weekly_categories = weekly_categories.sort_values('Rejected Products', ascending=False).head(5)
                weekly_categories['Percentage'] = (weekly_categories['Rejected Products'] / weekly_categories['Rejected Products'].sum() * 100).round(1)
                st.subheader("Top 5 Categories by Rejected Products (Weekly)")
                st.dataframe(weekly_categories)
                
                # Create chart
                chart_data = {
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
                            "y": {
                                "beginAtZero": True,
                                "title": {"display": True, "text": "Number of Rejected Products"}
                            },
                            "x": {
                                "title": {"display": True, "text": "Category"}
                            }
                        }
                    }
                }
                st.markdown("**Chart: Top 5 Categories by Rejected Products**")
                st.json(chart_data, expanded=False)
            
            else:
                st.warning("No category data parsed.")
            
            # Aggregate Reasons
            if all_reasons_dfs:
                aggregated_reasons = pd.concat(all_reasons_dfs, ignore_index=True)
                weekly_reasons = aggregated_reasons.groupby('Rejection Reason')['Rejected Products'].sum().reset_index()
                weekly_reasons = weekly_reasons.sort_values('Rejected Products', ascending=False).head(5)
                weekly_reasons['Percentage'] = (weekly_reasons['Rejected Products'] / weekly_reasons['Rejected Products'].sum() * 100).round(1)
                st.subheader("Top 5 Rejection Reasons (Weekly)")
                st.dataframe(weekly_reasons)
                
                # Create chart
                chart_data = {
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
                            "y": {
                                "beginAtZero": True,
                                "title": {"display": True, "text": "Number of Rejected Products"}
                            },
                            "x": {
                                "title": {"display": True, "text": "Rejection Reason"}
                            }
                        }
                    }
                }
                st.markdown("**Chart: Top 5 Rejection Reasons**")
                st.json(chart_data, expanded=False)
            
            else:
                st.warning("No reasons data parsed.")
            
            # Deep Analysis
            st.subheader("Deep Analysis")
            total_rejections = 0
            if 'aggregated_sellers' in locals():
                total_rejections = aggregated_sellers['Rejected Products'].sum()
            elif 'aggregated_categories' in locals():
                total_rejections = aggregated_categories['Rejected Products'].sum()
            
            if total_rejections > 0:
                avg_daily_rej = total_rejections / len(set(dates))
                st.metric("Total Weekly Rejections", total_rejections)
                st.metric("Average Daily Rejections", f"{avg_daily_rej:.1f}")
                
                if 'weekly_sellers' in locals() and not weekly_sellers.empty:
                    top_seller_pct = weekly_sellers.iloc[0]['Percentage']
                    st.info(f"The top seller '{weekly_sellers.iloc[0]['Seller']}' accounts for {top_seller_pct:.1f}% of weekly rejections, indicating potential systemic issues in their listings.")
                
                if 'weekly_categories' in locals() and not weekly_categories.empty:
                    top_cat_pct = weekly_categories.iloc[0]['Percentage']
                    st.info(f"Category '{weekly_categories.iloc[0]['Category']}' has the highest rejections at {top_cat_pct:.1f}%, suggesting category-specific validation rules or training needs.")
                
                if 'weekly_reasons' in locals() and not weekly_reasons.empty:
                    top_reason_pct = weekly_reasons.iloc[0]['Percentage']
                    st.info(f"Primary rejection reason '{weekly_reasons.iloc[0]['Rejection Reason']}' drives {top_reason_pct:.1f}% of issues; prioritize automated checks or seller education here.")
                
                # Trend if multiple dates
                if len(set(dates)) > 1:
                    if 'aggregated_sellers' in locals():
                        daily_trend = aggregated_sellers.groupby('Date')['Rejected Products'].sum().reset_index()
                        chart_data = {
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
                                    "y": {
                                        "beginAtZero": True,
                                        "title": {"display": True, "text": "Number of Rejected Products"}
                                    },
                                    "x": {
                                        "title": {"display": True, "text": "Date"}
                                    }
                                }
                            }
                        }
                        st.markdown("**Chart: Daily Rejection Trend**")
                        st.json(chart_data, expanded=False)
            
            # Recommendations
            st.subheader("Recommendations")
            recs = []
            if 'weekly_sellers' in locals() and not weekly_sellers.empty:
                recs.append(f"- Schedule training sessions with top 3 sellers ({', '.join(weekly_sellers.head(3)['Seller'].tolist())}) on listing best practices to reduce duplicates and brand issues.")
            if 'weekly_categories' in locals() and not weekly_categories.empty:
                recs.append(f"- Implement category-specific guidelines for high-rejection categories like {', '.join(weekly_categories.head(3)['Category'].tolist())}.")
            if 'weekly_reasons' in locals() and not weekly_reasons.empty:
                recs.append(f"- Automate pre-validation for top reasons such as '{weekly_reasons.iloc[0]['Rejection Reason']}' using scripts to flag potential issues before upload.")
            if total_rejections > 0 and avg_daily_rej > 50:
                recs.append("- Overall rejection rate is high (>50/day); conduct a platform-wide audit on validation rules and seller onboarding.")
            else:
                recs.append("- Rejection trends are stable; continue monitoring but focus on proactive seller support.")
            
            for rec in recs:
                st.write(f"• {rec}")
            
            # Export
            st.subheader("Export Aggregated Weekly Data")
            export_dfs = {}
            if 'weekly_sellers' in locals():
                export_dfs['Top Sellers'] = weekly_sellers
            if 'weekly_categories' in locals():
                export_dfs['Top Categories'] = weekly_categories
            if 'weekly_reasons' in locals():
                export_dfs['Top Reasons'] = weekly_reasons
            if export_dfs:
                aggregated_excel = BytesIO()
                with pd.ExcelWriter(aggregated_excel, engine='xlsxwriter') as writer:
                    for sheet, df in export_dfs.items():
                        df.to_excel(writer, sheet_name=sheet, index=False)
                aggregated_excel.seek(0)
                current_date = datetime.now().strftime("%Y-%m-%d")
                st.download_button(
                    label="Download Aggregated Weekly Report",
                    data=aggregated_excel,
                    file_name=f"Weekly_Analysis_Report_{current_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.warning("No summary data found in the 'Sellers Data' sheets of uploaded files.")
    else:
        st.info("Upload one or more Excel files to start the weekly analysis.")

with tab3:
    st.subheader("Data Lake Validation")
    country = st.selectbox("Select Country", ["Kenya", "Uganda", "All Countries"], key="data_lake_country")
    uploaded_file = st.file_uploader("Upload your Data Lake Excel file", type='xlsx', key="data_lake_file")

    if uploaded_file is not None:
        current_date = datetime.now().strftime("%Y-%m-%d")
        file_prefix = "KE" if country == "Kenya" else "UG" if country == "Uganda" else "ALL"
        process_success = False
        try:
            # Read the Excel file, Sheet1
            raw_data = pd.read_excel(uploaded_file, sheet_name='Sheet1')
            st.write(f"Loaded Excel file with {len(raw_data)} rows.")

            if raw_data.empty:
                st.error("The uploaded Excel file is empty. Please verify that the file contains data in 'Sheet1'.")
                st.stop()

            # Map columns from Data Lake format to expected format
            column_mapping = {
                'cod_productset_sid': 'PRODUCT_SET_SID',
                'dsc_shop_active_country': 'ACTIVE_STATUS_COUNTRY',
                'dsc_name': 'NAME',
                'dsc_brand_name': 'BRAND',
                'dsc_category_name': 'CATEGORY',
                'cod_category_code': 'CATEGORY_CODE',
                'color': 'COLOR',
                'image1': 'MAIN_IMAGE',
                'list_variations': 'VARIATION',
                'cod_parent_sku': 'PARENTSKU',
                'dsc_shop_seller_name': 'SELLER_NAME',
                'list_seller_skus': 'SELLER_SKU',
                'dsc_shop_tax_class': 'TAX_CLASS'
                # Note: GLOBAL_PRICE and GLOBAL_SALE_PRICE are not present in the provided data, will be NA
            }

            # Rename columns
            data = raw_data.rename(columns=column_mapping).copy()

            # Filter by country if not "All Countries"
            country_code = COUNTRY_MAPPING[country]
            if country_code and 'ACTIVE_STATUS_COUNTRY' in data.columns:
                data = data[data['ACTIVE_STATUS_COUNTRY'].str.contains(country_code, na=False, case=False)]
                st.write(f"Filtered to {len(data)} products for {country} ({country_code}).")
                if data.empty:
                    unique_countries = raw_data['dsc_shop_active_country'].dropna().unique()
                    st.error(f"No products found for {country} ({country_code}). Possible reasons:\n"
                             f"- The 'dsc_shop_active_country' column does not contain '{country_code}'.\n"
                             f"- All rows were filtered out due to missing or invalid data.\n"
                             f"Available countries in data: {', '.join(unique_countries) if unique_countries.size > 0 else 'None'}")
                    st.stop()

            essential_input_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'COLOR', 'SELLER_NAME', 'PARENTSKU']
            for col in essential_input_cols:
                if col not in data.columns:
                    data[col] = pd.NA

            for col in ['NAME', 'BRAND', 'COLOR', 'SELLER_NAME', 'CATEGORY_CODE', 'PARENTSKU']:
                if col in data.columns:
                    data[col] = data[col].astype(str).fillna('')

            if data.empty:
                st.error("The DataFrame is empty after processing. Possible reasons:\n"
                         "- The file contains no valid data after column mapping.\n"
                         "- All rows were filtered out by the country selection.\n"
                         "- Required columns are missing or empty.\n"
                         f"Available columns: {', '.join(raw_data.columns)}")
                st.stop()

            st.write(f"Processed {len(data)} products after cleaning.")

            final_report_df, individual_flag_dfs = validate_products(
                data, config_data, blacklisted_words, reasons_dict_legacy,
                book_category_codes, sensitive_brand_words,
                approved_book_sellers, perfume_category_codes, country
            )
            process_success = True

            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

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

            selected_sellers = st.sidebar.multiselect("Select Sellers", seller_options, default=['All Sellers'], key="data_lake_sellers")

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
                    if 'All Sellers' not in selected_sellers and selected_sellers and seller in selected_sellers:
                        rej_count = current_seller_data[current_seller_data['Status'] == 'Rejected']['ParentSKU'].count()
                        app_count = current_seller_data[current_seller_data['Status'] == 'Approved']['ParentSKU'].count()
                        st.sidebar.write(f"{seller}: **Rej**: {rej_count}, **App**: {app_count}")
                    elif 'All Sellers' in selected_sellers:
                        rej_count = current_seller_data[current_seller_data['Status'] == 'Rejected']['ParentSKU'].count()
                        app_count = current_seller_data[current_seller_data['Status'] == 'Approved']['ParentSKU'].count()
                        st.sidebar.write(f"{seller}: **Rej**: {rej_count}, **App**: {app_count}")
            else:
                st.sidebar.write("Seller metrics unavailable (SELLER_NAME missing or no products).")

            st.sidebar.subheader(f"Exports for: {seller_label_filename.replace('_', ' ')}")
            seller_final_excel = to_excel(seller_final_report_df_filtered, reasons_df_from_config)
            st.sidebar.download_button(
                label="Seller Final Export",
                data=seller_final_excel,
                file_name=f"{file_prefix}_Final_Report_{current_date}_{seller_label_filename}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="data_lake_final_export"
            )
            
            seller_rejected_excel = to_excel(seller_rejected_df_filtered, reasons_df_from_config)
            st.sidebar.download_button(
                label="Seller Rejected Export",
                data=seller_rejected_excel,
                file_name=f"{file_prefix}_Rejected_Products_{current_date}_{seller_label_filename}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="data_lake_rejected_export"
            )

            seller_approved_excel = to_excel(seller_approved_df_filtered, reasons_df_from_config)
            st.sidebar.download_button(
                label="Seller Approved Export",
                data=seller_approved_excel,
                file_name=f"{file_prefix}_Approved_Products_{current_date}_{seller_label_filename}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="data_lake_approved_export"
            )

            seller_full_excel = to_excel_seller_data(seller_data_filtered, seller_final_report_df_filtered)
            st.sidebar.download_button(
                label="Seller Full Data Export",
                data=seller_full_excel,
                file_name=f"{file_prefix}_Seller_Data_Export_{current_date}_{seller_label_filename}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="data_lake_full_export"
            )

            st.header("Overall Product Validation Results")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Products in Upload", len(data))
                st.metric("Approved Products (Overall)", len(approved_df))
            with col2:
                st.metric("Rejected Products (Overall)", len(rejected_df))
                rejection_rate = (len(rejected_df)/len(data)*100) if len(data) > 0 else 0
                st.metric("Rejection Rate (Overall)", f"{rejection_rate:.1f}%")

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
                            key=f"data_lake_flag_{safe_title}"
                        )
                    else:
                        st.write("No issues found for this check.")

            st.header("Overall Data Exports (All Sellers)")
            col1_main, col2_main, col3_main, col4_main = st.columns(4)
            with col1_main:
                overall_final_excel = to_excel(final_report_df, reasons_df_from_config)
                st.download_button(
                    label="Final Export (All)",
                    data=overall_final_excel,
                    file_name=f"{file_prefix}_Final_Report_{current_date}_ALL.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="data_lake_overall_final"
                )
            with col2_main:
                overall_rejected_excel = to_excel(rejected_df, reasons_df_from_config)
                st.download_button(
                    label="Rejected Export (All)",
                    data=overall_rejected_excel,
                    file_name=f"{file_prefix}_Rejected_Products_{current_date}_ALL.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="data_lake_overall_rejected"
                )
            with col3_main:
                overall_approved_excel = to_excel(approved_df, reasons_df_from_config)
                st.download_button(
                    label="Approved Export (All)",
                    data=overall_approved_excel,
                    file_name=f"{file_prefix}_Approved_Products_{current_date}_ALL.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="data_lake_overall_approved"
                )
            with col4_main:
                overall_full_excel = to_excel_full_data(data.copy(), final_report_df)
                st.download_button(
                    label="Full Data Export (All)",
                    data=overall_full_excel,
                    file_name=f"{file_prefix}_Full_Data_Export_{current_date}_ALL.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="data_lake_overall_full"
                )

        except Exception as e:
            process_success = False
            st.error(f"An unexpected error occurred processing the file: {e}")
            import traceback
            st.error(f"Traceback: {traceback.format_exc()}")
            st.error("Possible issues:\n"
                     "- The Excel file may not have a 'Sheet1' or may be corrupted.\n"
                     "- Required columns (e.g., cod_productset_sid, dsc_name) may be missing or incorrectly formatted.\n"
                     "- The file may be too large or contain invalid data types.\n"
                     "Please verify the file structure and try again.")

        if not process_success and uploaded_file is not None:
            st.error("File processing failed. Please check the file format, content, console logs (if running locally), and error messages above, then try again.")
