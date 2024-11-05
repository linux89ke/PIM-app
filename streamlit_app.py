# Import necessary libraries
import pandas as pd
import streamlit as st
from io import BytesIO
import datetime

# Function to load blacklisted words
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

# Flagging criteria with specified reasons, comments, and display names
flagging_criteria = {
    "Missing COLOR": ("1000005 - Kindly confirm the actual product colour", "Kindly include color of the product"),
    "Missing BRAND or NAME": ("1000007 - Other Reason", "Missing BRAND or NAME"),
    "Name too short": ("1000008 - Kindly Improve Product Name Description", "Kindly Improve Product Name"),
    "Brand is Generic instead of Fashion": ("1000007 - Other Reason", "Kindly use Fashion as brand name for Fashion products"),
    "Perfume price too low": ("1000030 - Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)", ""),
    "Blacklisted word in NAME": ("1000033 - Keywords in your content/ Product name / description has been blacklisted", "Keywords in your content/ Product name / description has been blacklisted"),
    "BRAND name repeated in NAME": ("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", "Kindly Ensure Brand Name Is Not Repeated In Product Name"),
    "Duplicate product": ("1000007 - Other Reason", "Product is duplicated")
}

# Check if the file is uploaded
if uploaded_file is not None:
    try:
        # Load the uploaded CSV file
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')

        # Clean column names by stripping whitespace
        data.columns = data.columns.str.strip()

        # Display column names for debugging
        st.write("Columns in the uploaded CSV file:")
        st.write(data.columns.tolist())

        # Convert specific columns to string to avoid str accessor errors
        string_columns = ['NAME', 'BRAND', 'COLOR']
        for column in string_columns:
            if column in data.columns:
                data[column] = data[column].astype(str).fillna('')  # Convert to string and fill NaNs with empty strings

        # Convert numeric columns, catching errors
        numeric_columns = ['GLOBAL_PRICE', 'GLOBAL_SALE_PRICE']
        for column in numeric_columns:
            if column in data.columns:
                data[column] = pd.to_numeric(data[column], errors='coerce')

        # Display data types of the columns after conversion
        st.write("Data Types of the columns after conversion:")
        st.write(data.dtypes)

        # Check for the presence of 'PRODUCT_SET_SID'
        if 'PRODUCT_SET_SID' not in data.columns:
            st.error("'PRODUCT_SET_SID' column is missing. Please check your CSV file.")
        else:
            st.write("'PRODUCT_SET_SID' column is present.")

        # Check for necessary columns
        required_columns = ['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'COLOR', 'BRAND', 'NAME', 'CATEGORY_CODE', 'GLOBAL_PRICE', 'PARENTSKU', 'SELLER_NAME']
        missing_columns = [col for col in required_columns if col not in data.columns]

        if missing_columns:
            st.error(f"The following required columns are missing from the uploaded file: {', '.join(missing_columns)}")
        else:
            if not data.empty:
                st.write("CSV file loaded successfully. Preview of data:")
                st.write(data.head())

                # Initialize lists to collect flagged rows for each flag category
                flags_data = {flag: pd.DataFrame() for flag in flagging_criteria.keys()}

                # Apply flagging rules in order of importance, stopping at the first match per product
                flagged_products = set()
                for flag, (reason, comment) in flagging_criteria.items():
                    if flag == "Missing COLOR":
                        flags_data[flag] = data[(data['COLOR'].isna() | (data['COLOR'] == '')) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
                    elif flag == "Missing BRAND or NAME":
                        flags_data[flag] = data[(data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
                    elif flag == "Name too short":
                        flags_data[flag] = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book') & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
                    elif flag == "Brand is Generic instead of Fashion":
                        valid_category_codes_fas = category_fas_data['ID'].tolist()
                        flags_data[flag] = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic') & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
                    elif flag == "Perfume price too low":
                        perfumes_data = perfumes_data.sort_values(by="PRICE", ascending=False).drop_duplicates(subset=["BRAND", "KEYWORD"], keep="first")
                        flagged_perfumes = []
                        for _, row in data.iterrows():
                            if row['PRODUCT_SET_SID'] not in flagged_products:
                                brand = row['BRAND']
                                if brand in perfumes_data['BRAND'].values:
                                    keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                                    for keyword in keywords:
                                        if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                                            perfume_price = perfumes_data.loc[(perfumes_data['BRAND'] == brand) & (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                                            price_difference = row['GLOBAL_PRICE'] - perfume_price
                                            if price_difference < 0:
                                                flagged_perfumes.append(row)
                                                flagged_products.add(row['PRODUCT_SET_SID'])
                                                break
                        flags_data[flag] = pd.DataFrame(flagged_perfumes)
                    elif flag == "Blacklisted word in NAME":
                        def check_blacklist(name):
                            if isinstance(name, str):
                                name_words = name.lower().split()
                                return any(black_word.lower() in name_words for black_word in blacklisted_words)
                            return False
                        flags_data[flag] = data[data['NAME'].apply(check_blacklist) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
                    elif flag == "BRAND name repeated in NAME":
                        flags_data[flag] = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
                    elif flag == "Duplicate product":
                        flags_data[flag] = data[data.duplicated(subset='PRODUCT_SET_ID', keep=False) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]

                    # Track flagged products to prevent re-flagging
                    flagged_products.update(flags_data[flag]['PRODUCT_SET_SID'].tolist())

                # Display flagged items with counts
                for flag, df in flags_data.items():
                    count = len(df)
                    with st.expander(f"{flag} ({count} products)"):
                        if count > 0:
                            st.write(df[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                        else:
                            st.write("No products flagged.")

                # Prepare final report
                final_report_rows = []
                for index, row in data.iterrows():
                    first_flag = next((flag for flag in flags_data if row['PRODUCT_SET_SID'] in flags_data[flag]['PRODUCT_SET_SID'].values), None)
                    
                    if first_flag:
                        reason_code, comment = flagging_criteria[first_flag]
                        status = 'Rejected'
                        reason = reason_code
                    else:
                        status = 'Approved'
                        reason = ''
                    final_report_rows.append({
                        'ProductSetSid': row['PRODUCT_SET_SID'],
                        'ParentSKU': row['PARENTSKU'],
                        'Status': status,
                        'Reason': reason,
                        'Comment': comment
                    })

                # Create DataFrame for the final report
                final_report_df = pd.DataFrame(final_report_rows)

                # Output the report
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    final_report_df.to_excel(writer, sheet_name='ProductSets', index=False)
                    # Include additional sheets as required
                output.seek(0)

                # Provide download links for reports
                current_date = datetime.datetime.now().strftime("%Y-%m-%d")
                st.download_button(
                    label="Download Final Report",
                    data=output,
                    file_name=f'final_report_{current_date}.xlsx',
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    except Exception as e:
        st.error(f"An error occurred: {e}")
