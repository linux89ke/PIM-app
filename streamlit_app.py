import pandas as pd
import streamlit as st
from io import BytesIO

# Title and file uploader component
st.title("Product Validation: COLOR, NAME, CATEGORY_CODE, Price, and Brand Checks")
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

# Load supporting Excel files
try:
    check_variation_data = pd.read_excel("pages/check_variation.xlsx")  # Check for category and variation issues
    category_fas_data = pd.read_excel("pages/category_FAS.xlsx")  # Check for generic brand issues
    perfumes_data = pd.read_excel("perfumes.xlsx")  # Load perfumes data for keyword checks
except Exception as e:
    st.error(f"Error loading supporting files: {e}")

# Check if the file is uploaded
if uploaded_file is not None:
    try:
        # Load the uploaded CSV file
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')

        if not data.empty:
            st.write("CSV file loaded successfully. Preview of data:")
            st.write(data.head())

            # Flag 1: Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            if not missing_color.empty:
                st.error(f"Found {len(missing_color)} products with missing COLOR fields.")
                st.write(missing_color)

            # Flag 2: Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            if not missing_brand_or_name.empty:
                st.error(f"Found {len(missing_brand_or_name)} products with missing BRAND or NAME.")
                st.write(missing_brand_or_name)

            # Flag 3: Single-word NAME (but not for "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            if not single_word_name.empty:
                st.error(f"Found {len(single_word_name)} products with a single-word NAME.")
                st.write(single_word_name)

            # Flag 4: Category and Variation Check
            valid_category_codes = check_variation_data['ID'].tolist()
            category_variation_issues = data[data['CATEGORY_CODE'].isin(valid_category_codes) & 
                                              (data['VARIATION'].isna() | (data['VARIATION'] == ''))]
            if not category_variation_issues.empty:
                st.error(f"Found {len(category_variation_issues)} products with missing VARIATION for valid CATEGORY_CODE.")
                st.write(category_variation_issues)

            # Flag 5: Generic Brand Check
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & 
                                         (data['BRAND'] == 'Generic')]
            if not generic_brand_issues.empty:
                st.error(f"Found {len(generic_brand_issues)} products with GENERIC brand for valid CATEGORY_CODE.")
                st.write(generic_brand_issues)

            # Flag 6: Perfume Price and Keyword Check (Optimized)
            # Step 1: Merge uploaded data with perfumes.xlsx based on BRAND
            merged_data = pd.merge(data, perfumes_data[['BRAND', 'KEYWORD', 'PRICE']], on='BRAND', how='left')

            # Step 2: Filter rows where the NAME contains the keyword from perfumes.xlsx
            # Use .str.contains() to find the keyword in the NAME (case insensitive)
            merged_data['Keyword_Found'] = merged_data.apply(
                lambda row: row['KEYWORD'].lower() in row['NAME'].lower() if pd.notna(row['KEYWORD']) and pd.notna(row['NAME']) else False,
                axis=1
            )

            # Step 3: Calculate the price difference where keywords are found
            # Flag rows where the keyword is found and the GLOBAL_PRICE is less than the perfume's PRICE
            merged_data['Price_Difference'] = merged_data['GLOBAL_PRICE'] - merged_data['PRICE']

            flagged_perfumes = merged_data[(merged_data['Keyword_Found'] == True) & (merged_data['Price_Difference'] < 0)]

            # Step 4: Display flagged perfumes
            if not flagged_perfumes.empty:
                st.error(f"Found {len(flagged_perfumes)} products flagged due to perfume price issues.")
                st.write(flagged_perfumes[['PRODUCT_SET_SID', 'PARENTSKU', 'NAME', 'BRAND', 'GLOBAL_PRICE', 'PRICE', 'Price_Difference']])

            # Prepare a list to hold the final report rows
            final_report_rows = []

            # Iterate over each product row to populate the final report
            for index, row in data.iterrows():
                # Check if the row was flagged and set status accordingly
                reasons = []
                if row['PRODUCT_SET_SID'] in missing_color['PRODUCT_SET_SID'].values:
                    reasons.append("Missing COLOR")
                if row['PRODUCT_SET_SID'] in missing_brand_or_name['PRODUCT_SET_SID'].values:
                    reasons.append("Missing BRAND or NAME")
                if row['PRODUCT_SET_SID'] in single_word_name['PRODUCT_SET_SID'].values:
                    reasons.append("Single-word NAME")
                if row['PRODUCT_SET_SID'] in category_variation_issues['PRODUCT_SET_SID'].values:
                    reasons.append("Missing VARIATION")
                if row['PRODUCT_SET_SID'] in generic_brand_issues['PRODUCT_SET_SID'].values:
                    reasons.append("Generic BRAND")
                if row['PRODUCT_SET_SID'] in flagged_perfumes['PRODUCT_SET_SID'].values:
                    reasons.append("Perfume price issue")

                status = 'Rejected' if reasons else 'Approved'
                reason = '1000007 - Other Reason' if status == 'Rejected' else ''
                comment = ', '.join(reasons) if reasons else 'No issues'

                # Append the row to the list
                final_report_rows.append({
                    'ProductSetSid': row['PRODUCT_SET_SID'],  # from CSV file
                    'ParentSKU': row['PARENTSKU'],            # from CSV file
                    'Status': status,
                    'Reason': reason,
                    'Comment': comment
                })

            # Convert the list of rows to a DataFrame
            final_report = pd.DataFrame(final_report_rows)

            # Create an empty DataFrame for the RejectionReasons sheet
            rejection_reasons = pd.DataFrame()

            # Save both sheets to an Excel file in memory
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # Write the final report to the first sheet (ProductSets)
                final_report.to_excel(writer, sheet_name='ProductSets', index=False)

                # Write the empty RejectionReasons sheet
                rejection_reasons.to_excel(writer, sheet_name='RejectionReasons', index=False)

            # Allow users to download the final Excel file
            st.write("Here is a preview of the ProductSets sheet:")
            st.write(final_report)

            st.download_button(
                label="Download Excel File",
                data=output.getvalue(),
                file_name='ProductSets.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            st.error("Uploaded file is empty. Please upload a valid CSV file.")
    
    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
else:
    st.info("Please upload a CSV file to continue.")
