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
reasons_data = pd.read_excel('reasons.xlsx')

# Load the reasons data
blacklisted_words = load_blacklisted_words()

# Streamlit app layout
st.title("Product Validation Tool")

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Check if the file is uploaded
if uploaded_file is not None:
    try:
        # Load the uploaded CSV file data
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')

        if not data.empty:
            st.write("CSV file loaded successfully. Preview of data:")
            st.write(data.head())

            # Define reason codes and messages
            reasons_dict = {
                "Missing COLOR": ("1000005", "Kindly confirm the actual product colour", "Kindly include color of the product"),
                "Missing BRAND or NAME": ("1000007", "Other Reason", "Missing BRAND or NAME"),
                "Single-word NAME": ("1000008", "Kindly Improve Product Name Description", "Name too short"),
                "Generic BRAND": ("1000007", "Other Reason", "Kindly use Fashion as brand name for Fashion products"),
                "Perfume price issue": ("1000030", "Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)", ""),
                "Blacklisted word in NAME": ("1000033", "Keywords in your content/Product name/description has been blacklisted", "Blacklisted word in NAME"),
                "BRAND name repeated in NAME": ("1000002", "Kindly Ensure Brand Name Is Not Repeated In Product Name", "BRAND name repeated in NAME"),
                "Duplicate product": ("1000007", "Other Reason", "Product is duplicated")
            }

            # Flagging logic
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | 
                                          data['NAME'].isna() | (data['NAME'] == '')]
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & 
                                    (data['BRAND'] != 'Jumia Book')]
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & 
                                         (data['BRAND'] == 'Generic')]
            
            flagged_perfumes = []
            for index, row in data.iterrows():
                brand = row['BRAND']
                if brand in perfumes_data['BRAND'].values:
                    keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                    for keyword in keywords:
                        if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                            perfume_price = perfumes_data.loc[
                                (perfumes_data['BRAND'] == brand) & 
                                (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                            price_difference = row['GLOBAL_PRICE'] - perfume_price
                            if price_difference < 0:
                                flagged_perfumes.append(row)
                                break
            
            flagged_blacklisted = data[data['NAME'].apply(lambda name: any(black_word.lower() in name.lower().split() for black_word in blacklisted_words))]
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and 
                                              isinstance(row['NAME'], str) and 
                                              row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
            duplicate_products = data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]

            # Prepare the final report rows
            final_report_rows = []

            # Collect all flagged products for final report
            for index, row in data.iterrows():
                reasons = []
                reason_codes_and_messages = []

                if row['PRODUCT_SET_SID'] in missing_color['PRODUCT_SET_SID'].values:
                    reasons.append("Missing COLOR")
                    reason_codes_and_messages.append(reasons_dict["Missing COLOR"])
                
                if row['PRODUCT_SET_SID'] in missing_brand_or_name['PRODUCT_SET_SID'].values:
                    reasons.append("Missing BRAND or NAME")
                    reason_codes_and_messages.append(reasons_dict["Missing BRAND or NAME"])
                
                if row['PRODUCT_SET_SID'] in single_word_name['PRODUCT_SET_SID'].values:
                    reasons.append("Single-word NAME")
                    reason_codes_and_messages.append(reasons_dict["Single-word NAME"])
                
                if row['PRODUCT_SET_SID'] in generic_brand_issues['PRODUCT_SET_SID'].values:
                    reasons.append("Generic BRAND")
                    reason_codes_and_messages.append(reasons_dict["Generic BRAND"])
                
                if row['PRODUCT_SET_SID'] in [r['PRODUCT_SET_SID'] for r in flagged_perfumes]:
                    reasons.append("Perfume price issue")
                    reason_codes_and_messages.append(reasons_dict["Perfume price issue"])
                
                if row['PRODUCT_SET_SID'] in flagged_blacklisted['PRODUCT_SET_SID'].values:
                    reasons.append("Blacklisted word in NAME")
                    reason_codes_and_messages.append(reasons_dict["Blacklisted word in NAME"])
                
                if row['PRODUCT_SET_SID'] in brand_in_name['PRODUCT_SET_SID'].values:
                    reasons.append("BRAND name repeated in NAME")
                    reason_codes_and_messages.append(reasons_dict["BRAND name repeated in NAME"])
                
                if row['PRODUCT_SET_SID'] in duplicate_products['PRODUCT_SET_SID'].values:
                    reasons.append("Duplicate product")
                    reason_codes_and_messages.append(reasons_dict["Duplicate product"])

                status = 'Rejected' if reasons else 'Approved'
                
                # Prepare detailed reason string with codes and messages
                detailed_reasons = []
                for code, message, _ in reason_codes_and_messages:
                    detailed_reasons.append(f"{code} - {message}")
                
                reason_str = ' | '.join(detailed_reasons) if detailed_reasons else ''
                
                final_report_rows.append((row['PRODUCT_SET_SID'], row.get('PARENTSKU', ''), status, reason_str, reason_str))

            # Prepare the final report DataFrame
            final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment'])

            st.write("Final Report Preview")
            st.write(final_report_df)

            # Separate approved and rejected reports
            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

            # Function to create Excel files with two sheets each
            def to_excel(df1, df2, sheet1_name="ProductSets", sheet2_name="RejectionReasons"):
                # Create a BytesIO buffer
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df1.to_excel(writer, sheet_name=sheet1_name, index=False)
                    df2.to_excel(writer, sheet_name=sheet2_name, index=False)
                # Move to the beginning of the BytesIO buffer
                output.seek(0)
                return output.read()
            
            # Generate the Excel download button
            file_bytes = to_excel(approved_df, rejected_df)
            st.download_button(
                label="Download Final Report",
                data=file_bytes,
                file_name=f"final_report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.write("The file is empty. Please upload a valid CSV file.")
    except Exception as e:
        st.write(f"Error processing file: {e}")
else:
    st.write("Please upload a CSV file to proceed.")
