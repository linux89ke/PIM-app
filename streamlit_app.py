import pandas as pd
import streamlit as st
from io import BytesIO

# Sample data and functions (replace with actual processing logic)
def load_blacklisted_words():
    return ["blacklisted_word"]

def generate_excel(dataframe, sheet_name):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()

# Load data (replace with actual file loading)
data = pd.DataFrame({
    'PRODUCT_SET_ID': [1, 2, 3, 4],
    'PRODUCT_SET_SID': [101, 102, 103, 104],
    'NAME': ['Product A', 'Product B', 'Product C', 'Product D'],
    'BRAND': ['Brand A', 'Brand B', 'Brand A', 'Generic'],
    'CATEGORY': ['Cat1', 'Cat2', 'Cat1', 'Cat2'],
    'CATEGORY_CODE': ['CC1', 'CC2', 'CC3', 'CC2'],
    'COLOR': [None, 'Red', '', 'Blue'],
    'PARENTSKU': ['PSKU1', 'PSKU2', 'PSKU3', 'PSKU4'],
    'SELLER_NAME': ['Seller1', 'Seller2', 'Seller1', 'Seller2'],
    'GLOBAL_PRICE': [100, 150, 80, 120]
})

# Initializing dataframes for flags (replace with actual flag conditions)
missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
single_word_name = data[data['NAME'].str.split().str.len() == 1]
generic_brand_issues = data[data['BRAND'] == 'Generic']
flagged_perfumes = data[data['GLOBAL_PRICE'] < 90]  # Example perfume price flag condition
flagged_blacklisted = data[data['NAME'].str.contains('|'.join(load_blacklisted_words()), case=False, na=False)]
brand_in_name = data[data.apply(lambda row: row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

# Display flag results with collapsible sections
st.title("Product Validation Tool")

with st.expander(f"Missing COLOR ({len(missing_color)})"):
    st.write(missing_color)

with st.expander(f"Missing BRAND or NAME ({len(missing_brand_or_name)})"):
    st.write(missing_brand_or_name)

with st.expander(f"Single-word NAME ({len(single_word_name)})"):
    st.write(single_word_name)

with st.expander(f"Generic BRAND ({len(generic_brand_issues)})"):
    st.write(generic_brand_issues)

with st.expander(f"Perfume price issues ({len(flagged_perfumes)})"):
    st.write(flagged_perfumes)

with st.expander(f"Blacklisted words in NAME ({len(flagged_blacklisted)})"):
    st.write(flagged_blacklisted)

with st.expander(f"BRAND name repeated in NAME ({len(brand_in_name)})"):
    st.write(brand_in_name)

# Preparing final report
final_report_df = pd.concat([
    missing_color.assign(Reason="1000005 - Kindly confirm the actual product colour"),
    missing_brand_or_name.assign(Reason="1000007 - Other Reason"),
    single_word_name.assign(Reason="1000008 - Kindly Improve Product Name Description"),
    generic_brand_issues.assign(Reason="1000007 - Other Reason"),
    flagged_perfumes.assign(Reason="1000030 - Suspected Counterfeit/Fake Product"),
    flagged_blacklisted.assign(Reason="1000033 - Blacklisted keywords"),
    brand_in_name.assign(Reason="1000002 - Remove Brand Name from Product Name")
])

final_report_df['Status'] = final_report_df['Reason'].apply(lambda x: "Rejected" if x else "Approved")
approved_df = final_report_df[final_report_df['Status'] == 'Approved']
rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

# Download links for reports
st.subheader("Download Reports")

st.download_button(
    label="Download Approved Products Report",
    data=generate_excel(approved_df, 'Approved Products'),
    file_name="approved_products.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

st.download_button(
    label="Download Rejected Products Report",
    data=generate_excel(rejected_df, 'Rejected Products'),
    file_name="rejected_products.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

st.download_button(
    label="Download Combined Report",
    data=generate_excel(final_report_df, 'Combined Report'),
    file_name="combined_report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
