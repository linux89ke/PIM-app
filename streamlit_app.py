import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
from collections import OrderedDict  # For keeping track of validation results

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# --- Function Definitions (Keep these at the top) ---

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

# Load sensitive brands from the sensitive_brands.xlsx file
def load_sensitive_brands():
    try:
        sensitive_brands_df = pd.read_excel('sensitive_brands.xlsx')
        return sensitive_brands_df['BRAND'].tolist()  # Assuming the file has a 'Brand' column
    except FileNotFoundError:
        st.error("sensitive_brands.xlsx file not found!")
        return []
    except Exception as e:
        st.error(f"Error loading sensitive brands: {e}")
        return []

# Load category_FAS.xlsx to get the allowed CATEGORY_CODE values
def load_category_FAS():
    try:
        category_fas_df = pd.read_excel('category_FAS.xlsx')
        return category_fas_df['ID'].tolist()  # Assuming 'ID' column contains the category codes
    except FileNotFoundError:
        st.error("category_FAS.xlsx file not found!")
        return []
    except Exception as e:
        st.error(f"Error loading category_FAS data: {e}")
        return []

# Load and validate configuration files
def load_config_files():
    config_files = {
        'flags': 'flags.xlsx',
        'check_variation': 'check_variation.xlsx',
        'category_fas': 'category_FAS.xlsx',
        'perfumes': 'perfumes.xlsx',
        'reasons': 'reasons.xlsx'  # Adding reasons.xlsx
    }

    data = {}
    for key, filename in config_files.items():
        try:
            df = pd.read_excel(filename).rename(columns=lambda x: x.strip())  # Strip spaces from column names
            data[key] = df
        except Exception as e:
            st.error(f"❌ Error loading {filename}: {e}")
            st.error(f"Detailed error: {e}") # **Crucial:** Show the detailed error
            if key == 'flags':  # flags.xlsx is critical
                st.stop()
    return data

# Function to load allowed book sellers
def load_allowed_book_sellers():
    try:
        with open('Books.txt', 'r') as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        st.error("Books.txt file not found!")
        return []
    except Exception as e:
        st.error(f"Error loading allowed book sellers: {e}")
        return []

# Function to load book category names
def load_book_category_brands():
    try:
        with open('Books_cat.txt', 'r') as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        st.error("Books_cat.txt file not found!")
        return []
    except Exception as e:
        st.error(f"Error loading book category names: {e}")
        return []

# --- Main Streamlit App ---

# Initialize the app
st.title("Product Validation Tool")

# Load configuration files
try:
    config_data = load_config_files()
except Exception as e:
    st.error(f"Failed to load configuration files: {e}")
    st.stop()

# Load category_FAS and sensitive brands
try:
    category_FAS_codes = load_category_FAS()
    sensitive_brands = load_sensitive_brands()
except Exception as e:
    st.error(f"Failed to load category or sensitive brand data: {e}")
    st.stop()

# Load blacklisted words
try:
    blacklisted_words = load_blacklisted_words()
except Exception as e:
    st.error(f"Failed to load blacklisted words: {e}")
    st.stop()

# Load allowed book sellers and book brands
try:
    allowed_book_sellers = load_allowed_book_sellers()
    book_category_brands = load_book_category_brands()
except Exception as e:
    st.error(f"Failed to load book seller data: {e}")
    st.stop()

# Load and process flags data
flags_data = config_data['flags']
reasons_dict = {}
try:
    # Find the correct column names (case-insensitive)
    flag_col = next((col for col in flags_data.columns if col.lower() == 'flag'), None)
    reason_col = next((col for col in flags_data.columns if col.lower() == 'reason'), None)
    comment_col = next((col for col in flags_data.columns if col.lower() == 'comment'), None)

    if not all([flag_col, reason_col, comment_col]):
        st.error(f"Missing required columns in flags.xlsx. Required: Flag, Reason, Comment. Found: {flags_data.columns.tolist()}")
        st.stop()

    for _, row in flags_data.iterrows():
        flag = str(row[flag_col]).strip()
        reason = str(row[reason_col]).strip()
        comment = str(row[comment_col]).strip()
        reason_parts = reason.split(' - ', 1)
        code = reason_parts[0]
        message = reason_parts[1] if len(reason_parts) > 1 else ''
        reasons_dict[flag] = (code, message, comment)
