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

            # Check for necessary columns in the uploaded CSV
            required_columns = ['PRODUCT_SET_SID', 'PARENTSKU', 'NAME', 'BRAND', 'SELLER_NAME', 'CATEGORY_CODE', 'COLOR', 'GLOBAL_SALE_PRICE', 'GLOBAL_PRICE']
            missing_columns = [col for col in required_columns if col not in data.columns]

            if missing_columns:
                st.error(f"The following required columns are missing in your file: {', '.join(missing_columns)}")
            else:
                # Initialize list for flagged products
                flagged_rows = []

                # Define unique CATEGORY_CODE exceptions from category_FAS.xlsx
                unique_category_codes = category_fas_data['ID'].tolist()

                # Loop through each row and apply flags
                for index, row in data.iterrows():
                    reasons = []

                    # Missing Color flag
                    if pd.isna(row['COLOR']):
                        reasons.append("1000005 - Kindly confirm the actual product colour")

                    # Missing BRAND or NAME
                    if pd.isna(row['BRAND']) or pd.isna(row['NAME']):
                        reasons.append("1000007 - Other Reason")

                    # Single-word NAME
                    if isinstance(row['NAME'], str) and len(row['NAME'].split()) == 1:
                        reasons.append("1000008 - Kindly Improve Product Name Description")

                    # Generic BRAND
                    if row['BRAND'] == 'Generic':
                        reasons.append("1000007 - Other Reason")

                    # Perfume Price Issue
                    perfume = perfumes_data[perfumes_data['PRODUCT_NAME'].str.lower() == row['NAME'].lower()]
                    if not perfume.empty:
                        perfume_price = perfume.iloc[0]['PRICE']
                        price_difference = abs(row['GLOBAL_SALE_PRICE'] - perfume_price) / perfume_price
                        if price_difference < 0.3:
                            reasons.append("1000030 - Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)")

                    # Blacklisted words in NAME
                    if any(word in row['NAME'] for word in blacklisted_words):
                        reasons.append("1000033 - Keywords in your content/ Product name / description has been blacklisted")

                    # Brand Repetition in NAME
                    if isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower():
                        reasons.append("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name")

                    # Append flagged row
                    status = 'Rejected' if reasons else 'Approved'
                    comment = ' | '.join(set(reasons)) if reasons else 'No issues found'
                    flagged_rows.append({
                        'ProductSetSid': row['PRODUCT_SET_SID'],
                        'ParentSKU': row['PARENTSKU'],
                        'Status': status,
                        'Reason': ', '.join(set(reasons)) if reasons else 'Approved',
                        'Comment': comment
                    })

                # Duplicate Flag (with CATEGORY_CODE exception)
                duplicate_groups = data.groupby(['NAME', 'BRAND', 'SELLER_NAME'])
                for _, group in duplicate_groups:
                    if len(group) > 1:
                        is_exception = group['CATEGORY_CODE'].isin(unique_category_codes).all()

                        if not is_exception:
                            first_row = True
                            for _, row in group.iterrows():
                                if first_row:
                                    first_row = False
                                    if any(item['ProductSetSid'] == row['PRODUCT_SET_SID'] and item['Status'] == 'Rejected' for item in flagged_rows):
                                        continue  # If already rejected for another reason, skip flagging for duplicate
                                    else:
                                        flagged_rows.append({
                                            'ProductSetSid': row['PRODUCT_SET_SID'],
                                            'ParentSKU': row['PARENTSKU'],
                                            'Status': 'Approved',
                                            'Reason': 'Duplicate - Approved',
                                            'Comment': 'Duplicate - Approved but not flagged for any other reason'
                                        })
                                else:
                                    flagged_rows.append({
                                        'ProductSetSid': row['PRODUCT_SET_SID'],
                                        'ParentSKU': row['PARENTSKU'],
                                        'Status': 'Rejected',
                                        'Reason': 'Duplicate Product',
                                        'Comment': 'Duplicate based on NAME, BRAND, and SELLER_NAME'
                                    })

                # Prepare the final report DataFrame
                final_report_df = pd.DataFrame(flagged_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment'])
                st.write("Final Report Preview with Flags")
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
