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

            # Initialize a list to accumulate flagged entries
            final_report_rows = []

            # Flag 1: Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            missing_color_count = len(missing_color)

            # Flag 2: Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            missing_brand_or_name_count = len(missing_brand_or_name)

            # Flag 3: Single-word NAME (but not for "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            single_word_name_count = len(single_word_name)

            # Flag 4: Generic Brand Check
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]
            generic_brand_count = len(generic_brand_issues)

            # Flag 5: Perfume price check
            flagged_perfumes = []
            for _, row in data.iterrows():
                if row['BRAND'] in perfumes_data['BRAND'].values:
                    keywords = perfumes_data[perfumes_data['BRAND'] == row['BRAND']]['KEYWORD'].tolist()
                    for keyword in keywords:
                        if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                            perfume_price = perfumes_data.loc[(perfumes_data['BRAND'] == row['BRAND']) & (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                            if row['GLOBAL_PRICE'] - perfume_price < 0:
                                flagged_perfumes.append(row)
                                break
            flagged_perfumes_df = pd.DataFrame(flagged_perfumes)
            flagged_perfumes_count = len(flagged_perfumes_df)

            # Flag 6: Blacklisted Words in NAME
            def check_blacklist(name):
                if isinstance(name, str):
                    name_words = name.lower().split()
                    return any(black_word.lower() in name_words for black_word in blacklisted_words)
                return False

            flagged_blacklisted = data[data['NAME'].apply(check_blacklist)]
            flagged_blacklisted_count = len(flagged_blacklisted)

            # Flag 7: Brand name repeated in NAME
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
            brand_in_name_count = len(brand_in_name)

            # Flagging logic and result display
            for _, row in data.iterrows():
                reasons = []
                if row['PRODUCT_SET_SID'] in missing_color['PRODUCT_SET_SID'].values:
                    reasons.append("Missing COLOR")
                if row['PRODUCT_SET_SID'] in missing_brand_or_name['PRODUCT_SET_SID'].values:
                    reasons.append("Missing BRAND or NAME")
                if row['PRODUCT_SET_SID'] in single_word_name['PRODUCT_SET_SID'].values:
                    reasons.append("Single-word NAME")
                if row['PRODUCT_SET_SID'] in generic_brand_issues['PRODUCT_SET_SID'].values:
                    reasons.append("Generic BRAND")
                if row['PRODUCT_SET_SID'] in flagged_perfumes_df['PRODUCT_SET_SID'].values:
                    reasons.append("Perfume price issue")
                if row['PRODUCT_SET_SID'] in flagged_blacklisted['PRODUCT_SET_SID'].values:
                    reasons.append("Blacklisted word in NAME")
                if row['PRODUCT_SET_SID'] in brand_in_name['PRODUCT_SET_SID'].values:
                    reasons.append("BRAND name repeated in NAME")

                status = 'Rejected' if reasons else 'Approved'
                reason = ' | '.join(reasons) if reasons else ''
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], status, reason, reason))

            # Final report DataFrame
            final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment'])
            st.write("Final Report Preview")
            st.write(final_report_df)

            # Separate approved and rejected reports
            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

            # Export to Excel function
            def to_excel(dataframe):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    dataframe.to_excel(writer, index=False, sheet_name='ProductSets')
                    reasons_df = pd.read_excel('reasons.xlsx')
                    reasons_df.to_excel(writer, index=False, sheet_name='RejectionReasons')
                return output.getvalue()

            # Download buttons
            st.download_button("Download Approved Products Report", data=to_excel(approved_df), file_name='approved_products.xlsx')
            st.download_button("Download Rejected Products Report", data=to_excel(rejected_df), file_name='rejected_products.xlsx')
            st.download_button("Download Combined Report", data=to_excel(final_report_df), file_name='combined_report.xlsx')

    except Exception as e:
        st.error(f"An error occurred: {e}")
