import pandas as pd
import streamlit as st
from io import BytesIO

# Load data for checks (assume these are preloaded files available in the directory)
check_variation_data = pd.read_excel('check_variation.xlsx')
category_fas_data = pd.read_excel('category_FAS.xlsx')
perfumes_data = pd.read_excel('perfumes.xlsx')
blacklisted_words = ['example_blacklist_word1', 'example_blacklist_word2']  # Load blacklisted words as a list

# Streamlit app layout
st.title("Product Validation Tool")

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

if uploaded_file is not None:
    try:
        # Load the uploaded CSV file
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        st.write("CSV file loaded successfully. Preview of data:")
        st.write(data.head())

        # Flag 1: Missing COLOR
        missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]

        # Flag 2: Missing BRAND or NAME
        missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]

        # Flag 3: Single-word NAME (but not for "Jumia Book" BRAND)
        single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]

        # Flag 4: Generic Brand Check
        valid_category_codes_fas = category_fas_data['ID'].tolist()
        generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]

        # Flag 5: Perfume price issues based on keywords
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

        # Flag 6: Blacklisted Words in NAME
        flagged_blacklisted = data[data['NAME'].apply(lambda x: any(word in x for word in blacklisted_words) if isinstance(x, str) else False)]

        # Flag 7: BRAND name repeated in NAME
        brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

        # Display flags with collapsible sections
        st.subheader("Flagged Products")

        with st.expander(f"Missing COLOR ({len(missing_color)})"):
            st.write(missing_color[['PRODUCT_SET_ID', 'NAME', 'BRAND', 'COLOR']])

        with st.expander(f"Missing BRAND or NAME ({len(missing_brand_or_name)})"):
            st.write(missing_brand_or_name[['PRODUCT_SET_ID', 'NAME', 'BRAND']])

        with st.expander(f"Single-word NAME ({len(single_word_name)})"):
            st.write(single_word_name[['PRODUCT_SET_ID', 'NAME', 'BRAND']])

        with st.expander(f"Generic BRAND for valid CATEGORY_CODE ({len(generic_brand_issues)})"):
            st.write(generic_brand_issues[['PRODUCT_SET_ID', 'NAME', 'BRAND', 'CATEGORY_CODE']])

        with st.expander(f"Perfume price issue ({len(flagged_perfumes_df)})"):
            st.write(flagged_perfumes_df[['PRODUCT_SET_ID', 'NAME', 'BRAND', 'GLOBAL_PRICE']])

        with st.expander(f"Blacklisted words in NAME ({len(flagged_blacklisted)})"):
            st.write(flagged_blacklisted[['PRODUCT_SET_ID', 'NAME', 'BRAND']])

        with st.expander(f"BRAND name repeated in NAME ({len(brand_in_name)})"):
            st.write(brand_in_name[['PRODUCT_SET_ID', 'NAME', 'BRAND']])

    except Exception as e:
        st.error(f"An error occurred: {e}")
else:
    st.info("Please upload a CSV file to proceed.")
