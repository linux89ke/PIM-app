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
FX_RATE = 132.0
SPLIT_LIMIT = 9998 

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
    'dsc_status': 'LISTING_STATUS',
    'dsc_shop_email': 'SELLER_EMAIL',
    'product_warranty': 'PRODUCT_WARRANTY',
    'warranty_duration': 'WARRANTY_DURATION',
    'warranty_address': 'WARRANTY_ADDRESS',
    'warranty_type': 'WARRANTY_TYPE'
}

# Logger setup
logger = logging.getLogger(__name__)

# -------------------------------------------------
# ATTRIBUTE EXTRACTION UTILITIES
# -------------------------------------------------
COLOR_PATTERNS = {
    'red': ['red', 'crimson', 'scarlet', 'maroon', 'burgundy', 'wine', 'ruby'],
    'blue': ['blue', 'navy', 'royal', 'sky', 'azure', 'cobalt', 'sapphire'],
    'green': ['green', 'lime', 'olive', 'emerald', 'mint', 'forest', 'jade'],
    'black': ['black', 'onyx', 'ebony', 'jet', 'charcoal', 'midnight'],
    'white': ['white', 'ivory', 'cream', 'pearl', 'snow', 'alabaster'],
    'gray': ['gray', 'grey', 'silver', 'slate', 'ash', 'graphite'],
    'yellow': ['yellow', 'gold', 'golden', 'amber', 'lemon', 'mustard'],
    'orange': ['orange', 'tangerine', 'peach', 'coral', 'apricot'],
    'pink': ['pink', 'rose', 'magenta', 'fuchsia', 'salmon', 'blush'],
    'purple': ['purple', 'violet', 'lavender', 'plum', 'mauve', 'lilac'],
    'brown': ['brown', 'tan', 'beige', 'khaki', 'chocolate', 'coffee', 'bronze'],
    'multicolor': ['multicolor', 'multicolour', 'multi-color', 'rainbow', 'mixed']
}

COLOR_VARIANT_TO_BASE = {variant: base for base, variants in COLOR_PATTERNS.items() for variant in variants}

@dataclass
class ProductAttributes:
    base_name: str
    colors: Set[str]
    sizes: Set[str]
    storage: Set[str]
    memory: Set[str]
    quantities: Set[str]
    raw_name: str
    
    def get_variant_key(self) -> str:
        parts = [self.base_name]
        if self.colors: parts.append("_color_" + "_".join(sorted(self.colors)))
        if self.sizes: parts.append("_size_" + "_".join(sorted(self.sizes)))
        if self.storage: parts.append("_storage_" + "_".join(sorted(self.storage)))
        if self.memory: parts.append("_memory_" + "_".join(sorted(self.memory)))
        if self.quantities: parts.append("_qty_" + "_".join(sorted(self.quantities)))
        return "|".join(parts).lower()
    
    def get_base_key(self) -> str:
        return self.base_name.lower()

def clean_category_code(code) -> str:
    try:
        if pd.isna(code): return ""
        s = str(code).strip()
        if s.replace('.', '', 1).isdigit() and '.' in s:
            return str(int(float(s)))
        return s
    except:
        return str(code).strip()

def normalize_text(text: str) -> str:
    if pd.isna(text): return ""
    text = str(text).lower().strip()
    noise = r'\b(new|sale|original|genuine|authentic|official|premium|quality|best|hot|2024|2025)\b'
    text = re.sub(noise, '', text)
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', '', text)
    return text

def create_match_key(row: pd.Series) -> str:
    name = normalize_text(row.get('NAME', ''))
    brand = normalize_text(row.get('BRAND', ''))
    color = normalize_text(row.get('COLOR', ''))
    return f"{brand}|{name}|{color}"

# -------------------------------------------------
# DATA LOADING & VALIDATION RUNNERS
# -------------------------------------------------
@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    return {
        'Restricted brands': ('1000024 - Product does not have a license to be sold via Jumia (Not Authorized)', "Rejected due to absence of required license."),
        'Suspected Fake product': ('1000023 - Confirmation of counterfeit product', "Confirmed counterfeit by technical team."),
        'Product Warranty': ('1000013 - Kindly Provide Product Warranty Details', "Valid warranty required in description/tab."),
        'Poor Image Quality': ('1000002 - Poor Image Quality', "Image is blurred, has watermarks, or is low resolution."),
        'Wrong Category': ('1000003 - Categorization Error', "Product is listed in the incorrect category."),
        'Duplicate product': ('1000007 - Other Reason', "This product is a duplicate of another listing."),
        'Unnecessary words in NAME': ('1000008 - Kindly Improve Product Name', "Update title format: Name – Type – Color.")
    }

# (Note: Helper functions like check_restricted_brands, check_duplicate_products etc. are assumed to be present as per your original script)
# ... [Insert original validation functions here for brevity] ...

def validate_products(data: pd.DataFrame, support_files: Dict, country_validator: 'CountryValidator', data_has_warranty_cols: bool, common_sids: Optional[set] = None):
    # This matches the core logic from your original script
    # It runs the loop through 'validations' list and returns final_df, results
    # ... [Assuming the implementation from your first message] ...
    pass 

class CountryValidator:
    COUNTRY_CONFIG = {
        "Kenya": {"code": "KE", "skip_validations": [], "prohibited_products_file": "prohibited_productsKE.txt"},
        "Uganda": {"code": "UG", "skip_validations": ["Counterfeit Sneakers"], "prohibited_products_file": "prohibited_productsUG.txt"}
    }
    def __init__(self, country: str):
        self.country = country
        self.config = self.COUNTRY_CONFIG.get(country, self.COUNTRY_CONFIG["Kenya"])
        self.code = self.config["code"]

