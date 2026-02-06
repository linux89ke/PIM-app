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
import zipfile
import os
from dataclasses import dataclass

# -------------------------------------------------
# CONSTANTS & MAPPING
# -------------------------------------------------
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]
REJECTION_REASONS_COLS = ['CODE - REJECTION_REASON', 'COMMENT']

FULL_DATA_COLS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE",
    "COLOR", "COLOR_FAMILY", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU",
    "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG", "LISTING_STATUS", 
    "PRODUCT_WARRANTY", "WARRANTY_DURATION", "WARRANTY_ADDRESS", "WARRANTY_TYPE"
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
    'image1': 'MAIN_IMAGE'
}

# -------------------------------------------------
# UTILITIES & REASON MAPPING
# -------------------------------------------------
@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    return {
        'Restricted brands': ('1000024 - Not Authorized', "Product requires a license to be sold."),
        'Suspected Fake product': ('1000023 - Counterfeit', "Jumia technical team confirmed counterfeit."),
        'Poor Image Quality': ('1000002 - Poor Image Quality', "Image is blurred, has watermarks, or poor resolution."),
        'Wrong Category': ('1000003 - Wrong Category', "The product is listed in the incorrect category."),
        'Duplicate product': ('1000007 - Other Reason', "This product is a duplicate."),
        'Unnecessary words in NAME': ('1000008 - Name Improvement', "Format: Name – Type – Color."),
        'Missing COLOR': ('1000005 - Confirm Color', "Color missing in title or attributes.")
    }

def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()
    map_lower = {k.lower(): v for k, v in NEW_FILE_MAPPING.items()}
    new_cols = {}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in map_lower:
            new_cols[col] = map_lower[col_lower]
        else:
            new_cols[col] = col.upper()
    df = df.rename(columns=new_cols)
    return df

# -------------------------------------------------
# UI CONFIGURATION
# -------------------------------------------------
st.set_page_config(page_title="Product Validation Pro", layout="wide")

# Initialize Session States
if 'final_report' not in st.session_state: st.session_state.final_report = pd.DataFrame()
if 'all_data_map' not in st.session_state: st.session_state.all_data_map = pd.DataFrame()
if 'image_review_decisions' not in st.session_state: st.session_state.image_review_decisions = {}

# -------------------------------------------------
# SIDEBAR & UPLOAD
# -------------------------------------------------
with st.sidebar:
    st.title("⚙️ QC Settings")
    country = st.selectbox("Market", ["Kenya", "Uganda"])
    if st.button("🗑️ Clear All Progress"):
        st.session_state.clear()
        st.rerun()

st.title("🚀 Product Validation & Image Review")
uploaded_files = st.file_uploader("Upload Batch Files", type=['csv', 'xlsx'], accept_multiple_files=True)

# -------------------------------------------------
# DATA PROCESSING
# -------------------------------------------------
if uploaded_files:
    current_sig = sorted([f.name + str(f.size) for f in uploaded_files])
    if 'last_sig' not in st.session_state or st.session_state.last_sig != current_sig:
        with st.spinner("Processing files..."):
            all_dfs = []
            for f in uploaded_files:
                f.seek(0)
                df = pd.read_excel(f, dtype=str) if f.name.endswith('.xlsx') else pd.read_csv(f, dtype=str)
                all_dfs.append(standardize_input_data(df))
            
            combined = pd.concat(all_dfs, ignore_index=True).drop_duplicates(subset=['PRODUCT_SET_SID'])
            st.session_state.all_data_map = combined
            
            # MOCK VALIDATION: In your real app, call your check_duplicate_products etc.
            # For this full code, we pre-approve everything to allow for manual review.
            report_rows = []
            for _, row in combined.iterrows():
                report_rows.append({
                    'ProductSetSid': row['PRODUCT_SET_SID'],
                    'ParentSKU': row.get('PARENTSKU', ''),
                    'Status': 'Approved',
                    'Reason': '',
                    'Comment': '',
                    'FLAG': '',
                    'SellerName': row.get('SELLER_NAME', '')
                })
            
            st.session_state.final_report = pd.DataFrame(report_rows)
            st.session_state.image_review_decisions = {}
            st.session_state.last_sig = current_sig
            st.rerun()

