```python
import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import os

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# Constants
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG"]
REJECTION_REASONS_COLS = ['CODE - REJECTION_REASON', 'COMMENT']
FULL_DATA_COLS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY",
    "CATEGORY_CODE", "COLOR", "MAIN_IMAGE", "VARIATION", "PARENTSKU",
    "SELLER_NAME", "SELLER_SKU", "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG"
]

# Configuration file loading functions (simplified for completeness)
def load_blacklisted_words():
    try:
        with open('blacklisted.txt', 'r') as file:
            return [line.strip().lower() for line in file if line.strip()]
    except FileNotFoundError:
        st.warning("blacklisted.txt not found. Skipping blacklisted words validation.")
        return []
    except Exception as e:
        st.error(f"Error loading blacklisted.txt: {str(e)}")
        return []

def load_book_category_codes():
    try:
        with open('book_category_codes.txt', 'r') as file:
            return [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        st.warning("book_category_codes.txt not found. Skipping book category validation.")
        return []
    except Exception as e:
        st.error(f"Error loading book_category_codes.txt: {str(e)}")
        return []

def load_sensitive_brand_words():
    try:
        df = pd.read_excel('sensitive_brands.xlsx')
        return df['Brand'].str.lower().tolist()
    except FileNotFoundError:
        st.warning("sensitive_brands.xlsx not found. Skipping sensitive brand validation.")
        return []
    except Exception as e:
        st.error(f"Error loading sensitive_brands.xlsx: {str(e)}")
        return []

def load_approved_book_sellers():
    try:
        df = pd.read_excel('approved_book_sellers.xlsx')
        return df['Seller'].str.lower().tolist()
    except FileNotFoundError:
        st.warning("approved_book_sellers.xlsx not found. Skipping seller approval validation.")
        return []
    except Exception as e:
        st.error(f"Error loading approved_book_sellers.xlsx: {str(e)}")
        return []

def load_perfume_category_codes():
    try:
        df = pd.read_excel('perfumes.xlsx')
        return df['Category_Code'].str.lower().tolist()
    except FileNotFoundError:
        st.warning("perfumes.xlsx not found. Skipping perfume price validation.")
        return []
    except Exception as e:
        st.error(f"Error loading perfumes.xlsx: {str(e)}")
        return []

def load_config_files():
    config_files = {
        'check_variation': 'check_variation.xlsx',
        'category_FAS': 'category_FAS.xlsx',
        'perfumes': 'perfumes.xlsx',
        'reasons': 'reasons.xlsx'
    }
    configs = {}
    for key, file in config_files.items():
        try:
            configs[key] = pd.read_excel(file)
        except FileNotFoundError:
            st.warning(f"{file} not found. Skipping {key} validation.")
            configs[key] = pd.DataFrame()
        except Exception as e:
            st.error(f"Error loading {file}: {str(e)}")
            configs[key] = pd.DataFrame()
    return configs

# Validation functions (simplified for completeness)
def check_missing_color(df, book_category_codes):
    return df[
        (~df['CATEGORY_CODE'].isin(book_category_codes)) &
        (df['COLOR'].isna() | (df['COLOR'] == ''))
    ][['PRODUCT_SET_SID', 'PARENTSKU']].assign(
        Status='Rejected',
        Reason='1000005 - Kindly confirm the actual product colour',
        Comment='Kindly add color on the color field',
        FLAG='Missing COLOR'
    )

def check_missing_brand_or_name(df):
    return df[
        (df['BRAND'].isna() | (df['BRAND'] == '') | df['NAME'].isna() | (df['NAME'] == ''))
    ][['PRODUCT_SET_SID', 'PARENTSKU']].assign(
        Status='Rejected',
        Reason='1000006 - Missing Brand or Name',
        Comment='Please provide both Brand and Name fields',
        FLAG='Missing BRAND or NAME'
    )

def check_single_word_name(df, book_category_codes):
    return df[
        (~df['CATEGORY_CODE'].isin(book_category_codes)) &
        (df['NAME'].str.split().str.len() == 1)
    ][['PRODUCT_SET_SID', 'PARENTSKU']].assign(
        Status='Rejected',
        Reason='1000008 - Kindly Improve Product Name Description',
        Comment='Kindly update the product title to be more descriptive (more than one word)',
        FLAG='Single-word NAME'
    )

# Placeholder for other validation checks
def validate_products(data, country):
    try:
        book_category_codes = load_book_category_codes()
        configs = load_config_files()
        reasons_df = configs.get('reasons', pd.DataFrame(columns=REJECTION_REASONS_COLS))
        
        # Initialize final report
        final_report = pd.DataFrame(columns=PRODUCTSETS_COLS)
        processed_sids = set()
        
        # Validation checks (simplified)
        validation_checks = [
            ('Missing COLOR', lambda x: check_missing_color(x, book_category_codes)),
            ('Missing BRAND or NAME', check_missing_brand_or_name),
            ('Single-word NAME', lambda x: check_single_word_name(x, book_category_codes))
            # Add other checks as needed
        ]
        
        for flag_name, check_func in validation_checks:
            if data.empty:
                continue
            flagged = check_func(data)
            if not flagged.empty:
                flagged['ProductSetSid'] = flagged['PRODUCT_SET_SID'].astype(str)
                flagged = flagged[~flagged['ProductSetSid'].isin(processed_sids)]
                final_report = pd.concat([final_report, flagged[PRODUCTSETS_COLS]], ignore_index=True)
                processed_sids.update(flagged['ProductSetSid'])
        
        # Approve remaining products
        remaining = data[~data['PRODUCT_SET_SID'].isin(processed_sids)][['PRODUCT_SET_SID', 'PARENTSKU']]
        if not remaining.empty:
            remaining = remaining.assign(
                Status='Approved',
                Reason='',
                Comment='',
                FLAG='',
                ProductSetSid=remaining['PRODUCT_SET_SID'].astype(str)
            )
            final_report = pd.concat([final_report, remaining[PRODUCTSETS_COLS]], ignore_index=True)
        
        return final_report
    except Exception as e:
        st.error(f"Error in validate_products: {str(e)}")
        return pd.DataFrame(columns=PRODUCTSETS_COLS)

# Export functions
def to_excel_base(df_to_export, sheet_name, columns_to_include, writer):
    try:
        df_prepared = df_to_export.copy()
        for col in columns_to_include:
            if col not in df_prepared.columns:
                df_prepared[col] = pd.NA
        df_prepared[columns_to_include].to_excel(writer, index=False, sheet_name=sheet_name)
    except Exception as e:
        st.error(f"Error in to_excel_base: {str(e)}")

def to_excel(df_to_export, reasons_df):
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            to_excel_base(df_to_export, 'ProductSets', PRODUCTSETS_COLS, writer)
            to_excel_base(reasons_df, 'RejectionReasons', REJECTION_REASONS_COLS, writer)
        output.seek(0)
        return output
    except Exception as e:
        st.error(f"Error in to_excel: {str(e)}")
        return BytesIO()

def to_excel_full_data(data_df, final_report_df):
    try:
        output = BytesIO()
        data_df_copy = data_df.copy()
        final_report_df_copy = final_report_df.copy()
        
        # Ensure consistent data types
        data_df_copy['PRODUCT_SET_SID'] = data_df_copy['PRODUCT_SET_SID'].astype(str).str.strip()
        final_report_df_copy['ProductSetSid'] = final_report_df_copy['ProductSetSid'].astype(str).str.strip()

        # Merge input data with validation results
        merged_df = pd.merge(
            data_df_copy,
            final_report_df_copy[["ProductSetSid", "Status", "Reason", "Comment", "FLAG"]],
            left_on="PRODUCT_SET_SID",
            right_on="ProductSetSid",
            how="left"
        )
        
        if merged_df.empty:
            st.error("Merged DataFrame is empty. Verify PRODUCT_SET_SID values match.")
            return output
        
        # Clean up merge artifacts
        if 'ProductSetSid_y' in merged_df.columns:
            merged_df.drop(columns=['ProductSetSid_y'], inplace=True)
        if 'ProductSetSid_x' in merged_df.columns:
            merged_df.rename(columns={'ProductSetSid_x': 'PRODUCT_SET_SID'}, inplace=True)
        
        if 'FLAG' in merged_df.columns:
            merged_df['FLAG'] = merged_df['FLAG'].fillna('')
        
        # Sellers Data sheet
        sellers_data_rows = []
        
        # Sellers Summary
        try:
            if 'SELLER_NAME' in merged_df.columns and not merged_df['SELLER_NAME'].isna().all():
                seller_rejections = (merged_df[merged_df['Status'] == 'Rejected']
                                   .groupby('SELLER_NAME')
                                   .size()
                                   .reset_index(name='Rejected Products'))
                sellers_data_rows.append(pd.DataFrame([['', '']]))
                sellers_data_rows.append(pd.DataFrame([['Sellers Summary', '']]))
                sellers_data_rows.append(seller_rejections.rename(
                    columns={'SELLER_NAME': 'Seller', 'Rejected Products': 'Number of Rejected Products'}))
            else:
                sellers_data_rows.append(pd.DataFrame([['Sellers Summary', 'No valid SELLER_NAME data available']]))
        except Exception as e:
            sellers_data_rows.append(pd.DataFrame([['Sellers Summary', f'Error: {str(e)}']]))

        # Categories Summary
        try:
            category_column = 'CATEGORY_CODE' if 'CATEGORY_CODE' in merged_df.columns else 'CATEGORY' if 'CATEGORY' in merged_df.columns else None
            if category_column and not merged_df[category_column].isna().all():
                category_rejections = (merged_df[merged_df['Status'] == 'Rejected']
                                     .groupby(category_column)
                                     .size()
                                     .reset_index(name='Rejected Products'))
                sellers_data_rows.append(pd.DataFrame([['', '']]))
                sellers_data_rows.append(pd.DataFrame([['Categories Summary', '']]))
                sellers_data_rows.append(category_rejections.rename(
                    columns={category_column: 'Category', 'Rejected Products': 'Number of Rejected Products'}))
            else:
                sellers_data_rows.append(pd.DataFrame([['Categories Summary', 'No valid CATEGORY or CATEGORY_CODE data available']]))
        except Exception as e:
            sellers_data_rows.append(pd.DataFrame([['Categories Summary', f'Error: {str(e)}']]))

        # Rejection Reasons Summary
        try:
            if 'Reason' in merged_df.columns and not merged_df['Reason'].isna().all():
                reason_rejections = (merged_df[merged_df['Status'] == 'Rejected']
                                   .groupby('Reason')
                                   .size()
                                   .reset_index(name='Rejected Products'))
                sellers_data_rows.append(pd.DataFrame([['', '']]))
                sellers_data_rows.append(pd.DataFrame([['Rejection Reasons Summary', '']]))
                sellers_data_rows.append(reason_rejections.rename(
                    columns={'Reason': 'Rejection Reason', 'Rejected Products': 'Number of Rejected Products'}))
            else:
                sellers_data_rows.append(pd.DataFrame([['Rejection Reasons Summary', 'No valid Reason data available']]))
        except Exception as e:
            sellers_data_rows.append(pd.DataFrame([['Rejection Reasons Summary', f'Error: {str(e)}']]))

        # Write to Excel
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            to_excel_base(merged_df, "ProductSets", FULL_DATA_COLS, writer)
            start_row = 0
            for df in sellers_data_rows:
                df.to_excel(writer, sheet_name='Sellers Data', startrow=start_row, index=False)
                start_row += len(df) + 1

        output.seek(0)
        return output
    except Exception as e:
        st.error(f"Error generating Full Data Export: {str(e)}")
        return BytesIO()

# Main app logic
st.title("Product Validation Tool")
country = st.selectbox("Select Country", ["Kenya", "Uganda"], key="country")
uploaded_file = st.file_uploader("Upload Product CSV", type=["csv"])

if uploaded_file:
    try:
        # Load CSV with error handling
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        
        # Validate required columns
        required_cols = ['PRODUCT_SET_SID']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            st.error(f"Missing required columns: {', '.join(missing_cols)}")
        else:
            # Run validation
            final_report_df = validate_products(data, country)
            prefix = "KE" if country == "Kenya" else "UG"
            date = datetime.now().strftime("%Y-%m-%d")

            # Metrics
            total_products = len(data)
            approved_df = final_report_df[final_report_df['Status'] == 'Approved']
            rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']
            approved_count = len(approved_df)
            rejected_count = len(rejected_df)
            rejection_rate = (rejected_count / total_products * 100) if total_products > 0 else 0

            st.subheader("Metrics")
            st.write(f"Total Products: {total_products}")
            st.write(f"Approved Products: {approved_count}")
            st.write(f"Rejected Products: {rejected_count}")
            st.write(f"Rejection Rate: {rejection_rate:.2f}%")

            # Overall Data Exports
            st.subheader("Overall Data Exports (All Sellers)")
            try:
                st.download_button(
                    label="Final Report (All)",
                    data=to_excel(final_report_df, load_config_files().get('reasons', pd.DataFrame())),
                    file_name=f"{prefix}_Final_Report_{date}_ALL.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.download_button(
                    label="Rejected Products (All)",
                    data=to_excel(rejected_df, load_config_files().get('reasons', pd.DataFrame())),
                    file_name=f"{prefix}_Rejected_Products_{date}_ALL.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.download_button(
                    label="Approved Products (All)",
                    data=to_excel(approved_df, load_config_files().get('reasons', pd.DataFrame())),
                    file_name=f"{prefix}_Approved_Products_{date}_ALL.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.download_button(
                    label="Full Data Export (All)",
                    data=to_excel_full_data(data.copy(), final_report_df),
                    file_name=f"{prefix}_Full_Data_Export_{date}_ALL.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as e:
                st.error(f"Error generating exports: {str(e)}")

            # Display individual validation flags (simplified)
            for flag_name, _ in [
                ('Missing COLOR', None),
                ('Missing BRAND or NAME', None),
                ('Single-word NAME', None)
            ]:
                flagged = final_report_df[final_report_df['FLAG'] == flag_name]
                if not flagged.empty:
                    with st.expander(f"{flag_name} ({len(flagged)} products)"):
                        st.dataframe(flagged)
    except Exception as e:
        st.error(f"Error processing CSV: {str(e)}")

# Sidebar for seller filtering (simplified)
if uploaded_file and not final_report_df.empty:
    st.sidebar.subheader("Seller Filter")
    sellers = data['SELLER_NAME'].unique().tolist() if 'SELLER_NAME' in data.columns else []
    sellers.append("All Sellers")
    selected_sellers = st.sidebar.multiselect("Select Sellers", sellers, default="All Sellers")
    # Add seller-specific exports as needed
```
