import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
from typing import List

# -------------------------------------------------
# 1. SETUP & MAPPING
# -------------------------------------------------
st.set_page_config(page_title="Brand Validation Tool", layout="centered")

NEW_FILE_MAPPING = {
    'cod_productset_sid': 'PRODUCT_SET_SID',
    'dsc_name': 'NAME',
    'dsc_brand_name': 'BRAND',
    'cod_category_code': 'CATEGORY_CODE',
    'dsc_category_name': 'CATEGORY',
    'dsc_shop_seller_name': 'SELLER_NAME',
    'dsc_shop_active_country': 'ACTIVE_STATUS_COUNTRY',
    'cod_parent_sku': 'PARENTSKU',
}

# The Error Code to apply when a brand is found
ERROR_CODE = "1000002 - Kindly Ensure Brand Name Is Correct"
ERROR_MSG = "This product is listed as 'Generic', but the name starts with a known brand. Please update the Brand field."

# -------------------------------------------------
# 2. UTILITIES
# -------------------------------------------------
@st.cache_data
def load_brands_file() -> List[str]:
    """Loads brands.txt and returns a list of brands."""
    try:
        with open('brands.txt', 'r', encoding='utf-8') as f:
            # Strip whitespace and ignore empty lines
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    """Renames columns to standard names."""
    df = df.copy()
    # Normalize headers to lowercase for mapping
    df.columns = df.columns.str.strip().str.lower()
    
    # Invert mapping to find match (Key in mapping is the standardized name we want? No, usually CSV has the key)
    # The mapping provided in previous code was: 'csv_header': 'INTERNAL_COL'
    # Let's handle the specific mapping provided:
    
    # Create a lower-case map
    map_lower = {k.lower(): v for k, v in NEW_FILE_MAPPING.items()}
    
    # Rename
    df = df.rename(columns=map_lower)
    
    # Ensure critical columns exist
    required = ['PRODUCT_SET_SID', 'NAME', 'BRAND']
    for col in required:
        if col not in df.columns:
            df[col] = "" # Fill missing with empty string to prevent crashes
            
    return df

def to_excel_download(df):
    """Helper to generate Excel download link."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='ValidationResults')
    output.seek(0)
    return output

# -------------------------------------------------
# 3. CORE LOGIC
# -------------------------------------------------
def check_generic_with_brand_in_name(data: pd.DataFrame, brands_list: List[str]) -> pd.DataFrame:
    """
    Flags products where BRAND is 'Generic' but the NAME starts with 
    a known brand from brands.txt.
    """
    if data.empty or not brands_list:
        return pd.DataFrame()

    # 1. Filter for Generic items only (Strict Check)
    # We create a boolean mask first
    is_generic = data['BRAND'].astype(str).str.strip().str.lower() == 'generic'
    generic_items = data[is_generic].copy()
    
    if generic_items.empty:
        return pd.DataFrame()

    # 2. Sort brands by length (descending) to catch "Dr Rashel" before "Dr"
    sorted_brands = sorted([str(b).strip().lower() for b in brands_list if b], key=len, reverse=True)

    def normalize_text(text):
        """
        Normalize text for comparison:
        - Lowercase
        - Remove apostrophes, periods, hyphens
        - Collapse spaces
        """
        text = str(text).lower()
        text = re.sub(r"['\.\-]", ' ', text) # Replace special chars with space
        text = re.sub(r'\s+', ' ', text)     # Collapse multiple spaces
        return text.strip()

    def detect_brand(name):
        name_clean = normalize_text(name)
        
        for brand in sorted_brands:
            brand_clean = normalize_text(brand)
            
            # Check if normalized name starts with normalized brand
            if name_clean.startswith(brand_clean):
                
                # OPTIONAL SAFETY: Check that the character after the match isn't a letter
                # This prevents "Dr" matching "Dress"
                # Logic: If brand is shorter than name, next char must be space/non-alphanumeric
                if len(name_clean) > len(brand_clean):
                    next_char = name_clean[len(brand_clean)]
                    if next_char.isalnum():
                        continue # It's part of a longer word
                
                return brand.title() # Return nice Title Case
        return None

    # 3. Run Detection
    # Using progress bar if data is large
    generic_items['Detected_Brand'] = generic_items['NAME'].apply(detect_brand)
    
    # 4. Filter only those that matched
    flagged = generic_items[generic_items['Detected_Brand'].notna()].copy()
    
    if not flagged.empty:
        # Create output columns similar to the original tool
        flagged['Status'] = 'Rejected'
        flagged['Reason'] = ERROR_CODE
        flagged['Comment'] = ERROR_MSG + " (Detected: " + flagged['Detected_Brand'] + ")"
        flagged['FLAG'] = 'Brand in Generic Name'
        
    return flagged

# -------------------------------------------------
# 4. UI STRUCTURE
# -------------------------------------------------
st.title("🛡️ Brand Name Validator")
st.markdown("Checks if **'Generic'** products have a real brand name hidden in the title.")

# Sidebar for Brands
with st.sidebar:
    st.header("Configuration")
    brands = load_brands_file()
    if brands:
        st.success(f"✅ Loaded {len(brands)} brands from brands.txt")
        with st.expander("View Brands"):
            st.write(brands)
    else:
        st.error("❌ brands.txt not found or empty!")
        st.info("Please add a file named 'brands.txt' in the app directory.")

# Main Interface
uploaded_files = st.file_uploader("Upload CSV or Excel files", type=['csv', 'xlsx'], accept_multiple_files=True)

if uploaded_files and brands:
    if st.button("Run Validation"):
        all_results = []
        
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            try:
                # Load Data
                if file.name.endswith('.csv'):
                    try:
                        df = pd.read_csv(file, dtype=str)
                    except:
                        file.seek(0)
                        df = pd.read_csv(file, sep=';', dtype=str)
                else:
                    df = pd.read_excel(file, dtype=str)
                
                # Standardize
                df_std = standardize_input_data(df)
                
                # Run Check
                result = check_generic_with_brand_in_name(df_std, brands)
                
                if not result.empty:
                    # Keep original columns + validation columns
                    cols_to_keep = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'Status', 'Reason', 'Comment', 'FLAG', 'SELLER_NAME']
                    # Add any missing cols
                    for c in cols_to_keep:
                        if c not in result.columns: result[c] = ""
                    
                    all_results.append(result[cols_to_keep])
                
            except Exception as e:
                st.error(f"Error processing {file.name}: {e}")
            
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        progress_bar.empty()

        # Display Results
        if all_results:
            final_df = pd.concat(all_results, ignore_index=True)
            st.success(f"Found {len(final_df)} issues!")
            
            st.dataframe(final_df, use_container_width=True)
            
            # Download
            excel_data = to_excel_download(final_df)
            date_str = datetime.now().strftime("%Y-%m-%d")
            st.download_button(
                label="📥 Download Rejected Products",
                data=excel_data,
                file_name=f"Brand_Mismatch_Results_{date_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.balloons()
            st.success("✅ No issues found! All 'Generic' items appear clean.")

elif not brands:
    st.warning("Please fix the brands.txt file to proceed.")
