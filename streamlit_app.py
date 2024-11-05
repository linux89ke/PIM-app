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

            # Flag checks (as before)
            # [Insert all previous flags here, for Missing COLOR, BRAND, single-word NAME, Generic BRAND, etc.]

            # Duplicate Flag
            duplicate_flag_rows = []
            unique_flag = category_fas_data['ID'].tolist()
            duplicate_groups = data.groupby(['NAME', 'BRAND', 'SELLER_NAME'])

            for _, group in duplicate_groups:
                if len(group) > 1:
                    # Check if CATEGORY_CODE exists in the exceptions file (category_FAS.xlsx)
                    is_exception = group['CATEGORY_CODE'].isin(unique_flag).all()

                    if not is_exception:
                        reasons = group['PRODUCT_SET_SID'].apply(lambda x: [])
                        first_row = True

                        for index, row in group.iterrows():
                            if first_row:
                                # Approve first item unless it has other flags
                                if row['PRODUCT_SET_SID'] not in [row['PRODUCT_SET_SID'] for row in duplicate_flag_rows]:
                                    duplicate_flag_rows.append({
                                        'ProductSetSid': row['PRODUCT_SET_SID'],
                                        'ParentSKU': row['PARENTSKU'],
                                        'Status': 'Approved',
                                        'Reason': 'Duplicate - Approved',
                                        'Comment': 'Duplicate - Approved but not flagged for any other reason'
                                    })
                                first_row = False
                            else:
                                # Flag other duplicates
                                duplicate_flag_rows.append({
                                    'ProductSetSid': row['PRODUCT_SET_SID'],
                                    'ParentSKU': row['PARENTSKU'],
                                    'Status': 'Rejected',
                                    'Reason': 'Duplicate Product',
                                    'Comment': 'Duplicate based on NAME, BRAND, and SELLER_NAME'
                                })

            # Prepare the final report DataFrame
            final_report_df = pd.DataFrame(duplicate_flag_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment'])
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
                output.seek(0)
                return output

            # Download buttons for approved and rejected reports
            st.download_button(label='Download Approved Products', data=to_excel(approved_df), file_name='approved_products.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            st.download_button(label='Download Rejected Products', data=to_excel(rejected_df), file_name='rejected_products.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

            # Combined report button
            st.download_button(label='Download Combined Report', data=to_excel(final_report_df), file_name='combined_report.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        st.error(f"An error occurred: {e}")
