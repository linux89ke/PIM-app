import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import logging
from typing import Dict, List, Tuple, Optional
import traceback
import json

# -------------------------------------------------
# Page config
# -------------------------------------------------
st.set_page_config(page_title="Product Validation Tool", layout="wide")

# -------------------------------------------------
# Constants & Mapping
# -------------------------------------------------
VISIBLE_COLUMNS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", 
    "CATEGORY", "CATEGORY_CODE", "COLOR", "MAIN_IMAGE", 
    "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU"
]

NEW_FILE_MAPPING = {
    'cod_productset_sid': 'PRODUCT_SET_SID',
    'dsc_name': 'NAME',
    'dsc_brand_name': 'BRAND',
    'cod_category_code': 'CATEGORY_CODE',
    'dsc_category_name': 'CATEGORY',
    'dsc_shop_seller_name': 'SELLER_NAME',
    'dsc_shop_active_country': 'ACTIVE_STATUS_COUNTRY',
    'cod_parent_sku': 'PARENTSKU',
    'color': 'COLOR',
    'color_family': 'COLOR_FAMILY',
    'list_seller_skus': 'SELLER_SKU',
    'image1': 'MAIN_IMAGE',
    'product_warranty': 'PRODUCT_WARRANTY',
    'warranty_duration': 'WARRANTY_DURATION'
}

# -------------------------------------------------
# Data Helpers
# -------------------------------------------------
def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    df = df.rename(columns=NEW_FILE_MAPPING)
    if 'ACTIVE_STATUS_COUNTRY' in df.columns:
        df['ACTIVE_STATUS_COUNTRY'] = (
            df['ACTIVE_STATUS_COUNTRY'].astype(str).str.lower()
            .str.replace('jumia-', '', regex=False).str.strip().str.upper()
        )
    return df

@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    return {
        'Seller Not approved to sell Refurb': ('1000028', "Confirm possibility of sale for Refurbished items."),
        'BRAND name repeated in NAME': ('1000002', "Brand name should not be repeated in Product Name."),
        'Missing COLOR': ('1000005', "Clearly mention color in title and attributes."),
        'Duplicate product': ('1000007', "Kindly avoid creating duplicate SKUs."),
        'Prohibited products': ('1000024', "Product is not authorized for sale."),
        'Single-word NAME': ('1000008', "Improve Name: Use Name – Type – Color format."),
        'Unnecessary words in NAME': ('1000008', "Remove unnecessary filler words."),
        'Generic BRAND Issues': ('1000014', "Request brand creation via the official form."),
        'Counterfeit Sneakers': ('1000030', "Suspected counterfeit/fake product."),
        'Product Warranty': ('1000013', "Valid warranty details required for this category."),
        'Suspected Fake product': ('1000030', "Price logic indicates suspected fake product.")
    }

# -------------------------------------------------
# Simple Validation Mock (Replace with your logic)
# -------------------------------------------------
def run_validations(data, support_mapping):
    # This is a placeholder for your existing validation functions
    # It returns a dictionary of dataframes keyed by flag name
    flag_dfs = {}
    
    # Example logic: Flag "Generic" brands
    if 'BRAND' in data.columns:
        generic = data[data['BRAND'].astype(str).str.lower() == 'generic']
        if not generic.empty:
            flag_dfs['Generic BRAND Issues'] = generic

    # Example logic: Flag single word names
    if 'NAME' in data.columns:
        single_word = data[data['NAME'].astype(str).str.split().str.len() == 1]
        if not single_word.empty:
            flag_dfs['Single-word NAME'] = single_word

    return flag_dfs

