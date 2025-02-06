import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# Function to load book category codes from Books_cat.txt
def load_book_category_codes(filepath='Books_cat.txt'):
    with open(filepath, 'r') as file:
        return set(file.read().splitlines())

# Check for missing color, excluding books
def check_missing_color(data, book_category_codes):
    # Filter out book products by checking if CATEGORY_CODE is in book_category_codes
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    missing_color_non_books = non_book_data[non_book_data['COLOR'].isna() | (non_book_data['COLOR'] == '')]
    return missing_color_non_books

# Check for single word names, excluding books
def check_single_word_name(data, book_category_codes):
    # Filter out book products by checking if CATEGORY_CODE is in book_category_codes
    non_book_data = data[~data['CATEGORY_CODE'].isin(book_category_codes)]
    return non_book_data[(non_book_data['NAME'].str.split().str.len() == 1) & (non_book_data['BRAND'] != 'Jumia Book')]

# Check for missing brand or name
def check_missing_brand_or_name(data):
    return data[data['BRAND'].isna() | (data['NAME'].isna())]

# Check for blacklisted words in name
def check_blacklisted_words(data, blacklisted_words):
    return data[data['NAME'].str.contains('|'.join(blacklisted_words), na=False)]

# Flagging products based on different conditions
def flag_products(data, book_category_codes, blacklisted_words):
    flagged_data = pd.DataFrame()

    # Check for missing color (exempting books)
    missing_color = check_missing_color(data, book_category_codes)
    if not missing_color.empty:
        missing_color['Flag'] = 'Missing COLOR'
        flagged_data = pd.concat([flagged_data, missing_color])

    # Check for single word name (exempting books)
    single_word_name = check_single_word_name(data, book_category_codes)
    if not single_word_name.empty:
        single_word_name['Flag'] = 'Single-word NAME'
        flagged_data = pd.concat([flagged_data, single_word_name])

    # Check for missing brand or name
    missing_brand_or_name = check_missing_brand_or_name(data)
    if not missing_brand_or_name.empty:
        missing_brand_or_name['Flag'] = 'Missing BRAND or NAME'
        flagged_data = pd.concat([flagged_data, missing_brand_or_name])

    # Check for blacklisted words in name
    blacklisted = check_blacklisted_words(data, blacklisted_words)
    if not blacklisted.empty:
        blacklisted['Flag'] = 'Blacklisted word in NAME'
        flagged_data = pd.concat([flagged_data, blacklisted])

    return flagged_data

# Function to generate report
def generate_report(data, book_category_codes, blacklisted_words, output_path='flagged_products.xlsx'):
    # Flag the products
    flagged_data = flag_products(data, book_category_codes, blacklisted_words)

    # Save flagged data to an Excel file
    with pd.ExcelWriter(output_path) as writer:
        flagged_data.to_excel(writer, sheet_name='Flagged Products', index=False)
        print(f"Report generated at {output_path}")

# Streamlit interface
def main():
    st.title("Product Flagging Tool")

    # Upload product data CSV
    uploaded_file = st.file_uploader("Upload Product Data CSV", type="csv")
    if uploaded_file is not None:
        data = pd.read_csv(uploaded_file)
        st.write("Uploaded data preview", data.head())

        # Upload the book category codes
        book_category_codes = load_book_category_codes('Books_cat.txt')
        
        # Upload blacklisted words
        blacklisted_file = st.file_uploader("Upload Blacklisted Words File", type="txt")
        if blacklisted_file is not None:
            blacklisted_words = set(blacklisted_file.read().decode().splitlines())
        
            # Flagging the products
            flagged_data = flag_products(data, book_category_codes, blacklisted_words)

            # Display flagged products
            st.write("Flagged Products", flagged_data)

            # Allow download of flagged products as an Excel file
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                flagged_data.to_excel(writer, sheet_name="Flagged Products", index=False)
            output.seek(0)
            st.download_button(
                label="Download Flagged Products Report",
                data=output,
                file_name="flagged_products.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Please upload the blacklisted words file.")
    else:
        st.warning("Please upload the product data CSV.")

# Run the app
if __name__ == "__main__":
    main()
