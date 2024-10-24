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
                st.write(missing_color)

            # Flag 2: Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            if not missing_brand_or_name.empty:
                flagged_count = len(missing_brand_or_name)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with missing BRAND or NAME.")
                st.write(missing_brand_or_name)

            # Flag 3: Single-word NAME (but not for "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            if not single_word_name.empty:
                flagged_count = len(single_word_name)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with a single-word NAME.")
                st.write(single_word_name)

            # Flag 4: Category and Variation Check
            valid_category_codes = check_variation_data['ID'].tolist()
            category_variation_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes)) &
                                             ((data['VARIATION'].isna()) | (data['VARIATION'] == ''))]
            if not category_variation_issues.empty:
                flagged_count = len(category_variation_issues)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with missing VARIATION for valid CATEGORY_CODE.")
                st.write(category_variation_issues)

            # Flag 5: Generic Brand Check
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) &
                                        (data['BRAND'] == 'Generic')]
            if not generic_brand_issues.empty:
                flagged_count = len(generic_brand_issues)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products with GENERIC brand for valid CATEGORY_CODE.")
                st.write(generic_brand_issues)

            # Flag 6: Price and Keyword Check (Perfume Check)
            # Sort by price and drop duplicates based on BRAND and KEYWORD, keeping the highest price
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
                            if price_difference < 0:  # Assuming flagged if uploaded price is less than the perfume price
                                flagged_perfumes.append(row)
                                break  # Stop checking once we find a match
            if flagged_perfumes:
                flagged_count = len(flagged_perfumes)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products flagged due to perfume price issues.")
                st.write(pd.DataFrame(flagged_perfumes))

            # Flag 7: Blacklisted Words in NAME
            def check_blacklist(name):
                if isinstance(name, str):  # Ensure the value is a string
                    return any(black_word.lower() in name.lower() for black_word in blacklisted_words)
                return False

            flagged_blacklisted = data[data['NAME'].apply(check_blacklist)]
            if not flagged_blacklisted.empty:
                flagged_count = len(flagged_blacklisted)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products flagged due to blacklisted words in NAME.")
                st.write(flagged_blacklisted)

            # Flag 8: Brand name repeated in NAME (case-insensitive)
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
            if not brand_in_name.empty:
                flagged_count = len(brand_in_name)
                total_flagged_products += flagged_count
                st.error(f"Found {flagged_count} products where BRAND name is repeated in NAME.")
                st.write(brand_in_name)

            # Show total number of rows and flagged products
            total_rows = len(data)
            st.write(f"Total number of rows: {total_rows}")
            st.write(f"Total number of flagged products: {total_flagged_products}")

            # Prepare a list to hold the final report rows
            final_report_rows = []

            # Iterate over each product row to populate the final report
            for index, row in data.iterrows():
                # Check if the row was flagged and set status accordingly
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

                # Append the row to the list
                final_report_rows.append({
                    'ProductSetSid': row['PRODUCT_SET_SID'],  # from CSV file
                    'ParentSKU': row['PARENTSKU'],            # from CSV file
                    'Status': status,
                    'Reason': reason,
                    'Comment': comment
                })

            # Convert the list of rows to a DataFrame
            final_report = pd.DataFrame(final_report_rows)

            # Create an empty DataFrame for the RejectionReasons sheet
            rejection_reasons = pd.DataFrame()

            # Save both sheets to an Excel file in memory
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # Write the final report to the first sheet (ProductSets)
                final_report.to_excel(writer, sheet_name='ProductSets', index=False)
                # Write the empty RejectionReasons sheet
                rejection_reasons.to_excel(writer, sheet_name='RejectionReasons', index=False)

            # Allow users to download the final Excel file
            st.write("Here is a preview of the ProductSets sheet:")
            st.write(final_report)
            st.download_button(
                label="Download Excel File",
                data=output.getvalue(),
                file_name='ProductSets.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            st.error("Uploaded file is empty. Please upload a valid CSV file.")
    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
