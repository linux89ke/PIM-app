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
reasons_data = pd.read_excel('reasons.xlsx')  # Load the reasons data
blacklisted_words = load_blacklisted_words()

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

            # Initialize a list for flagged products
            flagged_products = []

            # Define a mapping of reasons with their corresponding codes
            reason_codes = {
                "Missing COLOR": ("1000005", "Kindly confirm the actual product colour"),
                "Missing BRAND or NAME": ("1000007", "Missing BRAND or NAME"),
                "Single-word NAME": ("1000008", "Kindly Improve Product Name Description"),
                "Generic BRAND": ("1000007", "Brand is Generic instead of Fashion"),
                "Perfume price issue": ("1000030", "Perfume price too low"),
                "Blacklisted word in NAME": ("1000033", "Keywords in your content/ Product name / description has been blacklisted"),
                "BRAND name repeated in NAME": ("1000002", "Kindly Ensure Brand Name Is Not Repeated In Product Name"),
                "Duplicate product": ("1000007", "Product is duplicated"),
            }

            # Priority order of reasons
            priority_order = [
                "Missing COLOR",
                "Missing BRAND or NAME",
                "Single-word NAME",
                "Generic BRAND",
                "Perfume price issue",
                "Blacklisted word in NAME",
                "BRAND name repeated in NAME",
                "Duplicate product",
            ]

            # Flag checks
            missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
            missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]
            single_word_name = data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]
            valid_category_codes_fas = category_fas_data['ID'].tolist()
            generic_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]
            flagged_perfumes = []

            for index, row in data.iterrows():
                brand = row['BRAND']
                if brand in perfumes_data['BRAND'].values:
                    keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
                    for keyword in keywords:
                        if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                            perfume_price = perfumes_data.loc[(perfumes_data['BRAND'] == brand) & (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                            price_difference = row['GLOBAL_PRICE'] - perfume_price
                            if price_difference < 0:
                                flagged_perfumes.append(row)
                                break

            flagged_blacklisted = data[data['NAME'].apply(lambda name: any(word.lower() in name.lower() for word in blacklisted_words if isinstance(name, str)))]
            brand_in_name = data[data.apply(lambda row: isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and row['BRAND'].lower() in row['NAME'].lower(), axis=1)]
            duplicate_products = data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]

            # Prepare the final report rows
            final_report_rows = []

            # Collect all flagged products for the final report
            for index, row in data.iterrows():
                selected_reason = None

                for reason in priority_order:
                    if reason == "Missing COLOR" and row['PRODUCT_SET_SID'] in missing_color['PRODUCT_SET_SID'].values:
                        selected_reason = f"{reason_codes[reason][0]} - {reason_codes[reason][1]}"
                        break
                    elif reason == "Missing BRAND or NAME" and row['PRODUCT_SET_SID'] in missing_brand_or_name['PRODUCT_SET_SID'].values:
                        selected_reason = f"{reason_codes[reason][0]} - {reason_codes[reason][1]}"
                        break
                    elif reason == "Single-word NAME" and row['PRODUCT_SET_SID'] in single_word_name['PRODUCT_SET_SID'].values:
                        selected_reason = f"{reason_codes[reason][0]} - {reason_codes[reason][1]}"
                        break
                    elif reason == "Generic BRAND" and row['PRODUCT_SET_SID'] in generic_brand_issues['PRODUCT_SET_SID'].values:
                        selected_reason = f"{reason_codes[reason][0]} - {reason_codes[reason][1]}"
                        break
                    elif reason == "Perfume price issue" and row['PRODUCT_SET_SID'] in [r['PRODUCT_SET_SID'] for r in flagged_perfumes]:
                        selected_reason = f"{reason_codes[reason][0]} - {reason_codes[reason][1]}"
                        break
                    elif reason == "Blacklisted word in NAME" and row['PRODUCT_SET_SID'] in flagged_blacklisted['PRODUCT_SET_SID'].values:
                        selected_reason = f"{reason_codes[reason][0]} - {reason_codes[reason][1]}"
                        break
                    elif reason == "BRAND name repeated in NAME" and row['PRODUCT_SET_SID'] in brand_in_name['PRODUCT_SET_SID'].values:
                        selected_reason = f"{reason_codes[reason][0]} - {reason_codes[reason][1]}"
                        break
                    elif reason == "Duplicate product" and row['PRODUCT_SET_SID'] in duplicate_products['PRODUCT_SET_SID'].values:
                        selected_reason = f"{reason_codes[reason][0]} - {reason_codes[reason][1]}"
                        break

                status = 'Rejected' if selected_reason else 'Approved'
                reason = selected_reason if selected_reason else ''

                final_report_rows.append((row['PRODUCT_SET_SID'], row['PARENTSKU'], status, reason))

            # Prepare the final report DataFrame
            final_report_df = pd.DataFrame(final_report_rows, columns=['ProductSetSid', 'ParentSKU', 'Status', 'Reason'])
            st.write("Final Report Preview")
            st.write(final_report_df)

            # Separate approved and rejected reports
            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

            # Create containers for each flag result
            with st.expander(f"Missing COLOR ({len(missing_color)} products)"):
                if len(missing_color) > 0:
                    st.write(missing_color[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged.")

            with st.expander(f"Missing BRAND or NAME ({len(missing_brand_or_name)} products)"):
                if len(missing_brand_or_name) > 0:
                    st.write(missing_brand_or_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged.")

            with st.expander(f"Single-word NAME ({len(single_word_name)} products)"):
                if len(single_word_name) > 0:
                    st.write(single_word_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged.")

            with st.expander(f"Generic BRAND for valid CATEGORY_CODE ({len(generic_brand_issues)} products)"):
                if len(generic_brand_issues) > 0:
                    st.write(generic_brand_issues[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged.")

            with st.expander(f"Perfume price issue ({len(flagged_perfumes)} products)"):
                if len(flagged_perfumes) > 0:
                    flagged_perfumes_df = pd.DataFrame(flagged_perfumes)
                    st.write(flagged_perfumes_df[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME', 'GLOBAL_PRICE']])
                else:
                    st.write("No products flagged.")

            with st.expander(f"Blacklisted words in NAME ({len(flagged_blacklisted)} products)"):
                if len(flagged_blacklisted) > 0:
                    flagged_blacklisted['Blacklisted_Word'] = flagged_blacklisted['NAME'].apply(
                        lambda x: [word for word in blacklisted_words if word.lower() in x.lower().split()][0]
                    )
                    st.write(flagged_blacklisted[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'Blacklisted_Word', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged.")

            with st.expander(f"BRAND name repeated in NAME ({len(brand_in_name)} products)"):
                if len(brand_in_name) > 0:
                    st.write(brand_in_name[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged.")

            with st.expander(f"Duplicate products ({len(duplicate_products)} products)"):
                if len(duplicate_products) > 0:
                    st.write(duplicate_products[['PRODUCT_SET_ID', 'PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'PARENTSKU', 'SELLER_NAME']])
                else:
                    st.write("No products flagged.")

            # Download buttons for the reports
            def to_excel(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='ProductSets')
                output.seek(0)
                return output

            st.download_button("Download Final Report", to_excel(final_report_df), "final_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("Download Approved Products", to_excel(approved_df), "approved_products.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("Download Rejected Products", to_excel(rejected_df), "rejected_products.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        st.error(f"Error loading the CSV file: {e}")