# -------------------------------------------------
# DASHBOARD & IMAGE REVIEW
# -------------------------------------------------
if not st.session_state.final_report.empty:
    report = st.session_state.final_report
    source_data = st.session_state.all_data_map
    
    approved = report[report['Status'] == 'Approved']
    rejected = report[report['Status'] == 'Rejected']

    # --- Metrics ---
    m1, m2, m3 = st.columns(3)
    m1.metric("Total SKUs", len(source_data))
    m2.metric("✅ Approved", len(approved))
    m3.metric("❌ Rejected", len(rejected))

    # -------------------------------------------------
    # 🖼️ IMAGE REVIEW SECTION (FIXED)
    # -------------------------------------------------
    st.markdown("---")
    st.subheader("🖼️ Visual Quality Review")
    
    # Merge for images
    review_data = pd.merge(approved[['ProductSetSid']], source_data, left_on='ProductSetSid', right_on='PRODUCT_SET_SID', how='left')
    
    if 'MAIN_IMAGE' in review_data.columns:
        # Filter rows with actual image data
        valid_items = review_data[review_data['MAIN_IMAGE'].notna()].copy()
        
        if not valid_items.empty:
            with st.expander(f"📸 Review Approved Images ({len(valid_items)} total)", expanded=True):
                # Pagination
                items_per_pg = 12
                total_pgs = max(1, (len(valid_items) - 1) // items_per_pg + 1)
                pg = st.number_input("Page", 1, total_pgs, 1, key="img_pg")
                
                start_idx, end_idx = (pg-1)*items_per_pg, pg*items_per_pg
                curr_page_data = valid_items.iloc[start_idx:end_idx]

                # GRID DISPLAY (3 per row)
                
                grid = st.columns(3)
                for i, (_, row) in enumerate(curr_page_data.iterrows()):
                    with grid[i % 3]:
                        sid = str(row['PRODUCT_SET_SID'])
                        img_val = row['MAIN_IMAGE']
                        
                        # --- SAFE IMAGE LOADING BLOCK ---
                        is_valid_url = isinstance(img_val, str) and img_val.lower().startswith('http')
                        
                        if is_valid_url:
                            try:
                                st.image(img_val, use_container_width=True)
                                # Zoom/Pop-out
                                with st.popover("🔍 Zoom"):
                                    st.image(img_val, caption=f"Full View: {sid}")
                            except:
                                st.error("⚠️ Loading error")
                        else:
                            st.warning("🚫 No Image Link")
                        
                        st.write(f"**{row.get('NAME', 'No Name')[:40]}**")
                        
                        # Checkboxes
                        col1, col2 = st.columns(2)
                        with col1:
                            poor = st.checkbox("Poor Quality", key=f"p_{sid}_{pg}")
                        with col2:
                            wrong = st.checkbox("Wrong Cat", key=f"w_{sid}_{pg}")
                        
                        if poor or wrong:
                            st.session_state.image_review_decisions[sid] = "Poor Image Quality" if poor else "Wrong Category"
                        elif sid in st.session_state.image_review_decisions:
                            del st.session_state.image_review_decisions[sid]

                # --- Apply Actions ---
                if st.session_state.image_review_decisions:
                    st.divider()
                    st.warning(f"You have {len(st.session_state.image_review_decisions)} pending rejections.")
                    if st.button("🔥 Move Selected to Rejections", type="primary"):
                        flags_map = load_flags_mapping()
                        for sid, ftype in st.session_state.image_review_decisions.items():
                            info = flags_map.get(ftype)
                            mask = st.session_state.final_report['ProductSetSid'] == sid
                            st.session_state.final_report.loc[mask, ['Status', 'Reason', 'Comment', 'FLAG']] = ['Rejected', info[0], info[1], ftype]
                        
                        st.session_state.image_review_decisions = {}
                        st.success("Updated Successfully!")
                        st.rerun()

    # -------------------------------------------------
    # 📥 FINAL EXPORT SECTION
    # -------------------------------------------------
    st.markdown("---")
    st.header("📥 Final Batch Export")
    
    col_ex1, col_ex2 = st.columns(2)
    
    with col_ex1:
        # Full Report
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            st.session_state.final_report.to_excel(writer, index=False, sheet_name='ProductSets')
        st.download_button("Download QC Report (.xlsx)", output.getvalue(), f"QC_Report_{datetime.now().strftime('%H%M')}.xlsx")

    with col_ex2:
        # Rejection only
        rejected_only = st.session_state.final_report[st.session_state.final_report['Status'] == 'Rejected']
        if not rejected_only.empty:
            csv = rejected_only.to_csv(index=False)
            st.download_button("Download Rejections Only (.csv)", csv, "rejections.csv", "text/csv")
        else:
            st.info("No rejections to export yet.")
