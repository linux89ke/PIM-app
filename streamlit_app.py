import streamlit as st
import pandas as pd
import os
from zipfile import ZipFile

def load_excel_file(file):
    return pd.read_excel(file) if file else None

def load_text_file(file):
    if file:
        with open(file, 'r', encoding='utf-8') as f:
            return set(line.strip().lower() for line in f)
    return set()

def check_variations(df, category_variations):
    flagged = df[df['CATEGORY_CODE'].isin(category_variations) & df['VARIATION'].isna()]
    flagged['Reason'] = '1000005 - Kindly confirm the actual product colour'
    flagged['Comment'] = 'Kindly include color of the product'
    return flagged

def check_brand_name(df):
    flagged = df[df['BRAND'].isna() | df['NAME'].isna()]
    flagged['Reason'] = '1000007 - Other Reason'
    flagged['Comment'] = 'Missing BRAND or NAME'
    return flagged

def check_single_word_name(df):
    flagged = df[df['NAME'].str.split().str.len() == 1]
    flagged['Reason'] = '1000008 - Kindly Improve Product Name Description'
    flagged['Comment'] = 'Kindly Improve Product Name'
    return flagged

def check_blacklisted_words(df, blacklist):
    flagged = df[df['NAME'].apply(lambda x: any(word in x.lower().split() for word in blacklist))]
    flagged['Reason'] = '1000033 - Keywords in your content/ Product name / description has been blacklisted'
    flagged['Comment'] = 'Blacklisted word in NAME'
    return flagged

def check_duplicate_products(df):
    flagged = df[df.duplicated(subset=['PRODUCT_SET_ID'], keep=False)]
    flagged['Reason'] = '1000007 - Other Reason'
    flagged['Comment'] = 'Product is duplicated'
    return flagged

def process_files(uploaded_files, category_variations, blacklist):
    all_flagged = []
    for file in uploaded_files:
        df = load_excel_file(file)
        if df is not None:
            flagged_variations = check_variations(df, category_variations)
            flagged_brand_name = check_brand_name(df)
            flagged_short_name = check_single_word_name(df)
            flagged_blacklisted = check_blacklisted_words(df, blacklist)
            flagged_duplicates = check_duplicate_products(df)
            
            all_flagged.extend([flagged_variations, flagged_brand_name, flagged_short_name, flagged_blacklisted, flagged_duplicates])
    
    return pd.concat(all_flagged, ignore_index=True) if all_flagged else pd.DataFrame()

def generate_report(flagged_df):
    with pd.ExcelWriter("output/report.xlsx") as writer:
        flagged_df.to_excel(writer, sheet_name="ProductSets", index=False)
    return "output/report.xlsx"

def main():
    st.title("Product Validation Tool")
    uploaded_files = st.file_uploader("Upload Excel files", accept_multiple_files=True, type=['xlsx'])
    category_variations_file = st.file_uploader("Upload category variation file", type=['xlsx'])
    blacklist_file = st.file_uploader("Upload blacklist file", type=['txt'])
    
    if st.button("Process Files"):
        category_variations = load_excel_file(category_variations_file)['ID'].tolist() if category_variations_file else []
        blacklist = load_text_file(blacklist_file)
        flagged_df = process_files(uploaded_files, category_variations, blacklist)
        
        if not flagged_df.empty:
            report_path = generate_report(flagged_df)
            with open(report_path, "rb") as f:
                st.download_button("Download Report", f, file_name="validation_report.xlsx")
        else:
            st.write("No issues found!")

if __name__ == "__main__":
    main()
