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

            # Initialize final report rows
            final_report_rows = []

            # Flag 1: Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]

            # Flag 2: Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]

            # Flag 3: Single-word NAME (but not for "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]

            # Flag 4: Generic Brand Check
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]

            # Flag 5: Perfume price and keyword check
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

            # Flag 6: Blacklisted words in NAME
            def check_blacklist(name):
                if isinstance(name, str):
                    name_words = name.lower().split()
                    return any(black_word.lower() in name_words for black_word in blacklisted_words)
                return False

            flagged_blacklisted = data[data['NAME'].apply(check_blacklist)]

            # Flag 7: Brand name repeated in NAME (case-insensitive)
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

            # Add flags to final report rows
            for index, row in data.iterrows():
                reasons = []
                if row['PRODUCT_SET_SID'] in missing_color['PRODUCT_SET_SID'].values:
                    reasons.append("1000005 - Kindly confirm the actual product colour")
                if row['PRODUCT_SET_SID'] in missing_brand_or_name['PRODUCT_SET_SID'].values:
                    reasons.append("1000007 - Other Reason")
                if row['PRODUCT_SET_SID'] in single_word_name['PRODUCT_SET_SID'].values:
                    reasons.append("1000008 - Kindly Improve Product Name Description")
                if row['PRODUCT_SET_SID'] in generic_brand_issues['PRODUCT_SET_SID'].values:
                    reasons.append("1000007 - Other Reason")
                if row['PRODUCT_SET_SID'] in [r['PRODUCT_SET_SID'] for r in flagged_perfumes]:
                    reasons.append("1000030 - Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)")
                if row['PRODUCT_SET_SID'] in flagged_blacklisted['PRODUCT_SET_SID'].values:
                    reasons.append("1000033 - Keywords in your content/ Product name / description has been blacklisted")
                if row['PRODUCT_SET_SID'] in brand_in_name['PRODUCT_SET_SID'].values:
                    reasons.append("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name")

                status = 'Rejected' if reasons else 'Approved'
                reason = ' | '.join(reasons) if reasons else ''
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], status, reason, reason))

            # Prepare the final report DataFrame
            final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment'])

            # Separate approved and rejected reports
            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

            # Generate downloadable Excel files
            def generate_excel(dataframe, sheet_name):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
                return output.getvalue()

            st.write("Final Report Preview")
            st.write(final_report_df)

            if st.button("Download Approved Products Report"):
                st.download_button(
                    label="Download Approved Products",
                    data=generate_excel(approved_df, 'Approved Products'),
                    file_name="approved_products.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            if st.button("Download Rejected Products Report"):
                st.download_button(
                    label="Download Rejected Products",
                    data=generate_excel(rejected_df, 'Rejected Products'),
                    file_name="rejected_products.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            if st.button("Download Combined Report"):
                st.download_button(
                    label="Download Combined Report",
                    data=generate_excel(final_report_df, 'Combined Report'),
                    file_name="combined_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    except Exception as e:
        st.error(f"An error occurred: {e}")
