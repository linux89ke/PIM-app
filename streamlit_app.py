import pandas as pd
import streamlit as st
from io import BytesIO

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# Function to load blacklisted words from a file
def load_blacklisted_words():
    try:
        with open('blacklisted.txt', 'r') as f:
            return [line.strip().lower() for line in f.readlines()]  # Lowercase for case-insensitivity
    except FileNotFoundError:
        st.error("blacklisted.txt not found!")
        return []
    except Exception as e:
        st.error(f"Error loading blacklisted words: {e}")
        return []

# Function to load sensitive brands from the sensitive_brands.xlsx file
def load_sensitive_brands():
    try:
        df = pd.read_excel('sensitive_brands.xlsx')
        return [str(brand).lower() for brand in df['BRAND'].dropna().tolist()]  # Lowercase & handle potential NaN
    except FileNotFoundError:
        st.error("sensitive_brands.xlsx not found!")
        return []
    except Exception as e:
        st.error(f"Error loading sensitive brands: {e}")
        return []

# Load category_FAS.xlsx to get the allowed CATEGORY_CODE values
def load_category_FAS():
    try:
        df = pd.read_excel('category_FAS.xlsx')
        return [int(code) for code in df['ID'].dropna().tolist()]  # Ensure integers
    except FileNotFoundError:
        st.error("category_FAS.xlsx not found!")
        return []
    except Exception as e:
        st.error(f"Error loading category_FAS data: {e}")
        return []

# Load book categories from Books_cat.txt
def load_book_categories():
    try:
        with open('Books_cat.txt', 'r') as f:
            return [int(line.strip()) for line in f.readlines()]
    except FileNotFoundError:
        st.error("Books_cat.txt not found!")
        return []
    except ValueError:
        st.error("Books_cat.txt contains non-integer values!")
        return []
    except Exception as e:
        st.error(f"Error loading book categories: {e}")
        return []

# Load and validate configuration files
def load_config_files():
    config_files = {
        'flags': 'flags.xlsx',
        'check_variation': 'check_variation.xlsx',
        'perfumes': 'perfumes.xlsx'
    }

    data = {}
    for key, filename in config_files.items():
        try:
            df = pd.read_excel(filename).rename(columns=lambda x: x.strip())
            data[key] = df
        except FileNotFoundError:
            st.error(f"{filename} not found!")
            if key == 'flags':
                st.stop()
        except Exception as e:
            st.error(f"Error loading {filename}: {e}")
            if key == 'flags':
                st.stop()
    return data

# Function to validate a single product
def validate_product(row, config_data, blacklisted_words, book_categories, sensitive_brands, category_FAS_codes):
    reason = None
    reason_details = None

    # Convert relevant columns to string and handle NaN values before applying string methods
    try:
        brand = str(row['BRAND']).lower()
        name = str(row['NAME']).lower()
        color = str(row['COLOR']).lower()
        category_code = int(row['CATEGORY_CODE'])  # Convert to integer here
    except Exception as e:
        st.error(f"Error converting data to string or integer: {e}")
        return None, None

    # Missing COLOR
    if color.strip() == "":
        reason = "Missing COLOR"
        reason_details = ("COLOR-MISSING", "Color is missing or empty.", "")
        return reason, reason_details

    # Missing BRAND or NAME
    if brand.strip() == "" or name.strip() == "":
        reason = "Missing BRAND or NAME"
        reason_details = ("BRAND_OR_NAME-MISSING", "Brand or Name is missing or empty.", "")
        return reason, reason_details

    # Single-word NAME (excluding books)
    if len(name.split()) == 1 and category_code not in book_categories and brand != 'jumia book':
        reason = "Single-word NAME"
        reason_details = ("SINGLE-WORD-NAME", "Product name has only one word and is not a book.", "")
        return reason, reason_details

    # Generic BRAND in specific categories
    if brand == 'generic' and category_code in category_FAS_codes:
        reason = "Generic BRAND"
        reason_details = ("GENERIC-BRAND", "Product is of Generic brand in this category.", "")
        return reason, reason_details

    # Perfume price validation
    perfumes_data = config_data.get('perfumes')
    if perfumes_data is not None:
        if brand in [str(b).lower() for b in perfumes_data['BRAND'].tolist()]:  # Convert to string during lookup
            brand_perfumes = perfumes_data[perfumes_data['BRAND'].str.lower() == brand]
            keywords = [str(k).lower() for k in brand_perfumes['KEYWORD'].tolist()] #Convert to string during lookup
            for keyword in keywords:
                if keyword in name:
                    try: #ensure that GLOBAL_PRICE exists for perfumes.
                        perfume_price = brand_perfumes.loc[brand_perfumes['KEYWORD'].str.lower() == keyword, 'PRICE'].values[0]
                        if row['GLOBAL_PRICE'] < perfume_price:
                            reason = "Perfume price issue"
                            reason_details = ("PERFUME-PRICE", "Perfume price is below the threshold.", "")
                            return reason, reason_details
                    except KeyError:
                        st.error("GLOBAL_PRICE column missing in input file.")
                        return None, None
                    except IndexError:
                        st.error(f"No price found for BRAND: {brand}, KEYWORD: {keyword}")
                        return None, None

    # Blacklisted word in NAME
    if any(black_word in name.split() for black_word in blacklisted_words):
        reason = "Blacklisted word in NAME"
        reason_details = ("BLACKLISTED-WORD", "Name contains a blacklisted word.", "")
        return reason, reason_details

    # BRAND name repeated in NAME
    if brand in name:
        reason = "BRAND name repeated in NAME"
        reason_details = ("BRAND-IN-NAME", "Brand name is found in the product name.", "")
        return reason, reason_details

    # Missing Variation in specific categories
    check_variation_data = config_data.get('check_variation')
    if check_variation_data is not None and int(row['CATEGORY_CODE']) not in [int(i) for i in check_variation_data['ID'].tolist()] and pd.isna(row['VARIATION']):
        reason = "Missing Variation"
        reason_details = ("MISSING-VARIATION", "Variation is missing for this category.", "")
        return reason, reason_details

    # Sensitive Brand in specific categories
    if brand in sensitive_brands and category_code in category_FAS_codes:
        reason = "Sensitive Brand"
        reason_details = ("SENSITIVE-BRAND", "Product is from a sensitive brand in this category.", "")
        return reason, reason_details

    return None, None  # No issues found

