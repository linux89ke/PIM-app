import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

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

# Load and validate configuration files (excluding flags.xlsx)
def load_config_files():
    config_files = {
        'check_variation': 'check_variation.xlsx',
        'category_fas': 'category_FAS.xlsx',
        'perfumes': 'perfumes.xlsx',
        'reasons': 'reasons.xlsx' # Keeping reasons.xlsx for descriptions
    }

    data = {}
    for key, filename in config_files.items():
        try:
            df = pd.read_excel(filename).rename(columns=lambda x: x.strip())
            data[key] = df
        except FileNotFoundError:
            st.warning(f"{filename} file not found, functionality related to this file will be limited.")
        except Exception as e:
            st.error(f"❌ Error loading {filename}: {e}")
    return data

# Validation check functions (modularized)
def check_missing_color(data):
    return data[data['COLOR'].isna() | (data['COLOR'] == '')]

def check_missing_brand_or_name(data):
    return data[data['BRAND'].isna() | (data['BRAND'] == '') | data['NAME'].isna() | (data['NAME'] == '')]

def check_single_word_name(data):
    return data[(data['NAME'].str.split().str.len() == 1) & (data['BRAND'] != 'Jumia Book')]

def check_generic_brand_issues(data, valid_category_codes_fas):
    return data[(data['CATEGORY_CODE'].isin(valid_category_codes_fas)) & (data['BRAND'] == 'Generic')]

def check_perfume_price_issues(data, perfumes_data):
    flagged_perfumes = []
    for _, row in data.iterrows():
        brand = row['BRAND']
        if brand in perfumes_data['BRAND'].values:
            keywords = perfumes_data[perfumes_data['BRAND'] == brand]['KEYWORD'].tolist()
            for keyword in keywords:
                if isinstance(row['NAME'], str) and keyword.lower() in row['NAME'].lower():
                    perfume_price = perfumes_data.loc[
                        (perfumes_data['BRAND'] == brand) &
                        (perfumes_data['KEYWORD'] == keyword), 'PRICE'].values[0]
                    if row['GLOBAL_PRICE'] < perfume_price:
                        flagged_perfumes.append(row)
                        break
    return pd.DataFrame(flagged_perfumes)

def check_blacklisted_words(data, blacklisted_words):
    return data[data['NAME'].apply(lambda name:
        any(black_word.lower() in str(name).lower().split() for black_word in blacklisted_words))]

def check_brand_in_name(data):
    return data[data.apply(lambda row:
        isinstance(row['BRAND'], str) and isinstance(row['NAME'], str) and
        row['BRAND'].lower() in row['NAME'].lower(), axis=1)]

def check_duplicate_products(data):
    return data[data.duplicated(subset=['NAME', 'BRAND', 'SELLER_NAME'], keep=False)]

