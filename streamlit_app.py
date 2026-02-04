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
import requests
from difflib import SequenceMatcher
import zipfile
import concurrent.futures

# -------------------------------------------------
# 0. IMAGE HASHING & PROCESSING IMPORTS
# -------------------------------------------------
try:
    import imagehash
    from PIL import Image
    import cv2
    import numpy as np
except ImportError:
    st.error("Missing libraries! Please run: pip install imagehash Pillow requests opencv-python-headless numpy")
    st.stop()

# Global Cache for Image Hashes
_IMAGE_HASH_CACHE = {}

def clear_image_cache():
    """Clear the image hash cache to free memory."""
    global _IMAGE_HASH_CACHE
    _IMAGE_HASH_CACHE.clear()

def fetch_single_hash(url: str) -> None:
    """Helper function for the thread pool to fetch and cache a single hash."""
    if not url or url in _IMAGE_HASH_CACHE:
        return

    try:
        # [STABILITY] Increased timeout to 10s and added headers to prevent 403 blocks
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, timeout=10, stream=True, headers=headers)
        
        if response.status_code == 200:
            img = Image.open(response.raw)
            # [OPTIMIZATION] Resize large images to 256x256 before hashing to speed up processing
            img.thumbnail((256, 256), Image.Resampling.LANCZOS)
            _IMAGE_HASH_CACHE[url] = imagehash.phash(img)
        else:
            _IMAGE_HASH_CACHE[url] = None
    except Exception:
        _IMAGE_HASH_CACHE[url] = None

def prefetch_image_hashes(urls: List[str], max_workers: int = 10) -> None:
    """
    Downloads and hashes a list of URLs in parallel.
    Populates the global _IMAGE_HASH_CACHE.
    """
    valid_urls = [u for u in urls if u and pd.notna(u) and str(u).lower() not in ['nan', 'none', ''] and u not in _IMAGE_HASH_CACHE]
    valid_urls = list(set(valid_urls))
    
    if not valid_urls:
        return

    # [STABILITY] Reduced max_workers from 20 to 10 to prevent network congestion/timeouts
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        executor.map(fetch_single_hash, valid_urls)

def get_image_hash_fast(url: str) -> Optional[imagehash.ImageHash]:
    """Retreives hash from cache (instant)."""
    return _IMAGE_HASH_CACHE.get(str(url).strip())

# -------------------------------------------------
# Constants & Mapping
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
# UTILITIES
# -------------------------------------------------
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
# CORE DUPLICATE LOGIC (PARALLEL IMAGE HASHING)
# -------------------------------------------------
def check_duplicate_products(
    data: pd.DataFrame, 
    exempt_categories: List[str] = None,
    similarity_threshold: float = 0.60, 
    known_colors: List[str] = None, 
    use_image_hash: bool = True,  
    **kwargs
) -> pd.DataFrame:
    
    # --- 1. SETUP ---
    required_cols = ['NAME', 'SELLER_NAME', 'BRAND']
    if not all(col in data.columns for col in required_cols):
        return pd.DataFrame(columns=data.columns)

    data_to_check = data.copy()
    data_to_check['_grp_seller'] = data_to_check['SELLER_NAME'].astype(str).str.strip().str.lower()
    data_to_check['_grp_brand'] = data_to_check['BRAND'].astype(str).str.strip().str.lower()

    if exempt_categories and 'CATEGORY_CODE' in data_to_check.columns:
        cats_to_check = data_to_check['CATEGORY_CODE'].apply(clean_category_code)
        exempt_set = set(clean_category_code(c) for c in exempt_categories)
        data_to_check = data_to_check[~cats_to_check.isin(exempt_set)]

    if data_to_check.empty:
        return pd.DataFrame(columns=data.columns)

    if known_colors:
        color_set = set(str(c).lower().strip() for c in known_colors if c)
    else:
        color_set = set()

    fluff_words = {
        'professional', 'high', 'quality', 'best', 'sale', 'new', 'original', 'genuine', 
        'authentic', 'premium', 'official', 'hot', 'promo', 'deal', 'combo', 'kit', 
        'set', 'pack', 'bundle', 'full', 'complete', 'for', 'with', 'and', 'the', 
        'in', 'on', 'at', 'to', 'of', 'plus', 'recording', 'condenser', 'studio', 
        'mic', 'microphone', 'sound', 'card', 'interface', 'mixer', 'audio', 'voice', 
        'vocal', 'music', 'input', 'output', 'wired', 'wireless', 'usb', 'cable', 
        'equipment', 'device', 'gear', 'setup', 'live', 'streaming', 'stream', 
        'podcast', 'podcasting', 'broadcasting', 'broadcast', 'gaming', 'gamer', 
        'game', 'karaoke', 'singing', 'song', 'teaching', 'class', 'online', 'school', 
        'zoom', 'meeting', 'home', 'office', 'work', 'church', 'stage', 'performance', 
        'speech', 'dj', 'youtube', 'tiktok', 'facebook', 'instagram', 'skype', 'video', 
        'content', 'creator', 'vlogging', 'vlog', 'pc', 'computer', 'laptop', 
        'desktop', 'phone', 'smartphone', 'mobile', 'android', 'ios', 'iphone', 
        'tablet', 'ipad', 'mac', 'windows'
    }

    def get_token_data(row):
        name_text = str(row.get('NAME', '')).lower()
        name_text = re.sub(r'[^\w\s]', '', name_text) 
        tokens = set(name_text.split()) - fluff_words
        
        col_color = str(row.get('COLOR', '')).lower().strip()
        if col_color in ['nan', 'none', '', 'null']: col_color = None
        
        img_url = None
        # Only extract URL if hashing is enabled
        if use_image_hash and 'MAIN_IMAGE' in row:
            raw_url = str(row['MAIN_IMAGE']).strip()
            if raw_url.lower() not in ['nan', 'none', '']:
                img_url = raw_url

        found_colors_in_name = tokens.intersection(color_set)
        
        return {
            'tokens': tokens,
            'col_color': col_color,
            'name_colors': found_colors_in_name,
            'img_url': img_url
        }

    data_to_check['search_data'] = data_to_check.apply(get_token_data, axis=1)
    
    # Use a set for faster lookups
    rejected_sids = set()
    
    # --- 2. GROUPING & PARALLEL PREFETCH ---
    grouped = data_to_check.groupby(['_grp_seller', '_grp_brand'])
    
    for (seller, brand), group in grouped:
        if len(group) < 2: continue
        
        products = group.to_dict('records')
        
        # --- PARALLEL IMAGE FETCHING ---
        if use_image_hash:
            urls_to_fetch = [p['search_data']['img_url'] for p in products if p['search_data']['img_url']]
            # [OPTIMIZATION] Reduced workers to 10 for stability
            prefetch_image_hashes(urls_to_fetch, max_workers=10) 
        
        # [OPTIMIZATION] Reduced window size from 100 to 50 for faster checks
        WINDOW_SIZE = min(50, len(products)) 
        
        for i in range(len(products)):
            current = products[i]
            if current['PRODUCT_SET_SID'] in rejected_sids: continue

            data_A = current['search_data']
            
            # --- BUFFER LIST: STORE POTENTIAL DUPLICATES FOR THIS ANCHOR ---
            potential_duplicates = []
            
            for j in range(i + 1, min(i + WINDOW_SIZE, len(products))):
                compare = products[j]
                if compare['PRODUCT_SET_SID'] in rejected_sids: continue

                data_B = compare['search_data']

                # 1. Color Check
                if data_A['col_color'] and data_B['col_color'] and data_A['col_color'] != data_B['col_color']:
                    continue
                if data_A['name_colors'] and data_B['name_colors'] and data_A['name_colors'].isdisjoint(data_B['name_colors']):
                    continue

                # 2. Text Check
                tokens_A = data_A['tokens']
                tokens_B = data_B['tokens']
                
                is_text_duplicate = False
                if len(tokens_A) > 0 and len(tokens_B) > 0:
                    intersection = len(tokens_A.intersection(tokens_B))
                    union = len(tokens_A.union(tokens_B))
                    if union > 0 and (intersection / union) >= similarity_threshold:
                        is_text_duplicate = True
                elif len(tokens_A) == 0 and len(tokens_B) == 0:
                    is_text_duplicate = True

                # 3. Image Check (Instant Lookup from Cache)
                is_image_duplicate = False
                # [CONFIGURABLE] Only check images if flag is True
                if use_image_hash and not is_text_duplicate:
                    url_A = data_A['img_url']
                    url_B = data_B['img_url']
                    
                    if url_A and url_B:
                        if url_A == url_B:
                            is_image_duplicate = True
                        else:
                            hash_A = get_image_hash_fast(url_A)
                            if hash_A:
                                hash_B = get_image_hash_fast(url_B)
                                if hash_B and (hash_A - hash_B) < 5:
                                    is_image_duplicate = True

                # --- IF MATCH FOUND, ADD TO POTENTIAL LIST ---
                if is_text_duplicate or is_image_duplicate:
                    potential_duplicates.append(compare['PRODUCT_SET_SID'])

            # --- DECISION LOGIC: ONLY REJECT IF > 1 DUPLICATE FOUND (Total >= 3 SKUs) ---
            if len(potential_duplicates) >= 2:
                rejected_sids.update(potential_duplicates)

    # Convert set back to dataframe
    rejected_df = data_to_check[data_to_check['PRODUCT_SET_SID'].isin(rejected_sids)].copy()
    
    st.session_state.duplicate_stats = {
        'total': len(rejected_df),
        'method': f'Aggressive Token + Parallel Image Hash (Allow 1 Pair)'
    }

    return rejected_df[data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])

