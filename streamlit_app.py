import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import os

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# --- Constants for column names ---
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG"]
REJECTION_REASONS_COLS = ['CODE - REJECTION_REASON', 'COMMENT']
FULL_DATA_COLS = ["PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE", "COLOR", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU", "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG"]

# [Previous functions unchanged: load_blacklisted_words, load_book_category_codes, etc.]

# [Validation check functions unchanged: check_missing_color, check_missing_brand_or_name, etc.]

# [validate_products function unchanged]

# --- Export functions ---
def to_excel_base(df_to_export, sheet_name, columns_to_include, writer):
    df_prepared = df_to_export.copy()
    for col in columns_to_include:
        if col not in df_prepared.columns:
            df_prepared[col] = pd.NA
    df_prepared[columns_to_include].to_excel(writer, index=False, sheet_name=sheet_name)

def to_excel_full_data(data_df, final_report_df):
    output = BytesIO()
    data_df_copy = data_df.copy()
    final_report_df_copy = final_report_df.copy()
    data_df_copy['PRODUCT_SET_SID'] = data_df_copy['PRODUCT_SET_SID'].astype(str)
    final_report_df_copy['ProductSetSid'] = final_report_df_copy['ProductSetSid'].astype(str)

    # Merge input data with validation results
    merged_df = pd.merge(
        data_df_copy,
        final_report_df_copy[["ProductSetSid", "Status", "Reason", "Comment", "FLAG"]],
        left_on="PRODUCT_SET_SID",
        right_on="ProductSetSid",
        how="left"
    )
    if 'ProductSetSid_y' in merged_df.columns:
        merged_df.drop(columns=['ProductSetSid_y'], inplace=True)
    if 'ProductSetSid_x' in merged_df.columns:
        merged_df.rename(columns={'ProductSetSid_x': 'PRODUCT_SET_SID'}, inplace=True)
    
    if 'FLAG' in merged_df.columns:
        merged_df['FLAG'] = merged_df['FLAG'].fillna('')

    # Prepare Sellers Data sheet summaries
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Write ProductSets sheet
        to_excel_base(merged_df, "ProductSets", FULL_DATA_COLS, writer)

        # Sellers Data sheet
        sellers_data_rows = []
        
        # 1. Sellers Summary: Number of rejected products per seller
        if 'SELLER_NAME' in merged_df.columns:
            seller_rejections = merged_df[merged_df['Status'] == 'Rejected'].groupby('SELLER_NAME').size().reset_index(name='Rejected Products')
            sellers_data_rows.append(pd.DataFrame([['', '']]))  # Empty row for spacing
            sellers_data_rows.append(pd.DataFrame([['Sellers Summary', '']]))
            sellers_data_rows.append(seller_rejections.rename(columns={'SELLER_NAME': 'Seller', 'Rejected Products': 'Number of Rejected Products'}))
        else:
            sellers_data_rows.append(pd.DataFrame([['Sellers Summary', 'No SELLER_NAME column available']]))

        # 2. Categories Summary: Number of rejected products per category
        category_column = 'CATEGORY_CODE' if 'CATEGORY_CODE' in merged_df.columns else 'CATEGORY' if 'CATEGORY' in merged_df.columns else None
        if category_column:
            category_rejections = merged_df[merged_df['Status'] == 'Rejected'].groupby(category_column).size().reset_index(name='Rejected Products')
            sellers_data_rows.append(pd.DataFrame([['', '']]))  # Empty row for spacing
            sellers_data_rows.append(pd.DataFrame([['Categories Summary', '']]))
            sellers_data_rows.append(category_rejections.rename(columns={category_column: 'Category', 'Rejected Products': 'Number of Rejected Products'}))
        else:
            sellers_data_rows.append(pd.DataFrame([['Categories Summary', 'No CATEGORY or CATEGORY_CODE column available']]))

        # 3. Rejection Reasons Summary: Number of rejected products per reason
        if 'Reason' in merged_df.columns:
            reason_rejections = merged_df[merged_df['Status'] == 'Rejected'].groupby('Reason').size().reset_index(name='Rejected Products')
            sellers_data_rows.append(pd.DataFrame([['', '']]))  # Empty row for spacing
            sellers_data_rows.append(pd.DataFrame([['Rejection Reasons Summary', '']]))
            sellers_data_rows.append(reason_rejections.rename(columns={'Reason': 'Rejection Reason', 'Rejected Products': 'Number of Rejected Products'}))
        else:
            sellers_data_rows.append(pd.DataFrame([['Rejection Reasons Summary', 'No Reason column available']]))

        # Write Sellers Data sheet
        start_row = 0
        for df in sellers_data_rows:
            df.to_excel(writer, sheet_name='Sellers Data', startrow=start_row, index=False)
            start_row += len(df) + 1  # Add space between sections

    output.seek(0)
    return output

# [Remaining export functions unchanged: to_excel, to_excel_flag_data, to_excel_seller_data]

# [Rest of the Streamlit app code unchanged]
