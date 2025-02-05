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
        'reasons': 'reasons.xlsx'
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
        validation_results["Single-word NAME"] = data[(data['name'].str.split().str.len() == 1) &
                              (~data['category_code'].isin(book_category_brands))]

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
