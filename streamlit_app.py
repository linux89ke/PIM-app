import pandas as pd
import streamlit as st
from io import BytesIO

# Function to load blacklisted words from a file
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

            # Prepare the final report rows with separate flags for each issue
            final_report_rows = []
            for index, row in data.iterrows():
                flag_missing_color = False
                flag_missing_variation = False
                flag_price_diff = False
                flag_generic_brand = False
                flagged_word = None  # Track blacklisted word found

                # Flag 1: Missing COLOR
                if pd.isna(row['COLOR']) or row['COLOR'] == '':
                    flag_missing_color = True

                # Flag 2: Check CATEGORY_CODE in check_variation.xlsx and verify VARIATION
                if row['CATEGORY_CODE'] in check_variation_data['ID'].values:
                    if pd.isna(row['VARIATION']) or row['VARIATION'] == '':
                        flag_missing_variation = True

                # Flag 3: Price difference between GLOBAL_SALE_PRICE and PRICE in perfumes.xlsx
                matched_perfume = perfumes_data[perfumes_data['PRODUCT_NAME'].str.lower() == row['NAME'].lower()]
                if not matched_perfume.empty:
                    original_price = matched_perfume.iloc[0]['PRICE']
                    sale_price = row['GLOBAL_SALE_PRICE']
                    if original_price and sale_price and ((sale_price - original_price) / original_price < 0.3):
                        flag_price_diff = True

                # Flag 4: CATEGORY_CODE in category_FAS.xlsx and BRAND is 'Generic'
                if row['CATEGORY_CODE'] in category_fas_data['ID'].values and row['BRAND'].lower() == 'generic':
                    flag_generic_brand = True

                # Flag 5: Blacklisted word appears in NAME
                for word in blacklisted_words:
                    if f' {word} ' in f' {row["NAME"].lower()} ':
                        flagged_word = word
                        break

                # Set the status based on whether any flags were triggered
                status = 'Rejected' if (flag_missing_color or flag_missing_variation or flag_price_diff or flag_generic_brand or flagged_word) else 'Approved'
                reason = '1000007 - Other Reason' if status == 'Rejected' else ''

                # Add row to final report with columns for each flag status
                final_report_rows.append({
                    'ProductSetSid': row['PRODUCT_SET_SID'],
                    'ParentSKU': row['PARENTSKU'],
                    'Status': status,
                    'Reason': reason,
                    'Flag Missing Color': 'Yes' if flag_missing_color else '',
                    'Flag Missing Variation': 'Yes' if flag_missing_variation else '',
                    'Flag Price Difference': 'Yes' if flag_price_diff else '',
                    'Flag Generic Brand': 'Yes' if flag_generic_brand else '',
                    'Blacklisted Word': flagged_word if flagged_word else ''
                })

            # Create combined report DataFrame with columns for each flag
            combined_df = pd.DataFrame(final_report_rows)

            # Display the combined DataFrame with all flags to the user
            st.write("Combined Report with Flags:")
            st.write(combined_df)

            # Separate approved and rejected DataFrames for download
            approved_df = combined_df[combined_df['Status'] == 'Approved']
            rejected_df = combined_df[combined_df['Status'] == 'Rejected']

            # Function to create Excel file from DataFrame
            def create_excel(dataframe, sheet_name):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
                    pd.DataFrame().to_excel(writer, sheet_name='RejectionReasons', index=False)  # Empty sheet
                output.seek(0)
                return output

            # Generate downloadable files for each report type
            approved_excel = create_excel(approved_df, 'ApprovedReport')
            rejected_excel = create_excel(rejected_df, 'RejectedReport')
            combined_excel = create_excel(combined_df, 'CombinedReport')

            # Download buttons for each report
            st.download_button(
                label="Download Approved Report",
                data=approved_excel,
                file_name="approved_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.download_button(
                label="Download Rejected Report",
                data=rejected_excel,
                file_name="rejected_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.download_button(
                label="Download Combined Report",
                data=combined_excel,
                file_name="combined_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
