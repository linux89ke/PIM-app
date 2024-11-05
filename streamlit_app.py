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

# Flagging criteria with specified reasons, comments, and display names
flagging_criteria = {
    "Missing COLOR": ("1000005 - Kindly confirm the actual product colour", "Kindly include color of the product"),
    "Missing BRAND or NAME": ("1000007 - Other Reason", "Missing BRAND or NAME"),
    "Name too short": ("1000008 - Kindly Improve Product Name Description", "Kindly Improve Product Name"),
    "Brand is Generic instead of Fashion": ("1000007 - Other Reason", "Kindly use Fashion as brand name for Fashion products"),
    "Perfume price too low": ("1000030 - Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)", ""),
    "Blacklisted word in NAME": ("1000033 - Keywords in your content/ Product name / description has been blacklisted", "Keywords in your content/ Product name / description has been blacklisted"),
    "BRAND name repeated in NAME": ("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", "Kindly Ensure Brand Name Is Not Repeated In Product Name"),
    "Duplicate product": ("1000007 - Other Reason", "Product is duplicated")
}

# Check if the file is uploaded
if uploaded_file is not None:
    try:
        # Load the uploaded CSV file
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        if not data.empty:
            st.write("CSV file loaded successfully. Preview of data:")
            st.write(data.head())

            # Initialize lists to collect flagged rows for each flag category
            flags_data = {flag: pd.DataFrame() for flag in flagging_criteria.keys()}

            # Apply flagging rules in order of importance, stopping at the first match per product
            flagged_products = set()
            for flag, (reason, comment) in flagging_criteria.items():
                if flag == "Missing COLOR":
                    flags_data[flag] = data[(data['COLOR'].isna() | (data['COLOR'] == '')) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
                elif flag == "Missing BRAND or NAME":
                    flags_data[flag] = data[(data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
                elif flag == "Name too short":
                    flags_data[flag] = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book') & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
                elif flag == "Brand is Generic instead of Fashion":
                    valid_category_codes_fas = category_fas_data['ID'].tolist()
                    flags_data[flag] = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic') & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
                elif flag == "Perfume price too low":
                    perfumes_data = perfumes_data.sort_values(by="PRICE", ascending=False).drop_duplicates(subset=["BRAND", "KEYWORD"], keep="first")
                    flagged_perfumes = []
                    for _, row in data.iterrows():
                        if row['PRODUCT_SET_SID'] not in flagged_products:
                            brand = row['BRAND']
                            if brand in perfumes_data['BRAND'].values:
                                keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                                for keyword in keywords:
                                    if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                                        perfume_price = perfumes_data.loc[(perfumes_data['BRAND'] == brand) & (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                                        price_difference = row['GLOBAL_PRICE'] - perfume_price
                                        if price_difference < 0:
                                            flagged_perfumes.append(row)
                                            flagged_products.add(row['PRODUCT_SET_SID'])
                                            break
                    flags_data[flag] = pd.DataFrame(flagged_perfumes)
                elif flag == "Blacklisted word in NAME":
                    def check_blacklist(name):
                        if isinstance(name, str):
                            name_words = name.lower().split()
                            return any(black_word.lower() in name_words for black_word in blacklisted_words)
                        return False
                    flags_data[flag] = data[data['NAME'].apply(check_blacklist) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
                elif flag == "BRAND name repeated in NAME":
                    flags_data[flag] = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
                elif flag == "Duplicate product":
                    flags_data[flag] = data[data.duplicated(subset='PRODUCT_SET_ID', keep=False) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]

                # Track flagged products to prevent re-flagging
                flagged_products.update(flags_data[flag]['PRODUCT_SET_SID'].tolist())

            # Display flagged items with counts
            for flag, df in flags_data.items():
                count = len(df)
                with st.expander(f"{flag} ({count} products)"):
                    if count > 0:
                        st.write(df[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                    else:
                        st.write("No products flagged.")

            # Prepare final report
            final_report_rows = []
            for index, row in data.iterrows():
                first_flag = next((flag for flag in flags_data if row['PRODUCT_SET_SID'] in flags_data[flag]['PRODUCT_SET_SID'].values), None)
                
                if first_flag:
                    reason_code, comment = flagging_criteria[first_flag]
                    status = 'Rejected'
                    reason = reason_code
                else:
                    status = 'Approved'
                    reason = ''
                    comment = ''
                
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], status, reason, comment))

            # Prepare final report DataFrame
            final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment'])
            st.write("Final Report Preview")
            st.write(final_report_df)

            # Separate approved and rejected reports
            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

            # Function to convert DataFrame to downloadable Excel file
            def to_excel(dataframe):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    dataframe.to_excel(writer, index=False, sheet_name='ProductSets')
                    reasons_df = pd.read_excel('reasons.xlsx')
                    reasons_df.to_excel(writer, index=False, sheet_name='RejectionReasons')
                return output.getvalue()

            # Download buttons for reports
            st.download_button(
                label="Download Approved Products Report",
                data=to_excel(approved_df),
                file_name='approved_products.xlsx'
            )

            st.download_button(
                label="Download Rejected Products Report",
                data=to_excel(rejected_df),
                file_name='rejected_products.xlsx'
            )

            st.download_button(
                label="Download Combined Report",
                data=to_excel(final_report_df),
                file_name='combined_report.xlsx'
            )

    except Exception as e:
        st.error(f"An error occurred: {e}")
