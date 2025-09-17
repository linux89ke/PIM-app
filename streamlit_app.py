import streamlit as st
import pandas as pd
import io
import base64
from datetime import datetime

# Country mapping for Data Lake tab
COUNTRY_MAPPING = {
    "Kenya": "jumia-ke",
    "Uganda": "jumia-ug"
}

# Validation functions
def check_missing_color(df):
    missing_color = df[df['COLOR'].isna() | (df['COLOR'] == '')]
    return missing_color, "Missing or empty COLOR field"

def check_duplicate_products(df):
    duplicates = df[df.duplicated(subset=['PRODUCT_SET_SID'], keep=False)]
    return duplicates, "Duplicate PRODUCT_SET_SID"

def check_category_color(df):
    invalid_color = df[~df['CATEGORY'].isin(['Wrist Watches', 'Smart Watches']) & (df['COLOR'].str.lower() == 'multicolour')]
    return invalid_color, "Multicolour not allowed for non-watch categories"

def validate_data(df):
    validations = [check_missing_color, check_duplicate_products, check_category_color]
    results = []
    for func in validations:
        invalid_rows, reason = func(df)
        if not invalid_rows.empty:
            invalid_rows['REASON'] = reason
            results.append(invalid_rows)
    return pd.concat(results) if results else pd.DataFrame()

def generate_excel_download(df, filename):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

def get_download_link(data, filename, text):
    b64 = base64.b64encode(data).decode()
    return f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}">{text}</a>'

# Streamlit app
st.title("Product Validation Tool")

# Tabs
tab1, tab2 = st.tabs(["Daily Validation", "Data Lake"])

# Daily Validation Tab
with tab1:
    st.header("Daily Validation")
    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"], key="daily")
    country = st.selectbox("Select Country", ["Kenya", "Uganda"], key="daily_country")
    
    if uploaded_file and country:
        try:
            df = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
            required_columns = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'COLOR']
            if not all(col in df.columns for col in required_columns):
                st.error(f"Missing required columns: {', '.join(set(required_columns) - set(df.columns))}")
            else:
                # Filter by country
                df = df[df['ACTIVE_STATUS_COUNTRY'] == country[:2]]  # e.g., 'KE' for Kenya
                if df.empty:
                    st.error(f"No data found for country {country}")
                else:
                    st.write(f"Rows loaded: {len(df)}")
                    
                    # Validate data
                    invalid_df = validate_data(df)
                    approved_df = df[~df['PRODUCT_SET_SID'].isin(invalid_df['PRODUCT_SET_SID'])]
                    
                    # Generate reports
                    final_report = df.copy()
                    final_report['STATUS'] = final_report['PRODUCT_SET_SID'].apply(
                        lambda x: 'APPROVED' if x in approved_df['PRODUCT_SET_SID'].values else 'REJECTED'
                    )
                    
                    # Display results
                    st.write(f"Approved rows: {len(approved_df)}")
                    st.write(f"Rejected rows: {len(invalid_df)}")
                    
                    # Download links
                    final_excel = generate_excel_download(final_report, f"Final_Report_{country}.xlsx")
                    rejected_excel = generate_excel_download(invalid_df, f"Rejected_{country}.xlsx")
                    approved_excel = generate_excel_download(approved_df, f"Approved_{country}.xlsx")
                    full_excel = generate_excel_download(df, f"Full_Data_{country}.xlsx")
                    
                    st.markdown(get_download_link(final_excel, f"Final_Report_{country}.xlsx", "Download Final Report"), unsafe_allow_html=True)
                    st.markdown(get_download_link(rejected_excel, f"Rejected_{country}.xlsx", "Download Rejected Report"), unsafe_allow_html=True)
                    st.markdown(get_download_link(approved_excel, f"Approved_{country}.xlsx", "Download Approved Report"), unsafe_allow_html=True)
                    st.markdown(get_download_link(full_excel, f"Full_Data_{country}.xlsx", "Download Full Data"), unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")

# Data Lake Tab
with tab2:
    st.header("Data Lake")
    uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx"], key="data_lake")
    country = st.selectbox("Select Country", ["All Countries", "Kenya", "Uganda"], key="data_lake_country")
    
    if uploaded_file and country:
        try:
            raw_data = pd.read_excel(uploaded_file, sheet_name="Sheet1")
            
            # Debug: Show unique countries
            if 'dsc_shop_active_country' in raw_data.columns:
                st.write("Unique countries in data:", raw_data['dsc_shop_active_country'].dropna().unique().tolist())
            
            # Column mapping
            column_mapping = {
                'cod_productset_sid': 'PRODUCT_SET_SID',
                'dsc_name': 'NAME',
                'dsc_brand_name': 'BRAND',
                'dsc_category_name': 'CATEGORY',
                'color': 'COLOR'
            }
            df = raw_data.rename(columns=column_mapping)
            
            # Check required columns
            required_columns = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'COLOR']
            if not all(col in df.columns for col in required_columns):
                st.error(f"Missing required columns: {', '.join(set(required_columns) - set(df.columns))}")
            else:
                # Filter by country
                if country != "All Countries":
                    country_code = COUNTRY_MAPPING.get(country)
                    if 'dsc_shop_active_country' not in raw_data.columns:
                        st.error("Column 'dsc_shop_active_country' not found for country filtering")
                    else:
                        df = df[df['dsc_shop_active_country'] == country_code]
                        if df.empty:
                            st.error(f"No data found for country {country} ({country_code})")
                            st.write("Available countries:", raw_data['dsc_shop_active_country'].dropna().unique().tolist())
                            st.stop()
                
                st.write(f"Rows loaded: {len(df)}")
                
                # Validate data
                invalid_df = validate_data(df)
                approved_df = df[~df['PRODUCT_SET_SID'].isin(invalid_df['PRODUCT_SET_SID'])]
                
                # Generate reports
                final_report = df.copy()
                final_report['STATUS'] = final_report['PRODUCT_SET_SID'].apply(
                    lambda x: 'APPROVED' if x in approved_df['PRODUCT_SET_SID'].values else 'REJECTED'
                )
                
                # Handle SKU overlap by keeping unique PRODUCT_SET_SID
                final_report = final_report.drop_duplicates(subset=['PRODUCT_SET_SID'], keep='first')
                
                # Display results
                st.write(f"Approved rows: {len(approved_df)}")
                st.write(f"Rejected rows: {len(invalid_df)}")
                
                # Download links
                suffix = country if country != "All Countries" else "All"
                final_excel = generate_excel_download(final_report, f"Final_Report_{suffix}.xlsx")
                rejected_excel = generate_excel_download(invalid_df, f"Rejected_{suffix}.xlsx")
                approved_excel = generate_excel_download(approved_df, f"Approved_{suffix}.xlsx")
                full_excel = generate_excel_download(df, f"Full_Data_{suffix}.xlsx")
                
                st.markdown(get_download_link(final_excel, f"Final_Report_{suffix}.xlsx", "Download Final Report"), unsafe_allow_html=True)
                st.markdown(get_download_link(rejected_excel, f"Rejected_{suffix}.xlsx", "Download Rejected Report"), unsafe_allow_html=True)
                st.markdown(get_download_link(approved_excel, f"Approved_{suffix}.xlsx", "Download Approved Report"), unsafe_allow_html=True)
                st.markdown(get_download_link(full_excel, f"Full_Data_{suffix}.xlsx", "Download Full Data"), unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
