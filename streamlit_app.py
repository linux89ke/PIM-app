import pandas as pd
import streamlit as st
from io import BytesIO

# Function to load the blacklisted words from a file
def load_blacklisted_words():
    with open('blacklisted.txt', 'r') as f:
        return [line.strip() for line in f.readlines()]

# Load data for checks
check_variation_data = pd.read_excel('check_variation.xlsx')
category_fas_data = pd.read_excel('category_FAS.xlsx')
perfumes_data = pd.read_excel('perfumes.xlsx')
blacklisted_words = load_blacklisted_words()

# Load rejection reasons from the RejectionReasons sheet
rejection_reasons = pd.read_excel('reasons.xlsx', sheet_name='RejectionReasons')
rejection_reasons.columns = rejection_reasons.columns.str.strip()
reasons_dict = rejection_reasons.set_index('CODE - REJECTION_REASON').to_dict(orient='index')

# Streamlit app layout
st.title("Product Validation Tool")

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Check if the file is uploaded
if uploaded_file is not None:
    try:
        # Load the uploaded CSV file
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        if not data.empty:
            st.write("CSV file loaded successfully. Preview of data:")
            st.write(data.head())

            # Initialize containers for each flag result
            flagged_data = []

            # Flag 1: Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            if not missing_color.empty:
                for _, row in missing_color.iterrows():
                    flagged_data.append({
                        'ProductSetSid': row['PRODUCT_SET_SID'],
                        'ParentSKU': row['PARENTSKU'],
                        'Status': 'Rejected',
                        'Reason': '1000005 - Kindly confirm the actual product colour',
                        'Comment': reasons_dict.get('1000005 - Kindly confirm the actual product colour', {}).get('Reason', '')
                    })

            # Flag 2: Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            if not missing_brand_or_name.empty:
                for _, row in missing_brand_or_name.iterrows():
                    flagged_data.append({
                        'ProductSetSid': row['PRODUCT_SET_SID'],
                        'ParentSKU': row['PARENTSKU'],
                        'Status': 'Rejected',
                        'Reason': '1000007 - Other Reason',
                        'Comment': reasons_dict.get('1000007 - Other Reason', {}).get('Reason', '')
                    })

            # Flag 3: Single-word NAME (excluding "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            if not single_word_name.empty:
                for _, row in single_word_name.iterrows():
                    flagged_data.append({
                        'ProductSetSid': row['PRODUCT_SET_SID'],
                        'ParentSKU': row['PARENTSKU'],
                        'Status': 'Rejected',
                        'Reason': '1000008 - Kindly Improve Product Name Description',
                        'Comment': reasons_dict.get('1000008 - Kindly Improve Product Name Description', {}).get('Reason', '')
                    })

            # Flag 4: Generic BRAND for valid CATEGORY_CODE
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]
            if not generic_brand_issues.empty:
                for _, row in generic_brand_issues.iterrows():
                    flagged_data.append({
                        'ProductSetSid': row['PRODUCT_SET_SID'],
                        'ParentSKU': row['PARENTSKU'],
                        'Status': 'Rejected',
                        'Reason': '1000007 - Other Reason',
                        'Comment': reasons_dict.get('1000007 - Other Reason', {}).get('Reason', '')
                    })

            # Flag 5: Perfume price issue check
            perfumes_data = perfumes_data.sort_values(by="PRICE", ascending=False).drop_duplicates(subset=["BRAND", "KEYWORD"], keep="first")
            flagged_perfumes = []
            for _, row in data.iterrows():
                brand = row['BRAND']
                if brand in perfumes_data['BRAND'].values:
                    keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                    for keyword in keywords:
                        if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                            perfume_price = perfumes_data.loc[(perfumes_data['BRAND'] == brand) & (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                            price_difference = row['GLOBAL_PRICE'] - perfume_price
                            if price_difference < 0:
                                flagged_perfumes.append(row)
                                flagged_data.append({
                                    'ProductSetSid': row['PRODUCT_SET_SID'],
                                    'ParentSKU': row['PARENTSKU'],
                                    'Status': 'Rejected',
                                    'Reason': '1000030 - Suspected Counterfeit/Fake Product',
                                    'Comment': reasons_dict.get('1000030 - Suspected Counterfeit/Fake Product', {}).get('Reason', '')
                                })
                                break

            # Flag 6: Blacklisted words in NAME
            def check_blacklist(name):
                if isinstance(name, str):
                    name_words = name.lower().split()
                    return any(black_word.lower() in name_words for black_word in blacklisted_words)
                return False

            flagged_blacklisted = data[data['NAME'].apply(check_blacklist)]
            for _, row in flagged_blacklisted.iterrows():
                flagged_data.append({
                    'ProductSetSid': row['PRODUCT_SET_SID'],
                    'ParentSKU': row['PARENTSKU'],
                    'Status': 'Rejected',
                    'Reason': '1000033 - Blacklisted Keywords',
                    'Comment': reasons_dict.get('1000033 - Blacklisted Keywords', {}).get('Reason', '')
                })

            # Display flagged data in Streamlit
            st.write("Flagged Products Summary:")
            flagged_df = pd.DataFrame(flagged_data)
            st.write(flagged_df)

            # Prepare and download flagged data
            def to_excel(dataframe):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    dataframe.to_excel(writer, index=False, sheet_name='ProductSets')
                    rejection_reasons.to_excel(writer, index=False, sheet_name='RejectionReasons')
                output.seek(0)
                return output

            st.download_button(
                label='Download Flagged Products Report',
                data=to_excel(flagged_df),
                file_name='flagged_products_report.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

    except Exception as e:
        st.error(f"An error occurred: {e}")
