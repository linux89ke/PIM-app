import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import time
import re

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# Function to load configuration files (excluding flags.xlsx) - No changes needed
def load_config_files(): # ... (rest of load_config_files function is the same) ...
    # ... (function code as before) ...
    return data

# Function to load blacklisted words from a file (No changes needed)
def load_blacklisted_words(): # ... (rest of load_blacklisted_words function is the same) ...
    # ... (function code as before) ...
    return []

# Function to load book category codes from file (No changes needed)
def load_book_category_codes(): # ... (rest of load_book_category_codes function is the same) ...
    # ... (function code as before) ...
    return []

# Function to load sensitive brand words from Excel file (No changes needed)
def load_sensitive_brand_words(): # ... (rest of load_sensitive_brand_words function is the same) ...
    # ... (function code as before) ...
    return []

# Function to load approved book sellers from Excel file (No changes needed)
def load_approved_book_sellers(): # ... (rest of load_approved_book_sellers function is the same) ...
    # ... (function code as before) ...
    return []

# Validation check functions (modularized) - No changes needed
def check_missing_color(data, book_category_codes): # ... (rest of check_missing_color function is the same) ...
    # ... (function code as before) ...
    return missing_color_non_books

def check_missing_brand_or_name(data): # ... (rest of check_missing_brand_or_name function is the same) ...
    # ... (function code as before) ...
    return data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]

def check_single_word_name(data, book_category_codes): # ... (rest of check_single_word_name function is the same) ...
    # ... (function code as before) ...
    return flagged_non_book_single_word_names

def check_generic_brand_issues(data, valid_category_codes_fas): # ... (rest of check_generic_brand_issues function is the same) ...
    # ... (function code as before) ...
    return data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]

def check_brand_in_name(data): # ... (rest of check_brand_in_name function is the same) ...
    # ... (function code as before) ...
    return data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

def check_duplicate_products(data): # ... (rest of check_duplicate_products function is the same) ...
    # ... (function code as before) ...
    return data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME', 'COLOR'], keep=False)]

def check_sensitive_brands(data, sensitive_brand_words, book_category_codes): # ... (rest of check_sensitive_brands function is the same) ...
    # ... (function code as before) ...
    return book_data[combined_mask]

def check_seller_approved_for_books(data, book_category_codes, approved_book_sellers): # ... (rest of check_seller_approved_for_books function is the same) ...
    # ... (function code as before) ...
    return book_data[unapproved_book_sellers_mask]

