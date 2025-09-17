import streamlit as st
import pandas as pd
import io
import base64
import re
from datetime import datetime
from utils import load_config_files, validate_products, to_excel, to_excel_full_data, to_excel_flag_data, get_download_link, parse_sellers_data_sheet, extract_date_from_filename
from data_lake import data_lake_tab

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# Initialize app
st.title("Product Validation Tool")

# Load configuration files
config_data = load_config_files()
book_category_codes = config_data.get('books_cat', pd.DataFrame())['CategoryCode'].astype(str).tolist() if not config_data.get('books_cat', pd.DataFrame()).empty else []
sensitive_brand_words = config_data.get('sensitive_brands', pd.DataFrame())['BrandWords'].astype(str).tolist() if not config_data.get('sensitive_brands', pd.DataFrame()).empty else []
approved_book_sellers = config_data.get('approved_sellers', pd.DataFrame())['SellerName'].astype(str).tolist() if not config_data.get('approved_sellers', pd.DataFrame()).empty else []
perfume_category_codes = config_data.get('perfume_cat', [])
reasons_df = config_data.get('reasons', pd.DataFrame())

# Debug: Show valid colors
st.write("Valid colors from colors.txt:", config_data.get('valid_colors', []))

# SKU overlap tracking
if 'daily_data' not in st.session_state:
    st.session_state['daily_data'] = None
if 'lake_data' not in st.session_state:
    st.session_state['lake_data'] = None

# Tabs
tab1, tab2, tab3 = st.tabs(["Daily Validation", "Weekly Analysis", "Data Lake"])

