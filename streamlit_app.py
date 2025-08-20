import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import os

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# --- Constants for column names ---
PRODUCTSETS_COLS = ["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG"]
REJECTION_REASONS_COLS = ['CODE - REJECTION_REASON', 'COMMENT']
FULL_DATA_COLS = ["PRODUCT_SET_SID", "ACTIVE_STATUS_COUNTRY", "NAME", "BRAND", "CATEGORY", "CATEGORY_CODE", "COLOR", "MAIN_IMAGE", "VARIATION", "PARENTSKU", "SELLER_NAME", "SELLER_SKU", "GLOBAL_PRICE", "GLOBAL_SALE_PRICE", "TAX_CLASS", "FLAG"]


# Function to load blacklisted words from a file
def load_blacklisted_words():
    try:
        with open('blacklisted.txt', 'r') as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        st.error("blacklisted.txt file not found!")
        return []
    except Exception as e:
        st.error(f"Error loading blacklisted words: {e}")
        return []

# Function to load book category codes from file
def load_book_category_codes():
    try:
        book_cat_df = pd.read_excel('Books_cat.xlsx')
        return book_cat_df['CategoryCode'].astype(str).tolist()
    except FileNotFoundError:
        st.warning("Books_cat.xlsx file not found! Book category exemptions for missing color, single-word name, and sensitive brand checks will not be applied.")
        return []
    except Exception as e:
        st.error(f"Error loading Books_cat.xlsx: {e}")
        return []

# Function to load sensitive brand words from Excel file
def load_sensitive_brand_words():
    try:
        sensitive_brands_df = pd.read_excel('sensitive_brands.xlsx')
        return sensitive_brands_df['BrandWords'].astype(str).tolist()
    except FileNotFoundError:
        st.warning("sensitive_brands.xlsx file not found! Sensitive brand check will not be applied.")
        return []
    except Exception as e:
        st.error(f"Error loading sensitive_brands.xlsx: {e}")
        return []

# Function to load approved book sellers from Excel file
def load_approved_book_sellers():
    try:
        approved_sellers_df = pd.read_excel('Books_Approved_Sellers.xlsx')
        return approved_sellers_df['SellerName'].astype(str).tolist()
    except FileNotFoundError:
        st.warning("Books_Approved_Sellers.xlsx file not found! Book seller approval check for books will not be applied.")
        return []
    except Exception as e:
        st.error(f"Error loading Books_Approved_Sellers.xlsx: {e}")
        return []

# Function to load perfume category codes from file
def load_perfume_category_codes():
    try:
        with open('Perfume_cat.txt', 'r') as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        st.warning("Perfume_cat.txt file not found! Perfume category filtering for price check will not be applied.")
        return []
    except Exception as e:
        st.error(f"Error loading Perfume_cat.txt: {e}")
        return []


# Function to load configuration files
def load_config_files():
    config_files = {
        'check_variation': 'check_variation.xlsx',
        'category_fas': 'category_FAS.xlsx',
        'perfumes': 'perfumes.xlsx',
        'reasons': 'reasons.xlsx'
    }
    data = {}
    for key, filename in config_files.items():
        try:
            df = pd.read_excel(filename).rename(columns=lambda x: x.strip())
            data[key] = df
        except FileNotFoundError:
            st.warning(f"{filename} file not found, functionality related to this file will be limited.")
            data[key] = pd.DataFrame() # Return empty DataFrame if file not found
        except Exception as e:
            st.error(f"❌ Error loading {filename}: {e}")
            data[key] = pd.DataFrame() # Return empty DataFrame on other errors
    return data

# Validation check functions
def check_missing_color(data, book_category_codes):
    if 'CATEGORY_CODE' not in data.columns or 'COLOR' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    missing_color_non_books = non_book_data[non_book_data['COLOR'].isna() | (non_book_data['COLOR'] == '')]
    return missing_color_non_books

def check_missing_brand_or_name(data):
    if 'BRAND' not in data.columns or 'NAME' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    return data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]

def check_single_word_name(data, book_category_codes):
    if 'CATEGORY_CODE' not in data.columns or 'NAME' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    # Ensure NAME is string before splitting
    flagged_non_book_single_word_names = non_book_data[
        non_book_data['NAME'].astype(str).str.split().str.len() == 1
    ]
    return flagged_non_book_single_word_names

