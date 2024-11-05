import pandas as pd
import streamlit as st
from io import BytesIO

# Load rejection reasons from the RejectionReasons sheet
rejection_reasons = pd.read_excel('reasons.xlsx', sheet_name='RejectionReasons')
# Convert the reasons to a dictionary for easy lookup
reasons_dict = rejection_reasons.set_index('Flag').to_dict(orient='index')

# Define function to load blacklisted words
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

            # Flag products as per each condition
            def flag_reason(row):
                flags = []
                if pd.isna(row['COLOR']) or row['COLOR'] == '':
                    flags.append('Missing color')
                if pd.isna(row['BRAND']) or row['BRAND'] == '' or pd.isna(row['NAME']) or row['NAME'] == '':
                    flags.append('Missing brand or name')
                if isinstance(row['NAME'], str) and len(row['NAME'].split()) == 1 and row['BRAND'] != 'Jumia Book':
                    flags.append('Single-word names')
                if row['CATEGORY_CODE'] in category_fas_data['ID'].values and row['BRAND'] == 'Generic':
                    flags.append('Generic brands')
                if check_perfume(row):
                    flags.append('Perfume price issues')
                if check_blacklist(row['NAME']):
                    flags.append('Blacklisted words in names')
                if isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower():
                    flags.append('Brand name repetition in the product name')
                return flags

            def get_reason_text(flags):
                # Map each flag to the reason code and message from RejectionReasons
                return [f"{reasons_dict[flag]['Code']} - {reasons_dict[flag]['Message']}" for flag in flags if flag in reasons_dict]

            # Final report creation
            final_report_rows = []
            for _, row in data.iterrows():
                flags = flag_reason(row)
                status = 'Rejected' if flags else 'Approved'
                reason = ' | '.join(get_reason_text(flags)) if flags else ''
                comment = reason  # Temporarily using reason as comment, per instructions
                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], status, reason, comment))

            final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment'])
            st.write("Final Report Preview")
            st.write(final_report_df)

            # Function to export DataFrame as Excel
            def to_excel(dataframe):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    dataframe.to_excel(writer, index=False, sheet_name='ProductSets')
                    rejection_reasons.to_excel(writer, index=False, sheet_name='RejectionReasons')
                output.seek(0)
                return output

            # Download buttons for approved, rejected, and combined reports
            st.download_button(label='Download Approved Products', data=to_excel(final_report_df[final_report_df['Status'] == 'Approved']), file_name='approved_products.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            st.download_button(label='Download Rejected Products', data=to_excel(final_report_df[final_report_df['Status'] == 'Rejected']), file_name='rejected_products.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            st.download_button(label='Download Combined Report', data=to_excel(final_report_df), file_name='combined_report.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        st.error(f"Error processing the file: {e}")
