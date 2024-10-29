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

            # Create DataFrames to hold flagged products
            flagged_reports = {
                'missing_color': pd.DataFrame(),
                'missing_brand_or_name': pd.DataFrame(),
                'single_word_name': pd.DataFrame(),
                'category_variation_issues': pd.DataFrame(),
                'generic_brand_issues': pd.DataFrame(),
                'flagged_perfumes': pd.DataFrame(),
                'flagged_blacklisted': pd.DataFrame(),
                'brand_in_name': pd.DataFrame()
            }

            # Create DataFrames for approved and rejected products
            approved_products = []
            rejected_products = []

            # Flag 1: Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            if not missing_color.empty:
                flagged_reports['missing_color'] = missing_color[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']]
                flagged_count = len(missing_color)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with missing COLOR fields.")

            # Flag 2: Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            if not missing_brand_or_name.empty:
                flagged_reports['missing_brand_or_name'] = missing_brand_or_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']]
                flagged_count = len(missing_brand_or_name)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with missing BRAND or NAME.")

            # Flag 3: Single-word NAME (but not for "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            if not single_word_name.empty:
                flagged_reports['single_word_name'] = single_word_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']]
                flagged_count = len(single_word_name)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with a single-word NAME.")

            # Flag 4: Category and Variation Check
            valid_category_codes = check_variation_data['ID'].tolist()
            category_variation_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes)) & ((data['VARIATION'].isna()) | (data['VARIATION'] == ''))]
            if not category_variation_issues.empty:
                flagged_reports['category_variation_issues'] = category_variation_issues[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']]
                flagged_count = len(category_variation_issues)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with missing VARIATION for valid CATEGORY_CODE.")

            # Flag 5: Generic Brand Check
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]
            if not generic_brand_issues.empty:
                flagged_reports['generic_brand_issues'] = generic_brand_issues[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']]
                flagged_count = len(generic_brand_issues)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with GENERIC brand for valid CATEGORY_CODE.")

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
                flagged_reports['flagged_perfumes'] = pd.DataFrame(flagged_perfumes)[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME', 'GLOBAL_PRICE']]
                flagged_count = len(flagged_reports['flagged_perfumes'])
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products flagged due to perfume price issues.")

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
                flagged_reports['flagged_blacklisted'] = flagged_blacklisted[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'Blacklisted_Word', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']]
                flagged_count = len(flagged_reports['flagged_blacklisted'])
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products flagged due to blacklisted words in NAME.")

            # Flag 8: Brand name repeated in NAME (case-insensitive)
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
            if not brand_in_name.empty:
                flagged_reports['brand_in_name'] = brand_in_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']]
                flagged_count = len(flagged_reports['brand_in_name'])
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products where BRAND name is repeated in NAME.")

            # Show total number of rows and flagged products
            total_rows = len(data)
            st.write(f"Total number of rows: {total_rows}")
            st.write(f"Total number of flagged products: {total_flagged_products}")

            # Prepare a list to hold the final report rows
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
                    reasons.append("Category Variation Issue")
                if row['PRODUCT_SET_SID'] in generic_brand_issues['PRODUCT_SET_SID'].values:
                    reasons.append("Generic BRAND")
                if row['PRODUCT_SET_SID'] in flagged_reports['flagged_perfumes']['PRODUCT_SET_SID'].values:
                    reasons.append("Perfume Price Issue")
                if row['PRODUCT_SET_SID'] in flagged_blacklisted['PRODUCT_SET_SID'].values:
                    reasons.append("Blacklisted Word in NAME")
                if row['PRODUCT_SET_SID'] in brand_in_name['PRODUCT_SET_SID'].values:
                    reasons.append("BRAND name in NAME")

                # Determine status based on flagged reasons
                if reasons:
                    rejected_products.append({
                        'ProductSetSid': row['PRODUCT_SET_SID'],
                        'ParentSKU': row['PARENTSKU'],
                        'Status': "Rejected",
                        'Reason': ', '.join(reasons),
                        'Comment': 'Review flagged reasons'
                    })
                else:
                    approved_products.append({
                        'ProductSetSid': row['PRODUCT_SET_SID'],
                        'ParentSKU': row['PARENTSKU'],
                        'Status': "Approved",
                        'Reason': '',
                        'Comment': ''
                    })

            # Create DataFrames for approved and rejected products
            approved_df = pd.DataFrame(approved_products)
            rejected_df = pd.DataFrame(rejected_products)

            # Create a final report DataFrame
            final_report_df = pd.concat([approved_df, rejected_df], ignore_index=True)

            # Create a BytesIO object for the final report download
            final_report_buffer = BytesIO()
            with pd.ExcelWriter(final_report_buffer, engine='xlsxwriter') as writer:
                final_report_df.to_excel(writer, sheet_name='ProductSets', index=False)
                pd.DataFrame(columns=['']).to_excel(writer, sheet_name='RejectionReasons', index=False)
            final_report_buffer.seek(0)

            # Download button for the final report
            st.download_button(
                label="Download Final Report",
                data=final_report_buffer,
                file_name="final_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Download button for approved products
            if not approved_df.empty:
                approved_buffer = BytesIO()
                with pd.ExcelWriter(approved_buffer, engine='xlsxwriter') as writer:
                    approved_df.to_excel(writer, sheet_name='Approved Products', index=False)
                approved_buffer.seek(0)

                st.download_button(
                    label="Download Approved Products Report",
                    data=approved_buffer,
                    file_name="approved_products.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            # Download button for rejected products
            if not rejected_df.empty:
                rejected_buffer = BytesIO()
                with pd.ExcelWriter(rejected_buffer, engine='xlsxwriter') as writer:
                    rejected_df.to_excel(writer, sheet_name='Rejected Products', index=False)
                rejected_buffer.seek(0)

                st.download_button(
                    label="Download Rejected Products Report",
                    data=rejected_buffer,
                    file_name="rejected_products.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
