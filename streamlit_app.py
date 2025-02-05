import pandas as pd
import streamlit as st
from io import BytesIO

def validate_product(row, config_data, blacklisted_words, book_categories, sensitive_brands, category_FAS_codes):
    reason = None
    reason_details = None
    
    # Check for missing color
    if pd.isnull(row['COLOR']):
        reason = "1000005"
        reason_details = ("1000005", "Kindly confirm the actual product colour", "Kindly include color of the product")
    
    # Check for missing brand or name
    elif pd.isnull(row['BRAND']) or pd.isnull(row['NAME']):
        reason = "1000007"
        reason_details = ("1000007", "Missing BRAND or NAME", "Missing BRAND or NAME")
    
    # Check for single-word product name
    elif len(str(row['NAME']).split()) == 1:
        reason = "1000008"
        reason_details = ("1000008", "Kindly Improve Product Name Description", "Kindly Improve Product Name")
    
    # Check for generic brand
    elif row['BRAND'] == 'Generic':
        reason = "1000007"
        reason_details = ("1000007", "Kindly use Fashion as brand name for Fashion products", "Kindly use Fashion as brand name for Fashion products")
    
    # Check for perfume price issues
    elif row['CATEGORY_CODE'] == 'PERFUME' and row['GLOBAL_SALE_PRICE'] < 30:
        reason = "1000030"
        reason_details = ("1000030", "Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)", "Perfume price too low")
    
    # Check for blacklisted word in product name
    if any(word in row['NAME'] for word in blacklisted_words):
        reason = "1000033"
        reason_details = ("1000033", "Keywords in your content/ Product name / description has been blacklisted", "Keywords in your content/ Product name / description has been blacklisted")
    
    # Check for brand repetition in the name
    if row['BRAND'] in row['NAME']:
        reason = "1000002"
        reason_details = ("1000002", "Kindly Ensure Brand Name Is Not Repeated In Product Name", "Kindly Ensure Brand Name Is Not Repeated In Product Name")
    
    # Duplicate product check
    # Assuming a duplicate check based on product set ID or SKU
    # (Add your duplicate logic here as needed)
    
    return reason, reason_details

def generate_final_report(data, config_data, blacklisted_words, book_categories, sensitive_brands, category_FAS_codes):
    final_report_rows = []
    rejection_reasons_data = []  # To collect rejection reasons for the separate sheet

    for _, row in data.iterrows():
        reason, reason_details = validate_product(row, config_data, blacklisted_words, book_categories,
                                                  sensitive_brands, category_FAS_codes)
        if reason is not None:
            final_report_rows.append({
                'ProductSetSid': row['PRODUCT_SET_SID'],
                'ParentSKU': row['PARENTSKU'],
                'Status': 'Rejected',
                'Reason': reason,
                'Comment': reason_details[1]  # Assuming reason_details is always valid
            })
            rejection_reasons_data.append({
                'Reason Code': reason_details[0],
                'Reason Message': reason_details[1],
                'Comment': reason_details[2]
            })
        else:
            final_report_rows.append({
                'ProductSetSid': row['PRODUCT_SET_SID'],
                'ParentSKU': row['PARENTSKU'],
                'Status': 'Approved',
                'Reason': "",
                'Comment': ""
            })

    final_report_df = pd.DataFrame(final_report_rows)

    # Creating the Excel file in memory
    with BytesIO() as output:
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            final_report_df.to_excel(writer, sheet_name='ProductSets', index=False)
            
            # Write rejection reasons only if there are any
            if rejection_reasons_data:
                rejection_reasons_df = pd.DataFrame(rejection_reasons_data)
                rejection_reasons_df.to_excel(writer, sheet_name='RejectionReasons', index=False)

        # Move to the beginning of the BytesIO object
        output.seek(0)

        # Provide the download link to the user
        st.download_button(
            label="Download Final Report",
            data=output,
            file_name="final_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# Sample usage
# Load your data and configuration files (this is just a placeholder)
data = pd.read_csv('your_data_file.csv')  # Load your actual data
config_data = {}  # Add your actual config data
blacklisted_words = ['example', 'banned_word']  # Add your blacklisted words
book_categories = ['category1', 'category2']  # Add your book categories
sensitive_brands = ['brand1', 'brand2']  # Add your sensitive brands
category_FAS_codes = ['code1', 'code2']  # Add your category FAS codes

generate_final_report(data, config_data, blacklisted_words, book_categories, sensitive_brands, category_FAS_codes)
