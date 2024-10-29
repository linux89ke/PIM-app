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

            # Flag 1: Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            flagged_count = len(missing_color)
            total_flagged_products += flagged_count
            st.write(f"**Flag 1: Missing COLOR** - {flagged_count} products found.")
            st.write(missing_color)

            # Flag 2: Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            flagged_count = len(missing_brand_or_name)
            total_flagged_products += flagged_count
            st.write(f"**Flag 2: Missing BRAND or NAME** - {flagged_count} products found.")
            st.write(missing_brand_or_name)

            # Flag 3: Single-word NAME (but not for "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            flagged_count = len(single_word_name)
            total_flagged_products += flagged_count
            st.write(f"**Flag 3: Single-word NAME** - {flagged_count} products found.")
            st.write(single_word_name)

            # Flag 4: Category and Variation Check
            valid_category_codes = check_variation_data['ID'].tolist()
            category_variation_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes)) & ((data['VARIATION'].isna()) | (data['VARIATION'] == ''))]
            flagged_count = len(category_variation_issues)
            total_flagged_products += flagged_count
            st.write(f"**Flag 4: Missing VARIATION for valid CATEGORY_CODE** - {flagged_count} products found.")
            st.write(category_variation_issues)

            # Flag 5: Generic Brand Check
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]
            flagged_count = len(generic_brand_issues)
            total_flagged_products += flagged_count
            st.write(f"**Flag 5: Generic BRAND** - {flagged_count} products found.")
            st.write(generic_brand_issues)

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
            flagged_count = len(flagged_perfumes_df)
            total_flagged_products += flagged_count
            st.write(f"**Flag 6: Perfume price issues** - {flagged_count} products found.")
            st.write(flagged_perfumes_df)

            # Flag 7: Blacklisted Words in NAME
            def check_blacklist(name):
                return any(black_word.lower() in name.lower() for black_word in blacklisted_words) if isinstance(name, str) else False

            flagged_blacklisted = data[data['NAME'].apply(check_blacklist)]
            flagged_count = len(flagged_blacklisted)
            total_flagged_products += flagged_count
            st.write(f"**Flag 7: Blacklisted words in NAME** - {flagged_count} products found.")
            st.write(flagged_blacklisted)

            # Flag 8: Brand name repeated in NAME
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
            flagged_count = len(brand_in_name)
            total_flagged_products += flagged_count
            st.write(f"**Flag 8: BRAND name repeated in NAME** - {flagged_count} products found.")
            st.write(brand_in_name)

            # Show total number of rows and flagged products
            total_rows = len(data)
            st.write(f"Total number of rows: {total_rows}")
            st.write(f"Total number of flagged products: {total_flagged_products}")

            # Final report and download section (rest of your code)
            # ...
    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
