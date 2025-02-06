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

# Function to load approved book sellers from Excel file (No changes needed)
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

# Validation check functions (modularized) - No changes needed for these tests except data type fix in load_csv
def check_missing_color(data, book_category_codes):
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)] # Only check non-books
    missing_color_non_books = non_book_data[non_book_data['COLOR'].isna() | (non_book_data['COLOR'] == '')]
    return missing_color_non_books

def check_missing_brand_or_name(data):
    return data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]

def check_single_word_name(data, book_category_codes):
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)] # Only check non-books
    flagged_non_book_single_word_names = non_book_data[
        (non_book_data['NAME'].str.split().str.len() == 1)
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

    # Check if SellerName is NOT in approved list for book data
    unapproved_book_sellers_mask = ~book_data['SELLER_NAME'].isin(approved_book_sellers)
    return book_data[unapproved_book_sellers_mask] # Return DataFrame of unapproved book sellers


def validate_products(data, config_data, blacklisted_words, reasons_dict, book_category_codes, sensitive_brand_words, approved_book_sellers):
    validations = [
        ("Sensitive Brand Issues", check_sensitive_brands, {'sensitive_brand_words': sensitive_brand_words, 'book_category_codes': book_category_codes}), # Priority 1
        ("Seller Approve to sell books", check_seller_approved_for_books,  {'book_category_codes': book_category_codes, 'approved_book_sellers': approved_book_sellers}), # Priority 2
        ("Single-word NAME", check_single_word_name, {'book_category_codes': book_category_codes}), # Priority 3
        ("Missing BRAND or NAME", check_missing_brand_or_name, {}), # Priority 4
        ("Duplicate product", check_duplicate_products, {}), # Priority 5
        ("Generic BRAND Issues", check_generic_brand_issues, {'valid_category_codes_fas': config_data['category_fas']['ID'].tolist()}), # Priority 6
        ("Missing COLOR", check_missing_color, {'book_category_codes': book_category_codes}), # Priority 7
        ("BRAND name repeated in NAME", check_brand_in_name, {}), # Priority 8
    ] # Validations are now ORDERED by priority

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

        for flag_name, _, _ in validations: # Iterate through validations in PRIORITY ORDER
            validation_df = validation_results_dfs[flag_name] # Get pre-calculated DataFrame for this flag

            if not validation_df.empty and row['PRODUCT_SET_SID'] in validation_df['PRODUCT_SET_SID'].values:
                reason_details = reasons_dict.get(flag_name, ("", "", ""))
                reason_code, reason_message, reason_comment = reason_details
                detailed_reason = f"{reason_code} - {reason_message}" if reason_code and reason_message else flag_name

                rejection_reason = detailed_reason # Set the rejection reason (only the HIGHEST priority one)
                comment = reason_comment if reason_comment else "See rejection reasons documentation for details" # Get comment
                status = 'Rejected' # Change status to Rejected
                break # Stop checking further validations once a reason is found (due to priority)

        final_report_rows.append({
            'ProductSetSid': row['PRODUCT_SET_SID'],
            'ParentSKU': row.get('PARENTSKU', ''),
            'Status': status,
            'Reason': rejection_reason, # Only ONE rejection reason now
            'Comment': comment
        })

    final_report_df = pd.DataFrame(final_report_rows)
    return final_report_df


# Initialize the app
st.title("Product Validation Tool")

# Load configuration files
config_data = load_config_files()

# Load blacklisted words
blacklisted_words = load_blacklisted_words()

# Load book category codes
book_category_codes = load_book_category_codes()
print("\nLoaded Book Category Codes (from Books_cat.xlsx) at app start:\n", book_category_codes)

# Load sensitive brand words
sensitive_brand_words = load_sensitive_brand_words() # Load sensitive brand words
print("\nLoaded Sensitive Brand Words (from sensitive_brands.xlsx) at app start:\n", sensitive_brand_words)

# Load approved book sellers (NEW - load approved sellers)
approved_book_sellers = load_approved_book_sellers()
print("\nLoaded Approved Book Sellers (from Books_Approved_Sellers.xlsx) at app start:\n", approved_book_sellers)


# Load reasons dictionary from reasons.xlsx
reasons_df = config_data.get('reasons', pd.DataFrame()) # Load reasons.xlsx
reasons_dict = {}
if not reasons_df.empty:
    for _, row in reasons_df.iterrows():
        reason_text = row['CODE - REJECTION_REASON']
        reason_parts = reason_text.split(' - ', 1)
        code = reason_parts[0]
        message = row['CODE - REJECTION_REASON'] #MESSAGE
        comment = "See rejection reasons documentation for details"
        reasons_dict[f"{code} - {message}"] = (code, message, comment)
else:
    st.warning("reasons.xlsx file could not be loaded, detailed reasons in reports will be unavailable.")


# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Process uploaded file
if uploaded_file is not None:
    try:
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype={'CATEGORY_CODE': str}) # <--- ADDED dtype={'CATEGORY_CODE': str} HERE
        print("CSV file successfully read by pandas.")

        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()

        st.write("CSV file loaded successfully. Preview of data:")
        st.dataframe(data.head(10))

        # Validation and report generation - pass sensitive_brand_words & book_category_codes & approved_book_sellers
        final_report_df = validate_products(data, config_data, blacklisted_words, reasons_dict, book_category_codes, sensitive_brand_words, approved_book_sellers) # Added approved_book_sellers

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
            ("Missing COLOR", check_missing_color(data, book_category_codes)),
            ("Missing BRAND or NAME", check_missing_brand_or_name(data)),
            ("Single-word NAME", check_single_word_name(data, book_category_codes)),
            ("Generic BRAND Issues", check_generic_brand_issues(data, config_data['category_fas']['ID'].tolist())),
            ("Sensitive Brand Issues", check_sensitive_brands(data, sensitive_brand_words, book_category_codes)), # New expander - pass book_category_codes
            ("Brand in Name", check_brand_in_name(data)),
            ("Duplicate Products", check_duplicate_products(data)),
            ("Seller Approve to sell books", check_seller_approved_for_books(data, book_category_codes, approved_book_sellers)), # New expander
        ]

        for title, df in validation_results:
            with st.expander(f"{title} ({len(df)} products)"):
                if not df.empty:
                    st.dataframe(df)
                else:
                    st.write("No issues found")

        # Export functions - No change - Modified to include 'flag' column in rejected report
        def to_excel(df1, df2, sheet1_name="ProductSets", sheet2_name="RejectionReasons"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df1.to_excel(writer, index=False, sheet_name=sheet1_name)
                df2.to_excel(writer, index=False, sheet_name=sheet2_name)
            output.seek(0)
            return output

        # Download buttons - No change
        current_date = datetime.now().strftime("%Y-%m-%d")

        col1, col2, col3 = st.columns(3)

        with col1:
            final_report_excel = to_excel(final_report_df, reasons_df, "ProductSets", "RejectionReasons")
            st.download_button(
                label="Final Export",
                data=final_report_excel,
                file_name=f"Final_Report_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with col2:
            rejected_excel = to_excel(rejected_df, reasons_df, "ProductSets", "RejectionReasons")
            st.download_button(
                label="Rejected Export",
                data=rejected_excel,
                file_name=f"Rejected_Products_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with col3:
            approved_excel = to_excel(approved_df, reasons_df, "ProductSets", "RejectionReasons")
            st.download_button(
                label="Approved Export",
                data=approved_excel,
                file_name=f"Approved_Products_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Error processing the uploaded file: {e}")
        print(f"Exception details: {e}") # Also print to console for full traceback
