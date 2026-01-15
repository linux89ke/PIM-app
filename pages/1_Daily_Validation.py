import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import logging
from typing import Dict, List, Tuple, Optional, Set
import traceback
import json
import xlsxwriter
import altair as alt
import time
import altair as alt
import requests
from difflib import SequenceMatcher
import zipfile
import concurrent.futures

# Import shared utilities and functions
from streamlit_app import (
    load_support_files_lazy, CountryValidator, standardize_input_data,
    validate_input_schema, filter_by_country, propagate_metadata,
    validate_products, prepare_full_data_merged, generate_smart_export,
    to_excel_flag_data, log_validation_run, clear_image_cache
)

st.title("📊 Daily Product Validation")

# Sidebar configuration
try:
    with st.sidebar:
        st.header("Performance Settings")
        use_image_hash = st.checkbox("Enable Image Hashing (for duplicate detection)", value=True,
                                    help="Disable for faster processing on large datasets")
        st.caption("⚡ Disabling image hashing speeds up processing significantly")

        if st.button("🧹 Clear Image Cache", help="Free up memory by clearing cached image hashes"):
            clear_image_cache()
            st.success("Image cache cleared!")
except:
    use_image_hash = True

# Load configuration files (lazy loading - only when needed)
support_files = load_support_files_lazy()

# Main content
country = st.selectbox("Select Country", ["Kenya", "Uganda"], key="daily_country")
country_validator = CountryValidator(country)

uploaded_files = st.file_uploader("Upload files (CSV/XLSX)", type=['csv', 'xlsx'], accept_multiple_files=True, key="daily_files")

if 'final_report' not in st.session_state: st.session_state.final_report = pd.DataFrame()
if 'all_data_map' not in st.session_state: st.session_state.all_data_map = pd.DataFrame()
if 'intersection_sids' not in st.session_state: st.session_state.intersection_sids = set()

