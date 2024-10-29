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
            if not missing_color.empty:
                flagged_count = len(missing_color)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with missing COLOR fields.")
                st.write(missing_color[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])

            # Flag 2: Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            if not missing_brand_or_name.empty:
                flagged_count = len(missing_brand_or_name)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with missing BRAND or NAME.")
                st.write(missing_brand_or_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])

            # Flag 3: Single-word NAME (but not for "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            if not single_word_name.empty:
                flagged_count = len(single_word_name)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with a single-word NAME.")
                st.write(single_word_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])

            # Flag 4: Category and Variation Check
            valid_category_codes = check_variation_data['ID'].tolist()
            category_variation_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes)) & ((data['VARIATION'].isna()) | (data['VARIATION'] == ''))]
            if not category_variation_issues.empty:
                flagged_count = len(category_variation_issues)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with missing VARIATION for valid CATEGORY_CODE.")
                st.write(category_variation_issues[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])

            # Flag 5: Generic Brand Check
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]
            if not generic_brand_issues.empty:
                flagged_count = len(generic_brand_issues)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with GENERIC brand for valid CATEGORY_CODE.")
                st.write(generic_brand_issues[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])

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
            if flagged_perfumes:
                flagged_perfumes_df = pd.DataFrame(flagged_perfumes)
                flagged_count = len(flagged_perfumes_df)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products flagged due to perfume price issues.")
                st.write(flagged_perfumes_df[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME', 'GLOBAL_PRICE']])

            # Flag 7: Blacklisted Words in NAME (word appears in full and on its own)
            def check_blacklist(name):
                if isinstance(name, str):
                    name_words = name.lower().split()
                    return any(black_word.lower() in name_words for black_word in blacklisted_words)
                return False

            flagged_blacklisted = data[data['NAME'].apply(check_blacklist)]
            if not flagged_blacklisted.empty:
                flagged_blacklisted['Blacklisted_Word'] = flagged_blacklisted['NAME'].apply(
                    lambda x: [word for word in blacklisted_words if word.lower() in x.lower().split()][0]
                )
                flagged_count = len(flagged_blacklisted)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products flagged due to blacklisted words in NAME.")
                st.write(flagged_blacklisted[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'Blacklisted_Word', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])

            # Flag 8: Brand name repeated in NAME (case-insensitive)
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
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
                    reasons.append("Missing VARIATION")
                if row['PRODUCT_SET_SID'] in generic_brand_issues['PRODUCT_SET_SID'].values:
                    reasons.append("Generic BRAND")
                if row['PRODUCT_SET_SID'] in [r['PRODUCT_SET_SID'] for r in flagged_perfumes]:
                    reasons.append("Perfume price issue")
                if row['PRODUCT_SET_SID'] in flagged_blacklisted['PRODUCT_SET_SID'].values:
                    reasons.append("Blacklisted word in NAME")
                if row['PRODUCT_SET_SID'] in brand_in_name['PRODUCT_SET_SID'].values:
                    reasons.append("BRAND name repeated in NAME")

                status = 'Rejected' if reasons else 'Approved'
                reason = '1000007 - Other Reason' if status == 'Rejected' else ''
                comment = ', '.join(reasons) if reasons else 'No issues'

                final_report_rows.append({
                    'ProductSetSid': row['PRODUCT_SET_SID'],
                    'ParentSKU': row['PARENTSKU'],
                    'Status': status,
                    'Reason': reason,
                    'Comment': comment
                })

            # Create final report DataFrames for approved, rejected, and combined products
            final_report_df = pd.DataFrame(final