def validate_products(data, config_data, blacklisted_words, reasons_dict):
    valid_category_codes_fas = config_data['category_fas']['ID'].tolist()
    perfumes_data = config_data['perfumes']

    missing_color = check_missing_color(data)
    missing_brand_or_name = check_missing_brand_or_name(data)
    single_word_name = check_single_word_name(data)
    generic_brand_issues = check_generic_brand_issues(data, valid_category_codes_fas)
    perfume_price_issues = check_perfume_price_issues(data, perfumes_data)
    flagged_blacklisted = check_blacklisted_words(data, blacklisted_words)
    brand_in_name_issues = check_brand_in_name(data)
    duplicate_products = check_duplicate_products(data)

    # Define flags and rejection reasons directly in code
    flags = {
        "Brand NOT Allowed": ("1000001", "Brand NOT Allowed", "Brand is not permitted"),
        "Brand Name Repeated in Product Name": ("1000002", "Kindly Ensure Brand Name Is Not Repeated In Product Name", "Remove redundant brand name from product name"),
        "Restricted Brand": ("1000003", "Restricted Brand", "Brand is restricted"),
        "Wrong Category": ("1000004", "Wrong Category", "Category is incorrect"),
        "Confirm Actual Product Colour": ("1000005", "Kindly confirm the actual product colour", "Verify and correct the product color"),
        "Wrong Description": ("1000006", "Wrong description", "Product description is inaccurate"),
        "Other Reason": ("1000007", "Other Reason", "Unspecified reason, check comments"),
        "Improve Product Name Description": ("1000008", "Kindly Improve Product Name Description", "Enhance product name for clarity and detail"),
        "Improve Product Name and Description": ("1000009", "Kindly improve product name description, product description", "Improve both name and description"),
        "Product Weight Format": ("1000010", "Product Weight in .kg only eg 1, 0.5", "Format product weight correctly in kg"),
        "Provide Product Model Number": ("1000011", "Kindly Provide Product's Model Number", "Add the product model number"),
        "Provide Health/Food Regulation Registration": ("1000012", "Kindly Provide Product's Health/Food Regulation Registration", "Provide necessary health/food regulation details"),
        "Provide Product Warranty Details": ("1000013", "Kindly Provide Product Warranty Details", "Include product warranty information"),
        "Request Brand Creation": ("1000014", "Kindly request for the creation of this product's actual brand", "Request brand creation for accurate branding"),
        "Fundamentals Of A Product CANNOT Be Changed": ("1000015", "Fundamentals Of A Product CANNOT Be Changed; Brand/UPC/MPN", "Cannot change fundamental product attributes"),
        "Proof of NG manufacture or assembly required": ("1000016", "Proof of NG manufacture or assembly required", "Provide proof of local manufacture or assembly"),
        "Product Description Narrative Paragraph 1": ("1000017", "Kindly Ensure Product Description Is a Narrative, Paragraph 1", "Ensure description is narrative paragraph 1"),
        "Product Description Narrative Paragraph 2": ("1000018", "Kindly Ensure Product Description Is a Narrative, Paragraph 2", "Ensure description is narrative paragraph 2"),
        "Return Rate Too High": ("1000019", "Return Rate of the item is too high (Not Authorized)", "Item return rate exceeds threshold"),
        "Rejection Rate Too High": ("1000020", "Return and rejection rate is greater than 3% (Not Authorized)", "Item rejection rate exceeds threshold"),
        "Over 3 Failed Deliveries": ("1000021", "Over 3 failed deliveries -Size and Quality (Not Authorized)", "Item has excessive delivery failures"),
        "Too Many Bad Reviews": ("1000022", "Item has received greater than 3 bad reviews (Not Authorized)", "Item has too many negative reviews"),
        "Confirmation of Counterfeit": ("1000023", "Confirmation of counterfeit product by Jumia technical team", "Product confirmed as counterfeit"),
        "No License to Sell": ("1000024", "Product does not have a license to be sold via Jumia (Not Authorized)", "Seller lacks license to sell this product on Jumia"),
        "Out of Stock Too Often": ("1000025", "Product was out of stock on greater than 3 occasions (Not Authorized)", "Item is frequently out of stock"),
        "Failed QC Too Often": ("1000026", "Product has failed QC greater than 3 times within 1 week - Not Authorized", "Item has repeatedly failed quality control"),
        "Low Content Score": ("1000027", "Product has low content score", "Product content score is too low"),
        "Contact Seller Support Possibility 1": ("1000028", "Kindly Contact Jumia Seller Support To Confirm Possibility Of Resolving This Issue", "Contact seller support for issue resolution possibility 1"),
        "Contact Seller Support Verify Possibility 2": ("1000029", "Kindly Contact Jumia Seller Support To Verify This Product's Authenticity", "Contact seller support to verify product authenticity"),
        "Suspected Counterfeit/Fake Product": ("1000030", "Suspected Counterfeit/Fake Product.Please Contact Seller Support For Guidance", "Suspected counterfeit, contact seller support"),
        "Review & Update Price/Confirm The Price": ("1000031", "Kindly Review & Update This Product's Price or Confirm The Price", "Review and update/confirm product price"),
        "Mismatch Product Images & Description": ("1000032", "The Product Images & Product Description Do Not Match. Kindly Correct Urgently", "Product images and description are inconsistent"),
        "Keywords Inappropriate": ("1000033", "Keywords in your content/ Product name / description has been rejected", "Inappropriate keywords used in content"),
        "Infringing Images": ("1000034", "Listing of infringing images on the Jumia platform is prohibited", "Listing contains infringing images"),
        "Confirm Actual Product Weight": ("1000035", "Kindly Confirm Actual Product Weight", "Verify and correct product weight"),
        "Confirm Actual Product Size": ("1000036", "Kindly confirm the actual product size", "Verify and correct product size"),
        "UK Sizes Only": ("1000037", "UK Sizes Only eg 8, 10, 12 etc", "UK sizes are not allowed, use EU or other sizes"),
        "Ensure ALL Sizes as Variation": ("1000038", "Kindly Ensure ALL Sizes Of This Product Are Created As Variations", "Create all sizes as variations of the product"),
        "Product Poorly Created Variation": ("1000039", "Product Poorly Created. Each Variation Of This Product Should Be Well Created", "Improve creation of product variations"),
        "Image Corrupt": ("1000040", "Image corrupt", "Product image file is corrupt"),
        "Wrong Image": ("1000041", "Wrong Image, To Many Things Displayed", "Incorrect image or too many elements in image"),
        "Follow Image Guideline": ("1000042", "Kindly follow our product image upload guideline.", "Adhere to product image upload guidelines"),
        "Add More Descriptive Images": ("1000043", "Kindly add more descriptive images showing different angles", "Add more images showing different angles"),
        "Improve Image Quality - Stretched": ("1000044", "Kindly Improve Image Quality; Image looks stretched", "Improve image quality, image appears stretched"),
        "Improve Image Quality - Blurry": ("1000045", "Kindly Improve Image Quality; Image Is Blurry", "Improve image quality, image is blurry"),
        "Improve Image Quality - Poorly Edited": ("1000046", "Kindly Improve Image Quality; Image Poorly Edited", "Improve image quality, image is poorly edited"),
        "Poor Image Quality/Editing - Use Studio Value": ("1000047", "Poor Image Quality/Editing - Consider using our Studio Value", "Improve image quality, consider using Studio Value service"),
        "Images Without Watermark": ("1000048", "Kindly Ensure ALL Product Images Are Without Watermarks", "Remove watermarks from all product images"),
        "Price Too High": ("1000049", "Price too high", "Product price is too high"),
        "Missing COLOR": ("MC", "Missing Color", "Color is mandatory"),
        "Missing BRAND or NAME": ("BNM", "Missing Brand or Name", "Brand and Name are essential"),
        "Single-word NAME": ("SWN", "Single-word Name", "Name should be descriptive"),
        "Generic BRAND Issues": ("GB", "Generic BRAND", "Use specific brand for FAS"),
        "Perfume price issue": ("PPI", "Perfume Price Issue", "Price below configured threshold"),
        "Blacklisted word in NAME": ("BLW", "Blacklisted word in NAME", "Inappropriate word used"),
        "BRAND name repeated in NAME": ("BRN", "BRAND name repeated in NAME", "Redundant brand name in product name"),
        "Duplicate product": ("DUP", "Duplicate product", "Product is a duplicate listing"),
        "Long Product Name": ("LPN", "Product Name Too Long", "Keep product names concise") # Example new flag - already in your code
    }

    final_report_rows = []
    for _, row in data.iterrows():
        reason = None
        reason_details = None

        validations = [
            (missing_color, "Missing COLOR"),
            (missing_brand_or_name, "Missing BRAND or NAME"),
            (single_word_name, "Single-word NAME"),
            (generic_brand_issues, "Generic BRAND Issues"),
            (perfume_price_issues, "Perfume price issue"),
            (flagged_blacklisted, "Blacklisted word in NAME"),
            (brand_in_name_issues, "BRAND name repeated in NAME"),
            (duplicate_products, "Duplicate product"),
            (check_long_product_name(data), "Long Product Name") # Include the new flag here
        ]

        for validation_df, flag_name in validations:
            if not validation_df.empty and row['PRODUCT_SET_SID'] in validation_df['PRODUCT_SET_SID'].values:
                reason = flag_name
                reason_details = flags.get(flag_name, ("", "", "")) # Get reason details from in-code dict
                break

        status = 'Rejected' if reason else 'Approved'
        reason_code, reason_message, comment = flags.get(reason, ("", "", "")) if reason else ("", "", "")
        detailed_reason = f"{reason_code} - {reason_message}" if reason_code and reason_message else ""

        report_reason_message = reason_message if reason_message else reason # Fallback to flag name if no message

        final_report_rows.append({
            'ProductSetSid': row['PRODUCT_SET_SID'],
            'ParentSKU': row.get('PARENTSKU', ''),
            'Status': status,
            'Reason': report_reason_message, # Use the message for final report
            'Comment': comment
        })

    final_report_df = pd.DataFrame(final_report_rows)
    return final_report_df


