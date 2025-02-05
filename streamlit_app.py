import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
from collections import OrderedDict  # For keeping track of validation results

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# --- Function Definitions (Keep these at the top) ---

def load_config_files():
    config_files = {
        'flags': 'flags.xlsx',
        'reasons': 'reasons.xlsx'#REASONS
        #'category_fas': 'category_FAS.xlsx',  #NOT NOW
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

config_data = load_config_files() # Load config

# Load book category names
try:
    book_category_brands = load_book_category_brands()
except Exception as e:
    st.error(f"Error loading book category data: {e}")
    st.stop()

# Load allowed book sellers and book brands
try:
    allowed_book_sellers = load_allowed_book_sellers()
except Exception as e:
    st.error(f"Failed to load book seller data: {e}")
    st.stop()

# Load sensitive brands
try:
    sensitive_brands = load_sensitive_brands()
except Exception as e:
    st.error(f"Failed to load sensitive brand data: {e}")
    st.stop()


# Load blacklisted words
try:
    blacklisted_words = load_blacklisted_words()
except Exception as e:
    st.error(f"Failed to load blacklisted words: {e}")
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
        st.info("Loading and processing your CSV file...") # message
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1') #data loaded

        # Strip and Lowercase Column Names:
        data.columns = [col.strip().lower() for col in data.columns]

        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()

        # **Debug: Print Column Names:** See what columns are actually present.
        st.write("Column Names in Uploaded File:", data.columns.tolist())

        st.write("CSV file loaded successfully. Preview of data:")
        st.write(data.head())

        # --- Track Validation Results using OrderedDict ---
        validation_results = OrderedDict()  # Order matters

        # Use PRODUCT_SET_SID to identify rows in the validation results
        validation_results["Missing COLOR"] = data[data['color'].isna() | (data['color'] == '')]

        # Single-word NAME check, EXCLUDING books:
        # Check if category_code exists first (handle possible missing data)
        category_condition = (~data['category_code'].isin(book_category_brands)) if 'category_code' in data else False #New to handle missing row in category codes!

        validation_results["Single-word NAME"] = data[
            (data['name'].str.split().str.len() == 1) &
            category_condition
        ]

        sensitive_brand_issues = data[
            (data['category_code'].isin(category_FAS_codes)) &
            (data['brand'].isin(sensitive_brands))
        ]

        validation_results["Generic BRAND"] = data[(data['category_code'].isin(category_FAS_codes)) &
                                          (data['brand'] == 'generic')] # Check the 'generic BRAND ' column
                                          

        validation_results["Sensitive Brand"] = sensitive_brand_issues  # Load

        validation_results["Blacklisted word in NAME"] = data[data['name'].apply(lambda name:
                any(black_word.lower() in str(name).lower().split() for black_word in blacklisted_words))]  # Use Name List 

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
