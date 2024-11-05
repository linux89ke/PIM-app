import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime

# Function to convert DataFrame to downloadable Excel file with two sheets
def to_excel(dataframe):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        dataframe.to_excel(writer, index=False, sheet_name='ProductSets')
        reasons_df = pd.read_excel('reasons.xlsx')  # Load rejection reasons
        reasons_df.to_excel(writer, index=False, sheet_name='RejectionReasons')
    return output.getvalue()

# Load and process data
def process_data(data):
    # Placeholder code for data processing
    # Flagging logic (based on flags you described) to be implemented here
    data['Flag'] = ''  # Initialize Flag column for simplicity
    data['Reason'] = ''  # Initialize Reason column
    data['Comment'] = ''  # Initialize Comment column

    # Apply flags based on your rules:
    conditions = [
        (data['COLOR'].isna(), '1000005 - Kindly confirm the actual product colour', 'Kindly include color of the product', 'Missing COLOR'),
        (data['BRAND'].isna() | data['NAME'].isna(), '1000007 - Other Reason', 'Missing BRAND or NAME', 'Missing BRAND or NAME'),
        (data['NAME'].str.split().str.len() == 1, '1000008 - Kindly Improve Product Name Description', 'Kindly Improve Product Name', 'Name too short'),
        (data['BRAND'] == 'Generic', '1000007 - Other Reason', 'Kindly use Fashion as brand name for Fashion products', 'Brand is Generic instead of Fashion'),
        # Add more flags based on your requirements...
    ]
    
    # Assign flags
    for condition, reason, comment, display in conditions:
        data.loc[condition & (data['Flag'] == ''), ['Flag', 'Reason', 'Comment']] = display, reason, comment

    # Separate approved and rejected products
    approved_df = data[data['Flag'] == '']
    rejected_df = data[data['Flag'] != '']
    
    return approved_df, rejected_df, data

# Load the sample data
# Assuming you have a CSV or Excel file uploaded to Streamlit
uploaded_file = st.file_uploader("Upload your CSV file", type="csv")
if uploaded_file is not None:
    data = pd.read_csv(uploaded_file)

    # Process the data for flagging
    approved_df, rejected_df, final_report_df = process_data(data)

    # Timestamp for file naming
    current_time = datetime.now().strftime("%m-%d_%H")

    # Download buttons with formatted date and hour in file names
    st.download_button(
        label="Download Approved Products Report",
        data=to_excel(approved_df),
        file_name=f'approved_products_{current_time}.xlsx'
    )

    st.download_button(
        label="Download Rejected Products Report",
        data=to_excel(rejected_df),
        file_name=f'rejected_products_{current_time}.xlsx'
    )

    st.download_button(
        label="Download Combined Report",
        data=to_excel(final_report_df),
        file_name=f'combined_report_{current_time}.xlsx'
    )