if uploaded_files:
    current_file_signature = sorted([f.name + str(f.size) for f in uploaded_files])
    if 'last_processed_files' not in st.session_state or st.session_state.last_processed_files != current_file_signature:
        try:
            current_date = datetime.now().strftime('%Y-%m-%d')
            file_prefix = country_validator.code
            all_dfs = []
            file_sids_sets = []

            for uploaded_file in uploaded_files:
                uploaded_file.seek(0)
                try:
                    if uploaded_file.name.endswith('.xlsx'):
                        raw_data = pd.read_excel(uploaded_file, engine='openpyxl', dtype=str)
                    else:
                        try:
                            raw_data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype=str)
                            if len(raw_data.columns) <= 1:
                                uploaded_file.seek(0)
                                raw_data = pd.read_csv(uploaded_file, sep=',', encoding='ISO-8859-1', dtype=str)
                        except:
                            uploaded_file.seek(0)
                            raw_data = pd.read_csv(uploaded_file, sep=',', encoding='ISO-8859-1', dtype=str)
                    std_data = standardize_input_data(raw_data)
                    if 'PRODUCT_SET_SID' in std_data.columns:
                        file_sids_sets.append(set(std_data['PRODUCT_SET_SID'].unique()))
                    all_dfs.append(std_data)
                except Exception as e:
                    st.error(f"Failed to read file {uploaded_file.name}: {e}")
                    st.stop()

            if not all_dfs:
                st.error("No valid data loaded.")
                st.stop()

            merged_data = pd.concat(all_dfs, ignore_index=True)

            # Performance warning for large datasets
            data_size_mb = merged_data.memory_usage(deep=True).sum() / (1024 * 1024)
            if data_size_mb > 500:  # 500MB threshold
                st.warning(f"⚠️ Large dataset detected ({data_size_mb:.1f}MB). Consider disabling image hashing for faster processing.")

            st.success(f"Loaded total {len(merged_data)} rows from {len(uploaded_files)} files.")

            intersection_count = 0
            intersection_sids = set()
            if len(file_sids_sets) > 1:
                intersection_sids = set.intersection(*file_sids_sets)
                intersection_count = len(intersection_sids)

            st.session_state.intersection_sids = intersection_sids
            data_prop = propagate_metadata(merged_data)
            is_valid, errors = validate_input_schema(data_prop)

            if is_valid:
                data_filtered = filter_by_country(data_prop, country_validator, "Uploaded Files")
                data = data_filtered.drop_duplicates(subset=['PRODUCT_SET_SID'], keep='first')
                data_has_warranty_cols = all(col in data.columns for col in ['PRODUCT_WARRANTY', 'WARRANTY_DURATION'])
                for col in ['NAME', 'BRAND', 'COLOR', 'SELLER_NAME', 'CATEGORY_CODE']:
                    if col in data.columns: data[col] = data[col].astype(str).fillna('')
                if 'COLOR_FAMILY' not in data.columns: data['COLOR_FAMILY'] = ""

                # Enhanced progress indicators
                progress_container = st.container()
                with progress_container:
                    st.subheader("🔍 Validation Progress")
                    overall_progress = st.progress(0)
                    current_task = st.empty()
                    task_progress = st.progress(0)
                    stats_display = st.empty()

                current_task.text("⏳ Preparing validation engine...")
                overall_progress.progress(10)

                with st.spinner("Running comprehensive validations..."):
                    common_sids_to_pass = intersection_sids if intersection_count > 0 else None

                    # Update progress during validation
                    current_task.text("🔍 Running validation checks...")
                    overall_progress.progress(30)

                    final_report, flag_dfs = validate_products(
                        data, support_files, country_validator, data_has_warranty_cols, common_sids_to_pass, use_image_hash
                    )

                    overall_progress.progress(90)
                    current_task.text("📊 Finalizing results...")

                    st.session_state.final_report = final_report
                    st.session_state.all_data_map = data
                    st.session_state.intersection_count = intersection_count
                    st.session_state.last_processed_files = current_file_signature

                    # Clear image cache after processing to free memory
                    if not use_image_hash:
                        clear_image_cache()

                    approved_df = final_report[final_report['Status'] == 'Approved']
                    rejected_df = final_report[final_report['Status'] == 'Rejected']
                    log_validation_run(country, "Multi-Upload", len(data), len(approved_df), len(rejected_df))

                overall_progress.progress(100)
                current_task.text("✅ Validation complete!")

                # Show summary stats
                total_processed = len(data)
                approved_count = len(approved_df)
                rejected_count = len(rejected_df)
                rejection_rate = (rejected_count / total_processed * 100) if total_processed > 0 else 0

                stats_display.markdown(f"""
                **📈 Validation Summary:**
                - **Total Products:** {total_processed:,}
                - **Approved:** {approved_count:,} ({(approved_count/total_processed*100):.1f}%)
                - **Rejected:** {rejected_count:,} ({rejection_rate:.1f}%)
                - **Processing Time:** Complete
                """)

                # Clear progress indicators after a short delay
                time.sleep(1)
                progress_container.empty()
            else:
                for e in errors: st.error(e)
        except Exception as e:
            st.error(f"Error: {e}")
            st.code(traceback.format_exc())

    if not st.session_state.final_report.empty:
        final_report = st.session_state.final_report
        data = st.session_state.all_data_map
        intersection_count = st.session_state.intersection_count
        intersection_sids = st.session_state.intersection_sids
        current_date = datetime.now().strftime('%Y-%m-%d')
        file_prefix = country_validator.code

        approved_df = final_report[final_report['Status'] == 'Approved']
        rejected_df = final_report[final_report['Status'] == 'Rejected']

        st.sidebar.header("Seller Options")
        seller_opts = ['All Sellers'] + (data['SELLER_NAME'].dropna().unique().tolist() if 'SELLER_NAME' in data.columns else [])
        sel_sellers = st.sidebar.multiselect("Select Sellers", seller_opts, default=['All Sellers'])

        st.markdown("---")
        with st.container():
            st.header("Overall Results")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total", len(data))
            c2.metric("Approved", len(approved_df))
            c3.metric("Rejected", len(rejected_df))
            rt = (len(rejected_df)/len(data)*100) if len(data)>0 else 0
            c4.metric("Rate", f"{rt:.1f}%")
            c5.metric("SKUs in Both Files", intersection_count)

        if intersection_count > 0:
            common_skus_df = data[data['PRODUCT_SET_SID'].isin(intersection_sids)]
            csv_buffer = BytesIO()
            common_skus_df.to_csv(csv_buffer, index=False)
            st.download_button(label=f"📥 Download Common SKUs ({intersection_count})", data=csv_buffer.getvalue(), file_name=f"{file_prefix}_Common_SKUs_{current_date}.csv", mime="text/csv")

        st.subheader("Validation Results by Flag")
        active_flags = rejected_df['FLAG'].unique()
        display_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY', 'COLOR', 'PARENTSKU', 'SELLER_NAME']

        for title in active_flags:
            df_flagged_report = rejected_df[rejected_df['FLAG'] == title]
            df_display = pd.merge(df_flagged_report[['ProductSetSid']], data, left_on='ProductSetSid', right_on='PRODUCT_SET_SID', how='left')
            df_display = df_display[[c for c in display_cols if c in df_display.columns]]

            with st.expander(f"{title} ({len(df_display)})"):
                col1, col2 = st.columns([1, 1])
                with col1: search_term = st.text_input(f"🔍 Search {title}", placeholder="Name, Brand, or SKU...", key=f"search_{title}")
                with col2:
                    all_sellers = sorted(df_display['SELLER_NAME'].astype(str).unique())
                    seller_filter = st.multiselect(f"🏪 Filter Seller ({title})", all_sellers, key=f"filter_{title}")

                if search_term:
                    mask = df_display.apply(lambda x: x.astype(str).str.contains(search_term, case=False).any(), axis=1)
                    df_display = df_display[mask]
                if seller_filter: df_display = df_display[df_display['SELLER_NAME'].isin(seller_filter)]
                if len(df_display) != len(df_flagged_report): st.caption(f"Showing {len(df_display)} of {len(df_flagged_report)} rows")

                select_all_mode = st.checkbox("Select All", key=f"sa_{title}")
                df_display.insert(0, "Select", select_all_mode)

                edited_df = st.data_editor(df_display, hide_index=True, use_container_width=True, column_config={"Select": st.column_config.CheckboxColumn(required=True)}, disabled=[c for c in df_display.columns if c != "Select"], key=f"editor_{title}_{select_all_mode}")

                to_approve = edited_df[edited_df['Select'] == True]['PRODUCT_SET_SID'].tolist()
                if to_approve:
                    if st.button(f"✅ Approve {len(to_approve)} Selected Items", key=f"btn_{title}"):
                        st.session_state.final_report.loc[st.session_state.final_report['ProductSetSid'].isin(to_approve), ['Status', 'Reason', 'Comment', 'FLAG']] = ['Approved', '', '', 'Approved by User']
                        st.success("Updated! Rerunning to refresh...")
                        st.rerun()

                flag_export_df = pd.merge(df_flagged_report[['ProductSetSid']], data, left_on='ProductSetSid', right_on='PRODUCT_SET_SID', how='left')
                st.download_button(f"📥 Export {title} Data", to_excel_flag_data(flag_export_df, title), f"{file_prefix}_{title}.xlsx")

        st.markdown("---")
        st.header("Overall Exports")
        full_data_merged = prepare_full_data_merged(data, final_report)
        final_rep_data, final_rep_name, final_rep_mime = generate_smart_export(final_report, f"{file_prefix}_Final_Report_{current_date}", 'simple', support_files['reasons'])
        rej_data, rej_name, rej_mime = generate_smart_export(rejected_df, f"{file_prefix}_Rejected_{current_date}", 'simple', support_files['reasons'])
        app_data, app_name, app_mime = generate_smart_export(approved_df, f"{file_prefix}_Approved_{current_date}", 'simple', support_files['reasons'])
        full_data, full_name, full_mime = generate_smart_export(full_data_merged, f"{file_prefix}_Full_Data_{current_date}", 'full')

        c1, c2, c3, c4 = st.columns(4)
        c1.download_button("Final Report", final_rep_data, final_rep_name, mime=final_rep_mime)
        c2.download_button("Rejected", rej_data, rej_name, mime=rej_mime)
        c3.download_button("Approved", app_data, app_name, mime=app_mime)
        c4.download_button("Full Data", full_data, full_name, mime=full_mime)