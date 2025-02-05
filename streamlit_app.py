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


# Initialize the app
st.title("Product Validation Tool")

# Load configuration files
config_data = load_config_files()

# Load category_FAS and sensitive brands
category_FAS_codes = load_category_FAS()
sensitive_brands = load_sensitive_brands()

# Load blacklisted words
blacklisted_words = load_blacklisted_words()

# Load allowed book sellers and book brands
allowed_book_sellers = load_allowed_book_sellers()
book_category_brands = load_book_category_brands()


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
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        
        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()
            
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

         # **Book Seller Check:**
        invalid_book_sellers = data[
            (data['BRAND'].isin(book_category_brands)) &  # Is it a book?
            (~data['SELLER_NAME'].isin(allowed_book_sellers)) #Check if allowed
            ]

        # **Sensitive Brands Flag (only for categories in category_FAS.xlsx)**
        sensitive_brand_issues = data[
            (data['CATEGORY_CODE'].isin(category_FAS_codes)) &
            (data['BRAND'].isin(sensitive_brands))
        ]

        # Generate report with a single reason per rejection
        final_report_rows = []
        for _, row in data.iterrows():
            reason = None
            reason_details = None

            # Check all validation conditions in a specific order and take the first applicable one
            validations = [
                (missing_color, "Missing COLOR"),
                (missing_brand_or_name, "Missing BRAND or NAME"),
                (single_word_name, "Single-word NAME"),
                (generic_brand_issues, "Generic BRAND"),
                (flagged_blacklisted, "Blacklisted word in NAME"),
                (brand_in_name, "BRAND name repeated in NAME"),
                (duplicate_products, "Duplicate product"),
                (sensitive_brand_issues, "Sensitive Brand"),
                (invalid_
