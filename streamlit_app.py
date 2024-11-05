import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# Function to load the blacklisted words from a file
def load_blacklisted_words():
    with open('blacklisted.txt', 'r') as f:
        return [line.strip() for line in f.readlines()]

# Load data for checks
check_variation_data = pd.read_excel('check_variation.xlsx')
category_fas_data = pd.read_excel('category_FAS.xlsx')
perfumes_data = pd.read_excel('perfumes.xlsx')
reasons_data = pd.read_excel('reasons.xlsx')  # Load the reasons data
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

            # Initialize a list for flagged products
            final_report_rows = []

            # Define specific reasons, comments, and display names for each flag
            flag_definitions = {
                "Missing COLOR": {"Reason": "1000005 - Kindly confirm the actual product colour", "Comment": "Kindly include color of the product", "Display": "Missing COLOR"},
                "Missing BRAND or NAME": {"Reason": "1000007 - Other Reason", "Comment": "Missing BRAND or NAME", "Display": "Missing BRAND or NAME"},
                "Single-word NAME": {"Reason": "1000008 - Kindly Improve Product Name Description", "Comment": "Kindly Improve Product Name", "Display": "Name too short"},
                "Generic BRAND": {"Reason": "1000007 - Other Reason", "Comment": "Kindly use Fashion as brand name for Fashion products", "Display": "Brand is Generic instead of Fashion"},
                "Perfume price issue": {"Reason": "1000030 - Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)", "Display": "Perfume price too low"},
                "Blacklisted word in NAME": {"Reason": "1000033 - Keywords in your content/ Product name / description has been blacklisted", "Comment": "Keywords in your content/ Product name / description has been blacklisted", "Display": "Blacklisted word in NAME"},
                "BRAND name repeated in NAME": {"Reason": "1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", "Comment": "Kindly Ensure Brand Name Is Not Repeated In Product Name", "Display": "BRAND name repeated in NAME"},
                "Duplicate product": {"Reason": "1000007 - Other Reason", "Comment": "Product is duplicated", "Display": "Duplicate product"}
            }

            # Flag 1: Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]

            # Flag 2: Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]

            # Flag 3: Single-word NAME (but not for "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]

            # Flag 4: Generic Brand Check
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]

            # Flag 5: Price and Keyword Check (Perfume Check)
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

            # Flag 6: Blacklisted Words in NAME
            def check_blacklist(name):
                if isinstance(name, str):
                    name_words = name.lower().split()
                    return any(black_word.lower() in name_words for black_word in blacklisted_words)
                return False

            flagged_blacklisted = data[data['NAME'].apply(check_blacklist)]

            # Flag 7: Brand name repeated in NAME
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

            # Flag 8: Duplicate products based on NAME, BRAND, and SELLER_NAME
            duplicate_products = data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]

            # Collect all flagged products with reasons for the final report
            for index, row in data.iterrows():
                reasons = []
                if row['PRODUCT_SET_SID'] in missing_color['PRODUCT_SET_SID'].values:
                    reasons.append(flag_definitions["Missing COLOR"])
                if row['PRODUCT_SET_SID'] in missing_brand_or_name['PRODUCT_SET_SID'].values:
                    reasons.append(flag_definitions["Missing BRAND or NAME"])
                if row['PRODUCT_SET_SID'] in single_word_name['PRODUCT_SET_SID'].values:
                    reasons.append(flag_definitions["Single-word NAME"])
                if row['PRODUCT_SET_SID'] in generic_brand_issues['PRODUCT_SET_SID'].values:
                    reasons.append(flag_definitions["Generic BRAND"])
                if row['PRODUCT_SET_SID'] in [r['PRODUCT_SET_SID'] for r in flagged_perfumes]:
                    reasons.append(flag_definitions["Perfume price issue"])
                if row['PRODUCT_SET_SID'] in flagged_blacklisted['PRODUCT_SET_SID'].values:
                    reasons.append(flag_definitions["Blacklisted word in NAME"])
                if row['PRODUCT_SET_SID'] in brand_in_name['PRODUCT_SET_SID'].values:
                    reasons.append(flag_definitions["BRAND name repeated in NAME"])
                if row['PRODUCT_SET_SID'] in duplicate_products['PRODUCT_SET_SID'].values:
                    reasons.append(flag_definitions["Duplicate product"])

                status = 'Rejected' if reasons else 'Approved'
                reason_text = ' | '.join([r["Display"] for r in reasons]) if reasons else ''
                comment_text = ' | '.join([r.get("Comment", "") for r in reasons]) if reasons else ''
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], status, reason_text, comment_text))

            # Prepare the final report DataFrame
            final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment'])
            st.write("Final Report Preview")
            st.write(final_report_df)

            # Get today's date for file naming
            today_date = datetime.now().strftime("%Y-%m-%d")

            # Create download buttons for each report
            def to_excel(df, rejection_reasons_df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='ProductSets')
                    rejection_reasons_df.to_excel(writer, index=False, sheet_name='RejectionReasons')
                output.seek(0)
                return output

            st.download_button("Download Final Report", to_excel(final_report_df, reasons_data), f"final_report_{today_date}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("Download Approved Products", to_excel(final_report_df[final_report_df['Status'] == 'Approved'], reasons_data), f"approved_products_{today_date}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("Download Rejected Products", to_excel(final_report_df[final_report_df['Status'] == 'Rejected'], reasons_data), f"rejected_products_{today_date}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        st.error(f"Error loading the CSV file: {e}")
