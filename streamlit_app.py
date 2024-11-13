import pandas as pd
import streamlit as st
from io import BytesIO
import datetime

# Function to load reasons from reasons.xlsx
def load_reasons():
    try:
        reasons_df = pd.read_excel('reasons.xlsx').rename(columns=lambda x: x.strip())  # Strip spaces from column names
        return reasons_df
    except Exception as e:
        st.error(f"Error loading reasons.xlsx: {e}")
        return pd.DataFrame()  # Return empty DataFrame in case of error

# Load the RejectionReasons data from reasons.xlsx
reasons_data = load_reasons()

# Function to generate the Excel report with two sheets
def to_excel(df1, reasons_df, sheet1_name="ProductSets", sheet2_name="RejectionReasons"):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df1.to_excel(writer, index=False, sheet_name=sheet1_name)  # ProductSets sheet
        reasons_df.to_excel(writer, index=False, sheet_name=sheet2_name)  # RejectionReasons sheet
    output.seek(0)
    return output

# Assuming the data frames (final_report_df, approved_df, rejected_df) are already created
# You can replace these with your actual data processing steps.
final_report_df = pd.DataFrame()  # Replace with your final report data frame
approved_df = pd.DataFrame()  # Replace with your approved data frame
rejected_df = pd.DataFrame()  # Replace with your rejected data frame

# Get today's date for naming the file
current_date = datetime.datetime.now().strftime("%Y-%m-%d")

# Columns for downloading the reports
col1, col2, col3 = st.columns(3)

# Full Report
with col1:
    final_report_excel = to_excel(final_report_df, reasons_data)
    st.download_button(
        label="Download Full Report",
        data=final_report_excel,
        file_name=f"Product_Validation_Full_Report_{current_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Approved Report
with col2:
    approved_excel = to_excel(approved_df, reasons_data)
    st.download_button(
        label="Download Approved Only",
        data=approved_excel,
        file_name=f"Product_Validation_Approved_{current_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Rejected Report
with col3:
    rejected_excel = to_excel(rejected_df, reasons_data)
    st.download_button(
        label="Download Rejected Only",
        data=rejected_excel,
        file_name=f"Product_Validation_Rejected_{current_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
