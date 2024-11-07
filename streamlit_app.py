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

# Define the reason codes, messages, and displays for flagged items
reason_mapping = {
    "Missing COLOR": ("1000005 - Kindly confirm the actual product colour", "Kindly include color of the product"),
    "Missing BRAND or NAME": ("1000007 - Other Reason", "Missing BRAND or NAME"),
    "Single-word NAME": ("1000008 - Kindly Improve Product Name Description", "Kindly Improve Product Name"),
    "Generic BRAND": ("1000007 - Other Reason", "Kindly use Fashion as brand name for Fashion products"),
    "Perfume price issue": ("1000030 - Suspected Counterfeit/Fake Product", ""),
    "Blacklisted word in NAME": ("1000033 - Keywords in your content/ Product name / description has been blacklisted", "Keywords in your content/ Product name / description has been blacklisted"),
    "BRAND name repeated in NAME": ("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", "Kindly Ensure Brand Name Is Not Repeated In Product Name"),
    "Duplicate product": ("1000007 - Other Reason", "Product is duplicated")
}

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

            # Collect all flagged products for final report
            final_report_rows = []
            for index, row in data.iterrows():
                reasons = []
                comments = []

                # Check each flag and append reason/comment accordingly
                if row['PRODUCT_SET_SID'] in missing_color['PRODUCT_SET_SID'].values:
                    reasons.append(reason_mapping["Missing COLOR"][0])
                    comments.append(reason_mapping["Missing COLOR"][1])
                
                if row['PRODUCT_SET_SID'] in missing_brand_or_name['PRODUCT_SET_SID'].values:
                    reasons.append(reason_mapping["Missing BRAND or NAME"][0])
                    comments.append(reason_mapping["Missing BRAND or NAME"][1])
                
                if row['PRODUCT_SET_SID'] in single_word_name['PRODUCT_SET_SID'].values:
                    reasons.append(reason_mapping["Single-word NAME"][0])
                    comments.append(reason_mapping["Single-word NAME"][1])
                
                if row['PRODUCT_SET_SID'] in generic_brand_issues['PRODUCT_SET_SID'].values:
                    reasons.append(reason_mapping["Generic BRAND"][0])
                    comments.append(reason_mapping["Generic BRAND"][1])
                
                if row['PRODUCT_SET_SID'] in [r['PRODUCT_SET_SID'] for r in flagged_perfumes]:
                    reasons.append(reason_mapping["Perfume price issue"][0])
                
                if row['PRODUCT_SET_SID'] in flagged_blacklisted['PRODUCT_SET_SID'].values:
                    reasons.append(reason_mapping["Blacklisted word in NAME"][0])
                    comments.append(reason_mapping["Blacklisted word in NAME"][1])
                
                if row['PRODUCT_SET_SID'] in brand_in_name['PRODUCT_SET_SID'].values:
                    reasons.append(reason_mapping["BRAND name repeated in NAME"][0])
                    comments.append(reason_mapping["BRAND name repeated in NAME"][1])
                
                if row['PRODUCT_SET_SID'] in duplicate_products['PRODUCT_SET_SID'].values:
                    reasons.append(reason_mapping["Duplicate product"][0])
                    comments.append(reason_mapping["Duplicate product"][1])

                status = 'Rejected' if reasons else 'Approved'
                final_reason = ' | '.join(reasons) if reasons else ''
                final_comment = ' | '.join(comments) if comments else ''
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], status, final_reason, final_comment))

            # Prepare the final report DataFrame
            final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment'])
            st.write("Final Report Preview")
            st.write(final_report_df)

            # Download buttons for the reports
            def to_excel(df, rejection_reasons_df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='ProductSets')
                    rejection_reasons_df.to_excel(writer, index=False, sheet_name='RejectionReasons')
                output.seek(0)
                return output

            st.download_button("Download Final Report", to_excel(final_report_df, reasons_data), "final_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        st.error(f"Error loading the CSV file: {e}")
