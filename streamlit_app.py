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

# Load rejection reasons from the RejectionReasons sheet
rejection_reasons = pd.read_excel('reasons.xlsx', sheet_name='RejectionReasons')

# Strip any leading/trailing spaces from column names
rejection_reasons.columns = rejection_reasons.columns.str.strip()

# Convert the reasons to a dictionary using 'CODE - REJECTION_REASON' as the index
if 'CODE - REJECTION_REASON' in rejection_reasons.columns:
    reasons_dict = rejection_reasons.set_index('CODE - REJECTION_REASON').to_dict(orient='index')
else:
    st.error("The 'CODE - REJECTION_REASON' column was not found in the RejectionReasons sheet.")

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

            # Initialize counters for flagged products
            total_flagged_products = 0

            # Flag 1: Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            missing_color_count = len(missing_color)

            # Flag 2: Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            missing_brand_or_name_count = len(missing_brand_or_name)

            # Flag 3: Single-word NAME (but not for "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            single_word_name_count = len(single_word_name)

            # Flag 5: Generic Brand Check
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]
            generic_brand_count = len(generic_brand_issues)

            # Flag 6: Price and Keyword Check (Perfume Check)
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
            flagged_perfumes_count = len(flagged_perfumes)

            # Flag 7: Blacklisted Words in NAME (word appears in full and on its own)
            def check_blacklist(name):
                if isinstance(name, str):
                    name_words = name.lower().split()
                    return any(black_word.lower() in name_words for black_word in blacklisted_words)
                return False

            flagged_blacklisted = data[data['NAME'].apply(check_blacklist)]
            flagged_blacklisted_count = len(flagged_blacklisted)

            # Flag 8: Brand name repeated in NAME (case-insensitive)
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
            brand_in_name_count = len(brand_in_name)

            # Show total number of rows and flagged products
            total_rows = len(data)
            st.write(f"Total number of rows: {total_rows}")

            # Prepare a list to hold the final report rows
            final_report_rows = []

            # Collect all flagged products for final report
            for index, row in data.iterrows():
                reasons = []
                if row['PRODUCT_SET_SID'] in missing_color['PRODUCT_SET_SID'].values:
                    reasons.append("Missing COLOR")
                if row['PRODUCT_SET_SID'] in missing_brand_or_name['PRODUCT_SET_SID'].values:
                    reasons.append("Missing BRAND or NAME")
                if row['PRODUCT_SET_SID'] in single_word_name['PRODUCT_SET_SID'].values:
                    reasons.append("Single-word NAME")
                if row['PRODUCT_SET_SID'] in generic_brand_issues['PRODUCT_SET_SID'].values:
                    reasons.append("Generic BRAND")
                if row['PRODUCT_SET_SID'] in [r['PRODUCT_SET_SID'] for r in flagged_perfumes]:
                    reasons.append("Perfume price issue")
                if row['PRODUCT_SET_SID'] in flagged_blacklisted['PRODUCT_SET_SID'].values:
                    reasons.append("Blacklisted word in NAME")
                if row['PRODUCT_SET_SID'] in brand_in_name['PRODUCT_SET_SID'].values:
                    reasons.append("BRAND name repeated in NAME")

                # Match reasons with the rejection reasons dictionary
                reason_texts = [reasons_dict[reason]['Message'] for reason in reasons if reason in reasons_dict]
                reason_code = [reasons_dict[reason]['Code'] for reason in reasons if reason in reasons_dict]
                
                status = 'Rejected' if reasons else 'Approved'
                reason = ' | '.join(reason_texts) if reason_texts else ''
                comment = ' | '.join(reason_code) if reason_code else ''
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], status, reason, comment))

            # Prepare the final report DataFrame
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
                    rejection_reasons.to_excel(writer, index=False, sheet_name='RejectionReasons')
                output.seek(0)
                return output

            # Download buttons for approved and rejected reports
            st.download_button(label='Download Approved Products', data=to_excel(approved_df), file_name='approved_products.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            st.download_button(label='Download Rejected Products', data=to_excel(rejected_df), file_name='rejected_products.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

            # Combined report button
            st.download_button(label='Download Combined Report', data=to_excel(final_report_df), file_name='combined_report.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        st.error(f"An error occurred: {e}")
