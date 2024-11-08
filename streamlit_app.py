import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# Function to load the blacklisted words from a file
def load_blacklisted_words():
    with open('blacklisted.txt', 'r') as f:
        return [line.strip() for line in f.readlines()]

# Load data for checks
check_variation_data = pd.read_excel('check_variation.xlsx')
category_fas_data = pd.read_excel('category_FAS.xlsx')
perfumes_data = pd.read_excel('perfumes.xlsx')
reasons_data = pd.read_excel('reasons.xlsx')

# Load the reasons data
blacklisted_words = load_blacklisted_words()

# Load flags from flags.xlsx
flags_df = pd.read_excel('flags.xlsx')
flags_dict = {row['Flag']: (row['Reason'], row['Comment']) for index, row in flags_df.iterrows()}

# Streamlit app layout
st.title("Product Validation Tool")

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Check if the file is uploaded
if uploaded_file is not None:
    try:
        # Load the uploaded CSV file data
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        if not data.empty:
            st.write("CSV file loaded successfully. Preview of data:")
            st.write(data.head())

            # Prepare the final report rows
            final_report_rows = []

            # Flagging logic
            for index, row in data.iterrows():
                reason_code, comment = "", ""

                # Example validation checks (customize these as needed)
                if row['COLOR'] is None or row['COLOR'] == '':
                    reason_code, comment = flags_dict.get('Missing COLOR', ("", ""))
                
                elif row['BRAND'] is None or row['BRAND'] == '':
                    reason_code, comment = flags_dict.get('Missing BRAND or NAME', ("", ""))
                
                elif len(row['NAME'].split()) == 1:
                    reason_code, comment = flags_dict.get('Single-word NAME', ("", ""))
                
                elif row['BRAND'] == 'Generic':
                    reason_code, comment = flags_dict.get('Generic BRAND', ("", ""))
                
                elif row['GLOBAL_PRICE'] < 0:  # Example condition for perfume price issue
                    reason_code, comment = flags_dict.get('Perfume price issue', ("", ""))
                
                elif any(black_word.lower() in row['NAME'].lower() for black_word in blacklisted_words):
                    reason_code, comment = flags_dict.get('Blacklisted word in NAME', ("", ""))
                
                elif row['BRAND'] in brand_in_name['BRAND'].values:
                    reason_code, comment = flags_dict.get('BRAND name repeated in NAME', ("", ""))
                
                elif row['NAME'] in duplicate_products['NAME'].values:
                    reason_code, comment = flags_dict.get('Duplicate product', ("", ""))

                status = 'Rejected' if reason_code else 'Approved'
                
                final_report_rows.append((row['PRODUCT_SET_SID'], row.get('PARENTSKU', ''), status, f"{reason_code} - {comment}", comment))

            # Prepare the final report DataFrame
            final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason', 'Comment'])
            st.write("Final Report Preview")
            st.write(final_report_df)

            # Separate approved and rejected reports
            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

            # Create containers for each flag result with counts using expanders
            with st.expander(f"Missing COLOR ({len(missing_color)} products)"):
                st.write(missing_color if len(missing_color) > 0 else "No products flagged.")
            
            with st.expander(f"Missing BRAND or NAME ({len(missing_brand_or_name)} products)"):
                st.write(missing_brand_or_name if len(missing_brand_or_name) > 0 else "No products flagged.")
            
            with st.expander(f"Single-word NAME ({len(single_word_name)} products)"):
                st.write(single_word_name if len(single_word_name) > 0 else "No products flagged.")
            
            with st.expander(f"Generic BRAND for valid CATEGORY_CODE ({len(generic_brand_issues)} products)"):
                st.write(generic_brand_issues if len(generic_brand_issues) > 0 else "No products flagged.")
            
            with st.expander(f"Perfume price issue ({len(flagged_perfumes)} products)"):
                flagged_perfumes_df = pd.DataFrame(flagged_perfumes)
                st.write(flagged_perfumes_df if len(flagged_perfumes) > 0 else "No products flagged.")
            
            with st.expander(f"Blacklisted words in NAME ({len(flagged_blacklisted)} products)"):
                flagged_blacklisted['Blacklisted_Word'] = flagged_blacklisted['NAME'].apply(lambda x: [word for word in blacklisted_words if word.lower() in x.lower().split()][0])
                st.write(flagged_blacklisted if len(flagged_blacklisted) > 0 else "No products flagged.")
            
            with st.expander(f"BRAND name repeated in NAME ({len(brand_in_name)} products)"):
                st.write(brand_in_name if len(brand_in_name) > 0 else "No products flagged.")
            
            with st.expander(f"Duplicate products ({len(duplicate_products)} products)"):
                st.write(duplicate_products if len(duplicate_products) > 0 else "No products flagged.")

            # Function to create Excel files with three sheets each
            def to_excel(df1, df2, df3, sheet1_name="ApprovedProducts", sheet2_name="RejectedProducts", sheet3_name="FinalReport"):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df1.to_excel(writer, index=False, sheet_name=sheet1_name)
                    df2.to_excel(writer, index=False, sheet_name=sheet2_name)
                    df3.to_excel(writer, index=False, sheet_name=sheet3_name)
                output.seek(0)
                return output.getvalue()

            current_date = datetime.now().strftime("%Y-%m-%d")

            # Download buttons for the reports
            final_report_button_data = to_excel(approved_df, rejected_df, final_report_df)
            st.download_button(
                label=f"Download Final Report ({current_date})",
                data=final_report_button_data,
                file_name=f"final_report_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="final_report"
            )

        else:
            st.write("The file is empty. Please upload a valid CSV file.")
    except Exception as e:
        st.write(f"Error processing file: {e}")
else:
    st.write("Please upload a CSV file to proceed.")
