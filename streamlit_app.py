import pandas as pd
from typing import Dict, List, Tuple, Optional
import re
import logging

# -------------------------------------------------
# Mocking Environment and Data
# -------------------------------------------------
# Mocking Streamlit Caching/Environment
def st_cache_data(ttl=3600):
    def decorator(func): return func
    return decorator

# Mock Constants
FX_RATE = 132.0 
FILE_NAME = "productSetsPendingQc.2025-12-15T08_57_00Z.csv"
TARGET_SID = 'e26d0d34-d5c5-4a8c-88ae-d4dcd1f8777b'

# Mock data needed for flags that rely on external files.
def mock_load_excel_file(filename: str) -> pd.DataFrame:
    # MOCK UPDATE: Adding category 1029763 to Nike's suspect list.
    if 'suspected_fake.xlsx' in filename:
        data = {
            'Price': ['Price', None, None, None, None], 
            'Sony': [40, 1009219, 1000067, None, None], 
            # Original suspect categories + 1029763
            'Nike': [40, 1001810, 1003543, 1001691, 1029763], 
            'Adidas': [40, 1001810, 1003543, 1001691, None], 
        }
        df = pd.DataFrame(data)
        df.columns = df.iloc[0]
        df = df[1:].reset_index(drop=True)
        return df.rename(columns={'Price': 'Price'})
    return pd.DataFrame()

# -------------------------------------------------
# CORE VALIDATION LOGIC (Simplified from full script)
# -------------------------------------------------

def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    # Function to map column names
    NEW_FILE_MAPPING = {
        'cod_productset_sid': 'PRODUCT_SET_SID', 'dsc_name': 'NAME', 'dsc_brand_name': 'BRAND', 
        'cod_category_code': 'CATEGORY_CODE', 'dsc_shop_seller_name': 'SELLER_NAME', 
        'dsc_shop_active_country': 'ACTIVE_STATUS_COUNTRY', 'GLOBAL_PRICE': 'GLOBAL_PRICE',
        'GLOBAL_SALE_PRICE': 'GLOBAL_SALE_PRICE', 'dsc_category_name': 'CATEGORY'
    }
    df = df.rename(columns=NEW_FILE_MAPPING, errors='ignore')
    if 'ACTIVE_STATUS_COUNTRY' in df.columns:
        df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.strip().str.upper()
    return df

@st_cache_data(ttl=3600)
def compile_regex_patterns(words: List[str]) -> re.Pattern:
    if not words: return None
    pattern = '|'.join(r'\b' + re.escape(w) + r'\b' for w in words)
    return re.compile(pattern, re.IGNORECASE)

# --- Validation Functions ---

def check_suspected_fake_products(data: pd.DataFrame, suspected_fake_df: pd.DataFrame, fx_rate: float = 132.0) -> pd.DataFrame:
    required_cols = ['CATEGORY_CODE', 'BRAND', 'GLOBAL_SALE_PRICE', 'GLOBAL_PRICE', 'PRODUCT_SET_SID']
    if not all(c in data.columns for c in required_cols) or suspected_fake_df.empty: return pd.DataFrame(columns=data.columns)
    
    try:
        ref_data = suspected_fake_df.copy()
        brand_cols = [col for col in ref_data.columns if pd.notna(col) and col != 'Price']
        brand_category_price = {}
        
        for brand in brand_cols:
            try:
                # Convert price threshold to float immediately
                price_threshold = pd.to_numeric(ref_data[brand].iloc[0], errors='coerce').iloc[0] # Use iloc[0] to get scalar
                if pd.isna(price_threshold) or price_threshold <= 0: continue
            except: continue
            
            categories = ref_data[brand].iloc[1:].dropna()
            brand_lower = brand.strip().lower()
            
            for cat in categories:
                cat_base = str(cat).split('.')[0].strip()
                if cat_base and cat_base.lower() != 'nan':
                    brand_category_price[(brand_lower, cat_base)] = float(price_threshold)
        
        if not brand_category_price: return pd.DataFrame(columns=data.columns)
        
        check_data = data.copy()
        check_data['price_to_use'] = pd.to_numeric(check_data['GLOBAL_SALE_PRICE'], errors='coerce').where(
            (pd.to_numeric(check_data['GLOBAL_SALE_PRICE'], errors='coerce').notna()) & 
            (pd.to_numeric(check_data['GLOBAL_SALE_PRICE'], errors='coerce') > 0),
            pd.to_numeric(check_data['GLOBAL_PRICE'], errors='coerce')
        ).fillna(0)
        
        check_data['price_usd'] = check_data['price_to_use'] # Use as USD directly
        check_data['BRAND_LOWER'] = check_data['BRAND'].astype(str).str.strip().str.lower()
        check_data['CAT_BASE'] = check_data['CATEGORY_CODE'].astype(str).str.split('.').str[0].str.strip()
        
        def is_suspected_fake(row):
            key = (row['BRAND_LOWER'], row['CAT_BASE'])
            if key in brand_category_price:
                threshold = brand_category_price[key]
                if row['price_usd'] < threshold:
                    return True
            return False
        
        check_data['is_fake'] = check_data.apply(is_suspected_fake, axis=1)
        flagged = check_data[check_data['is_fake'] == True].copy()
        
        return flagged.drop_duplicates(subset=['PRODUCT_SET_SID'])
        
    except Exception as e:
        # print(f"Error in suspected fake product check: {e}") # Debugging error logging
        return pd.DataFrame(columns=data.columns)

