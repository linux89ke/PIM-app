import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import time
import re

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# Function to load blacklisted words from a file (No changes needed)
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

# Function to load book category codes from file (No changes needed)
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

# Function to load sensitive brand words from Excel file (No changes needed)
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

# Function to load approved book sellers from Excel file (NEW FUNCTION)
def load_approved_book_sellers():
    try:
        approved_sellers_df = pd.read_excel('Books_Approved_Sellers.xlsx')
        approved_sellers_list = approved_sellers_df['SellerName'].astype(str).tolist()
        print("\nLoaded Approved Book Sellers (from Books_Approved_Sellers.xlsx):\n", approved_sellers_list) # Debug print
        return approved_sellers_list
    except FileNotFoundError:
        st.warning("Books_Approved_Sellers.xlsx file not found! Book seller approval check will not be applied.")
        return []
    except Exception as e:
        st.error(f"Error loading Books_Approved_Sellers.xlsx: {e}")
        return []

# Function to load configuration files (excluding flags.xlsx) (No changes needed)
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
        except Exception as e:
            st.error(f"❌ Error loading {filename}: {e}")
    return data

# Validation check functions (modularized) - No changes needed for these tests
def check_missing_color(data, book_category_codes):
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)] # Only check non-books
    missing_color_non_books = non_book_data[non_book_data['COLOR'].isna() | (non_book_data['COLOR'] == '')]
    return missing_color_non_books

def check_missing_brand_or_name(data):
    return data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]

def check_single_word_name(data, book_category_codes):
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)] # Only check non-books
    flagged_non_book_single_word_names = non_book_data[
        (non_book_data['NAME'].str.split().str.len() == 1) & (non_book_data['BRAND'] != 'Jumia Book')
    ]
    return flagged_non_book_single_word_names

def check_generic_brand_issues(data, valid_category_codes_fas):
    return data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]

def check_brand_in_name(data):
    return data[data.apply(lambda row:
        isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and
        row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

def check_duplicate_products(data):
    return data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME', 'COLOR'], keep=False)]

def check_sensitive_brands(data, sensitive_brand_words, book_category_codes): # Modified Function
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)] # Filter for book categories
    if not sensitive_brand_words or book_data.empty:
        return pd.DataFrame()

    sensitive_regex_words = [r'\b' + re.escape(word.lower()) + r'\b' for word in sensitive_brand_words]
    sensitive_brands_regex = '|'.join(sensitive_regex_words)

    mask_name = book_data['NAME'].str.lower().str.contains(sensitive_brands_regex, regex=True, na=False) # Apply to book_data
    # mask_brand = book_data['BRAND'].str.lower().str.contains(sensitive_brands_regex, regex=True, na=False) # Brand check removed for books - per requirement

    # combined_mask = mask_name | mask_brand # Brand check removed for books
    combined_mask = mask_name # Only check NAME for sensitive words in books
    return book_data[combined_mask] # Return filtered book_data


def check_seller_approved_for_books(data, book_category_codes, approved_book_sellers):
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)] # Filter for book categories
    if book_data.empty:
        return pd.DataFrame() # No books, return empty DataFrame

    print("\nSeller Names in Book Data:\n", book_data['SELLER_NAME'].unique()) # Debug print: Seller names in book data
    print("\nApproved Book Sellers List:\n", approved_book_sellers) # Debug print: Approved sellers list

    # Check if SellerName is NOT in approved list for book data
    unapproved_book_sellers_mask = ~book_data['SELLER_NAME'].isin(approved_book_sellers)
    return book_data[unapproved_book_sellers_mask] # Return DataFrame of unapproved book sellers


