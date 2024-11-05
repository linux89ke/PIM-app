import pandas as pd
import streamlit as st

# Streamlit file uploader for the main CSV file
uploaded_data = st.file_uploader("Upload the main data CSV file", type="csv")
if uploaded_data is not None:
    data = pd.read_csv(uploaded_data)
else:
    st.error("Please upload the main data CSV file to proceed.")

# Streamlit file uploader for perfumes data
uploaded_perfumes = st.file_uploader("Upload the perfumes data file", type="xlsx")
if uploaded_perfumes is not None:
    perfumes_data = pd.read_excel(uploaded_perfumes)
else:
    st.error("Please upload the perfumes data file to proceed.")

# Streamlit file uploader for blacklisted words
uploaded_blacklisted = st.file_uploader("Upload the blacklisted words file (txt)", type="txt")
if uploaded_blacklisted is not None:
    blacklisted_words = [line.strip().lower() for line in uploaded_blacklisted]
else:
    st.error("Please upload the blacklisted words file to proceed.")

# Helper function to flag product with detailed reason
def flag_product(row, flag_name):
    reasons = {
        "Missing COLOR": ("1000005 - Kindly confirm the actual product colour", "Kindly include color of the product"),
        "Missing BRAND or NAME": ("1000007 - Other Reason", "Missing BRAND or NAME"),
        "Single-word NAME": ("1000008 - Kindly Improve Product Name Description", "Kindly Improve Product Name"),
        "Generic BRAND": ("1000007 - Other Reason", "Kindly use Fashion as brand name for Fashion products"),
        "Perfume price issue": ("1000030 - Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)", ""),
        "Blacklisted word in NAME": ("1000033 - Keywords in your content/ Product name / description has been blacklisted", "Keywords in your content/ Product name / description has been blacklisted"),
        "BRAND name repeated in NAME": ("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", "Kindly Ensure Brand Name Is Not Repeated In Product Name"),
        "Duplicate product": ("1000007 - Other Reason", "Product is duplicated")
    }
    reason, comment = reasons[flag_name]
    return {
        "ProductSetSid": row['PRODUCT_SET_SID'],
        "ParentSKU": row['PARENTSKU'],
        "Status": "Rejected",
        "Reason": reason,
        "Comment": comment
    }

# Ensure files are uploaded before processing
if uploaded_data and uploaded_perfumes and uploaded_blacklisted:
    # Flagging conditions
    missing_color = data[data['COLOR'].isna()]
    missing_brand_or_name = data[data['BRAND'].isna() | data['NAME'].isna()]
    single_word_name = data[data['NAME'].str.split().str.len() == 1]
    generic_brand_issues = data[(data['CATEGORY_CODE'].isin(perfumes_data['ID'])) & (data['BRAND'] == 'Generic')]

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

    # Convert flagged_perfumes to DataFrame
    flagged_perfumes_df = pd.DataFrame(flagged_perfumes) if flagged_perfumes else pd.DataFrame(columns=data.columns)

    # Blacklisted word check
    flagged_blacklisted = data[data['NAME'].apply(lambda x: any(word in x.lower() for word in blacklisted_words) if isinstance(x, str) else False)]

    # Brand repeated in NAME
    brand_in_name = data[data.apply(lambda x: x['BRAND'].lower() in x['NAME'].lower() if isinstance(x['NAME'], str) and isinstance(x['BRAND'], str) else False, axis=1)]

    # Duplicate products
    duplicate_products = data[data.duplicated(subset=['PARENTSKU'], keep=False)]

    # Consolidate flagged products
    flagged_dataframes = {}
    final_report_rows = []
    for flag_name, flagged_df in zip(
        ["Missing COLOR", "Missing BRAND or NAME", "Single-word NAME", "Generic BRAND", "Perfume price issue", "Blacklisted word in NAME", "BRAND name repeated in NAME", "Duplicate product"],
        [missing_color, missing_brand_or_name, single_word_name, generic_brand_issues, flagged_perfumes_df, flagged_blacklisted, brand_in_name, duplicate_products]
    ):
        if not flagged_df.empty:
            flagged_products = [flag_product(row, flag_name) for _, row in flagged_df.iterrows()]
            flagged_df_with_reasons = pd.DataFrame(flagged_products)
            final_report_rows.extend(flagged_products)
            flagged_dataframes[flag_name] = flagged_df_with_reasons

    # Prepare final report as DataFrame
    final_report_df = pd.DataFrame(final_report_rows)

    # Display flagged data in expanders on Streamlit
    st.title("Flagged Product Report")
    st.write(f"Report Date: {pd.Timestamp.now().strftime('%Y-%m-%d')}")

    for flag_name, flagged_df in flagged_dataframes.items():
        with st.expander(f"{flag_name} ({len(flagged_df)})"):
            st.write(flagged_df)

    # Downloadable Excel report with sheets for flagged products and reasons
    with pd.ExcelWriter("final_report.xlsx") as writer:
        final_report_df.to_excel(writer, sheet_name="ProductSets", index=False)
        reasons_data = pd.DataFrame(list(reasons.values()), columns=["Reason", "Comment"])
        reasons_data.to_excel(writer, sheet_name="RejectionReasons", index=False)

    st.download_button(
        label="Download Final Report",
        data=open("final_report.xlsx", "rb").read(),
        file_name="final_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.warning("Please upload all required files to generate the report.")