# -------------------------------------------------
# CACHED FILE LOADING
# -------------------------------------------------
@st.cache_data(ttl=3600)
def load_txt_file(filename: str) -> List[str]:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = [line.strip() for line in f if line.strip()]
        return data
    except Exception as e:
        logger.error(f"Error reading {filename}: {e}")
        return []

@st.cache_data(ttl=3600)
def load_excel_file(filename: str, column: Optional[str] = None):
    try:
        df = pd.read_excel(filename, engine='openpyxl', dtype=str)
        df.columns = df.columns.str.strip()
        if column and column in df.columns:
            return df[column].apply(clean_category_code).tolist()
        return df
    except Exception as e:
        logger.error(f"Error reading {filename}: {e}")
        return [] if column else pd.DataFrame()

@st.cache_data(ttl=3600)
def load_restricted_brands_config(filename: str) -> Dict:
    config = {}
    try:
        df1 = pd.read_excel(filename, sheet_name=0, engine='openpyxl', dtype=str)
        df1.columns = df1.columns.str.strip()
        try:
            df2 = pd.read_excel(filename, sheet_name=1, engine='openpyxl', dtype=str)
            df2.columns = df2.columns.str.strip()
        except:
            df2 = pd.DataFrame()

        for _, row in df1.iterrows():
            brand_raw = str(row.get('Brand', '')).strip()
            if not brand_raw or brand_raw.lower() == 'nan': continue
            brand_key = brand_raw.lower()
            sellers = set()
            if 'Sellers' in row and pd.notna(row['Sellers']):
                s = str(row['Sellers']).strip()
                if s.lower() != 'nan': sellers.add(s.lower())
            for col in df1.columns:
                if 'Unnamed' in col or col == 'Sellers':
                    val = str(row[col]).strip()
                    if val and val.lower() != 'nan' and col != 'Brand' and col != 'check name':
                          sellers.add(val.lower())
            config[brand_key] = {'sellers': sellers, 'categories': None}

        if not df2.empty:
            for col in df2.columns:
                brand_header_key = str(col).strip().lower()
                if brand_header_key in config:
                    cats = df2[col].dropna().astype(str).apply(clean_category_code).tolist()
                    if cats: config[brand_header_key]['categories'] = set(cats)
        return config
    except Exception as e:
        logger.error(f"Error loading restricted brands: {e}")
        return {}

@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    try:
        return {
            'Restricted brands': ('1000024 - Product does not have a license to be sold via Jumia (Not Authorized)', "This brand is restricted and can only be sold by authorized sellers."),
            'Seller Not approved to sell Refurb': ('1000028 - Kindly Contact Jumia Seller Support', "Please contact Jumia Seller Support and raise a claim to confirm whether this product is eligible for listing."),
            'BRAND name repeated in NAME': ('1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name', "Please do not write the brand name in the Product Name field."),
            'Missing COLOR': ('1000005 - Kindly confirm the actual product colour', "Please make sure that the product color is clearly mentioned in both the title and in the color tab."),
            'Duplicate product': ('1000007 - Other Reason', "Kindly avoid creating duplicate SKUs. Please consolidate variations into a single listing."),
            'Prohibited products': ('1000024 - Product does not have a license', "Your product listing has been rejected due to the absence of a required license."),
            'Single-word NAME': ('1000008 - Kindly Improve Product Name Description', "Kindly update the product title using this format: Name – Type – Color."),
            'Unnecessary words in NAME': ('1000008 - Kindly Improve Product Name Description', "Kindly update the product title and avoid unnecessary keywords."),
            'Generic BRAND Issues': ('1000014 - Creation of brand name required', "To create the actual brand name for this product, please fill out the form at: https://bit.ly/2kpjja8"),
            'Counterfeit Sneakers': ('1000030 - Suspected Counterfeit/Fake Product', "This product is suspected to be counterfeit or fake."),
            'Seller Approve to sell books': ('1000028 - Kindly Contact Seller Support', "Please contact Seller Support to confirm eligibility for this category."),
            'Seller Approved to Sell Perfume': ('1000028 - Kindly Contact Seller Support', "Please contact Seller Support to confirm eligibility for this category."),
            'Suspected counterfeit Jerseys': ('1000030 - Suspected Counterfeit/Fake Product', "This product is suspected to be counterfeit."),
            'Suspected Fake product': ('1000030 - Suspected Counterfeit/Fake Product', "This product is suspected to be counterfeit."),
            'Product Warranty': ('1000013 - Kindly Provide Product Warranty Details', "Listing this product requires a valid warranty as per platform guidelines."),
            'Sensitive words': ('1000001 - Brand NOT Allowed', "Includes banned brands (Chanel, Rolex, etc)."),
            'Poor Images': ('1000017 - Low Quality Image', "Image rejected: Blurry, too dark, has glare, or low resolution (<300px)."),
            'Generic branded products with genuine brands': ('1000014 - Kindly request for the creation of this product\'s actual brand name by filling this form: https://bit.ly/2kpjja8', "Kindly use the correct brand in the Brand field instead of using Generic"),
        }
    except Exception: return {}

@st.cache_data(ttl=3600)
def load_all_support_files() -> Dict:
    files = {
        'blacklisted_words': load_txt_file('blacklisted.txt'),
        'book_category_codes': load_excel_file('Books_cat.xlsx', 'CategoryCode'),
        'approved_book_sellers': load_excel_file('Books_Approved_Sellers.xlsx', 'SellerName'),
        'perfume_category_codes': load_txt_file('Perfume_cat.txt'),
        'sensitive_perfume_brands': [b.lower() for b in load_txt_file('sensitive_perfumes.txt')],
        'approved_perfume_sellers': load_excel_file('perfumeSellers.xlsx', 'SellerName'),
        'sneaker_category_codes': load_txt_file('Sneakers_Cat.txt'),
        'sneaker_sensitive_brands': [b.lower() for b in load_txt_file('Sneakers_Sensitive.txt')],
        'sensitive_words': [w.lower() for w in load_txt_file('sensitive_words.txt')],
        'unnecessary_words': [w.lower() for w in load_txt_file('unnecessary.txt')],
        'colors': [c.lower() for c in load_txt_file('colors.txt')],
        'color_categories': load_txt_file('color_cats.txt'),
        'category_fas': load_excel_file('category_FAS.xlsx'),
        'reasons': load_excel_file('reasons.xlsx'),
        'flags_mapping': load_flags_mapping(),
        'jerseys_config': load_excel_file('Jerseys.xlsx'),
        'warranty_category_codes': load_txt_file('warranty.txt'),
        'suspected_fake': load_excel_file('suspected_fake.xlsx'),
        'approved_refurb_sellers_ke': [s.lower() for s in load_txt_file('Refurb_LaptopKE.txt')],
        'approved_refurb_sellers_ug': [s.lower() for s in load_txt_file('Refurb_LaptopUG.txt')],
        'duplicate_exempt_codes': load_txt_file('duplicate_exempt.txt'),
        'restricted_brands_config': load_restricted_brands_config('restric_brands.xlsx'),
        'known_brands': [line.strip().lower() for line in load_txt_file('brands.txt') if line.strip()],
    }
    return files