# Initialize the app
st.title("Product Validation Tool")

# Load configuration files
config_data = load_config_files()

# Load blacklisted words
blacklisted_words = load_blacklisted_words()

# Load reasons dictionary from reasons.xlsx
reasons_df = config_data.get('reasons', pd.DataFrame()) # Load reasons.xlsx
reasons_dict = {}
if not reasons_df.empty:
    for _, row in reasons_df.iterrows():
        code = row['CODE - REJECTION_REASON']
        message = row['Message']
        comment = row['Comment']
        reasons_dict[f"{code} - {message}"] = (code, message, comment) # Create reasons_dict from dataframe
else:
    st.warning("reasons.xlsx file could not be loaded, detailed reasons in reports will be unavailable.")


# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Process uploaded file
if uploaded_file is not None:
    try:
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')

        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()

        st.write("CSV file loaded successfully. Preview of data:")
        st.write(data.head())

        # Validation and report generation
        final_report_df = validate_products(data, config_data, blacklisted_words, reasons_dict)

        # Split into approved and rejected
        approved_df = final_report_df[final_report_df['Status'] == 'Approved']
        rejected_df = final_report_df[final_report_df['Status'] == 'Rejected']

        # Display results metrics
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Products", len(data))
            st.metric("Approved Products", len(approved_df))
        with col2:
            st.metric("Rejected Products", len(rejected_df))
            st.metric("Rejection Rate", f"{(len(rejected_df)/len(data)*100):.1f}%")

        # Show detailed results in expanders (using flags list for titles)
        validation_results = [
            ("Missing COLOR", check_missing_color(data)),
            ("Missing BRAND or NAME", check_missing_brand_or_name(data)),
            ("Single-word NAME", check_single_word_name(data)),
            ("Generic BRAND Issues", check_generic_brand_issues(data, config_data['category_fas']['ID'].tolist())),
            ("Perfume Price Issues", check_perfume_price_issues(data, config_data['perfumes'])),
            ("Blacklisted Words", check_blacklisted_words(data, blacklisted_words)),
            ("Brand in Name", check_brand_in_name(data)),
            ("Duplicate Products", check_duplicate_products(data)),
            ("Long Product Name", check_long_product_name(data)) # Include the new flag here
        ]

        for title, df in validation_results:
            with st.expander(f"{title} ({len(df)} products)"):
                if not df.empty:
                    st.dataframe(df)
                else:
                    st.write("No issues found")

        # Export functions
        def to_excel(df1, df2, sheet1_name="ProductSets", sheet2_name="RejectionReasons"):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df1.to_excel(writer, index=False, sheet_name=sheet1_name)
                df2.to_excel(writer, index=False, sheet_name=sheet2_name)
            output.seek(0)
            return output

        # Download buttons
        current_date = datetime.now().strftime("%Y-%m-%d")

        col1, col2, col3 = st.columns(3)

        with col1:
            final_report_excel = to_excel(final_report_df, reasons_df, "ProductSets", "RejectionReasons")
            st.download_button(
                label="Final Export",
                data=final_report_excel,
                file_name=f"Final_Report_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with col2:
            rejected_excel = to_excel(rejected_df, reasons_df, "ProductSets", "RejectionReasons")
            st.download_button(
                label="Rejected Export",
                data=rejected_excel,
                file_name=f"Rejected_Products_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with col3:
            approved_excel = to_excel(approved_df, reasons_df, "ProductSets", "RejectionReasons")
            st.download_button(
                label="Approved Export",
                data=approved_excel,
                file_name=f"Approved_Products_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Error processing the uploaded file: {e}")
