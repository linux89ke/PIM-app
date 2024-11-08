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
reasons_data = pd.read_excel('reasons.xlsx')

# Load the reasons data
blacklisted_words = load_blacklisted_words()

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

            # Initialize a list for flagged products
            flagged_products = []

            # Define reason codes and messages
            reasons_dict = {
                "Missing COLOR": ("1000005", "Kindly confirm the actual product colour", "Kindly include color of the product"),
                "Missing BRAND or NAME": ("1000007", "Other Reason", "Missing BRAND or NAME"),
                "Single-word NAME": ("1000008", "Kindly Improve Product Name Description", "Name too short"),
                "Generic BRAND": ("1000007", "Other Reason", "Kindly use Fashion as brand name for Fashion products"),
                "Perfume price issue": ("1000030", "Suspected Counterfeit/Fake Product. Please Contact Seller Support By Raising A Claim, For Questions & Inquiries (Not Authorized)", ""),
                "Blacklisted word in NAME": ("1000033", "Keywords in your content/Product name/description has been blacklisted", "Blacklisted word in NAME"),
                "BRAND name repeated in NAME": ("1000002", "Kindly Ensure Brand Name Is Not Repeated In Product Name", "BRAND name repeated in NAME"),
                "Duplicate product": ("1000007", "Other Reason", "Product is duplicated")
            }

            # Flag 1: Missing COLOR
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            missing_color_count = len(missing_color)

            # Flag 2: Missing BRAND or NAME
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | 
                                          data['NAME'].isna() | (data['NAME'] == '')]
            missing_brand_or_name_count = len(missing_brand_or_name)

            # Flag 3: Single-word NAME (but not for "Jumia Book" BRAND)
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & 
                                    (data['BRAND'] != 'Jumia Book')]
            single_word_name_count = len(single_word_name)

            # Flag 4: Generic Brand Check
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & 
                                         (data['BRAND'] == 'Generic')]
            generic_brand_count = len(generic_brand_issues)

            # Flag 5: Price and Keyword Check (Perfume Check)
            flagged_perfumes = []
            for index, row in data.iterrows():
                brand = row['BRAND']
                if brand in perfumes_data['BRAND'].values:
                    keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                    for keyword in keywords:
                        if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                            perfume_price = perfumes_data.loc[
                                (perfumes_data['BRAND'] == brand) & 
                                (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                            price_difference = row['GLOBAL_PRICE'] - perfume_price
                            if price_difference < 0:
                                flagged_perfumes.append(row)
                                break
            flagged_perfumes_count = len(flagged_perfumes)

            # Flag 6: Blacklisted Words in NAME
            def check_blacklist(name):
                if isinstance(name, str):
                    name_words = name.lower().split()
                    return any(black_word.lower() in name_words for black_word in blacklisted_words)
                return False

            flagged_blacklisted = data[data['NAME'].apply(check_blacklist)]
            flagged_blacklisted_count = len(flagged_blacklisted)

            # Flag 7: Brand name repeated in NAME
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and 
                                              isinstance(row['NAME'], str) and 
                                              row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
            brand_in_name_count = len(brand_in_name)

            # Flag 8: Duplicate products based on NAME, BRAND, and SELLER_NAME
            duplicate_products = data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]
            duplicate_products_count = len(duplicate_products)

            # Prepare the final report rows
            final_report_rows = []

            # Collect all flagged products for final report
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

                status = 'Rejected' if reasons else 'Approved'
                
                # Prepare detailed reason string with codes and messages
                detailed_reasons = []
                for code, message, _ in reason_codes_and_messages:
                    detailed_reasons.append(f"{code} - {message}")
                
                reason_str = ' | '.join(detailed_reasons) if detailed_reasons else ''
                
                final_report_rows.append((row['PRODUCT_SET_SID'], row.get('PARENTSKU', ''), status, reason_str))

            # Prepare the final report DataFrame
            final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason'])

            st.write("Final Report Preview")
            st.write(final_report_df)

            # Separate approved and rejected reports
            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

            # Create containers for each flag result with counts
            with st.expander(f"Missing COLOR ({missing_color_count} products)"):
                st.write(missing_color[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 
                                         'CATEGORY', 'PARENTSKU', 'SELLER_NAME']] if missing_color_count > 0 else "No products flagged.")
                    
            with st.expander(f"Missing BRAND or NAME ({missing_brand_or_name_count} products)"):
                st.write(missing_brand_or_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 
                                                  'BRAND', 'CATEGORY', 'PARENTSKU', 
                                                  'SELLER_NAME']] if missing_brand_or_name_count > 0 else "No products flagged.")
                    
            with st.expander(f"Single-word NAME ({single_word_name_count} products)"):
                st.write(single_word_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 
                                            'BRAND', 'CATEGORY', 'PARENTSKU', 
                                            'SELLER_NAME']] if single_word_name_count > 0 else "No products flagged.")
                    
            with st.expander(f"Generic BRAND for valid CATEGORY_CODE ({generic_brand_count} products)"):
                st.write(generic_brand_issues[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 
                                                 'NAME', 'BRAND', 
                                                 'CATEGORY', 'PARENTSKU', 
                                                 'SELLER_NAME']] if generic_brand_count > 0 else "No products flagged.")
                    
            with st.expander(f"Perfume price issue ({flagged_perfumes_count} products)"):
                flagged_perfumes_df = pd.DataFrame(flagged_perfumes)
                st.write(flagged_perfumes_df[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 
                                                'NAME', 'BRAND',
                                                'CATEGORY', 'PARENTSKU',
                                                'SELLER_NAME',
                                                'GLOBAL_PRICE']] if flagged_perfumes_count > 0 else "No products flagged.")
                    
            with st.expander(f"Blacklisted words in NAME ({flagged_blacklisted_count} products)"):
                if flagged_blacklisted_count > 0:
                    flagged_blacklisted['Blacklisted_Word'] = flagged_blacklisted['NAME'].apply(
                        lambda x: [word for word in blacklisted_words if word.lower() in x.lower().split()][0]
                    )
                    st.write(flagged_blacklisted[['PRODUCT_SET_ID', 
                                                   'PRODUCT_SET_SID',
                                                   'NAME',
                                                   'Blacklisted_Word',
                                                   'BRAND',
                                                   'CATEGORY',
                                                   'PARENTSKU',
                                                   'SELLER_NAME']] )
                else:
                    st.write("No products flagged.")
                    
            with st.expander(f"BRAND name repeated in NAME ({brand_in_name_count} products)"):
                st.write(brand_in_name[['PRODUCT_SET_ID',
                                         'PRODUCT_SET_SID',
                                         'NAME',
                                         'BRAND',
                                         'CATEGORY',
                                         'PARENTSKU',
                                         'SELLER_NAME']] if brand_in_name_count > 0 else "No products flagged.")
                    
            with st.expander(f"Duplicate products ({duplicate_products_count} products)"):
                st.write(duplicate_products[['PRODUCT_SET_ID',
                                              'PRODUCT_SET_SID',
                                              'NAME',
                                              'BRAND',
                                              'CATEGORY',
                                              'PARENTSKU',
                                              'SELLER_NAME']] if duplicate_products_count > 0 else "No products flagged.")

            # Download buttons for the reports
            def to_excel(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='ProductSets')
                output.seek(0)
                return output
            
            st.download_button("Download Final Report", to_excel(final_report_df), 
                               "final_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            
    except Exception as e:
        st.error(f"Error loading the CSV file: {e}")
