import streamlit as st
import pandas as pd
from datetime import datetime
import io

# Function to convert DataFrame to Excel format for download
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Writing ProductSets and RejectionReasons sheets to the Excel file
        df['ProductSets'].to_excel(writer, sheet_name='ProductSets', index=False)
        df['RejectionReasons'].to_excel(writer, sheet_name='RejectionReasons', index=False)
    output.seek(0)
    return output

# Example function to process data and return the flagged reports
def process_data(data):
    # Initialize lists to hold flagged products
    flagged_products = []
    rejection_reasons = []

    # Example flagging logic (you will replace this with your actual logic)
    for index, row in data.iterrows():
        if row['COLOR'] == '':  # Placeholder condition for missing color
            flagged_products.append({
                'ProductSetSid': row['PRODUCT_SET_SID'],
                'ParentSKU': row['PARENTSKU'],
                'Status': 'Rejected',
                'Reason': 'Missing COLOR',
                'Comment': 'Kindly include color of the product'
            })
            rejection_reasons.append({
                'Reason': '1000005 - Kindly confirm the actual product colour',
                'Comment': 'Kindly include color of the product'
            })

    # Create DataFrames for flagged products and rejection reasons
    product_sets_df = pd.DataFrame(flagged_products)
    rejection_reasons_df = pd.DataFrame(rejection_reasons)

    # Separate approved and rejected DataFrames
    approved_df = data[data['STATUS'] == 'Approved']  # Assuming there's a STATUS column
    rejected_df = product_sets_df

    # Create the final report dictionary with two sheets
    final_report_df = {
        'ProductSets': product_sets_df,
        'RejectionReasons': rejection_reasons_df
    }
    
    return approved_df, rejected_df, final_report_df

# Streamlit app
st.title("Product Flagging Report Generator")

# File uploader for CSV
uploaded_file = st.file_uploader("Upload CSV file", type="csv")

# Load the uploaded CSV file with specified delimiter and encoding
if uploaded_file is not None:
    try:
        # Load CSV with custom delimiter and encoding
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        
        # Check if data is loaded and non-empty
        if not data.empty:
            st.write("CSV file loaded successfully. Preview of data:")
            st.write(data.head())

            # Process data to get approved, rejected, and combined reports
            approved_df, rejected_df, final_report_df = process_data(data)

            # Display the flagged products and reasons
            st.subheader("Flagged Products (Rejected)")
            st.write(rejected_df)  # Display the DataFrame of rejected products
            
            if not approved_df.empty:
                st.subheader("Approved Products")
                st.write(approved_df)  # Display the DataFrame of approved products

            # Generate current timestamp for file names
            current_time = datetime.now().strftime("%m-%d_%H")

            # Download buttons for each report with formatted names
            st.download_button(
                label="Download Approved Products Report",
                data=to_excel({'ProductSets': approved_df, 'RejectionReasons': final_report_df['RejectionReasons']}),
                file_name=f'approved_products_{current_time}.xlsx'
            )

            st.download_button(
                label="Download Rejected Products Report",
                data=to_excel({'ProductSets': rejected_df, 'RejectionReasons': final_report_df['RejectionReasons']}),
                file_name=f'rejected_products_{current_time}.xlsx'
            )

            st.download_button(
                label="Download Combined Report",
                data=to_excel(final_report_df),
                file_name=f'combined_report_{current_time}.xlsx'
            )
        else:
            st.error("The CSV file is empty. Please upload a file with data.")
    
    except Exception as e:
        st.error(f"Error loading CSV file: {e}")
