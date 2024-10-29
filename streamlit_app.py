import pandas as pd
import streamlit as st
from io import BytesIO
import os

# Function to load blacklisted words from a file
def load_blacklisted_words():
    with open('blacklisted.txt', 'r') as f:
        return [line.strip() for line in f.readlines()]

# Function to load data files with error handling
def load_data(file_name):
    if os.path.exists(file_name):
        return pd.read_excel(file_name)
    else:
        st.error(f"File {file_name} not found.")
        return None

# Load data for checks
check_variation_data = load_data('check_variation.xlsx')
category_fas_data = load_data('category_FAS.xlsx')
perfumes_data = load_data('perfumes.xlsx')
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

            # Function to check for missing COLOR
            def flag_missing_color(data):
                return data[data['COLOR'].isna() | (data['COLOR'] == '')]

            # Function to check for missing BRAND or NAME
            def flag_missing_brand_or_name(data):
                return data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]

            # Function to check for single-word NAME
            def flag_single_word_name(data):
                return data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]

            # Function to check for missing VARIATION based on CATEGORY_CODE
            def flag_category_variation(data):
                valid_category_codes = check_variation_data['ID'].tolist()
                return data[(data['CATEGORY_CODE'].isin(valid_category_codes)) & ((data['VARIATION'].isna()) | (data['VARIATION'] == ''))]

            # Function to check for GENERIC brand based on CATEGORY_CODE
            def flag_generic_brand(data):
                valid_category_codes_fas = category_fas_data['ID'].tolist()
                return data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]

            # Function to check for perfume price issues
            def flag_perfume_price_issues(data, perfumes_data):
                flagged_perfumes = []
                perfumes_data = perfumes_data.sort_values(by="PRICE", ascending=False).drop_duplicates(subset=["BRAND", "KEYWORD"], keep="first")
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
                return flagged_perfumes

            # Function to check for blacklisted words in NAME
            def check_blacklist(name):
                if isinstance(name, str):
                    name_words = name.lower().split()
                    return any(black_word.lower() in name_words for black_word in blacklisted_words)
                return False

            # Function to flag products based on blacklisted words
            def flag_blacklisted_words(data):
                flagged_blacklisted = data[data['NAME'].apply(check_blacklist)]
                if not flagged_blacklisted.empty:
                    flagged_blacklisted['Blacklisted_Word'] = flagged_blacklisted['NAME'].apply(
                        lambda x: [word for word in blacklisted_words if word.lower() in x.lower().split()][0]
                    )
                return flagged_blacklisted

            # Function to check for BRAND name repeated in NAME
            def flag_brand_in_name(data):
                return data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

            # Flag products
            missing_color = flag_missing_color(data)
            if not missing_color.empty:
                flagged_count = len(missing_color)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with missing COLOR fields.")
                st.write(missing_color[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])

            missing_brand_or_name = flag_missing_brand_or_name(data)
            if not missing_brand_or_name.empty:
                flagged_count = len(missing_brand_or_name)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with missing BRAND or NAME.")
                st.write(missing_brand_or_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])

            single_word_name = flag_single_word_name(data)
            if not single_word_name.empty:
                flagged_count = len(single_word_name)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with a single-word NAME.")
                st.write(single_word_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])

            category_variation_issues = flag_category_variation(data)
            if not category_variation_issues.empty:
                flagged_count = len(category_variation_issues)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with missing VARIATION for valid CATEGORY_CODE.")
                st.write(category_variation_issues[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])

            generic_brand_issues = flag_generic_brand(data)
            if not generic_brand_issues.empty:
                flagged_count = len(generic_brand_issues)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with GENERIC brand for valid CATEGORY_CODE.")
                st.write(generic_brand_issues[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])

            flagged_perfumes = flag_perfume_price_issues(data, perfumes_data)
            flagged_perfumes_df = pd.DataFrame(flagged_perfumes)
            if not flagged_perfumes_df.empty:
                flagged_count = len(flagged_perfumes_df)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products flagged due to perfume price issues.")
                st.write(flagged_perfumes_df[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME', 'GLOBAL_PRICE']])

            flagged_blacklisted = flag_blacklisted_words(data)
            if not flagged_blacklisted.empty:
                flagged_count = len(flagged_blacklisted)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products flagged due to blacklisted words in NAME.")
                st.write(flagged_blacklisted[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'Blacklisted_Word', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])

            brand_in_name = flag_brand_in_name(data)
            if not brand_in_name.empty:
                flagged_count = len(brand_in_name)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products where BRAND name is repeated in NAME.")
                st.write(brand_in_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])

            # Prepare the final report with status and reasons for each product
            final_report_rows = []
            for index, row in data.iterrows():
                reasons = []
                if row['PRODUCT_SET_SID'] in missing_color['PRODUCT_SET_SID'].values:
                    reasons.append("Missing COLOR")
                if row['PRODUCT_SET_SID'] in missing_brand_or_name['PRODUCT_SET_SID'].values:
                    reasons.append("Missing BRAND or NAME")
                if row['PRODUCT_SET_SID'] in single_word_name['PRODUCT_SET_SID'].values:
                    reasons.append("Single-word NAME")
                if row['PRODUCT_SET_SID'] in category_variation_issues['PRODUCT_SET_SID'].values:
                    reasons.append("Missing VARIATION for CATEGORY_CODE")
                if row['PRODUCT_SET_SID'] in generic_brand_issues['PRODUCT_SET_SID'].values:
                    reasons.append("Generic brand")
                if row['PRODUCT_SET_SID'] in flagged_blacklisted['PRODUCT_SET_SID'].values:
                    reasons.append("Blacklisted word in NAME")
                if row['PRODUCT_SET_SID'] in brand_in_name['PRODUCT_SET_SID'].values:
                    reasons.append("Brand name in NAME")
                if row['PRODUCT_SET_SID'] in flagged_perfumes_df['PRODUCT_SET_SID'].values:
                    reasons.append("Price issue with perfume")

                status = "Approved" if not reasons else "Rejected"
                final_report_rows.append({
                    'ProductSetSid': row['PRODUCT_SET_SID'],
                    'ParentSKU': row['PARENTSKU'],
                    'Status': status,
                    'Reason': ', '.join(reasons),
                    'Comment': 'Please review the flagged issues.'
                })

            # Create a DataFrame for the final report
            final_report_df = pd.DataFrame(final_report_rows)

            # Download button for the final report
            final_report_buffer = BytesIO()
            with pd.ExcelWriter(final_report_buffer, engine='xlsxwriter') as writer:
                final_report_df.to_excel(writer, sheet_name='ProductSets', index=False)

                # Create a blank sheet for rejection reasons
                rejection_reasons_df = pd.DataFrame(columns=['Reason Id', 'Reason Description'])
                rejection_reasons_df.to_excel(writer, sheet_name='RejectionReasons', index=False)

            final_report_buffer.seek(0)
            st.download_button(
                label="Download Final Report",
                data=final_report_buffer,
                file_name="final_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Display total flagged products
            st.success(f"Total flagged products: {total_flagged_products}")

    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
