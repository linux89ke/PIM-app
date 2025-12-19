import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import traceback

# -------------------------------------------------
# Page config
# -------------------------------------------------
st.set_page_config(page_title="Product Validation Tool", layout="wide")

# -------------------------------------------------
# 1. Constants & Schema Mapping
# -------------------------------------------------
# These are the columns shown in the Streamlit UI
VISIBLE_COLUMNS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", 
    "CATEGORY", "CATEGORY_CODE", "COLOR", "MAIN_IMAGE", 
    "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU"
]

# The mapping handles lowercase keys to be case-insensitive
COLUMN_MAPPING = {
    'cod_productset_sid': 'PRODUCT_SET_SID',
    'product_set_sid': 'PRODUCT_SET_SID',
    'sid': 'PRODUCT_SET_SID',
    'dsc_name': 'NAME',
    'name': 'NAME',
    'dsc_brand_name': 'BRAND',
    'brand': 'BRAND',
    'cod_category_code': 'CATEGORY_CODE',
    'dsc_category_name': 'CATEGORY',
    'dsc_shop_seller_name': 'SELLER_NAME',
    'seller_name': 'SELLER_NAME',
    'dsc_shop_active_country': 'ACTIVE_STATUS_COUNTRY',
    'active_status_country': 'ACTIVE_STATUS_COUNTRY',
    'cod_parent_sku': 'PARENTSKU',
    'parentsku': 'PARENTSKU',
    'color': 'COLOR',
    'image1': 'MAIN_IMAGE',
    'main_image': 'MAIN_IMAGE',
    'list_seller_skus': 'SELLER_SKU',
    'seller_sku': 'SELLER_SKU'
}

# -------------------------------------------------
# 2. Data Processing Helpers
# -------------------------------------------------
def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    """Standardizes column names and cleans country codes."""
    df = df.copy()
    # Normalize headers to lowercase to match COLUMN_MAPPING keys
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.rename(columns=COLUMN_MAPPING)
    
    if 'ACTIVE_STATUS_COUNTRY' in df.columns:
        df['ACTIVE_STATUS_COUNTRY'] = (
            df['ACTIVE_STATUS_COUNTRY'].astype(str).str.lower()
            .str.replace('jumia-', '', regex=False).str.strip().str.upper()
        )
    return df

@st.cache_data(ttl=3600)
def load_default_flags():
    """Initial baseline for rejection reasons."""
    return {
        'Seller Not approved to sell Refurb': ('1000028', "Contact Seller Support for Refurb authorization."),
        'BRAND name repeated in NAME': ('1000002', "Brand Name should not be inside Product Name."),
        'Missing COLOR': ('1000005', "Color must be clearly mentioned in Title and Attributes."),
        'Duplicate product': ('1000007', "Duplicate SKUs detected."),
        'Prohibited products': ('1000024', "Product is unauthorized for sale on Jumia."),
        'Single-word NAME': ('1000008', "Product Name must follow: Name – Type – Color."),
        'Generic BRAND Issues': ('1000014', "Request brand creation via: https://bit.ly/2kpjja8"),
        'Counterfeit Sneakers': ('1000030', "Suspected Counterfeit Product."),
        'Product Warranty': ('1000013', "Valid warranty details required for this category.")
    }

def run_mock_validations(data):
    """
    Placeholder: Replace this logic with your actual validation functions.
    It returns a dict of DataFrames keyed by the Flag Name.
    """
    flag_dfs = {}
    if data.empty: return flag_dfs

    # Example Check: Generic Brands
    if 'BRAND' in data.columns:
        mask = data['BRAND'].astype(str).str.lower() == 'generic'
        if mask.any(): flag_dfs['Generic BRAND Issues'] = data[mask]

    # Example Check: Single Word Names
    if 'NAME' in data.columns:
        mask = data['NAME'].astype(str).str.split().str.len() == 1
        if mask.any(): flag_dfs['Single-word NAME'] = data[mask]
        
    return flag_dfs