# Initialize the app
st.title("Product Validation Tool")

# Load configuration files
config_data = load_config_files()

# Load lists
category_FAS_codes = load_category_FAS()
sensitive_brands = load_sensitive_brands()
blacklisted_words = load_blacklisted_words()
book_categories = load_book_categories()

flags_data = config_data.get('flags')
reasons_dict = {}

if flags_data is not None:
    try:
        # Find the correct column names (case-insensitive)
        flag_col = next((col for col in flags_data.columns if col.lower() == 'flag'), None)
        reason_col = next((col for col in flags_data.columns if col.lower() == 'reason'), None)
        comment_col = next((col for col in flags_data.columns if col.lower() == 'comment'), None)

        if not all([flag_col, reason_col, comment_col]):
            st.error(f"Missing required columns in flags.xlsx. Required: Flag, Reason, Comment. Found: {flags_data.columns.tolist()}")

        else:
            st.subheader("Flags Data")
            st.write(f"Total number of flags: {len(flags_data)}")  # Display total number of flags

    except Exception as e:
        st.error(f"Error processing flags data: {e}")

# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Process uploaded file
if uploaded_file is not None:
    try:
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1', dtype=str)

        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()

        st.write("CSV file loaded successfully. Preview of data:")
        st.write(data.head())

        # Ensure that category code is an integer if possible.

        # Ensure that GLOBAL_PRICE is a float if possible
        try:
            data['GLOBAL_PRICE'] = data['GLOBAL_PRICE'].astype(float)
        except KeyError:
            st.warning("GLOBAL_PRICE column is missing. Perfume price validation will be skipped.")
        except ValueError:
            st.warning("GLOBAL_PRICE column contains invalid values (non-numeric). Perfume price validation will be skipped.")

        # Validation checks
        missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
        missing_brand_or_name = data[data['BRAND'].isna() | (data['BRAND'] == '') |
                                     data['NAME'].isna() | (data['NAME'] == '')]
        single_word_name = data[data['NAME'].str.split().str.len() == 1]

        flagged_rows = []
        for _, row in data.iterrows():
            reason, reason_details = validate_product(row, config_data, blacklisted_words, book_categories,
                                                      sensitive_brands, category_FAS_codes)
            if reason is not None:
                flagged_rows.append({
                    'ProductSetSid': row['PRODUCT_SET_SID'],
                    'ParentSKU': row['PARENTSKU'],
                    'Status': 'Rejected',
                    'Reason': reason,
                    'Comment': reason_details[1]
                })
            else:
                flagged_rows.append({
                    'ProductSetSid': row['PRODUCT_SET_SID'],
                    'ParentSKU': row['PARENTSKU'],
                    'Status': 'Approved',
                    'Reason': "",
                    'Comment': ""
                })

        final_report_rows = flagged_rows  # Store the flagged rows for final report generation.

        st.write(f"Total flagged rows: {len(flagged_rows)}")

    except Exception as e:
        st.error(f"Error processing uploaded file: {e}")

# Final report generation and file download section
if uploaded_file is not None:
    try:
        # Generate the final report DataFrame
        final_report_df = pd.DataFrame(final_report_rows)
        
        # Save the reasons data into a separate DataFrame
        rejection_reasons_df = pd.DataFrame({
            'Reason Code': [item[0] for item in reason_details],
            'Reason Message': [item[1] for item in reason_details],
            'Comment': [item[2] for item in reason_details]
        })
        
        # Creating the Excel file in memory
        with BytesIO() as output:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_report_df.to_excel(writer, sheet_name='ProductSets', index=False)
                rejection_reasons_df.to_excel(writer, sheet_name='RejectionReasons', index=False)

            # Move to the beginning of the BytesIO object
            output.seek(0)

            # Provide the download link to the user
            st.download_button(
                label="Download Final Report",
                data=output,
                file_name="final_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Error generating final report: {e}")
