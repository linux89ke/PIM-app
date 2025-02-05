import pandas as pd
import streamlit as st
from io import BytesIO

# Load category codes for books from Books_cat.txt
def load_books_category_codes():
    try:
        with open('Books_cat.txt', 'r') as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        st.error("Books_cat.txt file not found!")
        return []
    except Exception as e:
        st.error(f"Error loading books category codes: {e}")
        return []

# Load books category codes
books_category_codes = load_books_category_codes()

# Load other necessary configurations
def load_config_data():
    # Load necessary files for validation (this assumes you have your reasons.xlsx, perfumes.xlsx, etc. in place)
    config_data = {}
    try:
        config_data['reasons'] = pd.read_excel('reasons.xlsx')
        config_data['perfumes'] = pd.read_excel('perfumes.xlsx')
        config_data['category_FAS'] = pd.read_excel('category_FAS.xlsx')
        config_data['check_variation'] = pd.read_excel('check_variation.xlsx')
    except Exception as e:
        st.error(f"Error loading configuration files: {e}")
    return config_data

config_data = load_config_data()

# List of sensitive brands for validation
sensitive_brands = ["SensitiveBrand1", "SensitiveBrand2"]

# List of valid category codes for Fashion items
valid_category_codes_fas = config_data['category_FAS']['ID'].tolist()

# Load blacklisted words
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

blacklisted_words = load_blacklisted_words()

# Process uploaded file
uploaded_file = st.file_uploader("Upload CSV", type="csv")

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

        # Exclude books from the single-word name check
        single_word_name = data[(data['NAME'].str.split().str.len() == 1) & 
                              (data['BRAND'] != 'Jumia Book') & 
                              (~data['CATEGORY_CODE'].isin(books_category_codes))]
        
        # Other checks remain the same
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

        # Missing Variation Flag check
        missing_variation = data[~data['CATEGORY_CODE'].isin(config_data['check_variation']['ID']) &
                                 data['VARIATION'].isna()]

        # Sensitive Brands Flag (only for categories in category_FAS.xlsx)
        sensitive_brand_issues = data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & 
                                      (data['BRAND'].isin(sensitive_brands))]

        # Generate report with a single reason per rejection
        final_report_rows = []
        flag_counts = {
            'Missing COLOR': 0,
            'Missing BRAND or NAME': 0,
            'Single-word NAME': 0,
            'Generic BRAND': 0,
            'Perfume price issue': 0,
            'Blacklisted word in NAME': 0,
            'BRAND name repeated in NAME': 0,
            'Duplicate product': 0,
            'Missing Variation': 0,
            'Sensitive Brand': 0
        }
        
        for _, row in data.iterrows():
            reason = None
            reason_details = None

            # Check all validation conditions in a specific order and take the first applicable one
            validations = [
                (missing_color, "Missing COLOR"),
                (missing_brand_or_name, "Missing BRAND or NAME"),
                (single_word_name, "Single-word NAME"),
                (generic_brand_issues, "Generic BRAND"),
                (flagged_blacklisted, "Blacklisted word in NAME"),
                (brand_in_name, "BRAND name repeated in NAME"),
                (duplicate_products, "Duplicate product"),
                (missing_variation, "Missing Variation"),
                (sensitive_brand_issues, "Sensitive Brand")
            ]
            
            for validation_df, flag in validations:
                if row['PRODUCT_SET_SID'] in validation_df['PRODUCT_SET_SID'].values:
                    reason = flag
                    reason_details = reasons_dict.get(flag, ("", "", ""))
                    flag_counts[flag] += 1  # Increment the count for this flag
                    break  # Stop after finding the first applicable reason

            # Check perfume price issues separately
            if not reason and row['PRODUCT_SET_SID'] in [r['PRODUCT_SET_SID'] for r in flagged_perfumes]:
                reason = "Perfume price issue"
                reason_details = reasons_dict.get("Perfume price issue", ("", "", ""))
                flag_counts["Perfume price issue"] += 1

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

        # Create final report DataFrame
        final_report_df = pd.DataFrame(final_report_rows)
        
        # Display the flag counts on the front-end
        st.subheader("Number of Rows per Flag")
        for flag, count in flag_counts.items():
            st.write(f"{flag}: {count} products")

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
            ("Duplicate Products", duplicate_products),
            ("Missing Variation", missing_variation),
            ("Sensitive Brands", sensitive_brand_issues)
        ]

        for title, df in validation_results:
            with st.expander(title):
                if not df.empty:
                    st.write(df)

        # Download options for the report
        @st.cache_data
        def to_excel(df):
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df.to_excel(writer, sheet_name="ProductSets", index=False)
                config_data['reasons'].to_excel(writer, sheet_name="RejectionReasons", index=False)
            return output.getvalue()

        st.download_button("Download Final Report", to_excel(final_report_df), "final_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        st.error(f"❌ Error processing uploaded file: {e}")
