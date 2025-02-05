import pandas as pd
import streamlit as st

# File uploader section
uploaded_file = st.file_uploader("Upload a file", type=["csv", "xlsx"])

# If a file is uploaded, proceed with processing
if uploaded_file is not None:
    try:
        # Load the uploaded file into a DataFrame
        if uploaded_file.name.endswith('.csv'):
            data = pd.read_csv(uploaded_file)
        elif uploaded_file.name.endswith('.xlsx'):
            data = pd.read_excel(uploaded_file)

        # Check if necessary columns are present
        if 'CATEGORY_CODE' not in data.columns or 'VARIATION' not in data.columns:
            st.error("Uploaded file is missing necessary columns: 'CATEGORY_CODE' or 'VARIATION'.")
            st.stop()

        # Load check_variation.xlsx to compare the category codes
        try:
            check_variation_df = pd.read_excel('check_variation.xlsx')
            # Ensure the 'ID' column contains the category codes we are interested in
            valid_category_codes = check_variation_df['ID'].tolist()
        except FileNotFoundError:
            st.error("check_variation.xlsx file not found!")
            st.stop()
        except Exception as e:
            st.error(f"Error loading check_variation.xlsx: {e}")
            st.stop()

        # Check for rows with missing variation for valid category codes
        missing_variation = data[(data['CATEGORY_CODE'].isin(valid_category_codes)) & 
                                  (data['VARIATION'].isna() | (data['VARIATION'] == ''))]

        # Display the results for missing variation
        if not missing_variation.empty:
            st.write(f"Found {len(missing_variation)} rows with missing variation.")
            st.dataframe(missing_variation[['PRODUCT_SET_SID', 'CATEGORY_CODE', 'VARIATION']])
        else:
            st.write("No rows with missing variations.")

        # Proceed with the flags and reporting
        # --- Placeholder: Add your flagging logic here ---

        # Example: Show flagged products
        flagged_products = data[data['VARIATION'].isna()]  # Example: Flagging missing variations
        if not flagged_products.empty:
            st.write(f"Flagged {len(flagged_products)} rows due to missing variations.")
            st.dataframe(flagged_products[['PRODUCT_SET_SID', 'CATEGORY_CODE', 'VARIATION']])
        
        # --- Additional flagging checks for other conditions can be added here ---
        
        # Example: Creating the final report with flagged rows and reasons
        final_report = flagged_products.copy()
        final_report['Status'] = 'Rejected'
        final_report['Reason'] = 'Missing Variation'
        final_report['Comment'] = 'Kindly include variation for the product'

        # --- Optionally, add approved rows ---
        approved_products = data[~data['PRODUCT_SET_SID'].isin(flagged_products['PRODUCT_SET_SID'])]
        approved_products['Status'] = 'Approved'
        approved_products['Reason'] = 'N/A'
        approved_products['Comment'] = 'Product approved'

        # Combine both approved and flagged rows for final report
        combined_report = pd.concat([final_report, approved_products])

        # Allow user to download the final report
        with st.expander("Download Final Report"):
            final_excel = pd.ExcelWriter('final_report.xlsx', engine='xlsxwriter')
            combined_report.to_excel(final_excel, sheet_name='ProductSets', index=False)
            # Adding a "RejectionReasons" sheet (using the 'reasons.xlsx' file)
            try:
                reasons_df = pd.read_excel('reasons.xlsx')
                reasons_df.to_excel(final_excel, sheet_name='RejectionReasons', index=False)
            except FileNotFoundError:
                st.warning("Rejection reasons file 'reasons.xlsx' not found!")
            final_excel.save()

            # Provide download link
            st.download_button(label="Download Final Report", data=open('final_report.xlsx', 'rb'), file_name="final_report.xlsx", mime="application/vnd.ms-excel")

    except Exception as e:
        st.error(f"Error processing uploaded file: {e}")
else:
    st.info("Please upload a file to proceed.")
