import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# Load blacklisted words from a file
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

# Load configuration files
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
            df = pd.read_excel(filename).rename(columns=lambda x: x.strip())
            data[key] = df
        except Exception as e:
            st.error(f"❌ Error loading {filename}: {e}")
            if key == 'flags':  
                st.stop()
    return data

# Initialize the app
st.title("Product Validation Tool")

# Load configuration files
config_data = load_config_files()

# Load flags data
flags_data = config_data['flags']
reasons_data = config_data['reasons']
reasons_dict = {}
for _, row in flags_data.iterrows():
    flag = str(row['Flag']).strip()
    reason = str(row['Reason']).strip()
    comment = str(row['Comment']).strip()
    reason_parts = reason.split(' - ', 1)
    code = reason_parts[0]
    message = reason_parts[1] if len(reason_parts) > 1 else ''
    reasons_dict[flag] = (code, message, comment)

# Display flag definitions in an expander
with st.expander("View Flag Definitions"):
    st.write("Here are the validation flags used in the product validation process:")
    for flag, (code, message, comment) in reasons_dict.items():
        st.markdown(f"**{flag}**")
        st.write(f"- **Reason Code:** {code}")
        st.write(f"- **Message:** {message}")
        st.write(f"- **Comment:** {comment}")
        st.write("---")

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

        # Perform validations
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

        # Collect all flagged products for final report
        flagged_products = []
        for index, row in data.iterrows():
            reasons = []
            reason_codes_and_messages = []

            if row['PRODUCT_SET_SID'] in missing_color['PRODUCT_SET_SID'].values:
                reasons.append("Missing COLOR")
                reason_codes_and_messages.append(reasons_dict["Missing COLOR"])

            if row['PRODUCT_SET_SID'] in missing_brand_or_name['PRODUCT_SET_SID'].values:
                reasons.append("Missing BRAND or NAME")
                reason_codes_and_messages.append(reasons_dict["Missing BRAND or NAME"])

            if row['PRODUCT_SET_SID'] in single_word_name['PRODUCT_SET_SID'].values:
                reasons.append("Single-word NAME")
                reason_codes_and_messages.append(reasons_dict["Single-word NAME"])

            if row['PRODUCT_SET_SID'] in generic_brand_issues['PRODUCT_SET_SID'].values:
                reasons.append("Generic BRAND")
                reason_codes_and_messages.append(reasons_dict["Generic BRAND"])

            if row['PRODUCT_SET_SID'] in [r['PRODUCT_SET_SID'] for r in flagged_perfumes]:
                reasons.append("Perfume price issue")
                reason_codes_and_messages.append(reasons_dict["Perfume price issue"])

            if row['PRODUCT_SET_SID'] in flagged_blacklisted['PRODUCT_SET_SID'].values:
                reasons.append("Blacklisted word in NAME")
                reason_codes_and_messages.append(reasons_dict["Blacklisted word in NAME"])

            if row['PRODUCT_SET_SID'] in brand_in_name['PRODUCT_SET_SID'].values:
                reasons.append("BRAND name repeated in NAME")
                reason_codes_and_messages.append(reasons_dict["BRAND name repeated in NAME"])

            if row['PRODUCT_SET_SID'] in duplicate_products['PRODUCT_SET_SID'].values:
                reasons.append("Duplicate product")
                reason_codes_and_messages.append(reasons_dict["Duplicate product"])

            if reasons:
                flagged_products.append({
                    'ProductSetSid': row['PRODUCT_SET_SID'],
                    'ParentSKU': row.get('PARENTSKU', ''),
                    'Reasons': reasons,
                    'Reason Codes and Messages': reason_codes_and_messages
                })

        # Display flagged products in an expander
        with st.expander("Flagged Products Details"):
            st.write("Here are the flagged products and their reasons:")
            for product in flagged_products:
                st.write(f"**ProductSetSid:** {product['ProductSetSid']}")
                st.write(f"**ParentSKU:** {product['ParentSKU']}")
                st.write("**Reasons:**")
                for i, reason in enumerate(product['Reasons']):
                    reason_code, message, comment = product['Reason Codes and Messages'][i]
                    st.write(f"- **{reason}** - Code: {reason_code}, Message: {message}, Comment: {comment}")
                st.write("---")

    except Exception as e:
        st.error(f"Error processing uploaded file: {e}")
