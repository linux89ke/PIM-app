import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

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

# Function to load book category codes from Excel file
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

# Validation check functions (modularized) - No changes needed in these functions
def check_missing_color(data, book_category_codes):
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    missing_color_non_books = non_book_data[non_book_data['COLOR'].isna() | (non_book_data['COLOR'] == '')]
    return missing_color_non_books

def check_missing_brand_or_name(data):
    return data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]

def check_single_word_name(data, book_category_codes):
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_book_data[(non_book_data['NAME'].str.split().str.len() == 1) & (non_book_data['BRAND'] != 'Jumia Book')]

def check_generic_brand_issues(data, valid_category_codes_fas):
    return data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]

def check_perfume_price_issues(data, perfumes_data):
    flagged_perfumes = []
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
    return pd.DataFrame(flagged_perfumes)

def check_blacklisted_words(data, blacklisted_words):
    return data[data['NAME'].apply(lambda name:
        any(black_word.lower() in str(name).lower().split() for black_word in blacklisted_words))]

def check_brand_in_name(data):
    return data[data.apply(lambda row:
        isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and
        row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

def check_duplicate_products(data):
    return data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]

def check_long_product_name(data, max_words=10): # Make max_words configurable later if needed
    return data[data['NAME'].str.split().str.len() > max_words]


def validate_products(data, config_data, blacklisted_words, reasons_dict, book_category_codes): # Added book_category_codes
    valid_category_codes_fas = config_data['category_fas']['ID'].tolist()
    perfumes_data = config_data['perfumes']

    book_category_codes_str = [str(code) for code in book_category_codes] # Convert book category codes to strings

    # Debug print to check book_category_codes in validate_products (FUNCTION ENTRY POINT)
    print("\nvalidate_products - Book Category Codes:\n", book_category_codes_str)

    data['CATEGORY_CODE'] = data['CATEGORY_CODE'].astype(str) # Convert CATEGORY_CODE column to string

    missing_color = check_missing_color(data, book_category_codes_str) # Use string codes
    missing_brand_or_name = check_missing_brand_or_name(data)
    single_word_name = check_single_word_name(data, book_category_codes_str) # Use string codes

    # Debug print to check single_word_name DataFrame
    print("\nDataFrame from check_single_word_name:\n", single_word_name[['PRODUCT_SET_SID', 'CATEGORY_CODE', 'NAME', 'BRAND']].to_string())

    generic_brand_issues = check_generic_brand_issues(data, valid_category_codes_fas)
    perfume_price_issues = check_perfume_price_issues(data, perfumes_data)
    flagged_blacklisted = check_blacklisted_words(data, blacklisted_words)
    brand_in_name_issues = check_brand_in_name(data)
    duplicate_products = check_duplicate_products(data)
    long_product_name = check_long_product_name(data)

    # Define flags and rejection reasons directly in code (no changes here)
    flags = {
        "Missing COLOR": ("MC", "Missing Color", "Color is mandatory"),
        "Missing BRAND or NAME": ("BNM", "Missing Brand or Name", "Brand and Name are essential"),
        "Single-word NAME": ("SWN", "Single-word Name", "Name should be descriptive"),
        "Generic BRAND Issues": ("GB", "Generic BRAND", "Use specific brand for FAS"),
        "Perfume price issue": ("PPI", "Perfume Price Issue", "Price below configured threshold"),
        "Blacklisted word in NAME": ("BLW", "Blacklisted word in NAME", "Inappropriate word used"),
        "BRAND name repeated in NAME": ("BRN", "BRAND name repeated in NAME", "Redundant brand name in product name"),
        "Duplicate product": ("DUP", "Duplicate product", "Product is a duplicate listing"),
        "Long Product Name": ("LPN", "Product Name Too Long", "Keep product names concise"),
        "Missing COLOR (Books Exempt)": ("MC_BOOKS_EXEMPT", "Missing Color (Exempt Books)", "Color is mandatory except for books") # Example new flag - for books

    }

    final_report_rows = []
    for _, row in data.iterrows():
        reason = None
        reason_details = None

        validations = [
            (missing_color, "Missing COLOR"),
            (missing_brand_or_name, "Missing BRAND or NAME"),
            (single_word_name, "Single-word NAME"),
            (generic_brand_issues, "Generic BRAND Issues"),
            (perfume_price_issues, "Perfume price issue"),
            (flagged_blacklisted, "Blacklisted word in NAME"),
            (brand_in_name_issues, "BRAND name repeated in NAME"),
            (duplicate_products, "Duplicate product"),
            (long_product_name, "Long Product Name")
        ]

        for validation_df, flag_name in validations:
            if not validation_df.empty and row['PRODUCT_SET_SID'] in validation_df['PRODUCT_SET_SID'].values:
                reason = flag_name
                reason_details = flags.get(flag_name, ("", "", "")) # Get reason details from in-code dict
                break

        status = 'Rejected' if reason else 'Approved'
        reason_code, reason_message, comment = flags.get(reason, ("", "", "")) if reason else ("", "", "")
        detailed_reason = f"{reason_code} - {reason_message}" if reason_code and reason_message else ""

        report_reason_message = reason_message if reason_message else reason # Fallback to flag name if no message

        final_report_rows.append({
            'ProductSetSid': row['PRODUCT_SET_SID'],
            'ParentSKU': row.get('PARENTSKU', ''),
            'Status': status,
            'Reason': report_reason_message, # Use the message for final report
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
book_category_codes = load_book_category_codes() # Load book category codes
print("\nLoaded Book Category Codes (from Books_cat.txt) at app start:\n", book_category_codes) # DEBUG PRINT - CHECK BOOK CAT CODES LOADED

# Load reasons dictionary from reasons.xlsx
reasons_df = config_data.get('reasons', pd.DataFrame()) # Load reasons.xlsx
reasons_dict = {}
if not reasons_df.empty:
    for _, row in reasons_df.iterrows():
        reason_text = row['CODE - REJECTION_REASON'] # Correct column name
        reason_parts = reason_text.split(' - ', 1) # Split into code and message
        code = reason_parts[0] # Extract code
        message = row['CODE - REJECTION_REASON'] #MESSAGE
        comment = "See rejection reasons documentation for details" # Default comment
        reasons_dict[f"{code} - {message}"] = (code, message, comment) # Create reasons_dict
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
        st.dataframe(data.head(10)) # Display more rows in preview

        # Validation and report generation
        final_report_df = validate_products(data, config_data, blacklisted_words, reasons_dict, book_category_codes) # Pass book_category_codes

        # Split into approved and rejected
        approved_df = final_report_df[final_report_df['Status'] == 'Approved']
        rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

        # Display results metrics
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Products", len(data))
            st.metric("Approved Products", len(approved_df))
        with col2:
            st.metric("Rejected Products", len(rejected_df))
            st.metric("Rejection Rate", f"{(len(rejected_df)/len(data)*100):.1f}%")

        # Show detailed results in expanders (using flags list for titles)
        validation_results = [
            ("Missing COLOR", check_missing_color(data, book_category_codes)), # Pass book_category_codes
            ("Missing BRAND or NAME", check_missing_brand_or_name(data)),
            ("Single-word NAME", check_single_word_name(data, book_category_codes)), # Pass book_category_codes
            ("Generic BRAND Issues", check_generic_brand_issues(data, config_data['category_fas']['ID'].tolist())),
            ("Perfume Price Issues", check_perfume_price_issues(data, config_data['perfumes'])),
            ("Blacklisted Words", check_blacklisted_words(data, blacklisted_words)),
            ("Brand in Name", check_brand_in_name(data)),
            ("Duplicate Products", check_duplicate_products(data)),
            ("Long Product Name", check_long_product_name(data))
        ]

        for title, df in validation_results:
            with st.expander(f"{title} ({len(df)} products)"):
                if not df.empty:
                    st.dataframe(df)
                else:
                    st.write("No issues found")

        # Export functions
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
