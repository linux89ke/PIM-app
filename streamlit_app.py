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

# Load and validate configuration files
def load_config_files():
    config_files = {
        'flags': 'flags.xlsx',
        'check_variation': 'check_variation.xlsx',
        'category_fas': 'category_FAS.xlsx',
        'perfumes': 'perfumes.xlsx',
        'reasons': 'reasons.xlsx'
    }
    
    data = {}
    for key, filename in config_files.items():
        try:
            df = pd.read_excel(filename).rename(columns=lambda x: x.strip())  # Strip spaces from column names
            data[key] = df
        except Exception as e:
            st.error(f"❌ Error loading {filename}: {e}")
            if key == 'flags':  # flags.xlsx is critical
                st.stop()
    return data

# Initialize the app
st.title("Product Validation Tool")

# Load configuration files
config_data = load_config_files()

# Load flags data
flags_data = config_data['flags']
reasons_data = config_data['reasons']  # For RejectionReasons sheet
reasons_dict = {}
for _, row in flags_data.iterrows():
    flag = str(row['Flag']).strip()
    reason = str(row['Reason']).strip()
    comment = str(row['Comment']).strip()
    reason_parts = reason.split(' - ', 1)
    code = reason_parts[0]
    message = reason_parts[1] if len(reason_parts) > 1 else ''
    reasons_dict[flag] = (code, message, comment)

# Load blacklisted words
blacklisted_words = load_blacklisted_words()

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

if uploaded_file is not None:
    try:
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()
        st.write("CSV file loaded successfully. Preview of data:")
        st.write(data.head())

        # Validation checks
        missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
        missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | 
                                     data['NAME'].isna() | (data['NAME'] == '')]
        single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
        
        valid_category_codes_fas = config_data['category_fas']['ID'].tolist()
        generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & 
                                    (data['BRAND'] == 'Generic')]
        
        flagged_perfumes = []
        perfumes_data = config_data['perfumes']
        for _, row in data.iterrows():
            brand = row['BRAND']
            if brand in perfumes_data['BRAND'].values:
                keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                for keyword in keywords:
                    if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                        perfume_price = perfumes_data.loc[(perfumes_data['BRAND'] == brand) & 
                                                          (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                        if row['GLOBAL_PRICE'] < perfume_price:
                            flagged_perfumes.append(row)
                            break

        flagged_blacklisted = data[data['NAME'].apply(lambda name: 
            any(black_word.lower() in str(name).lower().split() for black_word in blacklisted_words))]
        
        brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and 
            isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
        
        duplicate_products = data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]

        # Generate report with a single reason per rejection
        final_report_rows = []
        for _, row in data.iterrows():
            reason = None
            reason_details = None

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
                    break

            if not reason and row['PRODUCT_SET_SID'] in [r['PRODUCT_SET_SID'] for r in flagged_perfumes]:
                reason = "Perfume price issue"
                reason_details = reasons_dict.get("Perfume price issue", ("", "", ""))

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
        approved_df = final_report_df[final_report_df['Status'] == 'Approved']
        rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Products", len(data))
            st.metric("Approved Products", len(approved_df))
        with col2:
            st.metric("Rejected Products", len(rejected_df))
            st.metric("Rejection Rate", f"{(len(rejected_df)/len(data)*100):.1f}%")

        def to_excel(df1, df2, sheet1_name="ProductSets", sheet2_name="RejectionReasons"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df1.to_excel(writer, index=False, sheet_name=sheet1_name)
                df2.to_excel(writer, index=False, sheet_name=sheet2_name)
            output.seek(0)
            return output

        current_date = datetime.now().strftime("%Y-%m-%d")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            full_report = to_excel(final_report_df, reasons_data)
            st.download_button("Download Full Report", full_report, 
                               file_name=f"Product_Validation_Full_Report_{current_date}.xlsx", 
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with col2:
            approved_report = to_excel(approved_df, reasons_data)
            st.download_button("Download Approved Only", approved_report, 
                               file_name=f"Product_Validation_Approved_{current_date}.xlsx", 
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with col3:
            rejected_report = to_excel(rejected_df, reasons_data)
            st.download_button("Download Rejected Only", rejected_report, 
                               file_name=f"Product_Validation_Rejected_{current_date}.xlsx", 
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        st.error(f"Error processing uploaded file: {e}")
