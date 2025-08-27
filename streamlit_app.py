import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import os

# -----------------------------
# Column configs
# -----------------------------
PRODUCTSETS_COLS = [
    "ProductSetSid","PRODUCT_SET_SID","SELLER_NAME","CATEGORY_CODE",
    "Status","Reason","Comment","FLAG"
]

REJECTION_REASONS_COLS = ["ReasonCode","Reason","CommentRequired"]

FULL_DATA_COLS = [
    "PRODUCT_SET_SID","SELLER_NAME","CATEGORY_CODE","Status",
    "Reason","Comment","FLAG"
]

# -----------------------------
# Base Excel writer helper
# -----------------------------
def to_excel_base(df, sheet_name, column_order, writer):
    if not df.empty:
        df_out = df.copy()
        # Reorder columns if available
        col_order = [col for col in column_order if col in df_out.columns]
        other_cols = [col for col in df_out.columns if col not in col_order]
        df_out = df_out[col_order + other_cols]
    else:
        df_out = pd.DataFrame(columns=column_order)
    df_out.to_excel(writer, index=False, sheet_name=sheet_name)

# -----------------------------
# Sellers summary builder
# -----------------------------
def build_sellers_sheet(report_df, data_df):
    if report_df.empty:
        return pd.DataFrame([["No rejected products found"]], columns=["Info"])

    merged = pd.merge(
        report_df,
        data_df[['PRODUCT_SET_SID','SELLER_NAME','CATEGORY_CODE']],
        left_on='ProductSetSid',
        right_on='PRODUCT_SET_SID',
        how='left'
    )

    rejected = merged[merged['Status'] == 'Rejected'].copy()
    if rejected.empty:
        return pd.DataFrame([["No rejected products found"]], columns=["Info"])

    # Sellers summary
    sellers_summary = rejected.groupby('SELLER_NAME')['ProductSetSid'].count().reset_index()
    sellers_summary.columns = ['Seller', 'Rejected_Count']

    # Categories summary
    categories_summary = rejected.groupby('CATEGORY_CODE')['ProductSetSid'].count().reset_index()
    categories_summary.columns = ['Category_Code', 'Rejected_Count']

    # Category + reason breakdown
    cat_reason_summary = rejected.groupby(['CATEGORY_CODE','Reason'])['ProductSetSid'].count().reset_index()
    cat_reason_summary.columns = ['Category_Code','Reason','Rejected_Count']

    # Stack into one DataFrame with section markers
    parts = []
    parts.append(pd.DataFrame([["SECTION: Rejected Sellers"]], columns=[" "]))
    parts.append(sellers_summary)

    parts.append(pd.DataFrame([["SECTION: Rejected Categories"]], columns=[" "]))
    parts.append(categories_summary)

    parts.append(pd.DataFrame([["SECTION: Category Reason Breakdown"]], columns=[" "]))
    parts.append(cat_reason_summary)

    return pd.concat(parts, ignore_index=True)

# -----------------------------
# Normal report export
# -----------------------------
def to_excel(report_df, reasons_config_df, sheet1_name="ProductSets", sheet2_name="RejectionReasons"):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(report_df, sheet1_name, PRODUCTSETS_COLS, writer)

        if not reasons_config_df.empty:
            to_excel_base(reasons_config_df, sheet2_name, REJECTION_REASONS_COLS, writer)
        else:
            pd.DataFrame(columns=REJECTION_REASONS_COLS).to_excel(writer, index=False, sheet_name=sheet2_name)
    output.seek(0)
    return output

# -----------------------------
# Full data export (with Sellers sheet)
# -----------------------------
def to_excel_full_data(data_df, final_report_df):
    output = BytesIO()
    data_df_copy = data_df.copy()
    final_report_df_copy = final_report_df.copy()

    # Align datatypes
    data_df_copy['PRODUCT_SET_SID'] = data_df_copy['PRODUCT_SET_SID'].astype(str)
    final_report_df_copy['ProductSetSid'] = final_report_df_copy['ProductSetSid'].astype(str)

    # Merge status info into full dataset
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

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # ProductSets sheet (full data)
        to_excel_base(merged_df, "ProductSets", FULL_DATA_COLS, writer)

        # Sellers summary sheet
        sellers_sheet = build_sellers_sheet(final_report_df_copy, data_df_copy)
        sellers_sheet.to_excel(writer, index=False, sheet_name="Sellers")

        # Formatting for Sellers sheet
        workbook  = writer.book
        worksheet = writer.sheets["Sellers"]

        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#D9E1F2',
            'align': 'center'
        })

        for row_num, value in enumerate(sellers_sheet.iloc[:,0]):
            if isinstance(value, str) and value.startswith("SECTION:"):
                worksheet.set_row(row_num+1, None, header_format)

    output.seek(0)
    return output
