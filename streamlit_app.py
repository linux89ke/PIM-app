import pandas as pd
import streamlit as st
from io import BytesIO

# Function to load the blacklisted words from a file
def load_blacklisted_words():
    with open('blacklisted.txt', 'r') as f:
        return [line.strip() for line in f.readlines()]

# Load data for checks
check_variation_data = pd.read_excel('check_variation.xlsx')
category_fas_data = pd.read_excel('category_FAS.xlsx')
perfumes_data = pd.read_excel('perfumes.xlsx')
blacklisted_words = load_blacklisted_words()

# Streamlit app layout
st.title("Product Validation Tool")

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Check if the file is uploaded
if uploaded_file is not None:
    try:
        # Load the uploaded CSV file and display the column names
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        st.write("CSV file loaded successfully. Available columns:", data.columns.tolist())

        # Rename columns as necessary if any column names don't match
        column_map = {
            'product_set_id': 'PRODUCT_SET_ID',
            'product_set_sid': 'PRODUCT_SET_SID',
            'name': 'NAME',
            'brand': 'BRAND',
            'category': 'CATEGORY',
            'parentsku': 'PARENTSKU',
            'seller_name': 'SELLER_NAME',
            'category_code': 'CATEGORY_CODE',
            'global_price': 'GLOBAL_PRICE'
        }
        data = data.rename(columns={col: column_map[col.lower()] for col in data.columns if col.lower() in column_map})

        # Initialize counters for flagged products
        total_flagged_products = 0

        # Check for required columns after renaming
        required_columns = ['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            st.error(f"The following required columns are missing from the uploaded file: {missing_columns}")
        else:
            # Proceed with flagging as originally coded
            # (Include all flagging logic here, ensuring all references to columns use the renamed version)
            # Example for Missing COLOR flag:
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            missing_color_count = len(missing_color)

            # Similarly, proceed with the other flags
            # ...
            # Display each flag's count and details using expanders as in the original code
            
            # Prepare final report and add download buttons as in the original code

    except Exception as e:
        st.error(f"An error occurred: {e}")
