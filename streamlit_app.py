import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import time  # Import time module for timing

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

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
        book_cat_df = pd.read_excel('Books_cat.xlsx') # Load from Excel
        return book_cat_df['CategoryCode'].astype(str).tolist()  # Extract CategoryCode column as string list
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

# Load and validate configuration files (excluding flags.xlsx)
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

# Validation check functions (modularized)
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

def check_perfume_price_issues(data, perfumes_data): # Optimized function
    if perfumes_data.empty or data.empty: # Quick return if either DataFrame is empty
        return pd.DataFrame()

    # 1. Merge data and perfumes_data based on 'BRAND'
    merged_df = pd.merge(data, perfumes_data, on='BRAND', how='inner')

    # 2. Filter rows where keyword is in NAME (case-insensitive)
    merged_df['keyword_found'] = merged_df.apply(
        lambda row: isinstance(row['NAME'], str) and row['KEYWORD'].lower() in row['NAME'].lower(), axis=1 # Still using apply here, can be improved more if needed but more readable
    )
    filtered_perfumes = merged_df[merged_df['keyword_found']]

    # 3. Filter for price issues
    flagged_perfumes = filtered_perfumes[filtered_perfumes['GLOBAL_PRICE'] < filtered_perfumes['PRICE']]

    if not flagged_perfumes.empty: # Select only columns from original 'data' DataFrame to match original function's return
        return data[data['PRODUCT_SET_SID'].isin(flagged_perfumes['PRODUCT_SET_SID'])]
    else:
        return pd.DataFrame()


def check_blacklisted_words(data, blacklisted_words):
    return data[data['NAME'].apply(lambda name:
        any(black_word.lower() in str(name).lower().split() for black_word in blacklisted_words))]

def check_brand_in_name(data):
    return data[data.apply(lambda row:
        isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and
        row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

def check_duplicate_products(data):
    return data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]

def check_sensitive_brands(data, sensitive_brand_words): # New check function
    return data[data.apply(lambda row:
        any(sensitive_word.lower() in str(row['NAME']).lower().split() for sensitive_word in sensitive_brand_words) or
        (isinstance(row['BRAND'], str) and any(sensitive_word.lower() in row['BRAND'].lower().split() for sensitive_word in sensitive_brand_words)), axis=1)]


def validate_products(data, config_data, blacklisted_words, reasons_dict, book_category_codes, sensitive_brand_words): # Added book_category_codes
    validations = [
        (check_missing_color, "Missing COLOR", {'book_category_codes': book_category_codes}), # Specify arguments for each function
        (check_missing_brand_or_name, "Missing BRAND or NAME", {}), # No extra arguments needed
        (check_single_word_name, "Single-word NAME", {'book_category_codes': book_category_codes}),
        (check_generic_brand_issues, "Generic BRAND Issues", {'valid_category_codes_fas': config_data['category_fas']['ID'].tolist()}),
        (check_perfume_price_issues, "Perfume price issue", {'perfumes_data': config_data['perfumes']}),
        (check_sensitive_brands, "Sensitive Brand", {'sensitive_brand_words': sensitive_brand_words}), # New Validation
        (check_blacklisted_words, "Blacklisted word in NAME", {'blacklisted_words': blacklisted_words}),
        (check_brand_in_name, "BRAND name repeated in NAME", {}),
        (check_duplicate_products, "Duplicate product", {}),

    ]

    final_report_rows = []
    for _, row in data.iterrows():
        reasons = [] # Changed to list to hold multiple reasons

        for check_func, flag_name, func_kwargs in validations:
            start_time = time.time() # <---- Start timing
            kwargs = {'data': data, **func_kwargs}
            validation_df = check_func(**kwargs)
            end_time = time.time() # <---- End timing
            elapsed_time = end_time - start_time
            print(f"Validation '{flag_name}' took: {elapsed_time:.4f} seconds") # <---- Print timing

            if not validation_df.empty and row['PRODUCT_SET_SID'] in validation_df['PRODUCT_SET_SID'].values:
                reason_details = reasons_dict.get(flag_name, ("", "", "")) # Renamed flags to reasons_dict
                reason_code, reason_message, comment = reason_details
                detailed_reason = f"{reason_code} - {reason_message}" if reason_code and reason_message else flag_name
                reasons.append(detailed_reason) # Append reason to list

        status = 'Rejected' if reasons else 'Approved' # Check if reasons list is empty
        # Join multiple reasons into single string for report
        report_reason_message = "; ".join(reasons) if reasons else ""
        comment = "; ".join([reasons_dict.get(reason_name, ("", "", ""))[2] for reason_name in reasons]) if reasons else "" # Combine comments # Renamed flags to reasons_dict

        final_report_rows.append({
            'ProductSetSid': row['PRODUCT_SET_SID'],
            'ParentSKU': row.get('PARENTSKU', ''),
            'Status': status,
            'Reason': report_reason_message, # Use joined reason messages
            'Comment': comment if comment else "See rejection reasons documentation for details" # Default comment if no comment from Excel
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
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')

        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()

        st.write("CSV file loaded successfully. Preview of data:")
        st.dataframe(data.head(10))

        # Validation and report generation - pass sensitive_brand_words & book_category_codes
        final_report_df = validate_products(data, config_data, blacklisted_words, reasons_dict, book_category_codes, sensitive_brand_words)

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

        # Validation results expanders - Updated to include "Sensitive Brand Issues"
        validation_results = [
            ("Missing COLOR", check_missing_color(data, book_category_codes)),
            ("Missing BRAND or NAME", check_missing_brand_or_name(data)),
            ("Single-word NAME", check_single_word_name(data, book_category_codes)),
            ("Generic BRAND Issues", check_generic_brand_issues(data, config_data['category_fas']['ID'].tolist())),
            ("Perfume Price Issues", check_perfume_price_issues(data, config_data['perfumes'])),
            ("Sensitive Brand Issues", check_sensitive_brands(data, sensitive_brand_words)), # New expander
            ("Blacklisted Words", check_blacklisted_words(data, blacklisted_words)),
            ("Brand in Name", check_brand_in_name(data)),
            ("Duplicate Products", check_duplicate_products(data)),
        ]

        for title, df in validation_results:
            with st.expander(f"{title} ({len(df)} products)"):
                if not df.empty:
                    st.dataframe(df)
                else:
                    st.write("No issues found")

        # Export functions - No change
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
