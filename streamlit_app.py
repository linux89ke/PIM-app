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

# Define reasons for each flag
flag_reasons = {
    "Missing COLOR": {
        "Reason": "1000005 - Kindly confirm the actual product colour",
        "Comment": "Kindly include color of the product",
        "Display": "Missing COLOR"
    },
    "Missing BRAND or NAME": {
        "Reason": "1000007 - Other Reason",
        "Comment": "Missing BRAND or NAME",
        "Display": "Missing BRAND or NAME"
    },
    "Single-word NAME": {
        "Reason": "1000008 - Kindly Improve Product Name Description",
        "Comment": "Kindly Improve Product Name",
        "Display": "Name too short"
    },
    "Generic BRAND": {
        "Reason": "1000007 - Other Reason",
        "Comment": "Kindly use Fashion as brand name for Fashion products",
        "Display": "Brand is Generic instead of Fashion"
    },
    "Perfume price issue": {
        "Reason": "1000030 - Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)",
        "Comment": "",
        "Display": "Perfume price too low"
    },
    "Blacklisted word in NAME": {
        "Reason": "1000033 - Keywords in your content/ Product name / description has been blacklisted",
        "Comment": "Keywords in your content/ Product name / description has been blacklisted",
        "Display": "Blacklisted word in NAME"
    },
    "BRAND name repeated in NAME": {
        "Reason": "1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name",
        "Comment": "Kindly Ensure Brand Name Is Not Repeated In Product Name",
        "Display": "BRAND name repeated in NAME"
    },
    "Duplicate product": {
        "Reason": "1000007 - Other Reason",
        "Comment": "Product is duplicated",
        "Display": "Duplicate product"
    }
}

# Streamlit app layout
st.title("Product Validation Tool")

# File upload section within an expander
with st.expander("Upload CSV File"):
    uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Check if the file is uploaded
if uploaded_file is not None:
    try:
        # Load the uploaded CSV file
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        if not data.empty:
            with st.expander("Data Preview"):
                st.write("CSV file loaded successfully. Preview of data:")
                st.write(data.head())

            # Initialize lists for flagged products
            final_report_rows = []

            # Loop through each product row and apply flags
            for index, row in data.iterrows():
                reasons = []
                comments = []
                displays = []

                # Check for each flag condition and append corresponding reason and comment
                if pd.isna(row['COLOR']) or row['COLOR'] == '':
                    reasons.append(flag_reasons["Missing COLOR"]["Reason"])
                    comments.append(flag_reasons["Missing COLOR"]["Comment"])
                    displays.append(flag_reasons["Missing COLOR"]["Display"])

                if pd.isna(row['BRAND']) or row['BRAND'] == '' or pd.isna(row['NAME']) or row['NAME'] == '':
                    reasons.append(flag_reasons["Missing BRAND or NAME"]["Reason"])
                    comments.append(flag_reasons["Missing BRAND or NAME"]["Comment"])
                    displays.append(flag_reasons["Missing BRAND or NAME"]["Display"])

                if isinstance(row['NAME'], str) and len(row['NAME'].split()) == 1 and row['BRAND'] != 'Jumia Book':
                    reasons.append(flag_reasons["Single-word NAME"]["Reason"])
                    comments.append(flag_reasons["Single-word NAME"]["Comment"])
                    displays.append(flag_reasons["Single-word NAME"]["Display"])

                valid_category_codes_fas = category_fas_data['ID'].tolist()
                if row['CATEGORY_CODE'] in valid_category_codes_fas and row['BRAND'] == 'Generic':
                    reasons.append(flag_reasons["Generic BRAND"]["Reason"])
                    comments.append(flag_reasons["Generic BRAND"]["Comment"])
                    displays.append(flag_reasons["Generic BRAND"]["Display"])

                brand = row['BRAND']
                if brand in perfumes_data['BRAND'].values:
                    keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                    for keyword in keywords:
                        if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                            perfume_price = perfumes_data.loc[(perfumes_data['BRAND'] == brand) & (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                            price_difference = row['GLOBAL_PRICE'] - perfume_price
                            if price_difference < 0:
                                reasons.append(flag_reasons["Perfume price issue"]["Reason"])
                                comments.append(flag_reasons["Perfume price issue"]["Comment"])
                                displays.append(flag_reasons["Perfume price issue"]["Display"])
                                break

                def check_blacklist(name):
                    if isinstance(name, str):
                        name_words = name.lower().split()
                        return any(black_word.lower() in name_words for black_word in blacklisted_words)
                    return False

                if check_blacklist(row['NAME']):
                    reasons.append(flag_reasons["Blacklisted word in NAME"]["Reason"])
                    comments.append(flag_reasons["Blacklisted word in NAME"]["Comment"])
                    displays.append(flag_reasons["Blacklisted word in NAME"]["Display"])

                if isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower():
                    reasons.append(flag_reasons["BRAND name repeated in NAME"]["Reason"])
                    comments.append(flag_reasons["BRAND name repeated in NAME"]["Comment"])
                    displays.append(flag_reasons["BRAND name repeated in NAME"]["Display"])

                duplicate_check = data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)
                if duplicate_check.iloc[index]:
                    reasons.append(flag_reasons["Duplicate product"]["Reason"])
                    comments.append(flag_reasons["Duplicate product"]["Comment"])
                    displays.append(flag_reasons["Duplicate product"]["Display"])

                status = 'Rejected' if reasons else 'Approved'
                reason_text = ' | '.join(reasons) if reasons else ''
                comment_text = ' | '.join(comments) if comments else ''
                display_text = ' | '.join(displays) if displays else ''

                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], status, reason_text, comment_text, display_text))

            # Create DataFrame for the final report
            final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment', 'Display'])
            
            # Display final report preview within an expander
            with st.expander("Final Report Preview"):
                st.write(final_report_df)

            # Download button to save the report
            def to_excel(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='ProductSets')
                    reasons_data.to_excel(writer, index=False, sheet_name='RejectionReasons')
                output.seek(0)
                return output

            st.download_button("Download Final Report", to_excel(final_report_df), "final_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        st.error(f"Error loading the CSV file: {e}")
