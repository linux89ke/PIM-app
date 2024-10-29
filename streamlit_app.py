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
        # Load the uploaded CSV file
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        if not data.empty:
            st.write("CSV file loaded successfully. Preview of data:")
            st.write(data.head())

            # Initialize counters for flagged products
            total_flagged_products = 0

            # Existing flagging logic for other flags (Flag 1 to Flag 6) would go here
            # ...

            # Flag 7: Blacklisted Words in NAME
            def find_blacklisted_words(name):
                found_words = [black_word for black_word in blacklisted_words if isinstance(name, str) and black_word.lower() in name.lower()]
                return ", ".join(found_words) if found_words else None

            # Apply the blacklisted word check and filter flagged entries
            data['Blacklisted Word'] = data['NAME'].apply(find_blacklisted_words)
            flagged_blacklisted = data[data['Blacklisted Word'].notna()]
            
            # Select the specified columns to display
            flagged_blacklisted = flagged_blacklisted[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'Blacklisted Word', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']]
            flagged_count = len(flagged_blacklisted)
            total_flagged_products += flagged_count
            st.write(f"**Flag 7: Blacklisted words in NAME** - {flagged_count} products found.")
            st.write(flagged_blacklisted)

            # Total flagged products and other summary info
            total_rows = len(data)
            st.write(f"Total number of rows: {total_rows}")
            st.write(f"Total number of flagged products: {total_flagged_products}")

            # Final report and download section (rest of your code)
            # ...
    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
