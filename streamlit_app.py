import pandas as pd
import streamlit as st

# Function to flag products based on blacklisted words in NAME
def flag_blacklisted_words(data, blacklist):
    flagged = data[data['NAME'].str.contains('|'.join(blacklist), case=False, na=False)]
    return flagged

# Function to validate and process the uploaded CSV file
def validate_products(uploaded_file, blacklist):
    try:
        # Read the uploaded CSV file
        data = pd.read_csv(uploaded_file)
        
        # Print DataFrame structure for debugging
        st.write("DataFrame loaded successfully.")
        st.write("Columns:", data.columns.tolist())
        
        # Check for missing COLOR
        missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
        st.write(f"Found {len(missing_color)} products with missing COLOR fields.")
        
        # Check for missing BRAND or NAME
        missing_brand_or_name = data[data['BRAND'].isna() | (data['NAME'].isna())]
        st.write(f"Found {len(missing_brand_or_name)} products with missing BRAND or NAME.")
        
        # Check for single-word NAME
        single_word_name = data[data['NAME'].str.split().str.len() == 1]
        st.write(f"Found {len(single_word_name)} products with a single-word NAME.")
        
        # Check for GENERIC brand with valid CATEGORY_CODE
        generic_brand = data[(data['BRAND'] == 'Generic') & (data['CATEGORY_CODE'].notna())]
        st.write(f"Found {len(generic_brand)} products with GENERIC brand for valid CATEGORY_CODE.")
        
        # Check for blacklisted words in NAME
        flagged_blacklisted = flag_blacklisted_words(data, blacklist)
        st.write(f"Found {len(flagged_blacklisted)} products flagged due to blacklisted words in NAME.")

        # Check for BRAND name in NAME
        brand_in_name = data[data['NAME'].str.contains(data['BRAND'], na=False)]
        st.write(f"Found {len(brand_in_name)} products with the BRAND name in NAME.")

        # Check for the PRODUCT_SET_SID column
        if 'PRODUCT_SET_SID' in data.columns:
            st.write("PRODUCT_SET_SID column exists.")
            # Here, you can add more processing related to PRODUCT_SET_SID if needed
        else:
            st.error("PRODUCT_SET_SID column is missing in the data.")

    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")

# Load the blacklist from a text file
def load_blacklist(file_path):
    try:
        with open(file_path, 'r') as f:
            blacklist = f.read().splitlines()
        return blacklist
    except Exception as e:
        st.error(f"Error loading blacklist: {e}")
        return []

# Streamlit interface
st.title("Product Validation Tool")
uploaded_file = st.file_uploader("Upload your CSV file", type="csv")

# Load the blacklist of words
blacklist_file = 'blacklisted.txt'  # Specify the path to your blacklist file
blacklist = load_blacklist(blacklist_file)

if uploaded_file:
    validate_products(uploaded_file, blacklist)
