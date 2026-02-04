import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import json
import xlsxwriter
import zipfile

# -------------------------------------------------
# Constants & Mapping
# -------------------------------------------------
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]
FULL_DATA_COLS = [
    "PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE",
    "COLOR", "COLOR_FAMILY", "MAIN_IMAGE", "PARENTSKU", "SELLER_NAME"
]
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
    'image1': 'MAIN_IMAGE',
}

# -------------------------------------------------
# Brand in Generic Name Check (improved - searches anywhere)
# -------------------------------------------------
def check_generic_with_brand_in_name(data: pd.DataFrame, brands_list: List[str]) -> pd.DataFrame:
    if not {'NAME', 'BRAND'}.issubset(data.columns) or not brands_list:
        return pd.DataFrame(columns=data.columns)
    
    generic_keywords = ['generic', 'fashion', 'unbranded', 'no brand', 'gen', 'other', 'none', '']
    temp_brand = data['BRAND'].astype(str).str.strip().str.lower()
    generic_items = data[temp_brand.isin(generic_keywords) | temp_brand.str.contains('|'.join(generic_keywords), na=False)].copy()
    
    if generic_items.empty:
        return pd.DataFrame(columns=data.columns)
    
    generic_items['clean_name'] = (
        generic_items['NAME']
        .astype(str)
        .str.lower()
        .str.replace(r'[^\w\s]', ' ', regex=True)
        .str.replace(r'\s+', ' ', regex=True)
        .str.strip()
    )
    
    cleaned_brands = [b.strip().lower() for b in brands_list if b.strip()]
    cleaned_brands = sorted(cleaned_brands, key=len, reverse=True)
    escaped_brands = [re.escape(b) for b in cleaned_brands]
    
    if not escaped_brands:
        return pd.DataFrame(columns=data.columns)
    pattern = re.compile(r'\b(' + '|'.join(escaped_brands) + r')\b')
    
    generic_items['Detected_Brand'] = generic_items['clean_name'].apply(lambda x: pattern.findall(x))
    
    flagged = generic_items[generic_items['Detected_Brand'].apply(len) > 0].copy()
    
    if not flagged.empty:
        flagged['Comment_Detail'] = flagged['Detected_Brand'].apply(lambda matches: "Detected Brand(s): " + ", ".join(set(m.title() for m in matches)))
        flagged = flagged.drop(columns=['clean_name', 'Detected_Brand'])
    
    return flagged.drop_duplicates(subset=['PRODUCT_SET_SID'])

# -------------------------------------------------
# Minimal Support Files (only brands.txt + flags)
# -------------------------------------------------
@st.cache_data(ttl=3600)
def load_txt_file(filename: str) -> List[str]:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip().lower() for line in f if line.strip()]
    except:
        return []

@st.cache_data(ttl=3600)
def load_flags_mapping() -> Dict[str, Tuple[str, str]]:
    return {
        'Brand in Generic Name': ('1000002 - Kindly Ensure Brand Name Is Correct', 
                                  "This product is listed as 'Generic', but the name contains a known brand. Please update the Brand field.")
    }

@st.cache_data(ttl=3600)
def load_support_files():
    return {
        'known_brands': load_txt_file('brands.txt'),
        'flags_mapping': load_flags_mapping()
    }

# -------------------------------------------------
# Data Prep
# -------------------------------------------------
def standardize_input_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.rename(columns=NEW_FILE_MAPPING)
    if 'ACTIVE_STATUS_COUNTRY' in df.columns:
        df['ACTIVE_STATUS_COUNTRY'] = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.lower().str.replace('jumia-', '', regex=False).str.strip().str.upper()
    return df

def validate_input_schema(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    required = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'ACTIVE_STATUS_COUNTRY']
    errors = [f"Missing: {field}" for field in required if field not in df.columns]
    return len(errors) == 0, errors

def filter_by_country(df: pd.DataFrame, country_code: str) -> pd.DataFrame:
    if 'ACTIVE_STATUS_COUNTRY' not in df.columns:
        return df
    mask = df['ACTIVE_STATUS_COUNTRY'].astype(str).str.strip().str.upper() == country_code
    filtered = df[mask].copy()
    if filtered.empty:
        st.error(f"No {country_code} rows found")
        st.stop()
    return filtered

# -------------------------------------------------
# Validation Runner (only generic brand check)
# -------------------------------------------------
def validate_products(data: pd.DataFrame, support_files: Dict):
    data['PRODUCT_SET_SID'] = data['PRODUCT_SET_SID'].astype(str).str.strip()
    flags_mapping = support_files['flags_mapping']
    
    validations = [
        ("Brand in Generic Name", check_generic_with_brand_in_name, {'brands_list': support_files['known_brands']}),
    ]
    
    results = {}
    for name, func, kwargs in validations:
        try:
            res = func(data=data, **kwargs)
            results[name] = res if not res.empty else pd.DataFrame(columns=data.columns)
        except Exception as e:
            st.error(f"Error in {name}: {e}")
            results[name] = pd.DataFrame(columns=data.columns)
    
    rows = []
    processed = set()
    
    for name in results:
        if results[name].empty:
            continue
        res = results[name]
        reason_info = flags_mapping.get(name, ("1000007 - Other Reason", f"Flagged by {name}"))
        
        flagged = pd.merge(res[['PRODUCT_SET_SID', 'Comment_Detail']] if 'Comment_Detail' in res.columns else res[['PRODUCT_SET_SID']],
                           data, on='PRODUCT_SET_SID', how='left')
        
        for _, r in flagged.iterrows():
            sid = str(r['PRODUCT_SET_SID']).strip()
            if sid in processed:
                continue
            processed.add(sid)
            detail = r.get('Comment_Detail', '')
            if pd.isna(detail): detail = ''
            comment = f"{reason_info[1]} ({detail})" if detail else reason_info[1]
            rows.append({
                'ProductSetSid': sid,
                'ParentSKU': r.get('PARENTSKU', ''),
                'Status': 'Rejected',
                'Reason': reason_info[0],
                'Comment': comment,
                'FLAG': name,
                'SellerName': r.get('SELLER_NAME', '')
            })
    
    approved = data[~data['PRODUCT_SET_SID'].isin(processed)]
    for _, r in approved.iterrows():
        sid = str(r['PRODUCT_SET_SID']).strip()
        rows.append({
            'ProductSetSid': sid,
            'ParentSKU': r.get('PARENTSKU', ''),
            'Status': 'Approved',
            'Reason': '',
            'Comment': '',
            'FLAG': '',
            'SellerName': r.get('SELLER_NAME', '')
        })
    
    final_df = pd.DataFrame(rows)
    for col in ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]:
        if col not in final_df.columns:
            final_df[col] = ""
    return final_df

