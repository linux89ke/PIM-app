import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# Sample data loading and initialization functions would go here (omitted for brevity)

def generate_excel(dataframe, sheet_name):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()

# Assume data processing and flagging logic has been completed and final_report_df created

# Sample final_report_df data to show the process (replace with actual data processing logic)
data = {
    'ProductSetSid': [1, 2, 3],
    'ParentSKU': ['SKU1', 'SKU2', 'SKU3'],
    'Status': ['Approved', 'Rejected', 'Approved'],
    'Reason': ['', '1000005 - Kindly confirm the actual product colour', ''],
    'Comment': ['', 'Missing color', '']
}
final_report_df = pd.DataFrame(data)

# Separate approved and rejected reports
approved_df = final_report_df[final_report_df['Status'] == 'Approved']
rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

# Display final report preview
st.write("Final Report Preview")
st.write(final_report_df)

# Generate downloadable Excel files for each report
today_date = datetime.today().strftime('%Y-%m-%d')

if st.button("Download Approved Products Report"):
    st.download_button(
        label="Download Approved Products",
        data=generate_excel(approved_df, 'Approved Products'),
        file_name=f"approved_products_{today_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if st.button("Download Rejected Products Report"):
    st.download_button(
        label="Download Rejected Products",
        data=generate_excel(rejected_df, 'Rejected Products'),
        file_name=f"rejected_products_{today_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if st.button("Download Combined Report"):
    st.download_button(
        label="Download Combined Report",
        data=generate_excel(final_report_df, 'Combined Report'),
        file_name=f"combined_report_{today_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
