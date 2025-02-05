import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# Function to load blacklisted words from a file
def load_blacklisted_words():
    try:
        with open('blacklisted.txt', 'r') as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        st.error("blacklisted.txt file not found!")
        return []
    except Exception as e:
        st.error(f"Error loading blacklisted words: {e}")
        return []

# Function to load sensitive brands from the sensitive_brands.xlsx file
def load_sensitive_brands():
    try:
        sensitive_brands_df = pd.read_excel('sensitive_brands.xlsx')
        return sensitive_brands_df['BRAND'].tolist()  # Assuming the file has a 'Brand' column
    except FileNotFoundError:
        st.error("sensitive_brands.xlsx file not found!")
        return []
    except Exception as e:
        st.error(f"Error loading sensitive brands: {e}")
        return []

# Load category_FAS.xlsx to get the allowed CATEGORY_CODE values
def load_category_FAS():
    try:
        category_fas_df = pd.read_excel('category_FAS.xlsx')
        return category_fas_df['ID'].tolist()  # Assuming 'ID' column contains the category codes
    except FileNotFoundError:
        st.error("category_FAS.xlsx file not found!")
        return []
    except Exception as e:
        st.error(f"Error loading category_FAS data: {e}")
        return []

# Load Books_cat.txt to get the CATEGORY_CODE values for books
def load_books_category_codes():
    try:
        with open('Books_cat.txt', 'r') as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        st.error("Books_cat.txt file not found!")
        return []
    except Exception as e:
        st.error(f"Error loading Books_cat.txt: {e}")
        return []

# Load and process flags data
def load_flags_data():
    try:
        flags_data = pd.read_excel('flags.xlsx')
        return flags_data
    except Exception as e:
        st.error(f"Error processing flags data: {e}")
        return pd.DataFrame()

# File upload section
st.title("Product Validation Tool")
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Process uploaded file
if uploaded_file is not None:
    try:
        data = pd.read_csv(uploaded_file, sep=';', encoding='utf-8')

        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()

        # Load validation files
        blacklisted_words = load_blacklisted_words()
        sensitive_brands = load_sensitive_brands()
        category_FAS_codes = load_category_FAS()
        books_category_codes = load_books_category_codes()
        flags_data = load_flags_data()

        # Create reasons_dict from flags data
        reasons_dict = {}
        try:
            for _, row in flags_data.iterrows():
                flag = str(row['Flag']).strip()
                reason = str(row['Reason']).strip()
                comment = str(row['Comment']).strip()
                reason_parts = reason.split(' - ', 1)
                code = reason_parts[0]
                message = reason_parts[1] if len(reason_parts) > 1 else ''
                reasons_dict[flag] = (code, message, comment)
        except Exception as e:
            st.error(f"Error processing flags data: {e}")
            st.stop()

        # Perform validations and flagging
        missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
        missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | 
                                     data['NAME'].isna() | (data['NAME'] == '')]
        single_word_name = data[(data['NAME'].str.split().str.len() == 1) & 
                                 (~data['CATEGORY_CODE'].isin(books_category_codes))]

        valid_category_codes_fas = category_FAS_codes
        generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & 
                                     (data['BRAND'] == 'Generic')]

        flagged_blacklisted = data[data['NAME'].apply(lambda name: 
            any(black_word.lower() in str(name).lower().split() for black_word in blacklisted_words))]

        brand_in_name = data[data.apply(lambda row: 
            isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and 
            row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
        
        duplicate_products = data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]
        
        # Show flag counts
        st.subheader("Flag Counts")
        st.write(f"Missing COLOR: {len(missing_color)}")
        st.write(f"Missing BRAND or NAME: {len(missing_brand_or_name)}")
        st.write(f"Single-word NAME (excluding books): {len(single_word_name)}")
        st.write(f"Generic BRAND issues: {len(generic_brand_issues)}")
        st.write(f"Blacklisted words in NAME: {len(flagged_blacklisted)}")
        st.write(f"Brand name repeated in NAME: {len(brand_in_name)}")
        st.write(f"Duplicate products: {len(duplicate_products)}")

        # Display flagged data
        st.subheader("Flagged Products")
        flag_columns = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'COLOR']
        st.write("### Missing Color", missing_color[flag_columns])
        st.write("### Missing Brand or Name", missing_brand_or_name[flag_columns])
        st.write("### Single-word Name", single_word_name[flag_columns])
        st.write("### Generic Brand Issues", generic_brand_issues[flag_columns])
        st.write("### Blacklisted Word Issues", flagged_blacklisted[flag_columns])
        st.write("### Brand Repeated in Name", brand_in_name[flag_columns])
        st.write("### Duplicate Products", duplicate_products[flag_columns])

        # Prepare final report
        final_report_rows = []
        for _, row in data.iterrows():
            reason = None
            reason_details = None

            # Check for the first applicable reason
            validations = [
                (missing_color, "Missing COLOR"),
                (missing_brand_or_name, "Missing BRAND or NAME"),
                (single_word_name, "Single-word NAME"),
                (generic_brand_issues, "Generic BRAND"),
                (flagged_blacklisted, "Blacklisted word in NAME"),
                (brand_in_name, "BRAND name repeated in NAME"),
                (duplicate_products, "Duplicate product")
            ]
            
            for validation_df, flag in validations:
                if row['PRODUCT_SET_SID'] in validation_df['PRODUCT_SET_SID'].values:
                    reason = flag
                    reason_details = reasons_dict.get(flag, ("", "", ""))
                    break  # Stop after finding the first applicable reason

            # Prepare report row
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

        final_report_df = pd.DataFrame(final_report_rows)

        # Create report download button
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            final_report_df.to_excel(writer, sheet_name="ProductSets", index=False)

        output.seek(0)
        st.download_button("Download Final Report", output, file_name=f"validation_report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx")

    except Exception as e:
        st.error(f"❌ Error processing uploaded file: {e}")
