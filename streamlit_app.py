import streamlit as st
import pandas as pd

# Load auxiliary files for flag checks
category_fas_data = pd.read_excel('category_FAS.xlsx')
reasons_data = pd.read_excel('reasons.xlsx')  # This file should contain flagging codes and reasons

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

            # Define flags
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(category_fas_data['ID'].tolist())) & (data['BRAND'] == 'Generic')]
            duplicate_products = data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]
            perfumes_price_issues = data[(data['CATEGORY'] == 'Perfume') & (data['GLOBAL_SALE_PRICE'] < data['PRICE'] * 0.7)]
            blacklisted_words_issues = data[data['NAME'].str.contains('|'.join(['blacklisted_word1', 'blacklisted_word2']), case=False, na=False)]
            brand_repetition_in_name = data[data['NAME'].str.contains(data['BRAND'], case=False, na=False)]
            
            # Display results with expanders
            with st.expander(f"Missing COLOR ({len(missing_color)} products)"):
                if len(missing_color) > 0:
                    st.write(missing_color[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged for missing COLOR.")

            with st.expander(f"Missing BRAND or NAME ({len(missing_brand_or_name)} products)"):
                if len(missing_brand_or_name) > 0:
                    st.write(missing_brand_or_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged for missing BRAND or NAME.")

            with st.expander(f"Single-word NAME ({len(single_word_name)} products)"):
                if len(single_word_name) > 0:
                    st.write(single_word_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged for single-word NAME.")

            with st.expander(f"Generic BRAND for valid CATEGORY_CODE ({len(generic_brand_issues)} products)"):
                if len(generic_brand_issues) > 0:
                    st.write(generic_brand_issues[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged for Generic BRAND.")

            with st.expander(f"Duplicate Products ({len(duplicate_products)} products)"):
                if len(duplicate_products) > 0:
                    st.write(duplicate_products[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged as duplicates.")

            with st.expander(f"Perfume Price Issues ({len(perfumes_price_issues)} products)"):
                if len(perfumes_price_issues) > 0:
                    st.write(perfumes_price_issues[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged for perfume price issues.")

            with st.expander(f"Blacklisted Words in NAME ({len(blacklisted_words_issues)} products)"):
                if len(blacklisted_words_issues) > 0:
                    st.write(blacklisted_words_issues[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged for blacklisted words in NAME.")

            with st.expander(f"Brand Name Repeated in NAME ({len(brand_repetition_in_name)} products)"):
                if len(brand_repetition_in_name) > 0:
                    st.write(brand_repetition_in_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged for brand name repetition in NAME.")

    except Exception as e:
        st.error(f"An error occurred: {e}")
