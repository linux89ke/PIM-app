import pandas as pd
import streamlit as st
from io import BytesIO

# Function to load blacklisted words
def load_blacklisted_words():
    try:
        with open('blacklisted.txt', 'r') as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        st.error("Blacklisted words file is missing.")
        return []

# Load data for checks
try:
    check_variation_data = pd.read_excel('check_variation.xlsx')
    category_fas_data = pd.read_excel('category_FAS.xlsx')
    perfumes_data = pd.read_excel('perfumes.xlsx')
except Exception as e:
    st.error(f"Error loading required files: {e}")

blacklisted_words = load_blacklisted_words()

# Streamlit app layout
st.title("Product Validation Tool")

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Check if the file is uploaded
if uploaded_file is not None:
    try:
        # Load uploaded CSV
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        if data.empty:
            st.error("Uploaded file is empty.")
            st.stop()
        
        st.write("CSV file loaded successfully. Preview:")
        st.write(data.head())

        # Initialize flag counter
        total_flagged_products = 0

        # Flag Checks
        flag_checks = {
            "Missing COLOR": data['COLOR'].isna() | (data['COLOR'] == ''),
            "Missing BRAND or NAME": data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == ''),
            "Single-word NAME": (data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book'),
            "Missing VARIATION for valid CATEGORY_CODE": data['CATEGORY_CODE'].isin(check_variation_data['ID']) & ((data['VARIATION'].isna()) | (data['VARIATION'] == '')),
            "Generic BRAND for valid CATEGORY_CODE": data['CATEGORY_CODE'].isin(category_fas_data['ID']) & (data['BRAND'] == 'Generic')
        }

        # Flag: Perfume Price Check
        flagged_perfumes = []
        perfumes_data = perfumes_data.sort_values(by="PRICE", ascending=False).drop_duplicates(subset=["BRAND", "KEYWORD"], keep="first")
        for index, row in data.iterrows():
            brand = row['BRAND']
            if brand in perfumes_data['BRAND'].values:
                keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                for keyword in keywords:
                    if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                        perfume_price = perfumes_data.loc[(perfumes_data['BRAND'] == brand) & (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                        if row['GLOBAL_PRICE'] < perfume_price:
                            flagged_perfumes.append(row)
                            break

        # Flag: Blacklisted Words in NAME
        flagged_blacklisted = data[data['NAME'].apply(lambda x: any(bw.lower() in str(x).lower() for bw in blacklisted_words) if isinstance(x, str) else False)]
        
        # Flag: BRAND Name Repeated in NAME
        brand_in_name = data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)

        # Compile Flag Results and Generate Report
        final_report_rows = []
        for index, row in data.iterrows():
            reasons = [name for name, condition in flag_checks.items() if condition.iloc[index]]
            if row in flagged_perfumes:
                reasons.append("Perfume price issue")
            if brand_in_name[index]:
                reasons.append("BRAND name repeated in NAME")
            if index in flagged_blacklisted.index:
                reasons.append("Blacklisted word in NAME")

            # Set Status and Comments
            status = 'Rejected' if reasons else 'Approved'
            reason = '1000007 - Other Reason' if status == 'Rejected' else ''
            comment = ', '.join(reasons) if reasons else 'No issues'

            # Add to final report
            final_report_rows.append({
                'ProductSetSid': row['PRODUCT_SET_SID'],  
                'ParentSKU': row['PARENTSKU'],            
                'Status': status,
                'Reason': reason,
                'Comment': comment
            })

        # Convert to DataFrame and write Excel report
        final_report = pd.DataFrame(final_report_rows)
        rejection_reasons = pd.DataFrame()  # Empty sheet for RejectionReasons

        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            final_report.to_excel(writer, sheet_name='ProductSets', index=False)
            rejection_reasons.to_excel(writer, sheet_name='RejectionReasons', index=False)

        # Display and download button
        st.write("Preview of the ProductSets sheet:")
        st.write(final_report)
        st.download_button(
            label="Download Excel File",
            data=output.getvalue(),
            file_name='ProductSets.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
