import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import time
import re

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# Function to load configuration files (excluding flags.xlsx)
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

# Validation check functions (modularized)
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

def check_sensitive_brands(data, sensitive_brand_words, book_category_codes):
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)] # Filter for book categories
    if not sensitive_brand_words or book_data.empty:
        return pd.DataFrame()

    sensitive_regex_words = [r'\b' + re.escape(word.lower()) + r'\b' for word in sensitive_brand_words]
    sensitive_brands_regex = '|'.join(sensitive_regex_words)

    mask_name = book_data['NAME'].str.lower().str.contains(sensitive_brands_regex, regex=True, na=False) # Apply to book_data
    # mask_brand = book_data['BRAND'].str.lower().str.contains(sensitive_brands_regex, regex=True, na=False) # Brand check removed for books - per requirement

    # combined_mask = mask_name | mask_brand # Brand check removed for books
    combined_mask = mask_name # Only check NAME for sensitive words in books
    return book_data[combined_mask]

def check_seller_approved_for_books(data, book_category_codes, approved_book_sellers):
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)] # Filter for book categories
    if book_data.empty:
        return pd.DataFrame() # No books, return empty DataFrame

    # Check if SellerName is NOT in approved list for book data
    unapproved_book_sellers_mask = ~book_data['SELLER_NAME'].isin(approved_book_sellers)
    return book_data[unapproved_book_sellers_mask]

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

    flag_reason_comment_mapping = { # Define mapping here
        "Sensitive Brand Issues": ("1000023 - Confirmation of counterfeit product by Jumia technical", "Please contact vendor support for sale of..."),
        "Seller Approve to sell books": ("1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale", "Kindly Contact Jumia Seller Support To Confirm Possibil"),
        "Single-word NAME": ("1000008 - Kindly Improve Product Name Description", ""), # Blank comment here
        "Missing BRAND or NAME": ("1000001 - Brand NOT Allowed", ""), # Blank comment here
        "Duplicate product": ("1000007 - Other Reason", "Product is duplicated"),
        "Generic BRAND Issues": ("1000001 - Brand NOT Allowed", "Kindly use Fashion for Fashion items"),
        "Missing COLOR": ("1000005 - Kindly confirm the actual product colour", "Kindly add color on the color field"),
        "BRAND name repeated in NAME": ("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", ""), # Blank comment here
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
def to_excel_full_data(df_to_export, filename):
    output = BytesIO()
    full_data_cols = ["PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE", "COLOR", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU", "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG"]
    productsets_cols = full_data_cols # Use full_data_cols for ProductSets sheet columns order

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if not df_to_export.empty:
            df_to_export[productsets_cols].to_excel(writer, index=False, sheet_name="ProductSets")
        else:
            df_to_export.to_excel(writer, index=False, sheet_name="ProductSets") # Write empty df if df_to_export is empty
    output.seek(0)
    return output

# Export functions - Modified to select and order columns for ProductSets sheet
def to_excel(df1, df2, sheet1_name="ProductSets", sheet2_name="RejectionReasons"):
    output = BytesIO()
    productsets_cols = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment"] # Desired columns order
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if not df1.empty: # Check if df1 is not empty before trying to select columns
            df1[productsets_cols].to_excel(writer, index=False, sheet_name=sheet1_name)
        else:
            df1.to_excel(writer, index=False, sheet_name=sheet1_name) # Write empty df if df1 is empty
        df2.to_excel(writer, index=False, sheet_name=sheet2_name)
    output.seek(0)
    return output


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


# Load reasons dictionary from reasons.xlsx - still load for RejectionReasons sheet
reasons_df = config_data.get('reasons', pd.DataFrame()) # Load reasons.xlsx
reasons_dict = {}
if not reasons_df.empty:
    for _, row in reasons_df.iterrows():
        reason_text = row['CODE - REJECTION_REASON']
        reason_parts = reason_text.split(' - ', 1)
        code = reason_parts[0]
        message = reason_parts[1] if len(reason_parts) > 1 else reason_parts[0] # MESSAGE
        comment = row['COMMENT'] if 'COMMENT' in row else "" # Get comment, use empty string if column missing or value is NaN
        reasons_dict[f"{code} - {message}"] = (code, message, comment)
else:
    st.warning("reasons.xlsx file could not be loaded, detailed reasons in reports will be unavailable.")

# --- Sidebar filters ---
st.sidebar.header("Seller Filters")
seller_names_input = st.sidebar.text_area("Enter Seller Names (one per line)")
filtered_sellers = [seller.strip() for seller in seller_names_input.splitlines() if seller.strip()]
seller_filter_button = st.sidebar.button("Filter by Sellers")

# --- Sidebar Download Button for Filtered Sellers ---
st.sidebar.header("Download Filtered Seller Report") # Header for filtered seller export in sidebar
current_date = datetime.now().strftime("%Y-%m-%d") # Define current_date in sidebar scope

filtered_seller_excel = BytesIO() # Initialize for filtered seller export

st.sidebar.download_button( # Filtered seller export button in sidebar
    label="Filtered Seller Export",
    data=filtered_seller_excel,
    file_name=f"Seller_Filtered_Data_{current_date}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    disabled=True, # Initially disabled
    key="filtered_seller_button" # Key to prevent re-creation
)


# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Process uploaded file
if uploaded_file is not None:
    current_date = datetime.now().strftime("%Y-%m-%d")
    try:
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype={'CATEGORY_CODE': str})
        print("CSV file successfully read by pandas.")

        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()

        # Apply seller filter if button is clicked and sellers are entered
        if seller_filter_button and filtered_sellers:
            data = data[data['SELLER_NAME'].isin(filtered_sellers)]
            if data.empty:
                st.warning("No data found for the selected sellers.")

        st.write("CSV file loaded successfully. Preview of data:")
        st.dataframe(data.head(10))

        # Validation and report generation
        final_report_df = validate_products(data, config_data, blacklisted_words, reasons_dict, book_category_codes, sensitive_brand_words, approved_book_sellers)

        # Split into approved and rejected
        approved_df = final_report_df[final_report_df['Status'] == 'Approved']
        rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

        # Update sidebar download button data and enable them
        filtered_seller_excel = to_excel_full_data(data.copy(), final_report_df) # Re-generate filtered data excel
        st.sidebar.download_button(label="Filtered Seller Export", data=filtered_seller_excel, file_name=f"Seller_Filtered_Data_{current_date}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", disabled=False, key="filtered_seller_button") # Added key


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

        # Download buttons in main body - 4 Columns
        col1, col2, col3, col4 = st.columns(4)

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

        with col4:
            full_data_excel = to_excel_full_data(data.copy(), final_report_df)
            st.download_button(
                label="Full Data Export",
                data=full_data_excel,
                file_name=f"Full_Data_Export_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


    except Exception as e:
        st.error(f"Error processing the uploaded file: {e}")
        print(f"Exception details: {e}") # Also print to console for full traceback
