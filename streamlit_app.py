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
            st.error(f"Detailed error: {e}")  # **Crucial:** Show the detailed error
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
    st.stop()

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Process uploaded file
if uploaded_file is not None:
    try:
        # **Immediate Feedback:**  Before reading, tell the user something is happening.
        st.info("Loading and processing your CSV file...")

        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')

        # **Strip and Lowercase Column Names:**  Do this *immediately* after reading.
        data.columns = [col.strip().lower() for col in data.columns]  # Strip and lowercase

        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()

        # **Debug: Print Column Names:** See what columns are actually present.
        st.write("Column Names in Uploaded File:", data.columns.tolist())

        st.write("CSV file loaded successfully. Preview of data:")
        st.write(data.head())

        # Category validation
        valid_category_codes_fas = config_data['category_fas']['ID'].tolist()

        # --- Track Validation Results using OrderedDict ---
        validation_results = OrderedDict()  # Order matters

        # Use PRODUCT_SET_SID to identify rows in the validation results
        validation_results["Missing COLOR"] = data[data['color'].isna() | (data['color'] == '')]
        validation_results["Missing BRAND or NAME"] = data[data['brand'].isna() | (data['brand'] == '') |
                                   data['name'].isna() | (data['name'] == '')]
        validation_results["Single-word NAME"] = data[(data['name'].str.split().str.len() == 1) &
                              (data['brand'] != 'jumia book')]
        validation_results["Generic BRAND"] = data[(data['category_code'].isin(valid_category_codes_fas)) &
                                  (data['brand'] == 'generic')]
        validation_results["Blacklisted word in NAME"] = data[data['name'].apply(lambda name:
            any(black_word.lower() in str(name).lower().split() for black_word in blacklisted_words))]
        validation_results["BRAND name repeated in NAME"] = data[data.apply(lambda row:
            isinstance(row['brand'], str) and isinstance(row['name'], str) and
            row['brand'].lower() in row['name'].lower(), axis=1)]
        # Duplicate product" flag has been removed in this build to check better the process
        #duplicate_products = data[data.duplicated(subset=['name', 'brand', 'seller_name'], keep=False)]
        #validation_results["Duplicate product"] = duplicate_products

        # Sensitive Brands Flag (only for categories in category_FAS.xlsx)
        sensitive_brand_issues = data[
            (data['category_code'].isin(category_FAS_codes)) &
            (data['brand'].isin(sensitive_brands))
        ]
        print("Sensitive Brand issues:") #debugging purpose
        print(sensitive_brand_issues[['product_set_sid', 'brand', 'category_code']]) #check what products are
        validation_results["Sensitive Brand"] = sensitive_brand_issues

        #Book Seller Check:
        invalid_book_sellers = data[
            (data['brand'].isin(book_category_brands)) &  # Is it a book?
            (data['seller_name'].isin(allowed_book_sellers)) &  # Seller is allowed...
            (~data['category_code'].isin(book_category_brands)) #but Category Code not in book category list
        ]
        validation_results["Invalid Book Seller"] = invalid_book_sellers

        # Display results
        for title, df in validation_results.items():
            with st.expander(f"{title} ({len(df)} products)"):
                if not df.empty:
                    st.dataframe(df)
                else:
                    st.write("No issues found")


    except Exception as e:
        st.error(f"Error processing the uploaded file: {e}")
        st.error(f"Detailed error: {e}")
