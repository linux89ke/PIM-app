import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
from typing import List

# -------------------------------------------------
# 1. SETUP
# -------------------------------------------------
st.set_page_config(page_title="Brand Validator", layout="centered")

# -------------------------------------------------
# 2. UTILITIES
# -------------------------------------------------
def load_brands_file() -> List[str]:
    """Loads brands.txt without caching to allow instant updates."""
    try:
        with open('brands.txt', 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensures all columns are UPPERCASE so validations can find 'NAME' and 'BRAND'.
    Handles mapping from internal codes (dsc_name) to standard names.
    """
    df = df.copy()
    
    # 1. Strip whitespace from headers
    df.columns = df.columns.str.strip()
    
    # 2. Map known internal codes to standard names
    # (Key is lowercase version of the header found in file)
    mapping = {
        'cod_productset_sid': 'PRODUCT_SET_SID',
        'dsc_name': 'NAME',
        'dsc_brand_name': 'BRAND',
        'dsc_shop_seller_name': 'SELLER_NAME',
        'list_seller_skus': 'SELLER_SKU',
        'image1': 'MAIN_IMAGE',
    }
    
    new_cols = {}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in mapping:
            new_cols[col] = mapping[col_lower]
        else:
            # Fallback: Just convert to UPPERCASE (e.g. 'Name' -> 'NAME')
            new_cols[col] = col.upper()
            
    df = df.rename(columns=new_cols)
    return df

def to_excel_download(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Results')
    output.seek(0)
    return output

# -------------------------------------------------
# 3. CORE LOGIC
# -------------------------------------------------
def check_generic_with_brand_in_name(data: pd.DataFrame, brands_list: List[str]) -> pd.DataFrame:
    # Quick Check: Do we have the columns we need?
    if 'NAME' not in data.columns or 'BRAND' not in data.columns:
        st.error(f"❌ Missing columns! Found: {list(data.columns)}")
        return pd.DataFrame()

    if not brands_list:
        return pd.DataFrame()

    # 1. Filter for Generic items only (Case-insensitive check)
    is_generic = data['BRAND'].astype(str).str.strip().str.lower() == 'generic'
    generic_items = data[is_generic].copy()
    
    if generic_items.empty:
        return pd.DataFrame()

    # 2. Sort brands longest first
    sorted_brands = sorted([str(b).strip().lower() for b in brands_list if b], key=len, reverse=True)

    # 3. Text Normalizer
    def normalize_text(text):
        text = str(text).lower()
        text = re.sub(r"['\.\-]", ' ', text) # Replace special chars with space
        text = re.sub(r'\s+', ' ', text)     # Collapse multiple spaces
        return text.strip()

    # 4. Brand Detector
    def detect_brand(name):
        name_clean = normalize_text(name)
        
        for brand in sorted_brands:
            brand_clean = normalize_text(brand)
            
            # Startswith check
            if name_clean.startswith(brand_clean):
                # Safety: Ensure it's not a partial word match (e.g. "Dr" vs "Dress")
                if len(name_clean) > len(brand_clean):
                    next_char = name_clean[len(brand_clean)]
                    if next_char.isalnum():
                        continue 
                return brand.title()
        return None

    # Apply
    generic_items['Detected_Brand'] = generic_items['NAME'].apply(detect_brand)
    
    # Filter matches
    flagged = generic_items[generic_items['Detected_Brand'].notna()].copy()
    
    if not flagged.empty:
        flagged['Status'] = 'Rejected'
        flagged['Reason'] = "1000002 - Kindly Ensure Brand Name Is Correct"
        flagged['Comment'] = "Generic item with detected brand: " + flagged['Detected_Brand']
        flagged['FLAG'] = 'Brand in Generic Name'
        
    return flagged

# -------------------------------------------------
# 4. UI
# -------------------------------------------------
st.title("🛡️ Brand Name Validator")

# Sidebar
with st.sidebar:
    st.header("Configuration")
    if st.button("🔄 Reload Brands File"):
        st.rerun()
        
    brands = load_brands_file()
    if brands:
        st.success(f"Loaded {len(brands)} brands")
        with st.expander("See Brands"):
            st.write(brands)
    else:
        st.error("brands.txt missing or empty!")

# Main
uploaded_files = st.file_uploader("Upload CSV/Excel", type=['csv', 'xlsx'], accept_multiple_files=True)

if uploaded_files and brands:
    if st.button("Run Validation", type="primary"):
        all_results = []
        progress = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            try:
                # Robust CSV Reading
                if file.name.endswith('.csv'):
                    file.seek(0)
                    # Try reading with default comma
                    df = pd.read_csv(file, dtype=str)
                    
                    # If it looks like it failed (only 1 column), try semicolon
                    if len(df.columns) <= 1:
                        file.seek(0)
                        df = pd.read_csv(file, sep=';', dtype=str)
                else:
                    df = pd.read_excel(file, dtype=str)
                
                # Standardize Columns
                df = standardize_input_data(df)
                
                # Run Check
                result = check_generic_with_brand_in_name(df, brands)
                
                if not result.empty:
                    # Select columns to display
                    cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'Detected_Brand', 'SELLER_NAME']
                    final_cols = [c for c in cols if c in result.columns]
                    all_results.append(result[final_cols])
                
            except Exception as e:
                st.error(f"Error reading {file.name}: {e}")
            
            progress.progress((i + 1) / len(uploaded_files))
            
        progress.empty()

        if all_results:
            final_df = pd.concat(all_results, ignore_index=True)
            st.error(f"Found {len(final_df)} issues!")
            st.dataframe(final_df, use_container_width=True)
            
            date_str = datetime.now().strftime("%Y-%m-%d")
            st.download_button(
                "📥 Download Report",
                data=to_excel_download(final_df),
                file_name=f"Brand_Issues_{date_str}.xlsx"
            )
        else:
            st.success("✅ No issues found. All clean!")

elif not brands:
    st.warning("⚠️ Please create a 'brands.txt' file in the folder.")