# -------------------------------------------------
# 3. Main Streamlit App
# -------------------------------------------------
def main():
    # Session States
    if 'manual_approvals' not in st.session_state:
        st.session_state.manual_approvals = set()
    if 'flags_map' not in st.session_state:
        st.session_state.flags_map = load_default_flags()

    st.title("Product Validation Tool")

    # Sidebar Tools
    if st.sidebar.button("🗑️ Reset QC Overrides"):
        st.session_state.manual_approvals.clear()
        st.rerun()

    # SECTION 1: Reason Editor
    with st.expander("⚙️ Edit Rejection Reasons & Seller Instructions"):
        temp_map = {}
        for flag, (code, instruction) in st.session_state.flags_map.items():
            c1, c2 = st.columns([1, 3])
            new_code = c1.text_input(f"Code: {flag}", value=code, key=f"code_{flag}")
            new_inst = c2.text_area(f"Instruction: {flag}", value=instruction, key=f"inst_{flag}", height=68)
            temp_map[flag] = (new_code, new_inst)
        st.session_state.flags_map = temp_map

    # SECTION 2: File Upload
    uploaded_files = st.file_uploader("Upload CSV/XLSX Files", type=['csv', 'xlsx'], accept_multiple_files=True)

    if uploaded_files:
        all_dfs = []
        for f in uploaded_files:
            try:
                if f.name.endswith('.xlsx'):
                    df = pd.read_excel(f, dtype=str)
                else:
                    f.seek(0)
                    # Automatically detects if file uses , or ; or \t
                    df = pd.read_csv(f, sep=None, engine='python', encoding='ISO-8859-1', dtype=str)
                
                all_dfs.append(standardize_input_data(df))
            except Exception as e:
                st.error(f"Error reading {f.name}: {e}")

        if all_dfs:
            combined_data = pd.concat(all_dfs, ignore_index=True)

            # CRITICAL COLUMN CHECK
            if 'PRODUCT_SET_SID' not in combined_data.columns:
                st.error("❌ Column 'PRODUCT_SET_SID' not found. Check your file headers.")
                st.info(f"Detected Headers: {list(combined_data.columns)}")
                st.stop()

            # Clean duplicates from input
            data = combined_data.drop_duplicates(subset=['PRODUCT_SET_SID'])
            
            # RUN VALIDATIONS
            flag_results = run_mock_validations(data)

            # SEARCH & METRICS
            st.divider()
            search_query = st.text_input("🔍 Global Search", placeholder="Search by SID, Seller, or Brand...").lower()
            
            total_flagged = sum(len(df) for df in flag_results.values())
            overridden = len(st.session_state.manual_approvals)
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Initial Flags", total_flagged)
            m2.metric("Manual QC Pass", overridden)
            m3.metric("Final Rejections", max(0, total_flagged - overridden))

            # SECTION 3: Flag Expanders
            st.header("Validation Results")
            for flag_name, df_flagged in flag_results.items():
                # Filter out items user already approved
                df_remaining = df_flagged[~df_flagged['PRODUCT_SET_SID'].isin(st.session_state.manual_approvals)]
                
                # Apply Global Search filter
                if search_query:
                    mask = df_remaining.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
                    df_display = df_remaining[mask].copy()
                else:
                    df_display = df_remaining.copy()

                with st.expander(f"{flag_name} ({len(df_display)})"):
                    if not df_display.empty:
                        # Add Checkbox column for override
                        df_display.insert(0, "QC_PASS", False)
                        # Filter to Visible Columns requested by user
                        cols_to_render = ["QC_PASS"] + [c for c in VISIBLE_COLUMNS if c in df_display.columns]
                        
                        edited_df = st.data_editor(
                            df_display[cols_to_render],
                            column_config={
                                "QC_PASS": st.column_config.CheckboxColumn("Approve?"),
                                "MAIN_IMAGE": st.column_config.ImageColumn("Preview")
                            },
                            disabled=[c for c in cols_to_render if c != "QC_PASS"],
                            hide_index=True,
                            key=f"editor_{flag_name}"
                        )

                        # Process manual approvals
                        new_approvals = edited_df[edited_df["QC_PASS"] == True]["PRODUCT_SET_SID"].tolist()
                        if new_approvals:
                            if st.button(f"Confirm Bulk Approval for {flag_name}", key=f"btn_{flag_name}"):
                                st.session_state.manual_approvals.update(new_approvals)
                                st.rerun()
                    else:
                        st.success("No products found for this flag.")

            # SECTION 4: Export Reports
            st.divider()
            st.header("Final Exports")
            
            # Build the report based on overrides
            report_data = []
            for _, row in data.iterrows():
                sid = row['PRODUCT_SET_SID']
                status, reason, comment, flag_val = "Approved", "", "", ""
                
                # Check if flagged
                for f_name, f_df in flag_results.items():
                    if sid in f_df['PRODUCT_SET_SID'].values:
                        if sid in st.session_state.manual_approvals:
                            status, comment = "Approved", "Manual QC Pass"
                        else:
                            status = "Rejected"
                            r_code, r_comm = st.session_state.flags_map.get(f_name, ("-", "-"))
                            reason, comment, flag_val = r_code, r_comm, f_name
                        break
                
                report_data.append({
                    "ProductSetSid": sid, "Status": status, "Reason": reason,
                    "Comment": comment, "FLAG": flag_val, "SellerName": row.get("SELLER_NAME", "")
                })

            final_df = pd.DataFrame(report_data)
            
            c1, c2, c3 = st.columns(3)
            c1.download_button("📥 Download Final Report", final_df.to_csv(index=False), "Final_Report.csv")
            c2.download_button("📥 Download Only Rejections", final_df[final_df['Status'] == 'Rejected'].to_csv(index=False), "Rejections.csv")
            c3.download_button("📥 Download Only Approved", final_df[final_df['Status'] == 'Approved'].to_csv(index=False), "Approved.csv")

if __name__ == "__main__":
    main()