@st.cache_data(ttl=3600)
def load_support_files_lazy():
    """Lazy load support files only when needed."""
    with st.spinner("Loading configuration files..."):
        support_files = load_all_support_files()
    if not support_files.get('flags_mapping'):
        st.error("Critical: flags.xlsx could not be loaded or is empty.")
        st.stop()
    return support_files

@st.cache_data(ttl=3600)
def compile_regex_patterns(words: List[str]) -> re.Pattern:
    if not words: return None
    words = sorted(words, key=len, reverse=True)
    pattern = '|'.join(r'\b' + re.escape(w) + r'\b' for w in words)
    return re.compile(pattern, re.IGNORECASE)

# -------------------------------------------------
# Country & Helper Classes
# -------------------------------------------------
class CountryValidator:
    COUNTRY_CONFIG = {
        "Kenya": {"code": "KE", "skip_validations": [], "prohibited_products_file": "prohibited_productsKE.txt"},
        "Uganda": {"code": "UG", "skip_validations": ["Seller Approve to sell books", "Seller Approved to Sell Perfume", "Counterfeit Sneakers", "Product Warranty"], "prohibited_products_file": "prohibited_productsUG.txt"}
    }
    
    def __init__(self, country: str):
        self.country = country
        self.config = self.COUNTRY_CONFIG.get(country, self.COUNTRY_CONFIG["Kenya"])
        self.code = self.config["code"]
        self.skip_validations = self.config["skip_validations"]
    
    def should_skip_validation(self, validation_name: str) -> bool:
        return validation_name in self.skip_validations
    
    def ensure_status_column(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty: return df
        if 'Status' not in df.columns: df['Status'] = 'Approved'
        return df
    
    @st.cache_data(ttl=3600)
    def load_prohibited_products(_self) -> List[str]:
        return [w.lower() for w in load_txt_file(_self.config["prohibited_products_file"])]

# -------------------------------------------------
# Data Loading & Validation Functions
# -------------------------------------------------
def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.rename(columns=NEW_FILE_MAPPING)
    if 'ACTIVE_STATUS_COUNTRY' in df.columns:
        df['ACTIVE_STATUS_COUNTRY'] = (
            df['ACTIVE_STATUS_COUNTRY'].astype(str).str.lower()
            .str.replace('jumia-', '', regex=False).str.strip().str.upper()
        )
    for col in ['ACTIVE_STATUS_COUNTRY', 'CATEGORY_CODE', 'BRAND', 'TAX_CLASS']:
        if col in df.columns: df[col] = df[col].astype('category')
    return df

def validate_input_schema(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    errors = []
    required = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'ACTIVE_STATUS_COUNTRY']
    for field in required:
        if field not in df.columns: errors.append(f"Missing: {field}")
    return len(errors) == 0, errors

def filter_by_country(df: pd.DataFrame, country_validator: CountryValidator, source: str) -> pd.DataFrame:
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns: return df
    df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.strip().str.upper()
    mask = df['ACTIVE_STATUS_COUNTRY'] == country_validator.code
    filtered = df[mask].copy()
    if filtered.empty:
        st.error(f"No {country_validator.code} rows left in {source}")
        st.stop()
    return filtered

def propagate_metadata(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    cols = ['COLOR_FAMILY', 'PRODUCT_WARRANTY', 'WARRANTY_DURATION', 'WARRANTY_ADDRESS', 'WARRANTY_TYPE']
    for col in cols:
        if col not in df.columns: df[col] = pd.NA
        df[col] = df.groupby('PRODUCT_SET_SID')[col].transform(lambda x: x.ffill().bfill())
    return df

# --- Validation Logic Functions ---

def check_poor_images(data: pd.DataFrame, max_workers: int = 10) -> pd.DataFrame:
    """
    Downloads images and checks for:
    1. Low Resolution (< 300x300)
    2. Blurriness (Laplacian Variance < 100)
    3. Darkness (Mean Brightness < 50)
    4. Flash Glare (Too many blown-out pixels)
    """
    if 'MAIN_IMAGE' not in data.columns:
        return pd.DataFrame(columns=data.columns)

    # Filter only rows with valid URLs
    valid_data = data[data['MAIN_IMAGE'].notna() & (data['MAIN_IMAGE'].str.strip() != '')].copy()
    if valid_data.empty:
        return pd.DataFrame(columns=data.columns)

    # Helper function to process a single image
    def analyze_image_quality(row_data):
        sid = row_data[0]
        url = row_data[1]
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, timeout=5, headers=headers)
            if resp.status_code != 200:
                return None # Could not check, skip rejection logic or handle as broken link
            
            # Convert bytes to numpy array for OpenCV
            image_array = np.asarray(bytearray(resp.content), dtype="uint8")
            img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            
            if img is None: return None

            h, w, _ = img.shape
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 1. Resolution Check
            if h < 300 or w < 300:
                return (sid, f"Low Resolution ({w}x{h})")

            # 2. Blurriness Check (Laplacian Variance)
            blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
            if blur_score < 100:
                return (sid, f"Blurry (Score: {int(blur_score)})")

            # 3. Darkness Check
            avg_brightness = np.mean(gray)
            if avg_brightness < 40:
                return (sid, f"Too Dark (Brightness: {int(avg_brightness)})")

            # 4. Glare Check (Pixels > 250)
            _, bright_mask = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY)
            bright_ratio = np.count_nonzero(bright_mask) / gray.size
            if bright_ratio > 0.05: # >5% pure white
                return (sid, "Flash/Glare Detected")

            return None # Pass
            
        except Exception:
            return None

    # Run in parallel
    rejected_reasons = {}
    rows_to_process = list(zip(valid_data['PRODUCT_SET_SID'], valid_data['MAIN_IMAGE']))
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(analyze_image_quality, rows_to_process)
        
        for res in results:
            if res:
                sid, reason = res
                rejected_reasons[sid] = reason

    # Filter and return data
    if not rejected_reasons:
        return pd.DataFrame(columns=data.columns)
        
    mask = data['PRODUCT_SET_SID'].isin(rejected_reasons.keys())
    result_df = data[mask].drop_duplicates(subset=['PRODUCT_SET_SID']).copy()
    
    # Add the specific failure reason to the Comment Detail if needed
    result_df['Comment_Detail'] = result_df['PRODUCT_SET_SID'].map(rejected_reasons)
    
    return result_df