def validate_products(data, config_data, blacklisted_words, reasons_dict, book_category_codes, sensitive_brand_words, approved_book_sellers):
    validations = [
        (check_missing_color, "Missing COLOR", {'book_category_codes': book_category_codes}),
        (check_missing_brand_or_name, "Missing BRAND or NAME", {}),
        (check_single_word_name, "Single-word NAME", {'book_category_codes': book_category_codes}),
        (check_generic_brand_issues, "Generic BRAND Issues", {'valid_category_codes_fas': config_data['category_fas']['ID'].tolist()}),
        (check_sensitive_brands, "Sensitive Brand", {'sensitive_brand_words': sensitive_brand_words, 'book_category_codes': book_category_codes}), # Pass book_category_codes here
        (check_brand_in_name, "BRAND name repeated in NAME", {}),
        (check_duplicate_products, "Duplicate product", {}),
        (check_seller_approved_for_books, "Seller Approve to sell books",  {'book_category_codes': book_category_codes, 'approved_book_sellers': approved_book_sellers}),
    ]

    # --- Calculate validation DataFrames ONCE, outside the loop ---
    validation_results_dfs = {}
    for check_func, flag_name, func_kwargs in validations:
        kwargs = {'data': data, **func_kwargs}
        validation_results_dfs[flag_name] = check_func(**kwargs)
    # --- Now validation_results_dfs contains DataFrames with flagged products for each check ---

    final_report_rows = []
    for _, row in data.iterrows():
        reasons = []

        for check_func, flag_name, func_kwargs in validations:
            start_time = time.time()
            validation_df = validation_results_dfs[flag_name] # <--- Get pre-calculated DataFrame
            end_time = time.time()
            elapsed_time = end_time - start_time
            print(f"Validation '{flag_name}' took: {elapsed_time:.4f} seconds")

            if not validation_df.empty and row['PRODUCT_SET_SID'] in validation_df['PRODUCT_SET_SID'].values:
                reason_details = reasons_dict.get(flag_name, ("", "", ""))
                reason_code, reason_message, comment = reason_details
                detailed_reason = f"{reason_code} - {reason_message}" if reason_code and reason_message else flag_name
                reasons.append(detailed_reason)

        status = 'Rejected' if reasons else 'Approved'
        report_reason_message = "; ".join(reasons) if reasons else ""
        comment = "; ".join([reasons_dict.get(reason_name, ("", "", ""))[2] for reason_name in reasons]) if reasons else ""

        final_report_rows.append({
            'ProductSetSid': row['PRODUCT_SET_SID'],
            'ParentSKU': row.get('PARENTSKU', ''),
            'Status': status,
            'Reason': report_reason_message,
            'Comment': comment if comment else "See rejection reasons documentation for details"
        })

    final_report_df = pd.DataFrame(final_report_rows)
    return final_report_df


# Initialize the app
st.title("Product Validation Tool")

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

if uploaded_file is not None:
    try:
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')

        # Load configuration files and lists (moved inside the if block so it only loads with file upload)
        config_data = load_config_files()
        blacklisted_words = load_blacklisted_words()
        book_category_codes = load_book_category_codes()
        sensitive_brand_words = load_sensitive_brand_words()
        approved_book_sellers = load_approved_book_sellers()
        reasons_dict = config_data.get('reasons', {}).to_dict('index') if config_data.get('reasons') is not None else {}


        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()

        st.write("CSV file loaded successfully. Preview of data:")
        st.dataframe(data.head(10))

        final_report_df = validate_products(data, config_data, blacklisted_words, reasons_dict, book_category_codes, sensitive_brand_words, approved_book_sellers)

        # Split into approved and rejected - No change
        approved_df = final_report_df[final_report_df['Status'] == 'Approved']
        rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

        # Display results metrics - No change
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Products", len(data))
            st.metric("Approved Products", len(approved_df))
        with col2:
            st.metric("Rejected Products", len(rejected_df))
            st.metric("Rejection Rate", f"{(len(rejected_df)/len(data)*100):.1f}%")

        # Validation results expanders - Updated to include "Sensitive Brand Issues" and "Seller Approve to sell books"
        validation_results = [
            ("Seller Approve to sell books", check_seller_approved_for_books(data, book_category_codes, approved_book_sellers)), # New expander
        ]

        for title, df in validation_results:
            with st.expander(f"{title} ({len(df)} products)"):
                if not df.empty:
                    st.dataframe(df)
                else:
                    st.write("No issues found")


    except Exception as e:
        st.error(f"Error processing the uploaded file: {e}")
        print(f"Exception details: {e}") # Also print to console for full traceback
