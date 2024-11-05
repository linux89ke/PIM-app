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
        st.write("CSV file loaded successfully. Preview of data:")
        st.write(data.head())

        # Initialize a list to hold the final report rows
        final_report_rows = []

        # Flagging criteria
        missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
        missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
        single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
        
        valid_category_codes_fas = category_fas_data['ID'].tolist()
        generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]
        
        # Perfume price issue
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
        flagged_perfumes_df = pd.DataFrame(flagged_perfumes)

        # Blacklisted words
        def check_blacklist(name):
            if isinstance(name, str):
                name_words = name.lower().split()
                return any(black_word.lower() in name_words for black_word in blacklisted_words)
            return False

        flagged_blacklisted = data[data['NAME'].apply(check_blacklist)]
        brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

        # Display each flag in Streamlit
        flag_sections = {
            "Missing COLOR": missing_color,
            "Missing BRAND or NAME": missing_brand_or_name,
            "Single-word NAME": single_word_name,
            "Generic BRAND for valid CATEGORY_CODE": generic_brand_issues,
            "Perfume price issue": flagged_perfumes_df,
            "Blacklisted words in NAME": flagged_blacklisted,
            "BRAND name repeated in NAME": brand_in_name
        }
        
        for flag, df in flag_sections.items():
            with st.expander(f"{flag} ({len(df)} products)"):
                st.write(df[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
        
        # Collect flagged products with reasons for final report
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
            if row['PRODUCT_SET_SID'] in flagged_perfumes_df['PRODUCT_SET_SID'].values:
                reasons.append("Perfume price issue")
            if row['PRODUCT_SET_SID'] in flagged_blacklisted['PRODUCT_SET_SID'].values:
                reasons.append("Blacklisted word in NAME")
            if row['PRODUCT_SET_SID'] in brand_in_name['PRODUCT_SET_SID'].values:
                reasons.append("BRAND name repeated in NAME")

            status = 'Rejected' if reasons else 'Approved'
            reason = ' | '.join(reasons)
            final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], status, reason, reason))

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
