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
            flagged_products = []

            # Prepare the final report rows
            final_report_rows = []

            # Flag 1: Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            for index, row in missing_color.iterrows():
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], 'Rejected', "1000005 - Kindly confirm the actual product colour", "Kindly include color of the product"))
                flagged_products.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], "Missing COLOR"))

            # Flag 2: Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            for index, row in missing_brand_or_name.iterrows():
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], 'Rejected', "1000007 - Other Reason", "Missing BRAND or NAME"))
                flagged_products.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], "Missing BRAND or NAME"))

            # Flag 3: Single-word NAME (but not for "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            for index, row in single_word_name.iterrows():
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], 'Rejected', "1000008 - Kindly Improve Product Name Description", "Kindly Improve Product Name"))
                flagged_products.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], "Single-word NAME"))

            # Flag 4: Generic Brand Check
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]
            for index, row in generic_brand_issues.iterrows():
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], 'Rejected', "1000007 - Other Reason", "Kindly use Fashion as brand name for Fashion products"))
                flagged_products.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], "Generic Brand"))

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
                                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], 'Rejected', "1000030 - Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)", "Perfume price too low"))
                                flagged_products.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], "Perfume price issue"))
                                break

            # Flag 6: Blacklisted Words in NAME
            flagged_blacklisted = data[data['NAME'].apply(lambda x: any(word.lower() in x.lower() for word in blacklisted_words if isinstance(x, str)))]
            for index, row in flagged_blacklisted.iterrows():
                flagged_word = [word for word in blacklisted_words if word.lower() in row['NAME'].lower()][0]
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], 'Rejected', "1000033 - Keywords in your content/ Product name / description has been blacklisted", "Keywords in your content/ Product name / description has been blacklisted"))
                flagged_products.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], "Blacklisted word in NAME"))

            # Flag 7: Brand name repeated in NAME
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
            for index, row in brand_in_name.iterrows():
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], 'Rejected', "1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", "Kindly Ensure Brand Name Is Not Repeated In Product Name"))
                flagged_products.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], "BRAND name repeated in NAME"))

            # Flag 8: Duplicate products based on NAME, BRAND, and SELLER_NAME
            duplicate_products = data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]
            for index, row in duplicate_products.iterrows():
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], 'Rejected', "1000007 - Other Reason", "Product is duplicated"))
                flagged_products.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], "Duplicate product"))

            # Display flagged products on the front end
            if flagged_products:
                st.subheader("Flagged Products:")
                flagged_df = pd.DataFrame(flagged_products, columns=['ProductSetSid', 'ParentSKU', 'Flag Reason'])
                st.write(flagged_df)
            else:
                st.write("No products were flagged.")

            # Prepare the final report DataFrame
            final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment'])
            st.write("Final Report Preview")
            st.write(final_report_df)

            # Separate approved and rejected reports
            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

            # Download buttons for the reports
            def to_excel(df, rejection_reasons_df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='ProductSets')
                    rejection_reasons_df.to_excel(writer, index=False, sheet_name='RejectionReasons')
                output.seek(0)
                return output

            st.download_button("Download Final Report", to_excel(final_report_df, reasons_data), "final_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("Download Approved Products", to_excel(approved_df, reasons_data), "approved_products.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("Download Rejected Products", to_excel(rejected_df, reasons_data), "rejected_products.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        st.error(f"Error loading the CSV file: {e}")
