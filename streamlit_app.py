import pandas as pd
import streamlit as st
from io import BytesIO
import datetime

# Function to convert dataframe to Excel
def to_excel(df, flags_data):
    with BytesIO() as b:
        with pd.ExcelWriter(b, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="ProductSets")
            flags_data.to_excel(writer, index=False, sheet_name="RejectionReasons")
        b.seek(0)
        return b.read()

# Load the necessary files
flags_file = 'flags.xlsx'
flags_data = pd.read_excel(flags_file)

check_variation_file = 'check_variation.xlsx'
check_variation = pd.read_excel(check_variation_file)

category_fas_file = 'category_FAS.xlsx'
category_fas = pd.read_excel(category_fas_file)

perfumes_file = 'perfumes.xlsx'
perfumes = pd.read_excel(perfumes_file)

# Set page configuration
st.set_page_config(page_title="Product Validation", layout="wide")

# Add a title and description
st.title("Product Validation")
st.markdown("""
This app validates the uploaded product data and checks for various issues.
""")

# File upload section
st.sidebar.header("Upload Files")
uploaded_file = st.sidebar.file_uploader("Upload your CSV file", type=["csv"])

# If a file is uploaded, process the file
if uploaded_file is not None:
    product_data = pd.read_csv(uploaded_file)

    # Check for missing color
    missing_color = product_data[product_data['COLOR'].isna()]

    # Check for missing brand or name
    missing_brand_or_name = product_data[product_data['BRAND'].isna() | product_data['NAME'].isna()]

    # Check for single-word product names
    single_word_name = product_data[product_data['NAME'].str.split().str.len() == 1]

    # Check for generic brand issues
    generic_brand_issues = product_data[product_data['BRAND'] == "Generic"]

    # Check for perfume price issues (flagging products with price issues)
    flagged_perfumes = product_data[product_data['CATEGORY_CODE'] == "Perfume"].copy()
    flagged_perfumes['PRICE_DIFF'] = abs(flagged_perfumes['GLOBAL_SALE_PRICE'] - flagged_perfumes['PRICE']) / flagged_perfumes['PRICE']
    flagged_perfumes = flagged_perfumes[flagged_perfumes['PRICE_DIFF'] < 0.30]

    # Check for blacklisted words in the product name
    with open("blacklisted.txt", "r") as file:
        blacklisted_words = file.read().splitlines()
    flagged_blacklisted = product_data[product_data['NAME'].apply(lambda x: any(word in x for word in blacklisted_words))]

    # Check for brand name repeated in the product name
    brand_in_name = product_data[product_data['NAME'].str.contains(product_data['BRAND'], case=False)]

    # Check for duplicate products
    duplicate_products = product_data[product_data.duplicated(subset=['NAME', 'BRAND', 'CATEGORY_CODE'], keep=False)]

    # Display results in expanders for each validation
    validation_results = [
        ("Missing COLOR", missing_color),
        ("Missing BRAND or NAME", missing_brand_or_name),
        ("Single-word NAME", single_word_name),
        ("Generic BRAND Issues", generic_brand_issues),
        ("Perfume Price Issues", flagged_perfumes),
        ("Blacklisted Words", flagged_blacklisted),
        ("Brand in Name", brand_in_name),
        ("Duplicate Products", duplicate_products)
    ]

    for title, df in validation_results:
        with st.expander(f"{title} ({len(df)} products)"):
            if not df.empty:
                st.dataframe(df)
            else:
                st.write("No issues found")

    # Add some space before the download buttons
    st.write("")  # Adds a small space
    st.write("")  # Adds another line of space
    st.markdown("<br><br>", unsafe_allow_html=True)  # Adds a larger space

    # Download buttons section
    col1, col2, col3 = st.columns(3)
    with col1:
        final_report_df = pd.concat([product_data, flagged_perfumes])  # Combine flagged products with main data
        final_report_excel = to_excel(final_report_df, flags_data)
        st.download_button(
            label="Download Full Report",
            data=final_report_excel,
            file_name=f"final_report_{datetime.datetime.now().strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col2:
        approved_df = product_data[~product_data['PARENTSKU'].isin(duplicate_products['PARENTSKU'])]
        approved_excel = to_excel(approved_df, flags_data)
        st.download_button(
            label="Download Approved Only",
            data=approved_excel,
            file_name=f"Product_Validation_Approved_{datetime.datetime.now().strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col3:
        rejected_df = product_data[product_data['PARENTSKU'].isin(duplicate_products['PARENTSKU'])]
        rejected_excel = to_excel(rejected_df, flags_data)
        st.download_button(
            label="Download Rejected Only",
            data=rejected_excel,
            file_name=f"Product_Validation_Rejected_{datetime.datetime.now().strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
