import streamlit as st
import pandas as pd
from datetime import datetime
from utils import validate_products, to_excel, to_excel_full_data, to_excel_flag_data, get_download_link, COUNTRY_MAPPING

def data_lake_tab(config_data, book_category_codes, sensitive_brand_words, approved_book_sellers, perfume_category_codes, reasons_df):
    st.header("Data Lake")
    country = st.selectbox("Select Country", ["All Countries", "Kenya", "Uganda"], index=1, key="data_lake_country")
    uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx"], key="data_lake_file")
    
    if uploaded_file:
        try:
            raw_data = pd.read_excel(uploaded_file, sheet_name="Sheet1")
            st.session_state['lake_data'] = raw_data
            st.write("Unique countries:", raw_data['dsc_shop_active_country'].dropna().unique().tolist())
            
            column_mapping = {
                'image1': 'MAIN_IMAGE',
                'cod_category_code': 'CATEGORY_CODE',
                'dsc_shop_tax_class': 'TAX_CLASS',
                'dsc_shop_active_country': 'ACTIVE_STATUS_COUNTRY',
                'cod_productset_sid': 'PRODUCT_SET_SID',
                'cod_parent_sku': 'PARENTSKU',
                'dsc_shop_seller_name': 'SELLER_NAME',
                'dsc_brand_name': 'BRAND',
                'dsc_name': 'NAME',
                'dsc_category_name': 'CATEGORY',
                'color': 'COLOR',
                'color_family': 'COLOR_FAMILY',
                'list_variations': 'VARIATION',
                'list_seller_skus': 'SELLER_SKU'
            }
            df = raw_data.rename(columns=column_mapping)
            df['COLOR'] = df['COLOR'].astype(str).replace('nan', '')
            df['COLOR_FAMILY'] = df['COLOR_FAMILY'].astype(str).replace('nan', '')
            
            required_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'CATEGORY_CODE', 'COLOR', 'COLOR_FAMILY', 'SELLER_NAME', 'PARENTSKU']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                st.error(f"Missing columns: {', '.join(missing_cols)}")
            else:
                if country != "All Countries":
                    country_code = COUNTRY_MAPPING[country]
                    df = df[df['ACTIVE_STATUS_COUNTRY'] == country_code]
                    if df.empty:
                        st.error(f"No data for {country} ({country_code})")
                        st.stop()
                
                # Check SKU overlap
                if st.session_state['daily_data'] is not None:
                    overlap = set(df['PRODUCT_SET_SID']).intersection(set(st.session_state['daily_data']['PRODUCT_SET_SID']))
                    if overlap:
                        st.warning(f"Found {len(overlap)} overlapping SKUs with Daily Validation file.")
                
                final_report, validation_results = validate_products(df, config_data, book_category_codes, sensitive_brand_words, approved_book_sellers, perfume_category_codes, country, is_data_lake=True)
                approved_df = final_report[final_report['Status'] == 'Approved']
                rejected_df = final_report[final_report['Status'] == 'Rejected']
                
                st.write(f"Total Products: {len(df)}")
                st.write(f"Approved: {len(approved_df)}")
                st.write(f"Rejected: {len(rejected_df)}")
                
                # Seller filtering
                seller_options = ['All Sellers'] + list(df['SELLER_NAME'].dropna().unique())
                selected_sellers = st.sidebar.multiselect("Select Sellers", seller_options, default=['All