def validate_products(data, config_data, blacklisted_words, reasons_dict, book_category_codes, sensitive_brand_words, approved_book_sellers):
    validations = [ # ... (rest of validations list is the same) ...
        ("Sensitive Brand Issues", check_sensitive_brands, {'sensitive_brand_words': sensitive_brand_words, 'book_category_codes': book_category_codes}),
        ("Seller Approve to sell books", check_seller_approved_for_books,  {'book_category_codes': book_category_codes, 'approved_book_sellers': approved_book_sellers}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': book_category_codes}),
        ("Missing BRAND or NAME", check_missing_brand_or_name, {}),
        ("Duplicate product", check_duplicate_products, {}),
        ("Generic BRAND Issues", check_generic_brand_issues, {'valid_category_codes_fas': config_data['category_fas']['ID'].tolist()}),
        ("Missing COLOR", check_missing_color, {'book_category_codes': book_category_codes}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
    ] # Validations are now ORDERED by priority

    flag_reason_comment_mapping = { # ... (rest of flag_reason_comment_mapping dict is the same) ...
        "Sensitive Brand Issues": ("1000023 - Confirmation of counterfeit product by Jumia technical", "Please contact vendor support for sale of..."),
        "Seller Approve to sell books": ("1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale", "Kindly Contact Jumia Seller Support To Confirm Possibil"),
        "Single-word NAME": ("1000008 - Kindly Improve Product Name Description", ""),
        "Missing BRAND or NAME": ("1000001 - Brand NOT Allowed", ""),
        "Duplicate product": ("1000007 - Other Reason", "Product is duplicated"),
        "Generic BRAND Issues": ("1000001 - Brand NOT Allowed", "Kindly use Fashion for Fashion items"),
        "Missing COLOR": ("1000005 - Kindly confirm the actual product colour", "Kindly add color on the color field"),
        "BRAND name repeated in NAME": ("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", ""),
    }

    # --- Calculate validation DataFrames ONCE, outside the loop ---
    validation_results_dfs = {}
    for flag_name, check_func, func_kwargs in validations: # Iterate through ordered validations
        kwargs = {'data': data, **func_kwargs}
        validation_results_dfs[flag_name] = check_func(**kwargs)
    # --- Now validation_results_dfs contains DataFrames with flagged products for each check ---

    final_report_rows = []
    for _, row in data.iterrows():
        rejection_reason = "" # Initialize as empty string, will hold only ONE reason
        comment = ""
        status = 'Approved' # Default to Approved, will change if rejection reason is found
        flag = "" # Initialize flag column

        for flag_name, _, _ in validations: # Iterate through validations in PRIORITY ORDER
            validation_df = validation_results_dfs[flag_name] # Get pre-calculated DataFrame for this flag

            if not validation_df.empty and row['PRODUCT_SET_SID'] in validation_df['PRODUCT_SET_SID'].values:
                rejection_reason, comment = flag_reason_comment_mapping.get(flag_name) # Get reason and comment from mapping
                status = 'Rejected' # Change status to Rejected
                flag = flag_name # Store the flag name
                break # Stop checking further validations once a reason is found (due to priority)

        final_report_rows.append({
            'ProductSetSid': row['PRODUCT_SET_SID'],
            'ParentSKU': row.get('PARENTSKU', ''),
            'Status': status,
            'Reason': rejection_reason, # Only ONE rejection reason now (from mapping)
            'Comment': comment,
            'FLAG': flag # Include the FLAG column here
        })

    final_report_df = pd.DataFrame(final_report_rows)
    return final_report_df

# --- New function to export full data ---
def to_excel_full_data(data, final_report_df):
    output = BytesIO()
    full_data_cols = ["PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE", "COLOR", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU", "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG"]
    merged_df = pd.merge(data[full_data_cols[:-1]], final_report_df[["ProductSetSid", "Status", "Reason", "Comment", "FLAG"]], left_on="PRODUCT_SET_SID", right_on="ProductSetSid", how="left")
    merged_df['FLAG'] = merged_df['FLAG'].fillna('') # Fill NaN flags with blank strings
    productsets_cols = full_data_cols # Use full_data_cols for ProductSets sheet columns order

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if not merged_df.empty:
            merged_df[productsets_cols].to_excel(writer, index=False, sheet_name="ProductSets")
        else:
            merged_df.to_excel(writer, index=False, sheet_name="ProductSets") # Write empty df if merged_df is empty
        writer.save() # Save the writer object
    output.seek(0)
    return output

# --- New function to export flag-specific data ---
def to_excel_flag_data(flag_df, flag_name):
    output = BytesIO()
    full_data_cols = ["PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE", "COLOR", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU", "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG"]
    flag_df['FLAG'] = flag_name # Set FLAG column for the specific flag
    productsets_cols = full_data_cols

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if not flag_df.empty:
            flag_df[productsets_cols].to_excel(writer, index=False, sheet_name="ProductSets")
        else:
            flag_df.to_excel(writer, index=False, sheet_name="ProductSets") # Write empty df if flag_df is empty
        writer.save() # Save the writer object
    output.seek(0)
    return output


# Initialize the app (No changes needed)
st.title("Product Validation Tool")

# Load configuration files, etc. (No changes needed)
config_data = load_config_files()
blacklisted_words = load_blacklisted_words()
book_category_codes = load_book_category_codes()
sensitive_brand_words = load_sensitive_brand_words()
approved_book_sellers = load_approved_book_sellers()
reasons_df = config_data.get('reasons', pd.DataFrame())
reasons_dict = {}
if not reasons_df.empty: # ... (rest of reasons_dict loading is the same) ...
    # ... (function code as before) ...

# File upload section (No changes needed)
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Process uploaded file
if uploaded_file is not None:
    try: # ... (rest of try block is the same until download buttons) ...
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype={'CATEGORY_CODE': str})
        # ... (rest of data processing and validation is the same) ...
        final_report_df = validate_products(data, config_data, blacklisted_words, reasons_dict, book_category_codes, sensitive_brand_words, approved_book_sellers)
        approved_df = final_report_df[final_report_df['Status'] == 'Approved']
        rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

        # Validation results expanders - Modified to add download buttons
        validation_results = [
            ("Missing COLOR", check_missing_color(data, book_category_codes)),
            ("Missing BRAND or NAME", check_missing_brand_or_name(data)),
            ("Single-word NAME", check_single_word_name(data, book_category_codes)),
            ("Generic BRAND Issues", check_generic_brand_issues(data, config_data['category_fas']['ID'].tolist())),
            ("Sensitive Brand Issues", check_sensitive_brands(data, sensitive_brand_words, book_category_codes)),
            ("Brand in Name", check_brand_in_name(data)),
            ("Duplicate Products", check_duplicate_products(data)),
            ("Seller Approve to sell books", check_seller_approved_for_books(data, book_category_codes, approved_book_sellers)),
        ]

        for title, df in validation_results:
            with st.expander(f"{title} ({len(df)} products)"):
                if not df.empty:
                    st.dataframe(df)
                    flag_excel = to_excel_flag_data(df.copy(), title) # Create flag-specific download
                    st.download_button(
                        label=f"Export {title} Data",
                        data=flag_excel,
                        file_name=f"{title.replace(' ', '_')}_Products_{current_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.write("No issues found")

        # Export functions - Modified to select and order columns for ProductSets sheet - No changes needed for this function itself
        def to_excel(df1, df2, sheet1_name="ProductSets", sheet2_name="RejectionReasons"): # ... (rest of to_excel function is the same) ...
            # ... (function code as before) ...
            return output

        # Download buttons - Modified to add Full Data Export button
        current_date = datetime.now().strftime("%Y-%m-%d")

        col1, col2, col3, col4 = st.columns(4) # Added one more column

        with col1: # ... (rest of "Final Export" button is the same) ...
            final_report_excel = to_excel(final_report_df, reasons_df, "ProductSets", "RejectionReasons")
            st.download_button(
                label="Final Export", # ... (rest of button params are the same) ...
                data=final_report_excel,
                file_name=f"Final_Report_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with col2: # ... (rest of "Rejected Export" button is the same) ...
            rejected_excel = to_excel(rejected_df, reasons_df, "ProductSets", "RejectionReasons")
            st.download_button(
                label="Rejected Export", # ... (rest of button params are the same) ...
                data=rejected_excel,
                file_name=f"Rejected_Products_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with col3: # ... (rest of "Approved Export" button is the same) ...
            approved_excel = to_excel(approved_df, reasons_df, "ProductSets", "RejectionReasons")
            st.download_button(
                label="Approved Export", # ... (rest of button params are the same) ...
                data=approved_excel,
                file_name=f"Approved_Products_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with col4: # --- New "Full Data Export" button ---
            full_data_excel = to_excel_full_data(data.copy(), final_report_df) # Create full data excel
            st.download_button(
                label="Full Data Export",
                data=full_data_excel,
                file_name=f"Full_Data_Export_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e: # ... (rest of exception handling is the same) ...
        # ... (exception handling code as before) ...
