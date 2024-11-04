import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# Function to load blacklisted words and refurb sellers
def load_blacklisted_words():
    with open('blacklisted.txt', 'r') as f:
        return [line.strip() for line in f.readlines()]

def load_refurb_sellers():
    with open('refurb.txt', 'r') as f:
        return [line.strip() for line in f.readlines()]

# Load data for checks
check_variation_data = pd.read_excel('check_variation.xlsx')
category_fas_data = pd.read_excel('category_FAS.xlsx')
perfumes_data = pd.read_excel('perfumes.xlsx')
blacklisted_words = load_blacklisted_words()
refurb_sellers = load_refurb_sellers()

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

            # Initialize flags and counters
            total_flagged_products = 0

            # Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            missing_color['Reason'] = "1000005 - Kindly confirm the actual product colour"

            # Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            missing_brand_or_name['Reason'] = "1000007 - Other Reason"

            # Single-word NAME (excluding "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            single_word_name['Reason'] = "1000008 - Kindly Improve Product Name Description"

            # Generic Brand Check
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]
            generic_brand_issues['Reason'] = "1000007 - Other Reason"

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
            flagged_perfumes_df['Reason'] = "1000030 - Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)"

            # Blacklisted words in NAME
            def check_blacklist(name):
                if isinstance(name, str):
                    name_words = name.lower().split()
                    return any(black_word.lower() in name_words for black_word in blacklisted_words)
                return False

            flagged_blacklisted = data[data['NAME'].apply(check_blacklist)]
            flagged_blacklisted['Reason'] = "1000033 - Keywords in your content/ Product name / description has been blacklisted"

            # BRAND name repetition in NAME
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
            brand_in_name['Reason'] = "1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name"

            # Refurbishment check
            refurb_check = data[(data['NAME'].str.contains('refurb', case=False, na=False)) & (~data['SELLER_NAME'].isin(refurb_sellers))]
            refurb_check['Reason'] = "1000040 - Unauthorized refurb seller"

            # Aggregate flagged data
            all_flags = pd.concat([
                missing_color, missing_brand_or_name, single_word_name, generic_brand_issues, 
                flagged_perfumes_df, flagged_blacklisted, brand_in_name, refurb_check
            ])
            total_flagged_products = len(all_flags)

            # Display flagged data
            st.write(f"Total flagged products: {total_flagged_products}")
            st.write(all_flags[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME', 'Reason']])

            # Prepare the final report DataFrame
            final_report_df = data[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'PARENTSKU']].copy()
            final_report_df['Status'] = final_report_df['PRODUCT_SET_SID'].apply(lambda x: 'Rejected' if x in all_flags['PRODUCT_SET_SID'].values else 'Approved')
            final_report_df['Reason'] = final_report_df['PRODUCT_SET_SID'].map(all_flags.set_index('PRODUCT_SET_SID')['Reason']).fillna('')
            final_report_df['Comment'] = final_report_df['Reason']

            # Separate approved and rejected reports
            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

            # Function to convert DataFrame to downloadable Excel file
            def to_excel(dataframe, sheet_name):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    dataframe.to_excel(writer, index=False, sheet_name=sheet_name)
                return output.getvalue()

            # Generate date for filenames
            date_str = datetime.now().strftime("%Y-%m-%d")

            # Download buttons for reports
            st.download_button("Download Approved Report", data=to_excel(approved_df, 'ProductSets'), file_name=f"approved_report_{date_str}.xlsx")
            st.download_button("Download Rejected Report", data=to_excel(rejected_df, 'ProductSets'), file_name=f"rejected_report_{date_str}.xlsx")
            st.download_button("Download Combined Report", data=to_excel(final_report_df, 'ProductSets'), file_name=f"combined_report_{date_str}.xlsx")

    except Exception as e:
        st.error(f"Error loading file: {e}")
else:
    st.info("Please upload a CSV file to proceed.")
