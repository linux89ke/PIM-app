import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="wide")

# Function to load the blacklisted words from a file
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
        'perfumes': 'perfumes.xlsx'
    }
    
    data = {}
    for key, filename in config_files.items():
        try:
            data[key] = pd.read_excel(filename)
            st.sidebar.success(f"✔️ {filename} loaded successfully")
        except Exception as e:
            st.sidebar.error(f"❌ Error loading {filename}: {e}")
            if key == 'flags':  # flags.xlsx is critical
                st.stop()
    return data

# Initialize the app
st.title("Product Validation Tool")
st.sidebar.title("Configuration Status")

# Load configuration files
config_data = load_config_files()

# Load and process flags data
flags_data = config_data['flags']
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

# Load blacklisted words
blacklisted_words = load_blacklisted_words()

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Process uploaded file
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
        single_word_name = data[(data['NAME'].str.split().str.len() == 1) & 
                              (data['BRAND'] != 'Jumia Book')]
        
        # Category validation
        valid_category_codes_fas = config_data['category_fas']['ID'].tolist()
        generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & 
                                  (data['BRAND'] == 'Generic')]
        
        # Perfume price validation
        flagged_perfumes = []
        perfumes_data = config_data['perfumes']
        for _, row in data.iterrows():
            brand = row['BRAND']
            if brand in perfumes_data['BRAND'].values:
                keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                for keyword in keywords:
                    if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                        perfume_price = perfumes_data.loc[
                            (perfumes_data['BRAND'] == brand) & 
                            (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                        if row['GLOBAL_PRICE'] < perfume_price:
                            flagged_perfumes.append(row)
                            break

        # Blacklist and brand name checks
        flagged_blacklisted = data[data['NAME'].apply(lambda name: 
            any(black_word.lower() in str(name).lower().split() for black_word in blacklisted_words))]
        
        brand_in_name = data[data.apply(lambda row: 
            isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and 
            row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
        
        duplicate_products = data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]

        # Generate report
        final_report_rows = []
        for _, row in data.iterrows():
            reasons = []
            reason_codes_and_messages = []
            
            # Check all validation conditions
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
                    reasons.append(flag)
                    reason_codes_and_messages.append(reasons_dict[flag])
            
            # Check perfume price issues separately
            if row['PRODUCT_SET_SID'] in [r['PRODUCT_SET_SID'] for r in flagged_perfumes]:
                reasons.append("Perfume price issue")
                reason_codes_and_messages.append(reasons_dict["Perfume price issue"])

            # Prepare report row
            status = 'Rejected' if reasons else 'Approved'
            detailed_reasons = [f"{code} - {message}" for code, message, _ in reason_codes_and_messages]
            comments = [comment for _, _, comment in reason_codes_and_messages]
            
            final_report_rows.append({
                'ProductSetSid': row['PRODUCT_SET_SID'],
                'ParentSKU': row.get('PARENTSKU', ''),
                'Status': status,
                'Reason': ' | '.join(detailed_reasons) if detailed_reasons else '',
                'Comment': ' | '.join(comments) if comments else ''
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
            st.metric("Rejection Rate", f"{(len(rejected_df)/len(data)*100):.1f}%")

        # Show detailed results in expanders
        validation_results = [
            ("Missing COLOR", missing_color),
            ("Missing BRAND or NAME", missing_brand_or_name),
            ("Single-word NAME", single_word_name),
            ("Generic BRAND Issues", generic_brand_issues),
            ("Perfume Price Issues", pd.DataFrame(flagged_perfumes)),
            ("Blacklisted Words", flagged_blacklisted),
            ("Brand in Name", brand_in_name),
            ("Duplicate Products", duplicate_products)
        ]

        for title, df in validation_results:
            with st.expander(f"{title} ({len(df)} products)"):
                if not df.empty:
                    st.dataframe(df)
                else:
                    st.write("No issues found")

        # Export functions
        def to_excel(df1, df2, sheet1_name="ProductSets", sheet2_name="Flags"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df1.to_excel(writer, index=False, sheet_name=sheet1_name)
                df2.to_excel(writer, index=False, sheet_name=sheet2_name)
            output.seek(0)
            return output

        # Download buttons
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            final_report_excel = to_excel(final_report_df, flags_data)
            st.download_button(
                "📊 Download Full Report",
                data=final_report_excel,
                file_name=f"final_report_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with col2:
            approved_excel = to_excel(approved_df, flags_data)
            st.download_button(
                "✅ Download Approved Products",
                data=approved_excel,
                file_name=f"approved_products_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with col3:
            rejected_excel = to_excel(rejected_df, flags_data)
            st.download_button(
                "❌ Download Rejected Products",
                data=rejected_excel,
                file_name=f"rejected_products_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Error processing file: {e}")
        st.exception(e)