except Exception as e:
    st.error(f"Error processing flags data: {e}")
    st.error(f"Detailed error: {e}")
    st.stop()

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Process uploaded file
if uploaded_file is not None:
    try:
        # **Immediate Feedback:**  Before reading, tell the user something is happening.
        st.info("Loading and processing your CSV file...")

        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')

        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()

        # **Debug: Print Column Names:** See what columns are actually present.
        st.write("Column Names in Uploaded File:", data.columns.tolist())

        st.write("CSV file loaded successfully. Preview of data:")
        st.write(data.head())

        # Validation checks
        missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
        missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') |
                                   data['NAME'].isna() | (data['NAME'] == '')]
        single_word_name = data[(data['NAME'].str.split().str.len() == 1) &
                              (data['BRAND'] != 'Jumia Book')]

        # Category validation
        valid_category_codes_fas = config_data['category_fas']['ID'].tolist()
        generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) &
                                  (data['BRAND'] == 'Generic')]

        # Perfume price validation
        flagged_perfumes = []
        perfumes_data = config_data['perfumes']
        for _, row in data.iterrows():
            brand = row['BRAND']
            if brand in perfumes_data['BRAND'].values:
                keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                for keyword in keywords:
                    if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                        perfume_price = perfumes_data.loc[
                            (perfumes_data['BRAND'] == brand) &
                            (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                        if row['GLOBAL_PRICE'] < perfume_price:
                            flagged_perfumes.append(row)
                            break

        # Blacklist and brand name checks
        flagged_blacklisted = data[data['NAME'].apply(lambda name:
            any(black_word.lower() in str(name).lower().split() for black_word in blacklisted_words))]

        brand_in_name = data[data.apply(lambda row:
            isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and
            row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

        duplicate_products = data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]

        # **Book Seller Check (Modified):**
        invalid_book_sellers = data[
            (data['BRAND'].isin(book_category_brands)) &  # Is it a book?
            (data['SELLER_NAME'].isin(allowed_book_sellers)) &  # Seller is allowed...
            (~data['CATEGORY_CODE'].isin(book_category_brands)) #but Category Code not in book category list
        ]
        # **Sensitive Brands Flag (only for categories in category_FAS.xlsx)**
        sensitive_brand_issues = data[
            (data['CATEGORY_CODE'].isin(category_FAS_codes)) &
            (data['BRAND'].isin(sensitive_brands))
        ]

        # --- Track Validation Results using OrderedDict ---
        validation_results = OrderedDict()  # Order matters

        # Use PRODUCT_SET_SID to identify rows in the validation results
        validation_results["Missing COLOR"] = missing_color
        validation_results["Missing BRAND or NAME"] = missing_brand_or_name
        validation_results["Single-word NAME"] = single_word_name
        validation_results["Generic BRAND"] = generic_brand_issues
        validation_results["Blacklisted word in NAME"] = flagged_blacklisted
        validation_results["BRAND name repeated in NAME"] = brand_in_name
        validation_results["Duplicate product"] = duplicate_products
        validation_results["Sensitive Brand"] = sensitive_brand_issues
        validation_results["Invalid Book Seller"] = invalid_book_sellers

        # Generate report with a single reason per rejection

        final_report_rows = []
        for _, row in data.iterrows():
            reason = None
            reason_details = None

            # Book seller check first: If an invalid book seller, reject immediately
            if (row['BRAND'] in book_category_brands) and (row['SELLER_NAME'] in allowed_book_sellers) and (row['CATEGORY_CODE'] not in book_category_brands):
                reason = "Invalid Book Seller"
                reason_details = reasons_dict.get("Invalid Book Seller", ("", "", ""))

            else:  # Only check other reasons if the book seller check passes.
                # Check all validation conditions in a specific order and take the first applicable one
                #
                for flag, validation_df in validation_results.items():
                    # Add a check to ensure 'PRODUCT_SET_SID' exists in the validation_df before accessing it
                    if 'PRODUCT_SET_SID' in validation_df.columns and row['PRODUCT_SET_SID'] in validation_df['PRODUCT_SET_SID'].values:
                        reason = flag  # Use the Key from  validation_results
                        reason_details = reasons_dict.get(flag, ("", "", ""))  # get
                        break  # Stop after finding the first applicable reason

            # Check perfume price issues separately
            if not reason and row['PRODUCT_SET_SID'] in [r['PRODUCT_SET_SID'] for r in flagged_perfumes]:
                reason = "Perfume price issue"
                reason_details = reasons_dict.get("Perfume price issue", ("", "", ""))

            # Prepare report row
            status = 'Rejected' if reason else 'Approved'
            reason_code, reason_message, comment = reason_details if reason_details else ("", "", "")
            detailed_reason = f"{reason_code} - {reason_message}" if reason_code and reason_message else ""

            final_report_rows.append({
                'ProductSetSid': row['PRODUCT_SET_SID'],
                'ParentSKU': row.get('PARENTSKU', ''),
                'Status': status,
                'Reason': detailed_reason,
                'Comment': comment
            })

        # Create final report DataFrame
        final_report_df = pd.DataFrame(final_report_rows)

        # Split into approved and rejected
        approved_df = final_report_df[final_report_df['Status'] == 'Approved']
        rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

        # Display results
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Products", len(data))
            st.metric("Approved Products", len(approved_df))
        with col2:
            st.metric("Rejected Products", len(rejected_df))
            st.metric("Rejection Rate", f"{(len(rejected_df) / len(data) * 100):.1f}%")

        # Show detailed results in expanders
        for title, df in validation_results.items():
            with st.expander(f"{title} ({len(df)} products)"):
                if not df.empty:
                    st.dataframe(df)
                else:
                    st.write("No issues found")

        # Export functions
        @st.cache_data
        def to_excel(df1, df2, sheet1_name="ProductSets", sheet2_name="RejectionReasons"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df1.to_excel(writer, index=False, sheet_name=sheet1_name)
                df2.to_excel(writer, index=False, sheet_name=sheet2_name)
            output.seek(0)
            return output

        # Download buttons
        current_date = datetime.now().strftime("%Y-%m-%d")

        col1, col2, col3 = st.columns(3)

        with col1:
            final_report_excel = to_excel(final_report_df, config_data['reasons'], "ProductSets", "RejectionReasons")
            st.download_button(
                label="Final Export",
                data=final_report_excel,
                file_name=f"Final_Report_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with col2:
            rejected_excel = to_excel(rejected_df, config_data['reasons'], "ProductSets", "RejectionReasons")
            st.download_button(
                label="Rejected Export",
                data=rejected_excel,
                file_name=f"Rejected_Products_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with col3:
            approved_excel = to_excel(approved_df, config_data['reasons'], "ProductSets", "RejectionReasons")
            st.download_button(
                label="Approved Export",
                data=approved_excel,
                file_name=f"Approved_Products_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Error processing the uploaded file: {e}")
        st.error(f"Detailed error: {e}")  # Show the full error
        st.stop()  # Stop execution after an error

print("test")
