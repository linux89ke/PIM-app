import pandas as pd
import streamlit as st
from io import BytesIO

# Title and file uploader component
st.title("Product Validation: COLOR, NAME, CATEGORY_CODE, Price, and Brand Checks")
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

# Load supporting Excel files with corrected file paths
try:
    check_variation_data = pd.read_excel("check_variation.xlsx")  # Check for category and variation issues
except FileNotFoundError:
    st.warning("check_variation.xlsx not found. Skipping category and variation check.")
    check_variation_data = None

try:
    category_fas_data = pd.read_excel("category_FAS.xlsx")  # Check for generic brand issues
except FileNotFoundError:
    st.warning("category_FAS.xlsx not found. Skipping generic brand check.")
    category_fas_data = None

try:
    perfumes_data = pd.read_excel("perfumes.xlsx")  # Load perfumes data for keyword checks
except FileNotFoundError:
    st.warning("perfumes.xlsx not found. Skipping perfume keyword and price checks.")
    perfumes_data = None

# Check if the file is uploaded
if uploaded_file is not None:
    try:
        # Load the uploaded CSV file
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')

        if not data.empty:
            st.write("CSV file loaded successfully. Preview of data:")
            st.write(data.head())

            # Flag 1: Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            if not missing_color.empty:
                st.error(f"Found {len(missing_color)} products with missing COLOR fields.")
                st.write(missing_color)

            # Add more checks and logic as required...
        
        else:
            st.error("Uploaded file is empty. Please upload a valid CSV file.")
    
    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
else:
    st.info("Please upload a CSV file to continue.")