# -------------------------------------------------
# Main App
# -------------------------------------------------
def main():
    # Session State for Overrides
    if 'manual_approvals' not in st.session_state:
        st.session_state.manual_approvals = set()

    st.title("Product Validation Tool")
    
    # Load Initial Mappings
    if 'flags_map' not in st.session_state:
        st.session_state.flags_map = load_flags_mapping()

    # SIDEBAR CONFIG
    st.sidebar.header("Settings")
    country = st.sidebar.selectbox("Country", ["Kenya", "Uganda"])
    
    # REJECTION REASON EDITOR
    with st.expander("⚙️ Edit Rejection Reasons & Seller Comments"):
        updated_map = {}
        for flag, (code, comm) in st.session_state.flags_map.items():
            c1, c2 = st.columns([1, 2])
            new_code = c1.text_input(f"Code: {flag}", value=code, key=f"code_{flag}")
            new_comm = c2.text_area(f"Comment: {flag}", value=comm, key=f"comm_{flag}", height=68)
            updated_map[flag] = (new_code, new_comm)
        st.session_state.flags_map = updated_map

    # FILE UPLOAD
    uploaded_files = st.file_uploader("Upload PIM Exports (CSV/XLSX)", type=['csv', 'xlsx'], accept_multiple_files=True)

    if uploaded_files:
        all_dfs = []
        for f in uploaded_files:
            try:
                if f.name.endswith('.xlsx'):
                    df = pd.read_excel(f, engine='openpyxl', dtype=str)
                else:
                    f.seek(0)
                    # Robust CSV reading: auto-detect separator
                    df = pd.read_csv(f, sep=None, engine='python', encoding='ISO-8859-1', dtype=str)
                all_dfs.append(standardize_input_data(df))
            except Exception as e:
                st.error(f"Error reading {f.name}: {e}")

        if all_dfs:
            data = pd.concat(all_dfs, ignore_index=True).drop_duplicates(subset=['PRODUCT_SET_SID'])
            st.success(f"Total Rows Loaded: {len(data)}")

            # RUN VALIDATIONS
            flag_results = run_validations(data, st.session_state.flags_map)

            # GLOBAL SEARCH
            search_query = st.text_input("🔍 Global Search", placeholder="Filter by SID, Seller, or Brand...").lower()

            # QC METRICS
            total_rej = sum(len(df) for df in flag_results.values())
            overridden = len(st.session_state.manual_approvals)
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Initial Flags", total_rej)
            m2.metric("Manual Overrides", overridden)
            m3.metric("Pending Rejections", max(0, total_rej - overridden))

            # FLAG DISPLAY LOOP
            st.header("Validation Results")
            for flag_name, df_flagged in flag_results.items():
                # Filter out manual approvals
                df_remaining = df_flagged[~df_flagged['PRODUCT_SET_SID'].isin(st.session_state.manual_approvals)]
                
                # Apply search filter
                if search_query:
                    mask = df_remaining.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
                    df_display = df_remaining[mask].copy()
                else:
                    df_display = df_remaining.copy()

                with st.expander(f"{flag_name} ({len(df_display)})"):
                    if not df_display.empty:
                        # Prepare Editor
                        df_display.insert(0, "Approve?", False)
                        cols_to_show = ["Approve?"] + [c for c in VISIBLE_COLUMNS if c in df_display.columns]
                        
                        edited_df = st.data_editor(
                            df_display[cols_to_show],
                            column_config={
                                "Approve?": st.column_config.CheckboxColumn("QC Pass"),
                                "MAIN_IMAGE": st.column_config.ImageColumn("Image")
                            },
                            disabled=[c for c in cols_to_show if c != "Approve?"],
                            hide_index=True,
                            key=f"editor_{flag_name}"
                        )

                        # Logic to confirm approvals
                        if st.button(f"Confirm Bulk Approval for {flag_name}", key=f"btn_{flag_name}"):
                            newly_approved = edited_df[edited_df["Approve?"] == True]["PRODUCT_SET_SID"].tolist()
                            if newly_approved:
                                st.session_state.manual_approvals.update(newly_approved)
                                st.rerun()
                    else:
                        st.success("No products found in this category.")

            # FINAL REPORT GENERATION
            st.divider()
            st.header("Final Exports")
            
            # Re-generate final report based on current session state
            report_rows = []
            for _, row in data.iterrows():
                sid = row['PRODUCT_SET_SID']
                status = "Approved"
                reason = ""
                comment = ""
                flag_found = ""
                
                # Check which flag this SID belongs to (prioritize first flag found)
                for f_name, f_df in flag_results.items():
                    if sid in f_df['PRODUCT_SET_SID'].values:
                        if sid in st.session_state.manual_approvals:
                            status = "Approved"
                            comment = "QC Override"
                        else:
                            status = "Rejected"
                            reason_info = st.session_state.flags_map.get(f_name, ("-", "-"))
                            reason = reason_info[0]
                            comment = reason_info[1]
                            flag_found = f_name
                        break
                
                report_rows.append({
                    "ProductSetSid": sid,
                    "Status": status,
                    "Reason": reason,
                    "Comment": comment,
                    "FLAG": flag_found,
                    "SellerName": row.get("SELLER_NAME", "")
                })

            final_report_df = pd.DataFrame(report_rows)
            
            c1, c2, c3 = st.columns(3)
            c1.download_button("📥 Final Validation Report", final_report_df.to_csv(index=False), "Final_Report.csv", "text/csv")
            
            # Reset Button
            if st.sidebar.button("🗑️ Reset All Overrides"):
                st.session_state.manual_approvals.clear()
                st.rerun()

if __name__ == "__main__":
    main()
