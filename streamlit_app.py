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

            # Define reason codes and messages with priority
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

            # Prioritized list of checks
            check_order = [
                ("Missing COLOR", data['COLOR'].isna() | (data['COLOR'] == '')),
                ("Missing BRAND or NAME", data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')),
                ("Single-word NAME", (data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')),
                ("Generic BRAND", data['CATEGORY_CODE'].isin(category_fas_data['ID'].tolist()) & (data['BRAND'] == 'Generic')),
                ("Perfume price issue", data.apply(lambda row: any(
                    (row['BRAND'] == brand and keyword.lower() in str(row['NAME']).lower() and row['GLOBAL_PRICE'] - price < 0)
                    for brand, keyword, price in zip(perfumes_data['BRAND'], perfumes_data['KEYWORD'], perfumes_data['PRICE'])), axis=1)),
                ("Blacklisted word in NAME", data['NAME'].apply(lambda name: any(black_word.lower() in name.lower().split() for black_word in blacklisted_words))),
                ("BRAND name repeated in NAME", data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)),
                ("Duplicate product", data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False))
            ]

            # Prepare the final report rows with only one reason
            final_report_rows = []

            for index, row in data.iterrows():
                status = 'Approved'
                reason_str = ''
                comment = ''
                reason_detail = {}

                for reason_name, condition in check_order:
                    if condition.iloc[index]:  # Check if the product matches the current reason
                        reason_code, message, comment_text = reasons_dict[reason_name]
                        reason_str = f"{reason_code} - {message}"
                        comment = comment_text
                        status = 'Rejected'
                        reason_detail = {
                            "Reason": reason_name,
                            "Message": message,
                            "Comment": comment_text
                        }
                        break  # Assign only the first applicable reason

                final_report_rows.append((row['PRODUCT_SET_SID'], row.get('PARENTSKU', ''), status, reason_str, comment, reason_detail))

            # Prepare the final report DataFrame
            final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment', 'ReasonDetail'])

            st.write("Final Report Preview")
            st.write(final_report_df)

            # Expandable flags for each rejected product
            for idx, row in final_report_df.iterrows():
                if row['Status'] == 'Rejected':
                    with st.expander(f"Flagged Reason for Product {row['ProductSetSid']} - {row['Reason']}"):
                        st.write(f"**Reason**: {row['Reason']}")
                        st.write(f"**Comment**: {row['Comment']}")
                        st.write(f"**Detailed Explanation**: {row['ReasonDetail']}")

            # Separate approved and rejected reports
            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

            # Function to create Excel files with two sheets each
            def to_excel(df1, df2, sheet1_name="ProductSets", sheet2_name="RejectionReasons"):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df1.to_excel(writer, index=False, sheet_name=sheet1_name)
                    df2.to_excel(writer, index=False, sheet_name=sheet2_name)
                output.seek(0)
                return output

            current_date = datetime.now().strftime("%Y-%m-%d")

            # Download buttons for the reports
            final_report_button_data = to_excel(final_report_df, reasons_data, 'ProductSets', 'RejectionReasons')
            st.download_button(
                label=f"Download Final Report ({current_date})",
                data=final_report_button_data,
                file_name=f"final_report_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="final_report"
            )

            approved_products_button_data = to_excel(approved_df, reasons_data, 'ProductSets', 'RejectionReasons')
            st.download_button(
                label=f"Download Approved Products ({current_date})",
                data=approved_products_button_data,
                file_name=f"approved_products_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="approved_products"
            )

            rejected_products_button_data = to_excel(rejected_df, reasons_data, 'ProductSets', 'RejectionReasons')
            st.download_button(
                label=f"Download Rejected Products ({current_date})",
                data=rejected_products_button_data,
                file_name=f"rejected_products_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="rejected_products"
            )

    except Exception as e:
        st.error(f"Error loading file: {e}")
