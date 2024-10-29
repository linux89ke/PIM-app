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
            st.write("CSV file loaded successfully. Available columns:")
            st.write(data.columns.tolist())  # Display available columns for reference

            # Initialize counters for flagged products
            total_flagged_products = 0

            # Define columns for each flag's output, handling missing columns
            required_columns = {
                "missing_color": ['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME', 'COLOR'],
                "missing_brand_or_name": ['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME'],
                "single_word_name": ['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME'],
                "category_variation_issues": ['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'CATEGORY_CODE', 'PARENTSKU', 'SELLER_NAME', 'VARIATION'],
                "generic_brand_issues": ['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'CATEGORY_CODE', 'PARENTSKU', 'SELLER_NAME'],
                "flagged_perfumes": ['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME', 'GLOBAL_PRICE'],
                "flagged_blacklisted": ['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'Blacklisted Word', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME'],
                "brand_in_name": ['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']
            }

            # Helper function to safely display flagged data based on available columns
            def display_flagged_data(dataframe, flag_name):
                columns = [col for col in required_columns[flag_name] if col in dataframe.columns]
                if columns:
                    st.write(f"**Flagged Products for {flag_name.replace('_', ' ').title()}**")
                    st.write(dataframe[columns])
                else:
                    st.write(f"No relevant columns found for {flag_name.replace('_', ' ').title()}")

            # Perform the checks and display the results for each flag

            # Flag 1: Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            display_flagged_data(missing_color, "missing_color")

            # Flag 2: Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            display_flagged_data(missing_brand_or_name, "missing_brand_or_name")

            # Flag 3: Single-word NAME (excluding "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            display_flagged_data(single_word_name, "single_word_name")

            # Flag 4: Category and Variation Check
            valid_category_codes = check_variation_data['ID'].tolist()
            category_variation_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes)) &
                                             ((data['VARIATION'].isna()) | (data['VARIATION'] == ''))]
            display_flagged_data(category_variation_issues, "category_variation_issues")

            # Flag 5: Generic Brand Check
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]
            display_flagged_data(generic_brand_issues, "generic_brand_issues")

            # Flag 6: Price and Keyword Check (Perfume Check)
            perfumes_data = perfumes_data.sort_values(by="PRICE", ascending=False).drop_duplicates(subset=["BRAND", "KEYWORD"], keep="first")
            flagged_perfumes = []
            for index, row in data.iterrows():
                brand = row['BRAND']
                if brand in perfumes_data['BRAND'].values:
                    keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                    for keyword in keywords:
                        if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                            perfume_price = perfumes_data.loc[(perfumes_data['BRAND'] == brand) & (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                            price_difference = row['GLOBAL_PRICE'] - perfume_price
                            if price_difference < 0:
                                flagged_perfumes.append(row)
                                break
            flagged_perfumes_df = pd.DataFrame(flagged_perfumes)
            display_flagged_data(flagged_perfumes_df, "flagged_perfumes")

            # Flag 7: Blacklisted Words in NAME
            def find_blacklisted_words(name):
                found_words = [black_word for black_word in blacklisted_words if isinstance(name, str) and black_word.lower() in name.lower()]
                return ", ".join(found_words) if found_words else None

            data['Blacklisted Word'] = data['NAME'].apply(find_blacklisted_words)
            flagged_blacklisted = data[data['Blacklisted Word'].notna()]
            display_flagged_data(flagged_blacklisted, "flagged_blacklisted")

            # Flag 8: Brand name repeated in NAME (case-insensitive)
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
            display_flagged_data(brand_in_name, "brand_in_name")

            # Summary
            st.write("Data processing complete. Check flagged sections above for each flag's results.")
    
    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