# -------------------------------------------------
# EXECUTION
# -------------------------------------------------
# 1. Load Data and Isolate Target SID
df_raw = pd.read_csv(FILE_NAME, sep=';', encoding='ISO-8859-1', dtype=str)
df_clean = standardize_input_data(df_raw)

target_df = df_clean[df_clean['PRODUCT_SET_SID'] == TARGET_SID].copy()

# 2. Load Support Files (MOCK includes the missing category 1029763 for Nike)
suspected_fake_df = mock_load_excel_file('suspected_fake.xlsx')

# 3. Run Suspected Fake Check on Target Product
flagged_results = check_suspected_fake_products(
    data=target_df,
    suspected_fake_df=suspected_fake_df,
    fx_rate=FX_RATE
)

# 4. Detailed Report Generation
product_info = target_df.iloc[0].to_dict()
product_price = pd.to_numeric(product_info.get('GLOBAL_SALE_PRICE', product_info.get('GLOBAL_PRICE')), errors='coerce')
brand_lower = str(product_info.get('BRAND', '')).lower()
category_base = str(product_info.get('CATEGORY_CODE', '')).split('.')[0].strip()

# Get mock threshold price for Nike, ensuring it's numeric
nike_threshold = pd.to_numeric(suspected_fake_df['Nike'].iloc[0], errors='coerce')

print("--- Detailed Evaluation for Suspected Fake Product Flag (Hypothesis Check) ---")
print(f"Product SID: {TARGET_SID}")
print(f"Product Price (USD): {product_price:.2f}")

print("\n--- Check 1: Price Condition ---")
is_price_low = pd.notna(product_price) and product_price < nike_threshold
print(f"Nike Price Threshold (Mock): ${nike_threshold:.2f}")
print(f"Result: Price < Threshold? {is_price_low}")

print("\n--- Check 2: Category Condition ---")
# Manually verify category inclusion based on the updated mock data
suspect_categories_list_raw = suspected_fake_df.get('Nike', pd.Series()).iloc[1:]
suspect_base_categories = set([str(c).split('.')[0].strip() for c in suspect_categories_list_raw.dropna()])
is_suspect_category = category_base in suspect_base_categories

print(f"Suspect Categories (Updated Mock): {suspect_base_categories}")
print(f"Result: Category {category_base} Match? {is_suspect_category}")

print("\n--- Final Suspected Fake Flag Result ---")
if is_suspect_category and is_price_low:
    print("FINAL FLAG STATUS: FLAGGED (Both conditions met).")
    print("Conclusion: Yes, the missing category code was the issue.")
else:
    print("FINAL FLAG STATUS: NOT FLAGGED (One or both conditions failed).")
    print("Conclusion: No, even with the updated mock, this product is not flagged.")