def check_generic_brand_issues(data, valid_category_codes_fas):
    if 'CATEGORY_CODE' not in data.columns or 'BRAND' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    if not valid_category_codes_fas: # If list is empty (e.g., file not found)
        return pd.DataFrame(columns=data.columns)
    return data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]

def check_brand_in_name(data):
    if 'BRAND' not in data.columns or 'NAME' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    return data[data.apply(lambda row:
        isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and
        row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

def check_duplicate_products(data):
    subset_cols = [col for col in ['NAME', 'BRAND', 'SELLER_NAME', 'COLOR'] if col in data.columns]
    if len(subset_cols) < 4: # Not enough columns to check for duplicates as defined
        return pd.DataFrame(columns=data.columns)
    return data[data.duplicated(subset=subset_cols, keep=False)]

def check_sensitive_brands(data, sensitive_brand_words, book_category_codes):
    if 'CATEGORY_CODE' not in data.columns or 'NAME' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if not sensitive_brand_words or book_data.empty:
        return pd.DataFrame(columns=data.columns)

    sensitive_regex_words = [r'\b' + re.escape(word.lower()) + r'\b' for word in sensitive_brand_words]
    sensitive_brands_regex = '|'.join(sensitive_regex_words)

    mask_name = book_data['NAME'].astype(str).str.lower().str.contains(sensitive_brands_regex, regex=True, na=False)
    return book_data[mask_name]

def check_seller_approved_for_books(data, book_category_codes, approved_book_sellers):
    if 'CATEGORY_CODE' not in data.columns or 'SELLER_NAME' not in data.columns:
        return pd.DataFrame(columns=data.columns)
    book_data = data[data['CATEGORY_CODE'].isin(book_category_codes)]
    if book_data.empty or not approved_book_sellers:
        return pd.DataFrame(columns=data.columns)
    unapproved_book_sellers_mask = ~book_data['SELLER_NAME'].isin(approved_book_sellers)
    return book_data[unapproved_book_sellers_mask]

def check_perfume_price(data, perfumes_df, perfume_category_codes):
    required_cols = ['CATEGORY_CODE', 'NAME', 'BRAND', 'GLOBAL_SALE_PRICE', 'GLOBAL_PRICE']
    if not all(col in data.columns for col in required_cols) or \
       perfumes_df.empty or not perfume_category_codes or \
       not all(col in perfumes_df.columns for col in ['BRAND', 'PRODUCT_NAME', 'KEYWORD', 'PRICE']):
        return pd.DataFrame(columns=data.columns)

    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)]
    if perfume_data.empty:
        return pd.DataFrame(columns=data.columns)

    flagged_perfumes_list = []
    for index, row in perfume_data.iterrows():
        seller_product_name = str(row['NAME']).strip().lower()
        seller_brand_name = str(row['BRAND']).strip().lower()
        seller_price = row['GLOBAL_SALE_PRICE'] if pd.notna(row['GLOBAL_SALE_PRICE']) and row['GLOBAL_SALE_PRICE'] > 0 else row['GLOBAL_PRICE']

        if not pd.notna(seller_price) or seller_price <= 0:
            continue

        matched_perfume_row = None
        for _, perfume_row in perfumes_df.iterrows():
            ref_brand = str(perfume_row['BRAND']).strip().lower()
            ref_product_name = str(perfume_row['PRODUCT_NAME']).strip().lower()
            if seller_brand_name == ref_brand and ref_product_name in seller_product_name:
                matched_perfume_row = perfume_row
                break
        if matched_perfume_row is None:
             for _, perfume_row in perfumes_df.iterrows():
                ref_brand = str(perfume_row['BRAND']).strip().lower()
                ref_keyword = str(perfume_row['KEYWORD']).strip().lower()
                ref_product_name = str(perfume_row['PRODUCT_NAME']).strip().lower() # Still need for context
                if seller_brand_name == ref_brand and (ref_keyword in seller_product_name or ref_product_name in seller_product_name):
                    matched_perfume_row = perfume_row
                    break
        if matched_perfume_row is not None:
            reference_price_dollar = matched_perfume_row['PRICE']
            price_difference = reference_price_dollar - (seller_price / 129) # Assuming rate of 129
            if price_difference >= 30:
                flagged_perfumes_list.append(row.to_dict())
    
    if flagged_perfumes_list:
        return pd.DataFrame(flagged_perfumes_list)
    else:
        return pd.DataFrame(columns=data.columns) # Ensure consistent columns if empty