# -------------------------------------------------
# Export
# -------------------------------------------------
def to_excel_base(df, sheet, cols, writer, format_status=False):
    df_to_write = df[[c for c in cols if c in df.columns]]
    df_to_write.to_excel(writer, index=False, sheet_name=sheet)
    if format_status and 'Status' in df_to_write.columns:
        workbook = writer.book
        worksheet = writer.sheets[sheet]
        red_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        green_fmt = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        status_idx = df_to_write.columns.get_loc('Status')
        worksheet.conditional_format(1, status_idx, len(df_to_write), status_idx,
                                     {'type': 'cell', 'criteria': 'equal', 'value': '"Rejected"', 'format': red_fmt})
        worksheet.conditional_format(1, status_idx, len(df_to_write), status_idx,
                                     {'type': 'cell', 'criteria': 'equal', 'value': '"Approved"', 'format': green_fmt})

def generate_export(df, prefix, export_type='simple'):
    cols = FULL_DATA_COLS + ["Status", "Reason", "Comment", "FLAG", "SellerName"] if export_type == 'full' else PRODUCTSETS_COLS
    sheet = "ProductSets"
    
    if len(df) <= SPLIT_LIMIT:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            to_excel_base(df, sheet, cols, writer, format_status=True)
        output.seek(0)
        return output, f"{prefix}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(0, len(df), SPLIT_LIMIT):
            chunk = df.iloc[i:i + SPLIT_LIMIT]
            part_output = BytesIO()
            with pd.ExcelWriter(part_output, engine='xlsxwriter') as writer:
                to_excel_base(chunk, sheet, cols, writer, format_status=True)
            part_output.seek(0)
            zf.writestr(f"{prefix}_Part_{(i//SPLIT_LIMIT)+1}.xlsx", part_output.getvalue())
    zip_buffer.seek(0)
    return zip_buffer, f"{prefix}.zip", "application/zip"

# -------------------------------------------------
# UI
# -------------------------------------------------
st.set_page_config(page_title="Generic Brand Checker", layout="centered")
st.title("Generic Brand Checker")
st.markdown("**Test mode:** Only checks for known brands in generic/fashion/unbranded listings.")

support_files = load_support_files()
if not support_files['known_brands']:
    st.error("brands.txt not found or empty!")
    st.stop()
st.sidebar.write(f"Brands loaded: **{len(support_files['known_brands'])}**")

country = st.selectbox("Country", ["Kenya", "Uganda"])
country_code = "KE" if country == "Kenya" else "UG"

uploaded_files = st.file_uploader("Upload CSV/XLSX files", type=['csv', 'xlsx'], accept_multiple_files=True)

if uploaded_files:
    all_dfs = []
    for f in uploaded_files:
        try:
            if f.name.endswith('.xlsx'):
                df = pd.read_excel(f, dtype=str)
            else:
                df = pd.read_csv(f, dtype=str, sep=None, engine='python')
            all_dfs.append(standardize_input_data(df))
        except Exception as e:
            st.error(f"Error reading {f.name}: {e}")
    
    if all_dfs:
        data = pd.concat(all_dfs, ignore_index=True)
        data = data.drop_duplicates(subset=['PRODUCT_SET_SID'])
        data = filter_by_country(data, country_code)
        
        is_valid, errors = validate_input_schema(data)
        if not is_valid:
            for e in errors: st.error(e)
            st.stop()
        
        with st.spinner("Checking for generic listings with known brands..."):
            final_report = validate_products(data, support_files)
        
        approved = final_report[final_report['Status'] == 'Approved']
        rejected = final_report[final_report['Status'] == 'Rejected']
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total", len(data))
        col2.metric("Approved", len(approved))
        col3.metric("Rejected", len(rejected))
        
        if not rejected.empty:
            st.subheader("Rejected Listings")
            display_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'SELLER_NAME', 'Comment']
            st.dataframe(rejected.merge(data)[display_cols], use_container_width=True)
        
        current_date = datetime.now().strftime('%Y-%m-%d')
        prefix = f"{country_code}_GenericCheck_{current_date}"
        
        st.markdown("### Downloads")
        c1, c2, c3 = st.columns(3)
        final_data, final_name, final_mime = generate_export(final_report, f"{prefix}_Report")
        rej_data, rej_name, rej_mime = generate_export(rejected, f"{prefix}_Rejected")
        full_data, full_name, full_mime = generate_export(final_report.merge(data), f"{prefix}_Full", 'full')
        
        c1.download_button("Final Report", final_data, final_name, final_mime)
        c2.download_button("Rejected Only", rej_data, rej_name, rej_mime)
        c3.download_button("Full Data", full_data, full_name, full_mime)
