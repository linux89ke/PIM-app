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
            'global_price': 'GLOBAL_PRICE',
            'global_sale_price': 'GLOBAL_SALE_PRICE',
            'color': 'COLOR'
        }
        data = data.rename(columns={col: column_map[col.lower()] for col in data.columns if col.lower() in column_map})

        # Initialize counters for flagged products
        total_flagged_products = 0

        # Check for required columns after renaming
        required_columns = ['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME', 'COLOR', 'CATEGORY_CODE', 'GLOBAL_PRICE', 'GLOBAL_SALE_PRICE']
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            st.error(f"The following required columns are missing from the uploaded file: {missing_columns}")
        else:
            # Flag for Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            missing_color_count = len(missing_color)
            total_flagged_products += missing_color_count

            # Flag for Missing BRAND or NAME
            missing_brand_name = data[data['BRAND'].isna() | data['NAME'].isna()]
            missing_brand_name_count = len(missing_brand_name)
            total_flagged_products += missing_brand_name_count

            # Flag for Single-word NAME
            single_word_name = data[data['NAME'].apply(lambda x: len(str(x).split()) == 1)]
            single_word_name_count = len(single_word_name)
            total_flagged_products += single_word_name_count

            # Flag for Generic BRAND for valid CATEGORY_CODE
            generic_brand = data[(data['BRAND'].str.lower() == 'generic') & (data['CATEGORY_CODE'].isin(category_fas_data['ID']))]
            generic_brand_count = len(generic_brand)
            total_flagged_products += generic_brand_count

            # Flag for Perfume price issues
            perfume_issues = data.merge(perfumes_data, left_on='NAME', right_on='PRODUCT_NAME', how='inner')
            perfume_issues = perfume_issues[abs(perfume_issues['GLOBAL_SALE_PRICE'] - perfume_issues['PRICE']) / perfume_issues['PRICE'] < 0.3]
            perfume_issues_count = len(perfume_issues)
            total_flagged_products += perfume_issues_count

            # Flag for blacklisted words in NAME
            blacklisted_name = data[data['NAME'].apply(lambda x: any(word in str(x) for word in blacklisted_words))]
            blacklisted_name_count = len(blacklisted_name)
            total_flagged_products += blacklisted_name_count

            # Display results
            st.write("Flagged Products Summary:")
            with st.expander("Missing COLOR"):
                st.write(f"Total: {missing_color_count}")
                st.dataframe(missing_color)
            
            with st.expander("Missing BRAND or NAME"):
                st.write(f"Total: {missing_brand_name_count}")
                st.dataframe(missing_brand_name)
            
            with st.expander("Single-word NAME"):
                st.write(f"Total: {single_word_name_count}")
                st.dataframe(single_word_name)
            
            with st.expander("Generic BRAND for valid CATEGORY_CODE"):
                st.write(f"Total: {generic_brand_count}")
                st.dataframe(generic_brand)
            
            with st.expander("Perfume price issues"):
                st.write(f"Total: {perfume_issues_count}")
                st.dataframe(perfume_issues)
            
            with st.expander("Blacklisted words in NAME"):
                st.write(f"Total: {blacklisted_name_count}")
                st.dataframe(blacklisted_name)

            # Prepare the final report for download
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                data.to_excel(writer, index=False, sheet_name='OriginalData')
                missing_color.to_excel(writer, index=False, sheet_name='MissingColor')
                missing_brand_name.to_excel(writer, index=False, sheet_name='MissingBrandOrName')
                single_word_name.to_excel(writer, index=False, sheet_name='SingleWordName')
                generic_brand.to_excel(writer, index=False, sheet_name='GenericBrand')
                perfume_issues.to_excel(writer, index=False, sheet_name='PerfumeIssues')
                blacklisted_name.to_excel(writer, index=False, sheet_name='BlacklistedName')

            st.download_button(
                label="Download Flagged Products Report",
                data=output.getvalue(),
                file_name="Flagged_Products_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"An error occurred: {e}")