# -------------------------------------------------
# STREAMLIT UI & LOGIC
# -------------------------------------------------
st.set_page_config(page_title="Product Validation Tool", layout="wide")

# Initialize Session States
if 'final_report' not in st.session_state: st.session_state.final_report = pd.DataFrame()
if 'all_data_map' not in st.session_state: st.session_state.all_data_map = pd.DataFrame()
if 'intersection_count' not in st.session_state: st.session_state.intersection_count = 0
if 'image_review_decisions' not in st.session_state: st.session_state.image_review_decisions = {}

st.title("Product Validation Tool")

with st.sidebar:
    st.header("Settings")
    country = st.selectbox("Select Country", ["Kenya", "Uganda"])
    country_validator = CountryValidator(country)
    if st.button("♻️ Clear Cache"):
        st.cache_data.clear()
        st.rerun()

uploaded_files = st.file_uploader("Upload CSV/XLSX Files", type=['csv', 'xlsx'], accept_multiple_files=True)

if uploaded_files:
    # Check if we need to process (Simple hash-like check)
    current_sig = sorted([f.name + str(f.size) for f in uploaded_files])
    if 'last_sig' not in st.session_state or st.session_state.last_sig != current_sig:
        # 1. LOAD AND MERGE DATA
        # 2. RUN VALIDATION (validate_products)
        # 3. UPDATE st.session_state.final_report
        # 4. RESET IMAGE DECISIONS
        st.session_state.image_review_decisions = {}
        st.session_state.last_sig = current_sig
        # ... [Processing logic here] ...

if not st.session_state.final_report.empty:
    final_report = st.session_state.final_report
    data = st.session_state.all_data_map
    
    approved_df = final_report[final_report['Status'] == 'Approved']
    rejected_df = final_report[final_report['Status'] == 'Rejected']

    # --- Metrics Section ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Total", len(data))
    c2.metric("Approved", len(approved_df))
    c3.metric("Rejected", len(rejected_df))

    # --- Automated Flag Review Section ---
    st.subheader("Validation Results by Flag")
    # ... [Loop through rejected flags and display data editor as in original script] ...

    # -------------------------------------------------
    # IMAGE REVIEW SECTION (NEW FEATURE)
    # -------------------------------------------------
    st.markdown("---")
    st.subheader("🖼️ Image Quality Review (Approved Products Only)")
    
    # Merge approved report with source data to get Image URLs
    approved_with_images = pd.merge(
        approved_df[['ProductSetSid']], 
        data, 
        left_on='ProductSetSid', right_on='PRODUCT_SET_SID', 
        how='left'
    )

    if 'MAIN_IMAGE' in approved_with_images.columns:
        valid_images = approved_with_images[approved_with_images['MAIN_IMAGE'].notna()]
        
        if not valid_images.empty:
            with st.expander(f"📸 Visual Audit ({len(valid_images)} products)", expanded=False):
                st.info("Check images for quality. Selected items will be moved to the 'Rejected' list.")
                
                # Search and Pagination
                img_search = st.text_input("🔍 Filter Images", placeholder="Search name/brand...")
                if img_search:
                    valid_images = valid_images[valid_images['NAME'].str.contains(img_search, case=False, na=False)]

                items_per_page = 12
                total_pages = max(1, (len(valid_images) - 1) // items_per_page + 1)
                curr_page = st.number_input("Review Page", 1, total_pages, 1)
                
                start_idx = (curr_page - 1) * items_per_page
                page_data = valid_images.iloc[start_idx : start_idx + items_per_page]

                # Grid Layout (3 columns)
                grid = st.columns(3)
                for i, (_, row) in enumerate(page_data.iterrows()):
                    with grid[i % 3]:
                        sid = str(row['PRODUCT_SET_SID'])
                        st.image(row['MAIN_IMAGE'], use_container_width=True)
                        st.markdown(f"**{row['NAME'][:50]}...**")
                        
                        # Decision Checkboxes
                        col_a, col_b = st.columns(2)
                        with col_a:
                            poor = st.checkbox("Poor Quality", key=f"poor_{sid}")
                        with col_b:
                            wrong = st.checkbox("Wrong Cat", key=f"wrong_{sid}")
                        
                        if poor or wrong:
                            st.session_state.image_review_decisions[sid] = "Poor Image Quality" if poor else "Wrong Category"
                        elif sid in st.session_state.image_review_decisions:
                            del st.session_state.image_review_decisions[sid]

                # Action Button
                if st.session_state.image_review_decisions:
                    if st.button("🚨 Apply Image Rejections", type="primary"):
                        flags_map = load_flags_mapping()
                        for sid, flag_type in st.session_state.image_review_decisions.items():
                            reason_info = flags_map.get(flag_type)
                            
                            # Update the report
                            mask = st.session_state.final_report['ProductSetSid'] == sid
                            st.session_state.final_report.loc[mask, ['Status', 'Reason', 'Comment', 'FLAG']] = [
                                'Rejected', reason_info[0], reason_info[1], flag_type
                            ]
                        
                        st.success(f"Moved {len(st.session_state.image_review_decisions)} items to Rejected.")
                        st.session_state.image_review_decisions = {}
                        st.rerun()

    # --- Export Section ---
    st.markdown("---")
    st.header("Overall Exports")
    # ... [Export logic using generate_smart_export from original script] ...
