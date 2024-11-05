import pandas as pd
import streamlit as st

# Load the category_FAS.xlsx file
category_fas_data = pd.read_excel('path/to/category_FAS.xlsx')  # Update with the correct path to your file

# Load the uploaded CSV file
uploaded_file = st.file_uploader("Upload CSV file", type='csv')
if uploaded_file is not None:
    data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
    if not data.empty:
        st.write("CSV file loaded successfully. Preview of data:")
        st.write(data.head())

        # Initialize lists to collect flagged rows for each flag category
        flags_data = {flag: pd.DataFrame() for flag in flagging_criteria.keys()}

        # Apply flagging rules in order of importance, stopping at the first match per product
        flagged_products = set()
        for flag, (reason, comment) in flagging_criteria.items():
            if flag == "Missing COLOR":
                flags_data[flag] = data[(data['COLOR'].isna() | (data['COLOR'] == '')) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
            elif flag == "Missing BRAND or NAME":
                flags_data[flag] = data[(data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
            elif flag == "Name too short":
                flags_data[flag] = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book') & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
            elif flag == "Brand is Generic instead of Fashion":
                valid_category_codes_fas = category_fas_data['ID'].tolist()  # Ensure this column exists in your file
                flags_data[flag] = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic') & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
            elif flag == "Perfume price too low":
                perfumes_data = perfumes_data.sort_values(by="PRICE", ascending=False).drop_duplicates(subset=["BRAND", "KEYWORD"], keep="first")
                flagged_perfumes = []
                for _, row in data.iterrows():
                    if row['PRODUCT_SET_SID'] not in flagged_products:
                        brand = row['BRAND']
                        if brand in perfumes_data['BRAND'].values:
                            keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                            for keyword in keywords:
                                if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                                    perfume_price = perfumes_data.loc[(perfumes_data['BRAND'] == brand) & (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                                    price_difference = row['GLOBAL_PRICE'] - perfume_price
                                    if price_difference < 0:
                                        flagged_perfumes.append(row)
                                        flagged_products.add(row['PRODUCT_SET_SID'])
                                        break
                flags_data[flag] = pd.DataFrame(flagged_perfumes)
            elif flag == "Blacklisted word in NAME":
                def check_blacklist(name):
                    if isinstance(name, str):
                        name_words = name.lower().split()
                        return any(black_word.lower() in name_words for black_word in blacklisted_words)
                    return False
                flags_data[flag] = data[data['NAME'].apply(check_blacklist) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
            elif flag == "BRAND name repeated in NAME":
                flags_data[flag] = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]
            elif flag == "Duplicate product":
                flags_data[flag] = data[data.duplicated(subset='PRODUCT_SET_ID', keep=False) & (~data['PRODUCT_SET_SID'].isin(flagged_products))]

            # Track flagged products to prevent re-flagging
            flagged_products.update(flags_data[flag]['PRODUCT_SET_SID'].tolist())

        # Display flagged items with counts
        for flag, df in flags_data.items():
            count = len(df)
            with st.expander(f"{flag} ({count} products)"):
                if count > 0:
                    st.write(df[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged.")

        # Prepare final report
        final_report_rows = []