# Daily Validation Tab
with tab1:
    st.header("Daily Validation")
    country = st.selectbox("Select Country", ["Kenya", "Uganda"], key="daily_country")
    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"], key="daily_file")
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype={'PRODUCT_SET_SID': str, 'CATEGORY_CODE': str, 'PARENTSKU': str})
            st.session_state['daily_data'] = df
            required_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'CATEGORY_CODE', 'COLOR', 'SELLER_NAME', 'PARENTSKU']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                st.error(f"Missing columns: {', '.join(missing_cols)}")
            else:
                df = df[df['ACTIVE_STATUS_COUNTRY'] == country[:2]]
                if df.empty:
                    st.error(f"No data for {country}")
                else:
                    # Check SKU overlap
                    if st.session_state['lake_data'] is not None:
                        overlap = set(df['PRODUCT_SET_SID']).intersection(set(st.session_state['lake_data']['cod_productset_sid']))
                        if overlap:
                            st.warning(f"Found {len(overlap)} overlapping SKUs with Data Lake file.")
                    
                    final_report, validation_results = validate_products(df, config_data, book_category_codes, sensitive_brand_words, approved_book_sellers, perfume_category_codes, country)
                    approved_df = final_report[final_report['Status'] == 'Approved']
                    rejected_df = final_report[final_report['Status'] == 'Rejected']
                    
                    st.write(f"Total Products: {len(df)}")
                    st.write(f"Approved: {len(approved_df)}")
                    st.write(f"Rejected: {len(rejected_df)}")
                    
                    # Seller filtering
                    seller_options = ['All Sellers'] + list(df['SELLER_NAME'].dropna().unique())
                    selected_sellers = st.sidebar.multiselect("Select Sellers", seller_options, default=['All Sellers'], key="daily_sellers")
                    if 'All Sellers' not in selected_sellers:
                        filtered_df = df[df['SELLER_NAME'].isin(selected_sellers)]
                        filtered_report = final_report[final_report['ProductSetSid'].isin(filtered_df['PRODUCT_SET_SID'])]
                        seller_label = "_".join(s.replace(" ", "_") for s in selected_sellers)
                    else:
                        filtered_df = df
                        filtered_report = final_report
                        seller_label = "All_Sellers"
                    
                    # Downloads
                    file_prefix = country[:2]
                    current_date = datetime.now().strftime("%Y-%m-%d")
                    final_excel = to_excel(filtered_report, reasons_df)
                    rejected_excel = to_excel(filtered_report[filtered_report['Status'] == 'Rejected'], reasons_df)
                    approved_excel = to_excel(filtered_report[final_report['Status'] == 'Approved'], reasons_df)
                    full_excel = to_excel_full_data(filtered_df, filtered_report)
                    
                    st.markdown(get_download_link(final_excel, f"{file_prefix}_Final_Report_{current_date}_{seller_label}.xlsx", "Download Final Report"), unsafe_allow_html=True)
                    st.markdown(get_download_link(rejected_excel, f"{file_prefix}_Rejected_{current_date}_{seller_label}.xlsx", "Download Rejected Report"), unsafe_allow_html=True)
                    st.markdown(get_download_link(approved_excel, f"{file_prefix}_Approved_{current_date}_{seller_label}.xlsx", "Download Approved Report"), unsafe_allow_html=True)
                    st.markdown(get_download_link(full_excel, f"{file_prefix}_Full_Data_{current_date}_{seller_label}.xlsx", "Download Full Data"), unsafe_allow_html=True)
                    
                    for title, df_flagged in validation_results.items():
                        with st.expander(f"{title} ({len(df_flagged)} products)"):
                            st.dataframe(df_flagged)
                            flag_excel = to_excel_flag_data(df_flagged, title)
                            st.markdown(get_download_link(flag_excel, f"{file_prefix}_{title.replace(' ', '_')}_{current_date}.xlsx", f"Download {title} Data"), unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error processing CSV: {e}")

# Weekly Analysis Tab
with tab2:
    st.header("Weekly Analysis")
    uploaded_files = st.file_uploader("Upload Excel files", type=['xlsx'], accept_multiple_files=True, key="weekly_files")
    
    if uploaded_files:
        all_sellers, all_categories, all_reasons, dates = [], [], [], []
        for file in uploaded_files:
            date = extract_date_from_filename(file.name)
            if date:
                try:
                    sellers_sheet = pd.read_excel(file, sheet_name='Sellers Data', header=None)
                    sellers_df, categories_df, reasons_df = parse_sellers_data_sheet(sellers_sheet, date)
                    if not sellers_df.empty:
                        all_sellers.append(sellers_df)
                    if not categories_df.empty:
                        all_categories.append(categories_df)
                    if not reasons_df.empty:
                        all_reasons.append(reasons_df)
                    dates.append(date)
                except Exception as e:
                    st.error(f"Error reading {file.name}: {e}")
        
        if all_sellers or all_categories or all_reasons:
            st.success(f"Parsed {len(dates)} files: {sorted(set(dates))}")
            
            if all_sellers:
                weekly_sellers = pd.concat(all_sellers).groupby('Seller')['Rejected Products'].sum().reset_index()
                weekly_sellers = weekly_sellers.sort_values('Rejected Products', ascending=False).head(5)
                weekly_sellers['Percentage'] = (weekly_sellers['Rejected Products'] / weekly_sellers['Rejected Products'].sum() * 100).round(1)
                st.subheader("Top 5 Sellers by Rejected Products")
                st.dataframe(weekly_sellers)
                st.markdown("**Chart: Top 5 Sellers**")
                st.json({
                    "type": "bar",
                    "data": {
                        "labels": weekly_sellers['Seller'].tolist(),
                        "datasets": [{
                            "label": "Rejected Products",
                            "data": weekly_sellers['Rejected Products'].tolist(),
                            "backgroundColor": ["#4CAF50", "#2196F3", "#FFC107", "#F44336", "#9C27B0"],
                            "borderColor": ["#388E3C", "#1976D2", "#FFA000", "#D32F2F", "#7B1FA2"],
                            "borderWidth": 1
                        }]
                    },
                    "options": {
                        "scales": {
                            "y": {"beginAtZero": True, "title": {"display": True, "text": "Rejected Products"}},
                            "x": {"title": {"display": True, "text": "Seller"}}
                        }
                    }
                }, expanded=False)
            
            if all_categories:
                weekly_categories = pd.concat(all_categories).groupby('Category')['Rejected Products'].sum().reset_index()
                weekly_categories = weekly_categories.sort_values('Rejected Products', ascending=False).head(5)
                weekly_categories['Percentage'] = (weekly_categories['Rejected Products'] / weekly_categories['Rejected Products'].sum() * 100).round(1)
                st.subheader("Top 5 Categories by Rejected Products")
                st.dataframe(weekly_categories)
                st.markdown("**Chart: Top 5 Categories**")
                st.json({
                    "type": "bar",
                    "data": {
                        "labels": weekly_categories['Category'].tolist(),
                        "datasets": [{
                            "label": "Rejected Products",
                            "data": weekly_categories['Rejected Products'].tolist(),
                            "backgroundColor": ["#4CAF50", "#2196F3", "#FFC107", "#F44336", "#9C27B0"],
                            "borderColor": ["#388E3C", "#1976D2", "#FFA000", "#D32F2F", "#7B1FA2"],
                            "borderWidth": 1
                        }]
                    },
                    "options": {
                        "scales": {
                            "y": {"beginAtZero": True, "title": {"display": True, "text": "Rejected Products"}},
                            "x": {"title": {"display": True, "text": "Category"}}
                        }
                    }
                }, expanded=False)
            
            if all_reasons:
                weekly_reasons = pd.concat(all_reasons).groupby('Rejection Reason')['Rejected Products'].sum().reset_index()
                weekly_reasons = weekly_reasons.sort_values('Rejected Products', ascending=False).head(5)
                weekly_reasons['Percentage'] = (weekly_reasons['Rejected Products'] / weekly_reasons['Rejected Products'].sum() * 100).round(1)
                st.subheader("Top 5 Rejection Reasons")
                st.dataframe(weekly_reasons)
                st.markdown("**Chart: Top 5 Rejection Reasons**")
                st.json({
                    "type": "bar",
                    "data": {
                        "labels": weekly_reasons['Rejection Reason'].tolist(),
                        "datasets": [{
                            "label": "Rejected Products",
                            "data": weekly_reasons['Rejected Products'].tolist(),
                            "backgroundColor": ["#4CAF50", "#2196F3", "#FFC107", "#F44336", "#9C27B0"],
                            "borderColor": ["#388E3C", "#1976D2", "#FFA000", "#D32F2F", "#7B1FA2"],
                            "borderWidth": 1
                        }]
                    },
                    "options": {
                        "scales": {
                            "y": {"beginAtZero": True, "title": {"display": True, "text": "Rejected Products"}},
                            "x": {"title": {"display": True, "text": "Rejection Reason"}}
                        }
                    }
                }, expanded=False)
            
            if len(set(dates)) > 1 and all_sellers:
                daily_trend = pd.concat(all_sellers).groupby('Date')['Rejected Products'].sum().reset_index()
                st.subheader("Daily Rejection Trend")
                st.json({
                    "type": "line",
                    "data": {
                        "labels": daily_trend['Date'].astype(str).tolist(),
                        "datasets": [{
                            "label": "Rejected Products",
                            "data": daily_trend['Rejected Products'].tolist(),
                            "fill": False,
                            "borderColor": "#2196F3",
                            "tension": 0.1
                        }]
                    },
                    "options": {
                        "scales": {
                            "y": {"beginAtZero": True, "title": {"display": True, "text": "Rejected Products"}},
                            "x": {"title": {"display": True, "text": "Date"}}
                        }
                    }
                }, expanded=False)
            
            st.subheader("Deep Analysis")
            total_rejections = pd.concat(all_sellers)['Rejected Products'].sum() if all_sellers else 0
            if total_rejections:
                avg_daily_rej = total_rejections / len(set(dates))
                st.metric("Total Weekly Rejections", total_rejections)
                st.metric("Average Daily Rejections", f"{avg_daily_rej:.1f}")
                if not weekly_sellers.empty:
                    st.info(f"Top seller '{weekly_sellers.iloc[0]['Seller']}' accounts for {weekly_sellers.iloc[0]['Percentage']}% of rejections.")
                if not weekly_categories.empty:
                    st.info(f"Top category '{weekly_categories.iloc[0]['Category']}' has {weekly_categories.iloc[0]['Percentage']}% of rejections.")
                if not weekly_reasons.empty:
                    st.info(f"Top reason '{weekly_reasons.iloc[0]['Rejection Reason']}' drives {weekly_reasons.iloc[0]['Percentage']}% of issues.")
            
            st.subheader("Recommendations")
            recs = []
            if not weekly_sellers.empty:
                recs.append(f"Train top sellers ({', '.join(weekly_sellers.head(3)['Seller'])}) on listing practices.")
            if not weekly_categories.empty:
                recs.append(f"Create guidelines for categories ({', '.join(weekly_categories.head(3)['Category'])}).")
            if not weekly_reasons.empty:
                recs.append(f"Automate checks for '{weekly_reasons.iloc[0]['Rejection Reason']}'.")
            if total_rejections > 0 and avg_daily_rej > 50:
                recs.append("High rejection rate (>50/day); conduct platform audit.")
            else:
                recs.append("Rejections stable; focus on seller support.")
            for rec in recs:
                st.write(f"• {rec}")
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                if not weekly_sellers.empty:
                    weekly_sellers.to_excel(writer, sheet_name='Top Sellers', index=False)
                if not weekly_categories.empty:
                    weekly_categories.to_excel(writer, sheet_name='Top Categories', index=False)
                if not weekly_reasons.empty:
                    weekly_reasons.to_excel(writer, sheet_name='Top Reasons', index=False)
            output.seek(0)
            st.download_button(
                label="Download Weekly Report",
                data=output,
                file_name=f"Weekly_Analysis_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# Data Lake Tab
with tab3:
    data_lake_tab(config_data, book_category_codes, sensitive_brand_words, approved_book_sellers, perfume_category_codes, reasons_df)
