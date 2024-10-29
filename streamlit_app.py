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

            # Initialize counters for flagged products
            total_flagged_products = 0

            # Flag 1: Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            # Other flags omitted for brevity but add them here as in previous code...

            # Prepare the final report rows with status and reasons for each product
            final_report_rows = []
            for index, row in data.iterrows():
                reasons = []
                # Add logic for all flag checks here and append relevant reasons
                status = 'Rejected' if reasons else 'Approved'
                reason = '1000007 - Other Reason' if status == 'Rejected' else ''
                comment = ', '.join(reasons) if reasons else 'No issues'

                final_report_rows.append({
                    'ProductSetSid': row['PRODUCT_SET_SID'],
                    'ParentSKU': row['PARENTSKU'],
                    'Status': status,
                    'Reason': reason,
                    'Comment': comment
                })

            # Create final combined report DataFrame
            combined_df = pd.DataFrame(final_report_rows)

            # Separate approved and rejected dataframes for download
            approved_df = combined_df[combined_df['Status'] == 'Approved']
            rejected_df = combined_df[combined_df['Status'] == 'Rejected']

            # Function to create Excel file from dataframe
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
