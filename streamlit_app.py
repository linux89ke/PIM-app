import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# Function to load blacklisted words
def load_blacklisted_words():
    with open('blacklisted.txt', 'r') as f:
        return [line.strip() for line in f.readlines()]

# Load required data files
check_variation_data = pd.read_excel('check_variation.xlsx')
category_fas_data = pd.read_excel('category_FAS.xlsx')
perfumes_data = pd.read_excel('perfumes.xlsx')
reasons_data = pd.read_excel('reasons.xlsx')
blacklisted_words = load_blacklisted_words()

# Flag definitions for specific reasons and comments
flag_definitions = {
    "Missing COLOR": {"Reason": "1000005 - Kindly confirm the actual product colour", "Comment": "Kindly include color of the product", "Display": "Missing COLOR"},
    "Missing BRAND or NAME": {"Reason": "1000007 - Other Reason", "Comment": "Missing BRAND or NAME", "Display": "Missing BRAND or NAME"},
    "Single-word NAME": {"Reason": "1000008 - Kindly Improve Product Name Description", "Comment": "Kindly Improve Product Name", "Display": "Name too short"},
    "Generic BRAND": {"Reason": "1000007 - Other Reason", "Comment": "Kindly use Fashion as brand name for Fashion products", "Display": "Brand is Generic instead of Fashion"},
    "Perfume price issue": {"Reason": "1000030 - Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)", "Display": "Perfume price too low"},
    "Blacklisted word in NAME": {"Reason": "1000033 - Keywords in your content/ Product name / description has been blacklisted", "Comment": "Keywords in your content/ Product name / description has been blacklisted", "Display": "Blacklisted word in NAME"},
    "BRAND name repeated in NAME": {"Reason": "1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", "Comment": "Kindly Ensure Brand Name Is Not Repeated In Product Name", "Display": "BRAND name repeated in NAME"},
    "Duplicate product": {"Reason": "1000007 - Other Reason", "Comment": "Product is duplicated", "Display": "Duplicate product"}
}

# Streamlit layout
st.title("Product Validation Tool")

uploaded_file = st.file_uploader("Upload your CSV file", type='csv')
if uploaded_file:
    try:
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        st.write("CSV file loaded successfully. Preview of data:")
        st.write(data.head())

        final_report_rows = []
        flagged_dataframes = {}

        def flag_product(row, flag_name):
            reason_info = flag_definitions[flag_name]
            return {
                "ProductSetSid": row['PRODUCT_SET_SID'],
                "ParentSKU": row['PARENTSKU'],
                "Status": "Rejected",
                "Reason": reason_info["Display"],
                "Comment": reason_info["Comment"]
            }

        # Define flagging conditions
        missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
        missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
        single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
        valid_category_codes_fas = category_fas_data['ID'].tolist()
        generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]

        # Perfume price check
        flagged_perfumes = []
        for _, row in data.iterrows():
            brand = row['BRAND']
            if brand in perfumes_data['BRAND'].values:
                keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                for keyword in keywords:
                    if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                        perfume_price = perfumes_data.loc[(perfumes_data['BRAND'] == brand) & (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                        if row['GLOBAL_PRICE'] < perfume_price * 1.3:
                            flagged_perfumes.append(row)
                            break

        # Blacklisted words in NAME
        def check_blacklist(name):
            if isinstance(name, str):
                return any(black_word.lower() in name.lower() for black_word in blacklisted_words)
            return False

        flagged_blacklisted = data[data['NAME'].apply(check_blacklist)]

        # Brand name repeated in NAME
        brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

        # Duplicate products
        duplicate_products = data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]

        # Consolidate all flagged products
        for flag_name, flagged_df in zip(
            ["Missing COLOR", "Missing BRAND or NAME", "Single-word NAME", "Generic BRAND", "Perfume price issue", "Blacklisted word in NAME", "BRAND name repeated in NAME", "Duplicate product"],
            [missing_color, missing_brand_or_name, single_word_name, generic_brand_issues, flagged_perfumes, flagged_blacklisted, brand_in_name, duplicate_products]
        ):
            if not flagged_df.empty:
                flagged_products = [flag_product(row, flag_name) for _, row in flagged_df.iterrows()]
                flagged_df_with_reasons = pd.DataFrame(flagged_products)
                final_report_rows.extend(flagged_products)
                flagged_dataframes[flag_name] = flagged_df_with_reasons

        # Display flagged dataframes in Streamlit expanders
        for flag_name, flagged_df in flagged_dataframes.items():
            with st.expander(f"{flag_name} ({len(flagged_df)})"):
                st.write(flagged_df)

        # Create final report DataFrame
        final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment'])
        
        # Split into Approved and Rejected DataFrames
        approved_df = final_report_df[final_report_df['Status'] == 'Approved']
        rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

        today_date = datetime.now().strftime("%Y-%m-%d")

        # Excel download function
        def to_excel(df, rejection_reasons_df):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='ProductSets')
                rejection_reasons_df.to_excel(writer, index=False, sheet_name='RejectionReasons')
            output.seek(0)
            return output

        # Download buttons for each report
        st.download_button(
            "Download Final Report",
            to_excel(final_report_df, reasons_data),
            f"final_report_{today_date}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.download_button(
            "Download Approved Products",
            to_excel(approved_df, reasons_data),
            f"approved_products_{today_date}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.download_button(
            "Download Rejected Products",
            to_excel(rejected_df, reasons_data),
            f"rejected_products_{today_date}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"Error loading the CSV file: {e}")
