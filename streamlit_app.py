import streamlit as st
import pandas as pd

# Function to check various validation rules
def validate_products(df, perfumes, blacklisted_words, category_variation):
    flagged_results = {}

    # 1. Missing COLOR
    flagged_results["Missing COLOR"] = df[df["COLOR"].isna()]

    # 2. Missing BRAND or NAME
    flagged_results["Missing BRAND or NAME"] = df[df["BRAND"].isna() | df["NAME"].isna()]

    # 3. Single-word NAME
    flagged_results["Single-word NAME"] = df[df["NAME"].str.split().str.len() == 1]

    # 4. Generic BRAND Issues
    flagged_results["Generic BRAND Issues"] = df[df["BRAND"].str.lower() == "generic"]

    # 5. Perfume Price Issues
    df_merged = df.merge(perfumes, left_on="NAME", right_on="PRODUCT_NAME", how="left")
    flagged_results["Perfume Price Issues"] = df_merged[
        (df_merged["GLOBAL_SALE_PRICE"] / df_merged["PRICE"]) >= 0.7
    ]

    # 6. Blacklisted Words in NAME
    blacklisted_pattern = "|".join(blacklisted_words)
    flagged_results["Blacklisted Words"] = df[df["NAME"].str.contains(blacklisted_pattern, case=False, na=False)]

    # 7. BRAND name repeated in NAME
    flagged_results["Brand in Name"] = df[
        df.apply(lambda row: row["BRAND"].lower() in row["NAME"].lower(), axis=1)
    ]

    # 8. Duplicate Products
    flagged_results["Duplicate Products"] = df[df.duplicated(subset=["PRODUCT_SET_ID"], keep=False)]

    # 9. Missing Variation
    flagged_results["Missing Variation"] = df[
        (df["CATEGORY_CODE"].isin(category_variation["ID"])) & (df["VARIATION"].isna())
    ]

    # 10. Sensitive Brands (Example check, adjust logic if needed)
    flagged_results["Sensitive Brands"] = df[df["BRAND"].str.contains("sensitive", case=False, na=False)]

    return flagged_results

# Streamlit UI
st.title("Product Validation Tool")

# File Uploads
uploaded_file = st.file_uploader("Upload your product CSV", type="csv")
perfumes_file = st.file_uploader("Upload perfumes.xlsx", type="xlsx")
blacklisted_file = st.file_uploader("Upload blacklisted.txt", type="txt")
category_variation_file = st.file_uploader("Upload check_variation.xlsx", type="xlsx")

if uploaded_file and perfumes_file and blacklisted_file and category_variation_file:
    df = pd.read_csv(uploaded_file)
    perfumes = pd.read_excel(perfumes_file)
    blacklisted_words = blacklisted_file.read().decode("utf-8").splitlines()
    category_variation = pd.read_excel(category_variation_file)

    # Validate products
    flagged_results = validate_products(df, perfumes, blacklisted_words, category_variation)

    # Show results with row counts
    for flag, result_df in flagged_results.items():
        count = len(result_df)
        with st.expander(f"{flag} ({count})"):
            if count > 0:
                st.write(result_df)
            else:
                st.write("No flagged rows")
