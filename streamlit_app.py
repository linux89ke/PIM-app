import pandas as pd
import streamlit as st

st.title("Product Validation Tool")

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Process uploaded file
if uploaded_file is not None:
    try:
        # 1. Read the CSV (explicit parameters for encoding and separator)
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')

        # 2. Basic Data Cleaning (strip whitespace and lowercase column names)
        data.columns = [col.strip().lower() for col in data.columns]

        # Print Column Names:** See what columns are actually present.
        st.write("Column Names in Uploaded File:", data.columns.tolist())

        # 3. Displaying Shape and Null
        st.write("Shape of Data:", data.shape)  # Very useful for debugging
        st.dataframe(data.isnull().sum())# Check the columns that has NaN

        # Basic Data Display: Show the first few rows.
        st.write("Preview of Data:")
        st.write(data.head())


    except Exception as e:
        st.error(f"Error processing the uploaded file: {e}")
        st.error(f"Detailed error: {e}")  # Show the full error