def check_restricted_brands(data: pd.DataFrame, restricted_config: Dict) -> pd.DataFrame:
    if not all(c in data.columns for c in ['NAME', 'BRAND', 'SELLER_NAME']) or not restricted_config:
        return pd.DataFrame(columns=data.columns)

    data_to_check = data.copy()
    data_to_check['NAME_LOWER'] = data_to_check['NAME'].astype(str).str.lower().str.strip()
    data_to_check['BRAND_LOWER'] = data_to_check['BRAND'].astype(str).str.lower().str.strip()
    data_to_check['SELLER_LOWER'] = data_to_check['SELLER_NAME'].astype(str).str.lower().str.strip()
    data_to_check['CAT_CODE_CLEAN'] = data_to_check['CATEGORY_CODE'].apply(clean_category_code)

    flagged_indices = set()
    for brand_key, rules in restricted_config.items():
        pattern = re.compile(r'\b' + re.escape(brand_key) + r'\b', re.IGNORECASE)
        mask_match = (data_to_check['BRAND_LOWER'].str.contains(pattern, regex=True) |
                      data_to_check['NAME_LOWER'].str.contains(pattern, regex=True))
        potential_rows = data_to_check[mask_match]
        
        if potential_rows.empty: continue
        
        restricted_cats = rules.get('categories')
        if restricted_cats:
            target_rows = potential_rows[potential_rows['CAT_CODE_CLEAN'].isin(restricted_cats)]
        else:
            target_rows = potential_rows
            
        if target_rows.empty: continue

        allowed_sellers = rules.get('sellers', set())
        if not allowed_sellers:
            flagged_indices.update(target_rows.index)
        else:
            mask_unauthorized = ~target_rows['SELLER_LOWER'].isin(allowed_sellers)
            flagged_indices.update(target_rows[mask_unauthorized].index)

    if not flagged_indices: return pd.DataFrame(columns=data.columns)
    return data.loc[list(flagged_indices)].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_refurb_seller_approval(data: pd.DataFrame, approved_sellers_ke: List[str], approved_sellers_ug: List[str], country_code: str) -> pd.DataFrame:
    if country_code == 'KE': approved_sellers = set(approved_sellers_ke)
    elif country_code == 'UG': approved_sellers = set(approved_sellers_ug)
    else: return pd.DataFrame(columns=data.columns)
    
    if not {'NAME', 'BRAND', 'SELLER_NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    
    data = data.copy()
    refurb_words = r'\b(refurb|refurbished|renewed)\b'
    data['NAME_LOWER'] = data['NAME'].astype(str).str.strip().str.lower()
    data['SELLER_LOWER'] = data['SELLER_NAME'].astype(str).str.strip().str.lower()
    
    trigger_mask = data['NAME_LOWER'].str.contains(refurb_words, regex=True, na=False) | (data['BRAND'].astype(str).str.lower() == 'renewed')
    triggered_data = data[trigger_mask].copy()
    if triggered_data.empty: return pd.DataFrame(columns=data.columns)
    
    return triggered_data[~triggered_data['SELLER_LOWER'].isin(approved_sellers)].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_unnecessary_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    data.loc[mask, 'Comment_Detail'] = "Matched keyword in Name"
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_product_warranty(data: pd.DataFrame, warranty_category_codes: List[str]) -> pd.DataFrame:
    for col in ['PRODUCT_WARRANTY', 'WARRANTY_DURATION']:
        if col not in data.columns: data[col] = ""
        data[col] = data[col].astype(str).fillna('').str.strip()
    if not warranty_category_codes: return pd.DataFrame(columns=data.columns)
    
    data['CAT_CLEAN'] = data['CATEGORY_CODE'].apply(clean_category_code)
    target_cats = [clean_category_code(c) for c in warranty_category_codes]
    target_data = data[data['CAT_CLEAN'].isin(target_cats)].copy()
    if target_data.empty: return pd.DataFrame(columns=data.columns)
    
    def is_present(series):
        s = series.astype(str).str.strip().str.lower()
        return (s != 'nan') & (s != '') & (s != 'none') & (s != 'nat') & (s != 'n/a')
    
    mask = ~(is_present(target_data['PRODUCT_WARRANTY']) | is_present(target_data['WARRANTY_DURATION']))
    flagged = target_data[mask]
    if 'CAT_CLEAN' in flagged.columns: flagged = flagged.drop(columns=['CAT_CLEAN'])
    return flagged.drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_missing_color(data: pd.DataFrame, pattern: re.Pattern, color_categories: List[str], country_code: str) -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    config_cats = set(clean_category_code(c) for c in color_categories)
    target = data[data_cats.isin(config_cats)].copy()
    if target.empty: return pd.DataFrame(columns=data.columns)
        
    has_color_col = 'COLOR' in data.columns
    def is_color_missing(row):
        name_val = str(row['NAME'])
        if pattern.search(name_val): return False
        if has_color_col:
            color_val = str(row['COLOR'])
            if color_val.strip().lower() not in ['nan', '', 'none', 'null']: return False
        return True

    mask = target.apply(is_color_missing, axis=1)
    return target[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_sensitive_words(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_prohibited_products(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    if not {'NAME'}.issubset(data.columns) or pattern is None: return pd.DataFrame(columns=data.columns)
    mask = data['NAME'].astype(str).str.strip().str.lower().str.contains(pattern, na=False)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_brand_in_name(data: pd.DataFrame) -> pd.DataFrame:
    if not {'BRAND','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    mask = data.apply(lambda r: str(r['BRAND']).strip().lower() in str(r['NAME']).strip().lower()
                      if pd.notna(r['BRAND']) and pd.notna(r['NAME']) else False, axis=1)
    return data[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_seller_approved_for_books(data: pd.DataFrame, book_category_codes: List[str], approved_book_sellers: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    book_cats = set(clean_category_code(c) for c in book_category_codes)
    books = data[data_cats.isin(book_cats)]
    return books[~books['SELLER_NAME'].isin(approved_book_sellers)].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_seller_approved_for_perfume(data: pd.DataFrame, perfume_category_codes: List[str], approved_perfume_sellers: List[str], sensitive_perfume_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','SELLER_NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    perfume_cats = set(clean_category_code(c) for c in perfume_category_codes)
    perfume_data = data[data_cats.isin(perfume_cats)].copy()
    if perfume_data.empty: return pd.DataFrame(columns=data.columns)
    
    brand_lower = perfume_data['BRAND'].astype(str).str.strip().str.lower()
    name_lower = perfume_data['NAME'].astype(str).str.strip().str.lower()
    
    sensitive_mask = brand_lower.isin(sensitive_perfume_brands)
    fake_brands = ['designers collection', 'smart collection', 'generic', 'original', 'fashion']
    fake_brand_mask = brand_lower.isin(fake_brands)
    name_contains_sensitive = name_lower.apply(lambda x: any(brand in x for brand in sensitive_perfume_brands))
    
    final_mask = (sensitive_mask | (fake_brand_mask & name_contains_sensitive)) & (~perfume_data['SELLER_NAME'].isin(approved_perfume_sellers))
    return perfume_data[final_mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_counterfeit_sneakers(data: pd.DataFrame, sneaker_category_codes: List[str], sneaker_sensitive_brands: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'NAME', 'BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    sneaker_cats = set(clean_category_code(c) for c in sneaker_category_codes)
    sneaker_data = data[data_cats.isin(sneaker_cats)].copy()
    if sneaker_data.empty: return pd.DataFrame(columns=data.columns)
    
    brand_lower = sneaker_data['BRAND'].astype(str).str.strip().str.lower()
    name_lower = sneaker_data['NAME'].astype(str).str.strip().str.lower()
    
    fake_brand_mask = brand_lower.isin(['generic', 'fashion'])
    name_contains_brand = name_lower.apply(lambda x: any(brand in x for brand in sneaker_sensitive_brands))
    
    return sneaker_data[fake_brand_mask & name_contains_brand].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_suspected_fake_products(data: pd.DataFrame, suspected_fake_df: pd.DataFrame, fx_rate: float = 132.0) -> pd.DataFrame:
    required_cols = ['CATEGORY_CODE', 'BRAND', 'GLOBAL_SALE_PRICE', 'GLOBAL_PRICE']
    if not all(c in data.columns for c in required_cols) or suspected_fake_df.empty: return pd.DataFrame(columns=data.columns)
    
    try:
        ref_data = suspected_fake_df.copy()
        brand_cols = [col for col in ref_data.columns if col not in ['Unnamed: 0', 'Brand', 'Price'] and pd.notna(col)]
        brand_category_price = {}
        for brand in brand_cols:
            try:
                price_threshold = pd.to_numeric(ref_data[brand].iloc[0], errors='coerce')
                if pd.isna(price_threshold) or price_threshold <= 0: continue
            except: continue
            categories = ref_data[brand].iloc[1:].dropna()
            brand_lower = brand.strip().lower()
            for cat in categories:
                cat_str = str(cat).strip()
                cat_base = cat_str.split('.')[0]
                if cat_base and cat_base.lower() != 'nan':
                    key = (brand_lower, cat_base)
                    brand_category_price[key] = price_threshold
        
        if not brand_category_price: return pd.DataFrame(columns=data.columns)
        
        check_data = data.copy()
        check_data['price_to_use'] = check_data['GLOBAL_SALE_PRICE'].where(
            (check_data['GLOBAL_SALE_PRICE'].notna()) & (pd.to_numeric(check_data['GLOBAL_SALE_PRICE'], errors='coerce') > 0),
            check_data['GLOBAL_PRICE']
        )
        check_data['price_to_use'] = pd.to_numeric(check_data['price_to_use'], errors='coerce').fillna(0)
        check_data['BRAND_LOWER'] = check_data['BRAND'].astype(str).str.strip().str.lower()
        check_data['CAT_BASE'] = check_data['CATEGORY_CODE'].apply(clean_category_code)
        
        def is_suspected_fake(row):
            key = (row['BRAND_LOWER'], row['CAT_BASE'])
            if key in brand_category_price:
                return row['price_to_use'] < brand_category_price[key]
            return False
        
        check_data['is_fake'] = check_data.apply(is_suspected_fake, axis=1)
        return check_data[check_data['is_fake'] == True][data.columns].drop_duplicates(subset=['PRODUCT_SET_SID'])
    except Exception as e:
        logger.error(f"Error in suspected fake: {e}")
        return pd.DataFrame(columns=data.columns)

def check_single_word_name(data: pd.DataFrame, book_category_codes: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','NAME'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    book_cats = set(clean_category_code(c) for c in book_category_codes)
    non_books = data[~data_cats.isin(book_cats)]
    return non_books[non_books['NAME'].astype(str).str.split().str.len() == 1].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_generic_brand_issues(data: pd.DataFrame, valid_category_codes_fas: List[str]) -> pd.DataFrame:
    if not {'CATEGORY_CODE','BRAND'}.issubset(data.columns): return pd.DataFrame(columns=data.columns)
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    fas_cats = set(clean_category_code(c) for c in valid_category_codes_fas)
    return data[data_cats.isin(fas_cats) & (data['BRAND']=='Generic')].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_counterfeit_jerseys(data: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    if not {'CATEGORY_CODE', 'NAME', 'SELLER_NAME'}.issubset(data.columns) or jerseys_df.empty: return pd.DataFrame(columns=data.columns)
    jersey_cats = [clean_category_code(c) for c in jerseys_df['Categories'].astype(str).unique() if c.lower() != 'nan']
    keywords = [w for w in jerseys_df['Checklist'].astype(str).str.strip().str.lower().unique() if w and w!='nan']
    exempt = [s for s in jerseys_df['Exempted'].astype(str).str.strip().unique() if s and s.lower()!='nan']
    
    if not jersey_cats or not keywords: return pd.DataFrame(columns=data.columns)
    regex = re.compile('|'.join(r'\b' + re.escape(w) + r'\b' for w in keywords), re.IGNORECASE)
    
    data_cats = data['CATEGORY_CODE'].apply(clean_category_code)
    jerseys = data[data_cats.isin(jersey_cats)].copy()
    if jerseys.empty: return pd.DataFrame(columns=data.columns)
    
    target = jerseys[~jerseys['SELLER_NAME'].isin(exempt)].copy()
    mask = target['NAME'].astype(str).str.strip().str.lower().str.contains(regex, na=False)
    return target[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])

def check_generic_with_brand_in_name(data: pd.DataFrame, brands_list: List[str]) -> pd.DataFrame:
    """
    Flags products where BRAND is 'Generic' but the NAME starts with 
    a known brand from brands.txt.
    """
    if not {'NAME', 'BRAND'}.issubset(data.columns) or not brands_list:
        return pd.DataFrame(columns=data.columns)

    # 1. Filter for Generic items only
    is_generic = data['BRAND'].astype(str).str.strip().str.lower() == 'generic'
    generic_items = data[is_generic].copy()
    
    if generic_items.empty:
        return pd.DataFrame(columns=data.columns)

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
                if len(name_clean) > len(brand_clean):
                    next_char = name_clean[len(brand_clean)]
                    if next_char.isalnum():
                        continue 
                
                return brand.title() # Return nice Title Case
        return None

    # 3. Run Detection
    generic_items['Detected_Brand'] = generic_items['NAME'].apply(detect_brand)
    
    # 4. Filter only those that matched
    flagged = generic_items[generic_items['Detected_Brand'].notna()].copy()
    
    if not flagged.empty:
        flagged['Comment_Detail'] = "Detected Brand: " + flagged['Detected_Brand']
        
    return flagged.drop_duplicates(subset=['PRODUCT_SET_SID'])

# -------------------------------------------------
# Master validation runner
# -------------------------------------------------
def validate_products(data: pd.DataFrame, support_files: Dict, country_validator: CountryValidator, data_has_warranty_cols: bool, common_sids: Optional[set] = None, use_image_hash: bool = True, perform_quality_check: bool = True):
    # Ensure ID match compatibility
    data['PRODUCT_SET_SID'] = data['PRODUCT_SET_SID'].astype(str).str.strip()
    
    flags_mapping = support_files['flags_mapping']
    
    validations = [
        ("Restricted brands", check_restricted_brands, {'restricted_config': support_files['restricted_brands_config']}),
        ("Poor Images", check_poor_images, {'max_workers': 10}),
        ("Suspected Fake product", check_suspected_fake_products, {'suspected_fake_df': support_files['suspected_fake'], 'fx_rate': FX_RATE}),
        ("Seller Not approved to sell Refurb", check_refurb_seller_approval, {
            'approved_sellers_ke': support_files['approved_refurb_sellers_ke'],
            'approved_sellers_ug': support_files['approved_refurb_sellers_ug'],
            'country_code': country_validator.code
        }),
        ("Product Warranty", check_product_warranty, {'warranty_category_codes': support_files['warranty_category_codes']}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': support_files['book_category_codes'], 'approved_book_sellers': support_files['approved_book_sellers']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'perfume_category_codes': support_files['perfume_category_codes'], 'approved_perfume_sellers': support_files['approved_perfume_sellers'], 'sensitive_perfume_brands': support_files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'sneaker_category_codes': support_files['sneaker_category_codes'], 'sneaker_sensitive_brands': support_files['sneaker_sensitive_brands']}),
        ("Suspected counterfeit Jerseys", check_counterfeit_jerseys, {'jerseys_df': support_files['jerseys_config']}),
        ("Prohibited products", check_prohibited_products, {'pattern': compile_regex_patterns(country_validator.load_prohibited_products())}),
        ("Unnecessary words in NAME", check_unnecessary_words, {'pattern': compile_regex_patterns(support_files['unnecessary_words'])}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': support_files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Generic branded products with genuine brands", check_generic_with_brand_in_name, {'brands_list': support_files.get('known_brands', [])}),
        ("Missing COLOR", check_missing_color, {'pattern': compile_regex_patterns(support_files['colors']), 'color_categories': support_files['color_categories']}),
        ("Duplicate product", check_duplicate_products, {
            'exempt_categories': support_files.get('duplicate_exempt_codes', []),
            'known_colors': support_files['colors'],
            'use_image_hash': use_image_hash
        }),
    ]
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    results = {}
    
    duplicate_groups = {}
    cols_for_dup = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    if len(cols_for_dup) == 4:
        data_temp = data.copy()
        data_temp['dup_key'] = data_temp[cols_for_dup].apply(
            lambda r: tuple(str(v).strip().lower() for v in r), axis=1
        )
        dup_counts = data_temp.groupby('dup_key')['PRODUCT_SET_SID'].apply(list).to_dict()
        for dup_key, sid_list in dup_counts.items():
            if len(sid_list) > 1:
                for sid in sid_list:
                    duplicate_groups[sid] = sid_list
    
    restricted_issue_keys = {}

    for i, (name, func, kwargs) in enumerate(validations):
        if name == "Restricted brands" and country_validator.code != 'KE': continue

        # CHECKBOX LOGIC: Skip Poor Images if perform_quality_check is False
        if name == "Poor Images" and not perform_quality_check:
            continue

        if name != "Seller Not approved to sell Refurb" and country_validator.should_skip_validation(name):
            if name == "Sensitive words": continue
            if name == "Product Warranty" and country_validator.code == 'UG': continue
            if name == "Seller Approve to sell books" and country_validator.code == 'UG': continue
            if name == "Seller Approved to Sell Perfume" and country_validator.code == 'UG': continue
            if name == "Counterfeit Sneakers" and country_validator.code == 'UG': continue
            if country_validator.should_skip_validation(name): continue
        
        ckwargs = {'data': data, **kwargs}
        
        if name == "Product Warranty":
            if not data_has_warranty_cols: continue
            check_data = data.copy()
            if common_sids is not None and len(common_sids) > 0:
                check_data = check_data[check_data['PRODUCT_SET_SID'].isin(common_sids)]
            if check_data.empty: continue
            ckwargs = {'data': check_data, **kwargs}
        
        elif name == "Missing COLOR":
            if common_sids is not None and len(common_sids) > 0:
                check_data = data[data['PRODUCT_SET_SID'].isin(common_sids)].copy()
                if check_data.empty: continue
                ckwargs = {'data': check_data, **kwargs}
        
        status_text.text(f"Running: {name}")
        
        if name == "Generic BRAND Issues":
            fas = support_files.get('category_fas', pd.DataFrame())
            ckwargs['valid_category_codes_fas'] = fas['ID'].astype(str).tolist() if not fas.empty and 'ID' in fas.columns else []
        elif name == "Missing COLOR":
            ckwargs['country_code'] = country_validator.code
        
        try:
            res = func(**ckwargs)
            if name != "Duplicate product" and not res.empty and 'PRODUCT_SET_SID' in res.columns:
                res['PRODUCT_SET_SID'] = res['PRODUCT_SET_SID'].astype(str).str.strip()
                
                if name in ["Seller Approve to sell books", "Seller Approved to Sell Perfume", "Counterfeit Sneakers", "Seller Not approved to sell Refurb", "Restricted brands"]:
                    res['match_key'] = res.apply(create_match_key, axis=1)
                    if name not in restricted_issue_keys: restricted_issue_keys[name] = set()
                    restricted_issue_keys[name].update(res['match_key'].unique())

                flagged_sids = set(res['PRODUCT_SET_SID'].unique())
                expanded_sids = set()
                for sid in flagged_sids:
                    if sid in duplicate_groups:
                        expanded_sids.update(duplicate_groups[sid])
                    else:
                        expanded_sids.add(sid)
                res = data[data['PRODUCT_SET_SID'].isin(expanded_sids)].copy()
                
                # IMPORTANT: Retain the Comment_Detail column if it was generated
                if 'Comment_Detail' not in res.columns and 'Comment_Detail' in res:
                    res['Comment_Detail'] = res['Comment_Detail']
            
            results[name] = res if not res.empty else pd.DataFrame(columns=data.columns)
        except Exception as e:
            logger.error(f"Error in {name}: {e}\n{traceback.format_exc()}")
            results[name] = pd.DataFrame(columns=data.columns)
        
        progress_bar.progress((i + 1) / len(validations))
    
    if restricted_issue_keys:
        data['match_key'] = data.apply(create_match_key, axis=1)
        for flag_name, keys in restricted_issue_keys.items():
            extra_rows = data[data['match_key'].isin(keys)].copy()
            if flag_name in results:
                existing = results[flag_name]
                combined = pd.concat([existing, extra_rows]).drop_duplicates(subset=['PRODUCT_SET_SID'])
                results[flag_name] = combined
            else:
                results[flag_name] = extra_rows

    status_text.text("Finalizing...")
    rows = []
    processed = set()
    
    for name, _, _ in validations:
        if name not in results or results[name].empty:
            continue
        res = results[name]
        if 'PRODUCT_SET_SID' not in res.columns:
            continue
        
        if name == "Seller Not approved to sell Refurb":
            reason_info = flags_mapping.get(name, ("1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim", f"Flagged by {name}"))
        else:
            reason_info = flags_mapping.get(name, ("1000007 - Other Reason", f"Flagged by {name}"))
        
        res['PRODUCT_SET_SID'] = res['PRODUCT_SET_SID'].astype(str).str.strip()
        
        # Merge back with original data to get all columns if needed, though 'res' should already have them
        # We also want to capture the specific comment detail if it exists in 'res'
        flagged = pd.merge(res[['PRODUCT_SET_SID', 'Comment_Detail']] if 'Comment_Detail' in res.columns else res[['PRODUCT_SET_SID']], 
                           data, on='PRODUCT_SET_SID', how='left')
        
        # If Comment_Detail was lost in merge or didn't exist in 'res', try to recover or default
        if 'Comment_Detail' not in flagged.columns and 'Comment_Detail' in res.columns:
             flagged['Comment_Detail'] = res['Comment_Detail']
        
        for _, r in flagged.iterrows():
            sid = str(r['PRODUCT_SET_SID']).strip()
            if sid in processed:
                continue
            processed.add(sid)
            
            # Construct the final comment
            base_comment = reason_info[1]
            detail = r.get('Comment_Detail', '')
            # Ensure detail is string and not nan
            if pd.isna(detail): detail = ''
            final_comment = f"{base_comment} ({detail})" if detail else base_comment

            rows.append({
                'ProductSetSid': sid,
                'ParentSKU': r.get('PARENTSKU', ''),
                'Status': 'Rejected',
                'Reason': reason_info[0],
                'Comment': final_comment,
                'FLAG': name,
                'SellerName': r.get('SELLER_NAME', '')
            })
    
    approved = data[~data['PRODUCT_SET_SID'].astype(str).str.strip().isin(processed)]
    for _, r in approved.iterrows():
        sid = str(r['PRODUCT_SET_SID']).strip()
        if sid not in processed:
            rows.append({
                'ProductSetSid': sid,
                'ParentSKU': r.get('PARENTSKU', ''),
                'Status': 'Approved',
                'Reason': "",
                'Comment': "",
                'FLAG': "",
                'SellerName': r.get('SELLER_NAME', '')
            })
            processed.add(sid)
    
    progress_bar.empty()
    status_text.empty()
    
    final_df = pd.DataFrame(rows)
    # Ensure required columns exist to prevent KeyErrors downstream
    expected_cols = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]
    for c in expected_cols:
        if c not in final_df.columns:
            final_df[c] = ""
            
    return country_validator.ensure_status_column(final_df), results

# -------------------------------------------------
# Export Logic
# -------------------------------------------------
def prepare_full_data_merged(data_df, final_report_df):
    try:
        d_cp = data_df.copy()
        r_cp = final_report_df.copy()
        d_cp['PRODUCT_SET_SID'] = d_cp['PRODUCT_SET_SID'].astype(str).str.strip()
        r_cp['ProductSetSid'] = r_cp['ProductSetSid'].astype(str).str.strip()
        merged = pd.merge(d_cp, r_cp[["ProductSetSid", "Status", "Reason", "Comment", "FLAG", "SellerName"]], left_on="PRODUCT_SET_SID", right_on="ProductSetSid", how='left')
        if 'ProductSetSid_y' in merged.columns: merged.drop(columns=['ProductSetSid_y'], inplace=True)
        if 'ProductSetSid_x' in merged.columns: merged.rename(columns={'ProductSetSid_x': 'PRODUCT_SET_SID'}, inplace=True)
        return merged
    except Exception: return pd.DataFrame()

def to_excel_base(df, sheet, cols, writer, format_rules=False):
    df_p = df.copy()
    for c in cols:
        if c not in df_p.columns: df_p[c] = pd.NA
    df_to_write = df_p[[c for c in cols if c in df_p.columns]]
    df_to_write.to_excel(writer, index=False, sheet_name=sheet)
    if format_rules and 'Status' in df_to_write.columns:
        workbook = writer.book
        worksheet = writer.sheets[sheet]
        red_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        green_fmt = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        status_idx = df_to_write.columns.get_loc('Status')
        worksheet.conditional_format(1, status_idx, len(df_to_write), status_idx, {'type': 'cell', 'criteria': 'equal', 'value': '"Rejected"', 'format': red_fmt})
        worksheet.conditional_format(1, status_idx, len(df_to_write), status_idx, {'type': 'cell', 'criteria': 'equal', 'value': '"Approved"', 'format': green_fmt})

def write_excel_single(df, sheet_name, cols, auxiliary_df=None, aux_sheet_name=None, aux_cols=None, format_status=False, full_data_stats=False):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(df, sheet_name, cols, writer, format_rules=format_status)
        if auxiliary_df is not None and not auxiliary_df.empty:
            to_excel_base(auxiliary_df, aux_sheet_name, aux_cols, writer)
        if full_data_stats and 'SELLER_NAME' in df.columns:
            wb = writer.book
            ws = wb.add_worksheet('Sellers Data')
            fmt = wb.add_format({'bold': True, 'bg_color': '#E6F0FA', 'border': 1, 'align': 'center'})
            
            if 'STOCK_QTY' not in df.columns: df['STOCK_QTY'] = 0
            if 'SELLER_RATING' not in df.columns: df['SELLER_RATING'] = 0

            if 'Status' in df.columns:
                df['Rejected_Count'] = (df['Status'] == 'Rejected').astype(int)
                df['Approved_Count'] = (df['Status'] == 'Approved').astype(int)
                
                summ = df.groupby('SELLER_NAME').agg(
                    Rejected=('Rejected_Count', 'sum'),
                    Approved=('Approved_Count', 'sum')
                ).reset_index().sort_values('Rejected', ascending=False)
                
                summ.insert(0, 'Rank', range(1, len(summ) + 1))
                ws.write(0, 0, "Sellers Summary (This File)", fmt)
                summ.to_excel(writer, sheet_name='Sellers Data', startrow=1, index=False)
    
    output.seek(0)
    return output

def generate_smart_export(df, filename_prefix, export_type='simple', auxiliary_df=None):
    if export_type == 'full':
        cols = FULL_DATA_COLS + [c for c in ["Status", "Reason", "Comment", "FLAG", "SellerName"] if c not in FULL_DATA_COLS]
        sheet_name = "ProductSets"
    else:
        cols = PRODUCTSETS_COLS
        sheet_name = "ProductSets"
    if len(df) <= SPLIT_LIMIT:
        if export_type == 'full':
            data = write_excel_single(df, sheet_name, cols, format_status=True, full_data_stats=True)
        else:
            data = write_excel_single(df, sheet_name, cols, auxiliary_df=auxiliary_df, aux_sheet_name="RejectionReasons", aux_cols=REJECTION_REASONS_COLS, format_status=True)
        return data, f"{filename_prefix}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            chunk_count = 0
            for i in range(0, len(df), SPLIT_LIMIT):
                chunk = df.iloc[i : i + SPLIT_LIMIT]
                chunk_count += 1
                part_name = f"{filename_prefix}_Part_{chunk_count}.xlsx"
                if export_type == 'full':
                    excel_data = write_excel_single(chunk, sheet_name, cols, format_status=True, full_data_stats=True)
                else:
                    excel_data = write_excel_single(chunk, sheet_name, cols, auxiliary_df=auxiliary_df, aux_sheet_name="RejectionReasons", aux_cols=REJECTION_REASONS_COLS, format_status=True)
                zf.writestr(part_name, excel_data.getvalue())
        zip_buffer.seek(0)
        return zip_buffer, f"{filename_prefix}.zip", "application/zip"

def to_excel_flag_data(flag_df, flag_name):
    output = BytesIO()
    df_copy = flag_df.copy()
    df_copy['FLAG'] = flag_name
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(df_copy, "ProductSets", FULL_DATA_COLS, writer)
    output.seek(0)
    return output

def log_validation_run(country, file, total, app, rej):
    try:
        entry = {'timestamp': datetime.now().isoformat(), 'country': country, 'file': file, 'total': total, 'approved': app, 'rejected': rej}
        with open('validation_audit.jsonl', 'a') as f: f.write(json.dumps(entry)+'\n')
    except: pass

# -------------------------------------------------
# UI
# -------------------------------------------------
if 'layout_mode' not in st.session_state:
    st.session_state.layout_mode = "centered"

try:
    st.set_page_config(
        page_title="Product Validation Tool",
        layout=st.session_state.layout_mode
    )
except:
    pass

st.title("Product Validation Tool")
st.markdown("---") 
try:
    with st.sidebar:
        st.header("Display Settings")
        layout_choice = st.radio("Layout Mode", ["Centered (Mobile-Friendly)", "Wide (Desktop-Optimized)"])
        new_mode = "wide" if "Wide" in layout_choice else "centered"
        if new_mode != st.session_state.layout_mode:
            st.session_state.layout_mode = new_mode
            st.rerun()
        
        st.header("Performance Settings")
        use_image_hash = st.checkbox("Enable Image Hashing (for duplicate detection)", value=True, 
                                     help="Disable for faster processing on large datasets")
        
        # --- NEW TOGGLE HERE ---
        check_image_quality = st.checkbox("Enable Quality Check (Blur/Glare)", value=True, 
                                          help="Analyze image quality (slow). Uncheck to skip.")
        
        st.caption("⚡ Disabling hashing/quality checks speeds up processing significantly")
        
        if st.button("🧹 Clear Image Cache", help="Free up memory by clearing cached image hashes"):
            clear_image_cache()
            st.success("Image cache cleared!")

        st.markdown("---")
        st.header("Debug Info")
        # Check if files loaded
        # We access support_files safely here
        try:
             # Lazy load happens in main body, but we can check if it exists in memory yet
             # If not, it will load when main body runs.
             pass
        except: pass
except:
    use_image_hash = True
    check_image_quality = True

# Load Configuration Files
try:
    support_files = load_support_files_lazy()
    
    # Optional Debug in Sidebar
    with st.sidebar:
        if 'known_brands' in support_files:
            count = len(support_files['known_brands'])
            st.write(f"Brands Loaded: **{count}**")
        else:
            st.error("brands.txt not loaded!")

except Exception as e:
    st.error(f"Failed to load configuration files: {e}")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Daily Validation", "Weekly Analysis", "Data Lake"])

# -------------------------------------------------
# TAB 1: DAILY VALIDATION
# -------------------------------------------------
with tab1:
    st.header("Daily Product Validation")
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
                            # --- ROBUST CSV LOADING LOGIC ---
                            # 1. Try reading with default comma
                            try:
                                raw_data = pd.read_csv(uploaded_file, dtype=str)
                                # 2. If it resulted in 1 column, it likely failed. Try semicolon.
                                if len(raw_data.columns) <= 1:
                                    uploaded_file.seek(0)
                                    raw_data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype=str)
                            except:
                                # 3. Fallback to semicolon if comma crashed
                                uploaded_file.seek(0)
                                raw_data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype=str)
                                
                        std_data = standardize_input_data(raw_data)
                        if 'PRODUCT_SET_SID' in std_data.columns:
                            std_data['PRODUCT_SET_SID'] = std_data['PRODUCT_SET_SID'].astype(str).str.strip()
                            file_sids_sets.append(set(std_data['PRODUCT_SET_SID'].unique()))
                        all_dfs.append(std_data)
                    except Exception as e:
                        st.error(f"Failed to read file {uploaded_file.name}: {e}")
                        st.stop()
                
                if not all_dfs:
                    st.error("No valid data loaded.")
                    st.stop()
                
                merged_data = pd.concat(all_dfs, ignore_index=True)
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
                    
                    with st.spinner("Running validations..."):
                        common_sids_to_pass = intersection_sids if intersection_count > 0 else None
                        final_report, flag_dfs = validate_products(
                            data, support_files, country_validator, data_has_warranty_cols, common_sids_to_pass, 
                            use_image_hash=use_image_hash, 
                            perform_quality_check=check_image_quality # Pass the UI state here
                        )
                        st.session_state.final_report = final_report
                        st.session_state.all_data_map = data
                        st.session_state.intersection_count = intersection_count
                        st.session_state.last_processed_files = current_file_signature
                        
                        approved_df = final_report[final_report['Status'] == 'Approved']
                        rejected_df = final_report[final_report['Status'] == 'Rejected']
                        log_validation_run(country, "Multi-Upload", len(data), len(approved_df), len(rejected_df))
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
            if not rejected_df.empty:
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
            else:
                st.success("No rejections found! All products approved.")

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

# -------------------------------------------------
# TAB 2: WEEKLY ANALYSIS
# -------------------------------------------------
with tab2:
    st.header("Weekly Analysis Dashboard")
    st.info("Upload multiple 'Full Data' files exported from the Daily tab to see aggregated trends.")
    weekly_files = st.file_uploader("Upload Full Data Files (XLSX/CSV)", accept_multiple_files=True, type=['xlsx', 'csv'], key="weekly_files", label_visibility="collapsed")
    if weekly_files:
        combined_df = pd.DataFrame()
        with st.spinner("Aggregating files..."):
            for f in weekly_files:
                try:
                    if f.name.endswith('.xlsx'):
                        try: df = pd.read_excel(f, sheet_name='ProductSets', engine='openpyxl', dtype=str)
                        except: f.seek(0); df = pd.read_excel(f, engine='openpyxl', dtype=str)
                    else: df = pd.read_csv(f, dtype=str)
                    df.columns = df.columns.str.strip()
                    df = standardize_input_data(df)
                    for col in ['Status', 'Reason', 'FLAG', 'SELLER_NAME', 'CATEGORY', 'PRODUCT_SET_SID']:
                        if col not in df.columns: df[col] = pd.NA
                    combined_df = pd.concat([combined_df, df], ignore_index=True)
                except Exception as e: st.error(f"Error reading {f.name}: {e}")
        
        if not combined_df.empty:
            combined_df = combined_df.drop_duplicates(subset=['PRODUCT_SET_SID'])
            rejected = combined_df[combined_df['Status'] == 'Rejected'].copy()
            st.markdown("### Key Metrics")
            with st.container():
                m1, m2, m3, m4 = st.columns(4)
                total = len(combined_df); rej_count = len(rejected); rej_rate = (rej_count/total * 100) if total else 0
                m1.metric("Total Products Checked", f"{total:,}"); m2.metric("Total Rejected", f"{rej_count:,}"); m3.metric("Rejection Rate", f"{rej_rate:.1f}%"); m4.metric("Unique Sellers", f"{combined_df['SELLER_NAME'].nunique():,}")
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Top Rejection Reasons (Flags)")
                if not rejected.empty and 'FLAG' in rejected.columns:
                    reason_counts = rejected['FLAG'].value_counts().reset_index(); reason_counts.columns = ['Flag', 'Count']
                    chart = alt.Chart(reason_counts.head(10)).mark_bar().encode(x=alt.X('Count'), y=alt.Y('Flag', sort='-x'), color=alt.value('#FF6B6B'), tooltip=['Flag', 'Count']).interactive()
                    st.altair_chart(chart, use_container_width=True)
            with c2:
                st.subheader("Top Rejected Categories")
                if not rejected.empty and 'CATEGORY' in rejected.columns:
                    cat_counts = rejected['CATEGORY'].value_counts().reset_index(); cat_counts.columns = ['Category', 'Count']
                    chart = alt.Chart(cat_counts.head(10)).mark_bar().encode(x=alt.X('Count'), y=alt.Y('Category', sort='-x'), color=alt.value('#4ECDC4'), tooltip=['Category', 'Count']).interactive()
                    st.altair_chart(chart, use_container_width=True)
            c3, c4 = st.columns(2)
            with c3:
                st.subheader("Seller Trust Score (Top 10)")
                if not combined_df.empty and 'SELLER_NAME' in combined_df.columns:
                    seller_stats = combined_df.groupby('SELLER_NAME').agg(Total=('PRODUCT_SET_SID', 'count'), Rejected=('Status', lambda x: (x == 'Rejected').sum()))
                    seller_stats['Trust Score'] = 100 - (seller_stats['Rejected'] / seller_stats['Total'] * 100)
                    seller_stats = seller_stats.sort_values('Rejected', ascending=False).head(10).reset_index()
                    chart = alt.Chart(seller_stats).mark_bar().encode(x=alt.X('SELLER_NAME', sort='-y'), y=alt.Y('Trust Score', scale=alt.Scale(domain=[0, 100])), color=alt.Color('Trust Score', scale=alt.Scale(scheme='redyellowgreen')), tooltip=['SELLER_NAME', 'Total', 'Rejected', 'Trust Score']).interactive()
                    st.altair_chart(chart, use_container_width=True)
            with c4:
                st.subheader("Seller vs. Reason Breakdown (Top 5)")
                if not rejected.empty and 'SELLER_NAME' in rejected.columns and 'Reason' in rejected.columns:
                    top_sellers = rejected['SELLER_NAME'].value_counts().head(5).index.tolist()
                    filtered_rej = rejected[rejected['SELLER_NAME'].isin(top_sellers)]
                    if not filtered_rej.empty:
                        breakdown = filtered_rej.groupby(['SELLER_NAME', 'Reason']).size().reset_index(name='Count')
                        chart = alt.Chart(breakdown).mark_bar().encode(x=alt.X('SELLER_NAME'), y=alt.Y('Count'), color=alt.Color('Reason'), tooltip=['SELLER_NAME', 'Reason', 'Count']).interactive()
                        st.altair_chart(chart, use_container_width=True)
            st.markdown("---")
            st.subheader("Top 5 Summaries")
            if not rejected.empty:
                top_reasons = rejected['FLAG'].value_counts().head(5).reset_index(); top_reasons.columns = ['Flag', 'Count']
                top_sellers = rejected['SELLER_NAME'].value_counts().head(5).reset_index(); top_sellers.columns = ['Seller', 'Rejection Count']
                top_cats = rejected['CATEGORY'].value_counts().head(5).reset_index(); top_cats.columns = ['Category', 'Rejection Count']
                c1, c2, c3 = st.columns(3)
                with c1: st.markdown("**Top 5 Reasons**"); st.dataframe(top_reasons, hide_index=True, use_container_width=True)
                with c2: st.markdown("**Top 5 Sellers**"); st.dataframe(top_sellers, hide_index=True, use_container_width=True)
                with c3: st.markdown("**Top 5 Categories**"); st.dataframe(top_cats, hide_index=True, use_container_width=True)
                summary_excel = BytesIO()
                with pd.ExcelWriter(summary_excel, engine='xlsxwriter') as writer:
                    pd.DataFrame([{'Metric': 'Total Rejected', 'Value': len(rejected)}, {'Metric': 'Total Checked', 'Value': len(combined_df)}, {'Metric': 'Rejection Rate (%)', 'Value': (len(rejected)/len(combined_df)*100)}]).to_excel(writer, sheet_name='Summary', index=False)
                    top_reasons.to_excel(writer, sheet_name='Top 5 Reasons', index=False)
                    top_sellers.to_excel(writer, sheet_name='Top 5 Sellers', index=False)
                    top_cats.to_excel(writer, sheet_name='Top 5 Categories', index=False)
                summary_excel.seek(0)
                st.download_button(label="📥 Download Summary Excel", data=summary_excel, file_name=f"Weekly_Analysis_Summary_{datetime.now().strftime('%Y-%m-%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab3:
    st.header("Data Lake Audit")
    file = st.file_uploader("Upload audit file", type=['jsonl','csv','xlsx'], key="audit_file")
    if file:
        if file.name.endswith('.jsonl'): df = pd.read_json(file, lines=True)
        elif file.name.endswith('.csv'): df = pd.read_csv(file)
        else: df = pd.read_excel(file)
        st.dataframe(df.head(50), use_container_width=True)
    else:
        try: st.dataframe(pd.read_json('validation_audit.jsonl', lines=True).tail(50), use_container_width=True)
        except: st.info("No audit log found.")
