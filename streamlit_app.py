import pandas as pd
import streamlit as st
from io import BytesIO

# Load any necessary files for checks
check_variation_data = pd.read_excel('check_variation.xlsx')
category_fas_data = pd.read_excel('category_FAS.xlsx')
perfumes_data = pd.read_excel('perfumes.xlsx')
blacklisted_words = ['example_blacklist_word1', 'example_blacklist_word2']  # Placeholder list

# Streamlit app layout
st.title("Product Validation Tool")

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

if uploaded_file is not None:
    try:
        # Load and display CSV file
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        st.write("CSV file loaded successfully. Preview of data:")
        st.write(data.head())

        # Flag and filter criteria
        missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')].assign(Reason="1000005 - Kindly confirm the actual product colour")
        missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')].assign(Reason="1000007 - Other Reason")
        single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')].assign(Reason="1000008 - Kindly Improve Product Name Description")
        valid_category_codes_fas = category_fas_data['ID'].tolist()
        generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')].assign(Reason="1000007 - Other Reason")

        # Perfume price issues flagging
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
                            flagged_perfumes.append({**row, "Reason": "1000030 - Suspected Counterfeit/Fake Product"})
                            break
        flagged_perfumes_df = pd.DataFrame(flagged_perfumes)

        # Blacklisted words flagging
        flagged_blacklisted = data[data['NAME'].apply(lambda x: any(word in x for word in blacklisted_words) if isinstance(x, str) else False)].assign(Reason="1000033 - Keywords in your content/ Product name / description has been blacklisted")

        # Brand name repetition in product name
        brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)].assign(Reason="1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name")

        # Compile all flagged items
        flagged_data = pd.concat([missing_color, missing_brand_or_name, single_word_name, generic_brand_issues, flagged_perfumes_df, flagged_blacklisted, brand_in_name]).drop_duplicates()

        # Separate approved and rejected data
        approved_data = data[~data['PRODUCT_SET_ID'].isin(flagged_data['PRODUCT_SET_ID'])]
        rejected_data = flagged_data

        # Display flagged data
        st.subheader("Flagged Products")
        st.write(flagged_data)

        # Create combined report
        combined_data = pd.concat([approved_data.assign(Status="Approved"), rejected_data.assign(Status="Rejected")])

        # Function to create a downloadable Excel file
        def to_excel(df, sheet_name="Sheet1"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name=sheet_name)
            return output.getvalue()

        # Display download links
        st.subheader("Download Reports")

        st.download_button(
            label="Download Approved Products",
            data=to_excel(approved_data, sheet_name="Approved"),
            file_name="approved_products.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.download_button(
            label="Download Rejected Products",
            data=to_excel(rejected_data, sheet_name="Rejected"),
            file_name="rejected_products.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.download_button(
            label="Download Combined Report",
            data=to_excel(combined_data, sheet_name="Combined Report"),
            file_name="combined_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"An error occurred: {e}")
else:
    st.info("Please upload a CSV file to proceed.")
