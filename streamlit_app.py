import pandas as pd
from io import StringIO
import re
import time
import streamlit as st # Import streamlit to use st.warning, st.error, etc.

# CSV data from the user's prompt
csv_data = """
PRODUCT_SET_ID;PRODUCT_SET_SID;TYPE;ACTIVE_STATUS_COUNTRY;NAME;BRAND;CATEGORY;CATEGORY_CODE;COLOR;MAIN_IMAGE;VARIATION;PARENTSKU;SELLER_NAME;SELLER_SKU;GLOBAL_PRICE;GLOBAL_SALE_PRICE;TAX_CLASS
214347318;b68725b0-48be-451e-b402-f78237c297cc;NEW_PRODUCT;KE;Beautiful;Fashion;Casual Dresses;1029492;Hot pink ;https://vendorcenter.jumia.com/product-set-images/2025/02/04/gvc.product.image.1738678625482.cb625efd-04d1-4b40-8633-59183740934a.jpeg;XL;ADDHOTP;Addiktivewear;ADDHOTP;22.21;20.73;NATIONAL
214339311;ae40917a-fa1b-4c23-be00-719fceadd399;NEW_PRODUCT;KE;Two;Jumia Book;Greeting Cards;1025432;Yellow;https://vendorcenter.jumia.com/product-set-images/2025/02/04/gvc.product.image.1738678632442.be062cab-c601-495a-85f2-82204c69b6f4.jpeg;...;Avocado-Halves-Colour;ADNEPTIS;Avocado-Halves-Colour;4.81;4.44;NATIONAL
214342773;de1cdff1-d0b6-4217-9f38-ef837a0be6be;NEW_PRODUCT;KE;Milk & Chocolate Chip Cookie Greeting Card;Jumia Book;Greeting Cards;1025432;Brown;https://vendorcenter.jumia.com/product-set-images/2025/02/04/gvc.product.image.1738669172553.d47bdb81-5e98-4a64-a2ec-2569354bc778.png;...;Milk-Chocolate-Chip-Colour;ADNEPTIS;Milk-Chocolate-Chip-Colour;4.81;4.44;NATIONAL
214341121;966840ef-0457-48d4-802a-75c79c693531;NEW_PRODUCT;KE;Tea & Biscuit Greeting Card;Jumia Book;Greeting Cards;1025432;Pastel Yellow;https://vendorcenter.jumia.com/product-set-images/2025/02/04/gvc.product.image.1738665342459.937f7a96-9b4b-44c2-8049-61bb6f7c4478.png;...;Tea-Biscuit-Colour;ADNEPTIS;Tea-Biscuit-Colour;4.81;4.44;NATIONAL
"""

# Load CSV data using StringIO
uploaded_file = StringIO(csv_data)
data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')

# Dummy configuration data (replace with your actual loading functions if files are available)
def load_config_files():
    return {'category_fas': pd.DataFrame({'ID': []}), 'reasons': pd.DataFrame()}
def load_blacklisted_words():
    return []
def load_book_category_codes():
    return ['1025432', '1000203', '1001361', '1000252', '1000243'] # Example book category codes
def load_sensitive_brand_words():
    return ['Jumia Book'] # Example sensitive brand word
def load_approved_book_sellers():
    return ['Atlantic Bookstore', 'Amazing bookshop'] # Example approved sellers


config_data = load_config_files()
blacklisted_words = load_blacklisted_words()
book_category_codes = load_book_category_codes()
sensitive_brand_words = load_sensitive_brand_words()
approved_book_sellers = load_approved_book_sellers()
reasons_dict = {} # Dummy reasons_dict

# Validation functions (include the modified check_sensitive_brands from the previous response)
def check_missing_color(data, book_category_codes):
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    missing_color_non_books = non_book_data[non_book_data['COLOR'].isna() | (non_book_data['COLOR'] == '')]
    return missing_color_non_books

def check_missing_brand_or_name(data):
    return data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]

def check_single_word_name(data, book_category_codes):
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
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
    if book_data.empty:
        return pd.DataFrame() # No books, return empty DataFrame

    if not sensitive_brand_words or book_data.empty: # Use book_data here
        return pd.DataFrame()

    sensitive_regex_words = [r'\b' + re.escape(word.lower()) + r'\b' for word in sensitive_brand_words]
    sensitive_brands_regex = '|'.join(sensitive_regex_words)

    mask_name = book_data['NAME'].str.lower().str.contains(sensitive_brands_regex, regex=True, na=False) # Apply to book_data
    mask_brand = book_data['BRAND'].str.lower().str.contains(sensitive_brands_regex, regex=True, na=False) # Apply to book_data

    combined_mask = mask_name | mask_brand
    return book_data[combined_mask] # Return filtered book_data


def check_seller_approved_for_books(data, book_category_codes, approved_book_sellers):
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)] # Filter for book categories
    if book_data.empty:
        return pd.DataFrame() # No books, return empty DataFrame

    # Check if SellerName is NOT in approved list for book data
    unapproved_book_sellers_mask = ~book_data['SELLER_NAME'].isin(approved_book_sellers)
    return book_data[unapproved_book_sellers_mask] # Return DataFrame of unapproved book sellers

# Modified validate_products function (with pre-calculation) - from previous response
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


# --- Main execution ---
final_report_df = validate_products(data.copy(), config_data, blacklisted_words, reasons_dict, book_category_codes, sensitive_brand_words, approved_book_sellers)

# Print the counts for each flag
validation_results = {
    "Missing COLOR": check_missing_color(data, book_category_codes),
    "Missing BRAND or NAME": check_missing_brand_or_name(data),
    "Single-word NAME": check_single_word_name(data, book_category_codes),
    "Generic BRAND Issues": check_generic_brand_issues(data, config_data['category_fas']['ID'].tolist()),
    "Sensitive Brand Issues": check_sensitive_brands(data, sensitive_brand_words, book_category_codes),
    "Brand in Name": check_brand_in_name(data),
    "Duplicate Products": check_duplicate_products(data),
    "Seller Approve to sell books": check_seller_approved_for_books(data, book_category_codes, approved_book_sellers),
}

for title, df in validation_results.items():
    print(f"{title}: {len(df)} flags")
