import streamlit as st
import pandas as pd
import os

def load_data(file):
    return pd.read_csv(file)

def flag_issues(df):
    flagged_rows = []
    
    for index, row in df.iterrows():
        reasons = []
        
        # Check for missing color
        if pd.isna(row['COLOR']) or row['COLOR'].strip() == '':
            reasons.append(("1000005 - Kindly confirm the actual product colour", "Kindly include color of the product", "Missing COLOR"))
        
        # Check for missing brand or name
        if pd.isna(row['BRAND']) or row['BRAND'].strip() == '' or pd.isna(row['NAME']) or row['NAME'].strip() == '':
            reasons.append(("1000007 - Other Reason", "Missing BRAND or NAME", "Missing BRAND or NAME"))
        
        # Check for single-word name
        if len(str(row['NAME']).split()) == 1:
            reasons.append(("1000008 - Kindly Improve Product Name Description", "Kindly Improve Product Name", "Name too short"))
        
        # Check for generic brand
        if row['BRAND'].strip().lower() == 'generic':
            reasons.append(("1000007 - Other Reason", "Kindly use Fashion as brand name for Fashion products", "Brand is Generic instead of Fashion"))
        
        # Check for blacklisted words in NAME
        if 'blacklisted.txt' in os.listdir():
            with open('blacklisted.txt', 'r') as file:
                blacklisted_words = {line.strip().lower() for line in file}
                name_words = set(str(row['NAME']).lower().split())
                if blacklisted_words & name_words:
                    reasons.append(("1000033 - Keywords in your content/ Product name / description has been blacklisted", "Keywords in your content/ Product name / description has been blacklisted", "Blacklisted word in NAME"))
        
        # Check for brand name repeated in name
        if row['BRAND'].strip().lower() in row['NAME'].strip().lower():
            reasons.append(("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", "Kindly Ensure Brand Name Is Not Repeated In Product Name", "BRAND name repeated in NAME"))
        
        # Check for duplicate product
        if df.duplicated(subset=['PRODUCT_SET_SID'], keep=False).iloc[index]:
            reasons.append(("1000007 - Other Reason", "Product is duplicated", "Duplicate product"))
        
        if reasons:
            flagged_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], "Rejected", reasons[0][0], reasons[0][1], reasons[0][2]))
    
    return pd.DataFrame(flagged_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment', 'Display'])

def main():
    st.title("Product Validation Tool")
    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"])
    
    if uploaded_file is not None:
        df = load_data(uploaded_file)
        flagged_df = flag_issues(df)
        
        st.subheader("Flagged Products")
        st.dataframe(flagged_df)
        
        if not flagged_df.empty:
            flagged_df.to_csv("flagged_products.csv", index=False)
            st.download_button(
                label="Download Flagged Products",
                data=open("flagged_products.csv", "rb"),
                file_name="flagged_products.csv",
                mime="text/csv"
            )

if __name__ == "__main__":
    main()
