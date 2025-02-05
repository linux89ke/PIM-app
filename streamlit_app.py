import pandas as pd
import streamlit as st
from io import BytesIO

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# Function to load blacklisted words from a file
def load_blacklisted_words():
    # ... (Same as before)

# Function to load sensitive brands from the sensitive_brands.xlsx file
def load_sensitive_brands():
    # ... (Same as before)

# Load category_FAS.xlsx to get the allowed CATEGORY_CODE values
def load_category_FAS():
    # ... (Same as before)

# Load book categories from Books_cat.txt
def load_book_categories():
    # ... (Same as before)

# Load and validate configuration files
def load_config_files():
    # ... (Same as before)

# Function to validate a single product
def validate_product(row, config_data, blacklisted_words, book_categories, sensitive_brands, category_FAS_codes):
    # ... (Same as before)

# Initialize the app
st.title("Product Validation Tool")

# Load configuration files
config_data = load_config_files()

# Load lists
category_FAS_codes = load_category_FAS()
sensitive_brands = load_sensitive_brands()
blacklisted_words = load_blacklisted_words()
book_categories = load_book_categories()


flags_data = config_data.get('flags')
reasons_dict = {}

if flags_data is not None:
    try:
        # Find the correct column names (case-insensitive)
        flag_col = next((col for col in flags_data.columns if col.lower() == 'flag'), None)
        reason_col = next((col for col in flags_data.columns if col.lower() == 'reason'), None)
        comment_col = next((col for col in flags_data.columns if col.lower() == 'comment'), None)

        if not all([flag_col, reason_col, comment_col]):
            st.error(f"Missing required columns in flags.xlsx. Required: Flag, Reason, Comment. Found: {flags_data.columns.tolist()}")
            st.stop()

        for _, row in flags_data.iterrows():
            flag = str(row[flag_col]).strip()
            reason = str(row[reason_col]).strip()
            comment = str(row[comment_col]).strip()
            reason_parts = reason.split(' - ', 1)
            code = reason_parts[0]
            message = reason_parts[1] if len(reason_parts) > 1 else ''
            reasons_dict[flag] = (code, message, comment)
    except Exception as e:
        st.error(f"Error processing flags data: {e}")
        st.stop()
        
#Display Flags data
st.subheader("Flags Data")
st.dataframe(flags_data)

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Process uploaded file
if uploaded_file is not None:
    try:
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype=str)

        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()

        st.write("CSV file loaded successfully. Preview of data:")
        st.write(data.head())

        # Ensure that category code is an integer if possible.
        try:
            data['CATEGORY_CODE'] = data['CATEGORY_CODE'].astype(int)
        except ValueError:
            st.error("CATEGORY_CODE column contains non-integer values.")
            st.stop()
            
        # Ensure that GLOBAL_PRICE is a float if possible
        try:
            data['GLOBAL_PRICE'] = data['GLOBAL_PRICE'].astype(float)
        except KeyError:
            st.warning("GLOBAL_PRICE column is missing. Perfume price validation will be skipped.")
        except ValueError:
            st.warning("GLOBAL_PRICE column contains invalid values (non-numeric). Perfume price validation will be skipped.")

        # Validation checks (Using validate_product function)
        final_report_rows = []
        for _, row in data.iterrows():
            reason, reason_details = validate_product(row, config_data, blacklisted_words, book_categories, sensitive_brands, category_FAS_codes)
            status = 'Rejected' if reason else 'Approved'
            reason_code, reason_message, comment = reason_details if reason_details else ("", "", "")
            detailed_reason = f"{reason_code} - {reason_message}" if reason_code and reason_message else ""

            final_report_rows.append({
                'ProductSetSid': row['PRODUCT_SET_SID'],
                'ParentSKU': row.get('PARENTSKU', ''),
                'Status': status,
                'Reason': detailed_reason,
                'Comment': comment
            })

        # Create final report DataFrame
        final_report_df = pd.DataFrame(final_report_rows)

        # Split into approved and rejected
        approved_df = final_report_df[final_report_df['Status'] == 'Approved']
        rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

        # Display results
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Products", len(data))
            st.metric("Approved Products", len(approved_df))
        with col2:
            st.metric("Rejected Products", len(rejected_df))
            st.metric("Rejection Rate", f"{(len(rejected_df) / len(data) * 100):.1f}%")
                
        # Download options for the report
        @st.cache_data
        def to_excel(df):
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Final Report")
            output.seek(0)
            return output

        excel_data = to_excel(final_report_df)
        st.download_button(label="Download Final Report", data=excel_data, file_name="validation_report.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        st.error(f"❌ Error processing the uploaded file: {e}")