def validate_products(data, config_data, blacklisted_words, reasons_dict, book_category_codes, sensitive_brand_words, approved_book_sellers, perfume_category_codes):
    # --- Define validations in PRIORITY ORDER ---
    # "Duplicate product" is now last
    validations = [
        ("Sensitive Brand Issues", check_sensitive_brands, {'sensitive_brand_words': sensitive_brand_words, 'book_category_codes': book_category_codes}),
        ("Seller Approve to sell books", check_seller_approved_for_books,  {'book_category_codes': book_category_codes, 'approved_book_sellers': approved_book_sellers}),
        ("Perfume Price Check", check_perfume_price, {'perfumes_df': config_data.get('perfumes', pd.DataFrame()), 'perfume_category_codes': perfume_category_codes}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': book_category_codes}),
        ("Missing BRAND or NAME", check_missing_brand_or_name, {}),
        ("Generic BRAND Issues", check_generic_brand_issues, {}), # Kwargs handled below
        ("Missing COLOR", check_missing_color, {'book_category_codes': book_category_codes}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Duplicate product", check_duplicate_products, {}), # MOVED TO LAST
    ]

    flag_reason_comment_mapping = {
        "Sensitive Brand Issues": ("1000023 - Confirmation of counterfeit product by Jumia technical team (Not Authorized)", "Please contact vendor support for sale of..."),
        "Seller Approve to sell books": ("1000028 - Kindly Contact Jumia Seller Support To Confirm Possibility Of Sale Of This Product By Raising A Claim", "Kindly Contact Jumia Seller Support To Confirm Possibility of selling this book"),
        "Perfume Price Check": ("1000029 - Kindly Contact Jumia Seller Support To Verify This Product's Authenticity By Raising A Claim", "Kindly raise a claim"),
        "Single-word NAME": ("1000008 - Kindly Improve Product Name Description", "Kindly Improve Product Name Description"),
        "Missing BRAND or NAME": ("1000001 - Brand NOT Allowed", "Brand NOT Allowed"),
        "Generic BRAND Issues": ("1000001 - Brand NOT Allowed", "Kindly use Fashion for Fashion items"),
        "Missing COLOR": ("1000005 - Kindly confirm the actual product colour", "Kindly add color on the color field"),
        "BRAND name repeated in NAME": ("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", "Kindly Ensure Brand Name Is Not Repeated In Product Name"),
        "Duplicate product": ("1000007 - Other Reason", "Product is duplicated"),
    }

    validation_results_dfs = {}
    for flag_name, check_func, func_kwargs in validations:
        current_kwargs = {'data': data}
        if flag_name == "Generic BRAND Issues":
            category_fas_df = config_data.get('category_fas', pd.DataFrame())
            if not category_fas_df.empty and 'ID' in category_fas_df.columns:
                current_kwargs['valid_category_codes_fas'] = category_fas_df['ID'].astype(str).tolist()
            else:
                current_kwargs['valid_category_codes_fas'] = [] # Pass empty list if no codes
        else:
            current_kwargs.update(func_kwargs)
        
        try:
            result_df = check_func(**current_kwargs)
            # Ensure PRODUCT_SET_SID is in the result if it's not empty
            if not result_df.empty and 'PRODUCT_SET_SID' not in result_df.columns and 'PRODUCT_SET_SID' in data.columns:
                # This case should ideally not happen if check_funcs return relevant slice of data
                st.warning(f"Check '{flag_name}' did not return 'PRODUCT_SET_SID'. Results might be incomplete.")
                validation_results_dfs[flag_name] = pd.DataFrame(columns=data.columns) # Fallback
            else:
                validation_results_dfs[flag_name] = result_df

        except Exception as e:
            st.error(f"Error during validation check '{flag_name}': {e}")
            validation_results_dfs[flag_name] = pd.DataFrame(columns=data.columns) # Fallback to empty DF with original columns

    final_report_rows = []
    processed_sids = set() # Keep track of SIDs that have been assigned a reason

    for flag_name, _, _ in validations:
        validation_df = validation_results_dfs.get(flag_name, pd.DataFrame())
        if validation_df.empty or 'PRODUCT_SET_SID' not in validation_df.columns:
            continue
        
        rejection_reason, comment = flag_reason_comment_mapping.get(flag_name, ("Unknown Reason", "No comment defined."))
        
        # Get the original row data for the flagged products
        flagged_sids_df = pd.merge(
            validation_df[['PRODUCT_SET_SID']],
            data,
            on='PRODUCT_SET_SID',
            how='left'
        )

        for _, row in flagged_sids_df.iterrows():
            current_product_sid = row.get('PRODUCT_SET_SID')
            if current_product_sid in processed_sids:
                continue # Skip if already processed by a higher-priority rule
            
            processed_sids.add(current_product_sid)
            final_report_rows.append({
                'ProductSetSid': current_product_sid,
                'ParentSKU': row.get('PARENTSKU', ''),
                'Status': 'Rejected',
                'Reason': rejection_reason,
                'Comment': comment,
                'FLAG': flag_name
            })
            
    # Add all the approved products that were not processed
    all_sids = set(data['PRODUCT_SET_SID'].astype(str).unique())
    approved_sids = all_sids - processed_sids
    
    approved_data = data[data['PRODUCT_SET_SID'].isin(approved_sids)]
    
    for _, row in approved_data.iterrows():
         final_report_rows.append({
            'ProductSetSid': row.get('PRODUCT_SET_SID'),
            'ParentSKU': row.get('PARENTSKU', ''),
            'Status': 'Approved',
            'Reason': "",
            'Comment': "",
            'FLAG': ""
        })
        
    final_report_df = pd.DataFrame(final_report_rows)
    return final_report_df, validation_results_dfs

# --- Export functions ---
def to_excel_base(df_to_export, sheet_name, columns_to_include, writer):
    """Helper to write a DataFrame to a sheet with specific columns."""
    # Ensure all columns_to_include are present, add as NA if missing
    df_prepared = df_to_export.copy()
    for col in columns_to_include:
        if col not in df_prepared.columns:
            df_prepared[col] = pd.NA
    df_prepared[columns_to_include].to_excel(writer, index=False, sheet_name=sheet_name)


def to_excel_full_data(data_df, final_report_df):
    output = BytesIO()
    # Merge original data with report status/reason/flag
    # Ensure PRODUCT_SET_SID is string for consistent merging
    data_df_copy = data_df.copy()
    final_report_df_copy = final_report_df.copy()
    data_df_copy['PRODUCT_SET_SID'] = data_df_copy['PRODUCT_SET_SID'].astype(str)
    final_report_df_copy['ProductSetSid'] = final_report_df_copy['ProductSetSid'].astype(str)

    merged_df = pd.merge(
        data_df_copy,
        final_report_df_copy[["ProductSetSid", "Status", "Reason", "Comment", "FLAG"]],
        left_on="PRODUCT_SET_SID",
        right_on="ProductSetSid",
        how="left"
    )
    # Drop the potentially duplicated ProductSetSid from the right DF
    if 'ProductSetSid_y' in merged_df.columns: # Older pandas might add suffixes
          merged_df.drop(columns=['ProductSetSid_y'], inplace=True)
    if 'ProductSetSid_x' in merged_df.columns: # Rename if needed
          merged_df.rename(columns={'ProductSetSid_x': 'PRODUCT_SET_SID'}, inplace=True)
    
    # If original data also had Status, Reason, etc., the ones from final_report_df (now merged) are preferred
    # Fill NA for FLAG which is the main addition here. Others should come from merge.
    if 'FLAG' in merged_df.columns:
        merged_df['FLAG'] = merged_df['FLAG'].fillna('')
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(merged_df, "ProductSets", FULL_DATA_COLS, writer)
    output.seek(0)
    return output

def to_excel_flag_data(flag_df, flag_name):
    output = BytesIO()
    df_copy = flag_df.copy()
    df_copy['FLAG'] = flag_name # Add the flag name column
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(df_copy, "ProductSets", FULL_DATA_COLS, writer)
    output.seek(0)
    return output

def to_excel_seller_data(seller_data_df, seller_final_report_df):
    # This is essentially the same as to_excel_full_data, but with potentially filtered data
    return to_excel_full_data(seller_data_df, seller_final_report_df)

def to_excel(report_df, reasons_config_df, sheet1_name="ProductSets", sheet2_name="RejectionReasons"):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        to_excel_base(report_df, sheet1_name, PRODUCTSETS_COLS, writer)
        if not reasons_config_df.empty:
            to_excel_base(reasons_config_df, sheet2_name, REJECTION_REASONS_COLS, writer)
        else: # Write empty sheet with headers if reasons_df is empty
            pd.DataFrame(columns=REJECTION_REASONS_COLS).to_excel(writer, index=False, sheet_name=sheet2_name)
    output.seek(0)
    return output

# --- Initialize the app ---
st.title("Product Validation Tool")

# --- Load configuration files ---
config_data = load_config_files()
blacklisted_words = load_blacklisted_words()
book_category_codes = load_book_category_codes()
sensitive_brand_words = load_sensitive_brand_words()
approved_book_sellers = load_approved_book_sellers()
perfume_category_codes = load_perfume_category_codes()

reasons_df_from_config = config_data.get('reasons', pd.DataFrame()) # Used for "RejectionReasons" sheet
# reasons_dict is not directly used by validate_products's mapping anymore, but kept for other potential uses or if logic changes.
reasons_dict_legacy = {}
if not reasons_df_from_config.empty:
    for _, row in reasons_df_from_config.iterrows():
        reason_text = row.get('CODE - REJECTION_REASON', "")
        comment = row.get('COMMENT', "") if pd.notna(row.get('COMMENT')) else ""
        if isinstance(reason_text, str) and ' - ' in reason_text:
            code, message = reason_text.split(' - ', 1)
            reasons_dict_legacy[f"{code} - {message}"] = (code, message, comment)
        elif isinstance(reason_text, str): # Handle if no ' - '
              reasons_dict_legacy[reason_text] = (reason_text, reason_text, comment)


# --- File upload section ---
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

if uploaded_file is not None:
    current_date = datetime.now().strftime("%Y-%m-%d")
    process_success = False
    try:
        # Read CSV, ensure key columns are strings
        dtype_spec = {
            'CATEGORY_CODE': str,
            'PRODUCT_SET_SID': str,
            'PARENTSKU': str,
            # Add other known ID-like columns if necessary
        }
        # Convert all other columns later if needed, or rely on pandas inference
        # but be mindful of columns used in string operations or merges.
        raw_data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype=dtype_spec)
        
        # Ensure essential columns for processing exist, fill with NA if not
        # These are columns directly used by check functions or for display/reporting logic.
        # FULL_DATA_COLS lists all columns for *output*, not all are necessarily *input*.
        essential_input_cols = ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'CATEGORY_CODE', 'COLOR', 'SELLER_NAME', 'GLOBAL_PRICE', 'GLOBAL_SALE_PRICE', 'PARENTSKU']
        data = raw_data.copy()
        for col in essential_input_cols:
            if col not in data.columns:
                data[col] = pd.NA # Add as NA if missing, specific checks will handle NA

        # Convert columns used in string operations to string type to avoid errors with mixed types or NaN
        for col in ['NAME', 'BRAND', 'COLOR', 'SELLER_NAME', 'CATEGORY_CODE', 'PARENTSKU']:
            if col in data.columns:
                data[col] = data[col].astype(str).fillna('') # Fill NaN with empty string after astype(str)

        if data.empty:
            st.warning("The uploaded file is empty or became empty after initial processing.")
            st.stop()

        st.write("CSV file loaded successfully.")

        # --- Validation and report generation ---
        final_report_df, individual_flag_dfs = validate_products(
            data, config_data, blacklisted_words, reasons_dict_legacy,
            book_category_codes, sensitive_brand_words,
            approved_book_sellers, perfume_category_codes
        )
        process_success = True

        approved_df = final_report_df[final_report_df['Status'] == 'Approved']
        rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

        # --- Sidebar for Seller Options ---
        st.sidebar.header("Seller Options")
        seller_options = ['All Sellers']
        # Calculate SKU counts for sidebar, ensure SELLER_NAME exists and ProductSetSid for join
        if 'SELLER_NAME' in data.columns and 'ProductSetSid' in final_report_df.columns and 'PRODUCT_SET_SID' in data.columns:
            # Ensure join keys are of the same type
            final_report_df_for_join = final_report_df.copy()
            final_report_df_for_join['ProductSetSid'] = final_report_df_for_join['ProductSetSid'].astype(str)
            data_for_join = data[['PRODUCT_SET_SID', 'SELLER_NAME']].copy()
            data_for_join['PRODUCT_SET_SID'] = data_for_join['PRODUCT_SET_SID'].astype(str)
            
            # Deduplicate data_for_join on PRODUCT_SET_SID before merging if necessary
            data_for_join.drop_duplicates(subset=['PRODUCT_SET_SID'], inplace=True)

            report_with_seller = pd.merge(
                final_report_df_for_join,
                data_for_join,
                left_on='ProductSetSid',
                right_on='PRODUCT_SET_SID',
                how='left'
            )
            if not report_with_seller.empty:
                rejected_sku_counts = report_with_seller[report_with_seller['Status'] == 'Rejected'].groupby('SELLER_NAME')['ParentSKU'].count().sort_values(ascending=False)
                approved_sku_counts = report_with_seller[report_with_seller['Status'] == 'Approved'].groupby('SELLER_NAME')['ParentSKU'].count()
                seller_options.extend(list(report_with_seller['SELLER_NAME'].dropna().unique()))


        selected_sellers = st.sidebar.multiselect("Select Sellers", seller_options, default=['All Sellers'])

        # Initialize seller-specific dataframes
        seller_data_filtered = data.copy() # For full data export of selected seller
        seller_final_report_df_filtered = final_report_df.copy() # For final report of selected seller
        seller_label_filename = "All_Sellers"

        if 'All Sellers' not in selected_sellers and selected_sellers: # If specific sellers are chosen
            if 'SELLER_NAME' in data.columns:
                seller_data_filtered = data[data['SELLER_NAME'].isin(selected_sellers)].copy()
                # Filter final_report_df based on ProductSetSids present in seller_data_filtered
                seller_final_report_df_filtered = final_report_df[final_report_df['ProductSetSid'].isin(seller_data_filtered['PRODUCT_SET_SID'])].copy()
                seller_label_filename = "_".join(s.replace(" ", "_").replace("/", "_") for s in selected_sellers) # Filename safe
            else:
                st.sidebar.warning("SELLER_NAME column missing, cannot filter by seller.")
        
        # Derive rejected/approved for selected sellers from their filtered final report
        seller_rejected_df_filtered = seller_final_report_df_filtered[seller_final_report_df_filtered['Status'] == 'Rejected']
        seller_approved_df_filtered = seller_final_report_df_filtered[seller_final_report_df_filtered['Status'] == 'Approved']

        # Display Seller Metrics in Sidebar
        st.sidebar.subheader("Seller SKU Metrics")
        if 'SELLER_NAME' in data.columns and 'report_with_seller' in locals() and not report_with_seller.empty:
              # Iterate over unique sellers present in the data if specific sellers were chosen, or all sellers if 'All Sellers'
            sellers_to_display = selected_sellers if 'All Sellers' not in selected_sellers and selected_sellers else seller_options[1:]
            for seller in sellers_to_display:
                if seller == 'All Sellers': continue # Skip 'All Sellers' for individual metrics
                
                current_seller_data = report_with_seller[report_with_seller['SELLER_NAME'] == seller]
                # Filter further if selected_sellers is active and this seller is in it
                if 'All Sellers' not in selected_sellers and selected_sellers and seller in selected_sellers:
                    rej_count = current_seller_data[current_seller_data['Status'] == 'Rejected']['ParentSKU'].count()
                    app_count = current_seller_data[current_seller_data['Status'] == 'Approved']['ParentSKU'].count()
                    st.sidebar.write(f"{seller}: **Rej**: {rej_count}, **App**: {app_count}")
                elif 'All Sellers' in selected_sellers: # Show all if 'All Sellers' is selected
                    rej_count = current_seller_data[current_seller_data['Status'] == 'Rejected']['ParentSKU'].count()
                    app_count = current_seller_data[current_seller_data['Status'] == 'Approved']['ParentSKU'].count()
                    st.sidebar.write(f"{seller}: **Rej**: {rej_count}, **App**: {app_count}")

        else:
            st.sidebar.write("Seller metrics unavailable (SELLER_NAME missing or no products).")


        # Seller Data Exports (using filtered dataframes)
        st.sidebar.subheader(f"Exports for: {seller_label_filename.replace('_', ' ')}")
        seller_final_excel = to_excel(seller_final_report_df_filtered, reasons_df_from_config)
        st.sidebar.download_button(label="Seller Final Export", data=seller_final_excel, file_name=f"Final_Report_{current_date}_{seller_label_filename}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        seller_rejected_excel = to_excel(seller_rejected_df_filtered, reasons_df_from_config)
        st.sidebar.download_button(label="Seller Rejected Export", data=seller_rejected_excel, file_name=f"Rejected_Products_{current_date}_{seller_label_filename}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        seller_approved_excel = to_excel(seller_approved_df_filtered, reasons_df_from_config)
        st.sidebar.download_button(label="Seller Approved Export", data=seller_approved_excel, file_name=f"Approved_Products_{current_date}_{seller_label_filename}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        seller_full_excel = to_excel_seller_data(seller_data_filtered, seller_final_report_df_filtered)
        st.sidebar.download_button(label="Seller Full Data Export", data=seller_full_excel, file_name=f"Seller_Data_Export_{current_date}_{seller_label_filename}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


        # --- Main page for overall metrics and validation results ---
        st.header("Overall Product Validation Results")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Products in Upload", len(data)) # Based on initially loaded data
            st.metric("Approved Products (Overall)", len(approved_df)) # Based on full final_report_df
        with col2:
            st.metric("Rejected Products (Overall)", len(rejected_df)) # Based on full final_report_df
            rejection_rate = (len(rejected_df)/len(data)*100) if len(data) > 0 else 0
            st.metric("Rejection Rate (Overall)", f"{rejection_rate:.1f}%")

        # Display individual validation failures using individual_flag_dfs
        # Order is preserved from `validations` list (Python 3.7+)
        for title, df_flagged in individual_flag_dfs.items():
            with st.expander(f"{title} ({len(df_flagged)} products overall)"):
                if not df_flagged.empty:
                    display_cols = [col for col in ['PRODUCT_SET_SID', 'NAME', 'BRAND', 'SELLER_NAME', 'CATEGORY_CODE', 'COLOR'] if col in df_flagged.columns]
                    st.dataframe(df_flagged[display_cols] if display_cols else df_flagged) # Show subset or all if subset not applicable
                    
                    flag_excel_export = to_excel_flag_data(df_flagged.copy(), title) # df_flagged.copy() is important
                    safe_title = title.replace(' ', '_').replace('/', '_')
                    st.download_button(
                        label=f"Export {title} Data",
                        data=flag_excel_export,
                        file_name=f"{safe_title}_Products_{current_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"download_flag_{safe_title}" # Unique key
                    )
                else:
                    st.write("No issues found for this check.")

        # --- Overall Data Exports (Main Page) ---
        st.header("Overall Data Exports (All Sellers)")
        col1_main, col2_main, col3_main, col4_main = st.columns(4)
        with col1_main:
            overall_final_excel = to_excel(final_report_df, reasons_df_from_config)
            st.download_button(label="Final Export (All)", data=overall_final_excel, file_name=f"Final_Report_{current_date}_ALL.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with col2_main:
            overall_rejected_excel = to_excel(rejected_df, reasons_df_from_config)
            st.download_button(label="Rejected Export (All)", data=overall_rejected_excel, file_name=f"Rejected_Products_{current_date}_ALL.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with col3_main:
            overall_approved_excel = to_excel(approved_df, reasons_df_from_config)
            st.download_button(label="Approved Export (All)", data=overall_approved_excel, file_name=f"Approved_Products_{current_date}_ALL.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with col4_main:
            overall_full_excel = to_excel_full_data(data.copy(), final_report_df) # Use overall data
            st.download_button(label="Full Data Export (All)", data=overall_full_excel, file_name=f"Full_Data_Export_{current_date}_ALL.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except pd.errors.ParserError as pe:
        process_success = False
        st.error(f"Error parsing the CSV file. Please ensure it's a valid CSV with ';' delimiter and UTF-8 or ISO-8859-1 encoding: {pe}")
    except Exception as e:
        process_success = False
        st.error(f"An unexpected error occurred processing the file: {e}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}") # Show traceback in Streamlit UI for easier debugging

    if not process_success and uploaded_file is not None: # Show if an upload was attempted and failed
        st.error("File processing failed. Please check the file format, content, console logs (if running locally), and error messages above, then try again.")
