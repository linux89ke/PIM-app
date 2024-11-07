import pandas as pd
import streamlit as st
from io import BytesIO

# Load necessary data files
def load_blacklisted_words():
    with open('blacklisted.txt', 'r') as f:
        return [line.strip() for line in f.readlines()]

# Load files
check_variation_data = pd.read_excel('check_variation.xlsx')
category_fas_data = pd.read_excel('category_FAS.xlsx')
perfumes_data = pd.read_excel('perfumes.xlsx')
blacklisted_words = load_blacklisted_words()

# Flagging reasons with corresponding codes, comments, and displays
flag_reasons = {
    "Missing COLOR": {
        "Reason": "1000005 - Kindly confirm the actual product colour",
        "Comment": "Kindly include color of the product"
    },
    "Missing BRAND or NAME": {
        "Reason": "1000007 - Other Reason",
        "Comment": "Missing BRAND or NAME"
    },
    "Single-word NAME": {
        "Reason": "1000008 - Kindly Improve Product Name Description",
        "Comment": "Kindly Improve Product Name"
    },
    "Generic BRAND": {
        "Reason": "1000007 - Other Reason",
        "Comment": "Kindly use Fashion as brand name for Fashion products"
    },
    "Perfume price issue": {
        "Reason": "1000030 - Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)",
        "Comment": ""
    },
    "Blacklisted word in NAME": {
        "Reason": "1000033 - Keywords in your content/ Product name / description has been blacklisted",
        "Comment": "Keywords in your content/ Product name / description has been blacklisted"
    },
    "BRAND name repeated in NAME": {
        "Reason": "1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name",
        "Comment": "Kindly Ensure Brand Name Is Not Repeated In Product Name"
    },
    "Duplicate product": {
        "Reason": "1000007 - Other Reason",
        "Comment": "Product is duplicated"
    }
}

# Function to apply the flagging rules
def flag_product(row):
    reasons = []
    comments = []

    # Example flagging conditions
    if pd.isna(row['COLOR']):
        reasons.append(flag_reasons["Missing COLOR"]["Reason"])
        comments.append(flag_reasons["Missing COLOR"]["Comment"])
    if pd.isna(row['BRAND']) or pd.isna(row['NAME']):
        reasons.append(flag_reasons["Missing BRAND or NAME"]["Reason"])
        comments.append(flag_reasons["Missing BRAND or NAME"]["Comment"])
    if len(str(row['NAME']).split()) == 1:
        reasons.append(flag_reasons["Single-word NAME"]["Reason"])
        comments.append(flag_reasons["Single-word NAME"]["Comment"])
    if row['BRAND'] == 'Generic':
        reasons.append(flag_reasons["Generic BRAND"]["Reason"])
        comments.append(flag_reasons["Generic BRAND"]["Comment"])
    if row['GLOBAL_SALE_PRICE'] < row['PRICE'] * 0.7:
        reasons.append(flag_reasons["Perfume price issue"]["Reason"])
        comments.append(flag_reasons["Perfume price issue"]["Comment"])
    if any(word in row['NAME'] for word in blacklisted_words):
        reasons.append(flag_reasons["Blacklisted word in NAME"]["Reason"])
        comments.append(flag_reasons["Blacklisted word in NAME"]["Comment"])
    if row['BRAND'] in row['NAME']:
        reasons.append(flag_reasons["BRAND name repeated in NAME"]["Reason"])
        comments.append(flag_reasons["BRAND name repeated in NAME"]["Comment"])

    # Aggregate reasons and comments if flagged
    if reasons:
        return {
            "Status": "Rejected",
            "Reason": "; ".join(reasons),
            "Comment": "; ".join(comments)
        }
    else:
        return {
            "Status": "Approved",
            "Reason": "",
            "Comment": ""
        }

# Apply the flagging function to each row
def process_data(df):
    flagged_data = df.apply(flag_product, axis=1, result_type='expand')
    return pd.concat([df[['PRODUCT_SET_SID', 'PARENTSKU']], flagged_data], axis=1)

# Streamlit UI
st.title("Product Flagging Report Generator")

uploaded_file = st.file_uploader("Upload your product CSV", type="csv")
if uploaded_file:
    data = pd.read_csv(uploaded_file)
    processed_data = process_data(data)
    
    # Rename columns for final report
    processed_data.columns = ['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment']
    
    # Downloadable Excel file with ProductSets sheet
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        processed_data.to_excel(writer, sheet_name='ProductSets', index=False)
    
    st.download_button(
        label="Download Report",
        data=output.getvalue(),
        file_name="Product_Flagging_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
