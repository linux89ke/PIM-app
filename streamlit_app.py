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

            # Apply flagging rules
            flags_data["Missing COLOR"] = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            flags_data["Missing BRAND or NAME"] = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            flags_data["Name too short"] = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            flags_data["Brand is Generic instead of Fashion"] = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]

            # Perfume price issue
            perfumes_data = perfumes_data.sort_values(by="PRICE", ascending=False).drop_duplicates(subset=["BRAND", "KEYWORD"], keep="first")
            flagged_perfumes = []
            for _, row in data.iterrows():
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
            flags_data["Perfume price too low"] = pd.DataFrame(flagged_perfumes)

            # Blacklisted words in NAME
            def check_blacklist(name):
                if isinstance(name, str):
                    name_words = name.lower().split()
                    return any(black_word.lower() in name_words for black_word in blacklisted_words)
                return False
            flags_data["Blacklisted word in NAME"] = data[data['NAME'].apply(check_blacklist)]

            # BRAND name repeated in NAME
            flags_data["BRAND name repeated in NAME"] = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

            # Duplicate product check (assume duplicate if PRODUCT_SET_ID is repeated)
            flags_data["Duplicate product"] = data[data.duplicated(subset='PRODUCT_SET_ID', keep=False)]

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
                reasons = []
                for flag, df in flags_data.items():
                    if row['PRODUCT_SET_SID'] in df['PRODUCT_SET_SID'].values:
                        reason_code, comment = flagging_criteria[flag]
                        reasons.append((reason_code, comment))
                
                if reasons:
                    status = 'Rejected'
                    reason = " | ".join([r[0] for r in reasons])
                    comment = " | ".join([r[1] for r in reasons if r[1]])
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
