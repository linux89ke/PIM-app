import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# Function to check if a category code is in the books category list
def is_book_category(category_code, books_cat_file='Books_cat.txt'):
    try:
        # Read the books category file
        with open(books_cat_file, 'r') as f:
            book_categories = [line.strip() for line in f.readlines()]
        return category_code in book_categories
    except FileNotFoundError:
        st.error(f"File {books_cat_file} not found!")
        return False

# Flagging and rejection logic
def flagging_rejection_logic(data):
    for index, row in data.iterrows():
        category_code = row.get('CATEGORY_CODE')
        name = row.get('NAME', '')
        color = row.get('COLOR', '')
        brand = row.get('BRAND', '')
        variation = row.get('VARIATION', '')
        
        # Check if the category is a book category
        is_book = is_book_category(category_code)

        # Check Missing COLOR (Exempt for books)
        if not is_book and pd.isnull(color):
            st.warning(f"Row {index}: Missing COLOR!")
            data.at[index, 'Status'] = 'Rejected'
            data.at[index, 'Reason'] = '1000005 - Kindly confirm the actual product colour'
            data.at[index, 'Comment'] = 'Kindly include color of the product'

        # Check Single-word NAME (Exempt for books)
        if not is_book and len(name.split()) == 1:
            st.warning(f"Row {index}: Single-word NAME!")
            data.at[index, 'Status'] = 'Rejected'
            data.at[index, 'Reason'] = '1000008 - Kindly Improve Product Name Description'
            data.at[index, 'Comment'] = 'Kindly Improve Product Name'

        # Check Generic BRAND (Exempt for books)
        if brand == 'Generic' and not is_book:
            st.warning(f"Row {index}: Generic BRAND!")
            data.at[index, 'Status'] = 'Rejected'
            data.at[index, 'Reason'] = '1000007 - Other Reason'
            data.at[index, 'Comment'] = 'Kindly use Fashion as brand name for Fashion products'

        # Check if VARIATION is blank (Exempt for books)
        if pd.isnull(variation) and not is_book:
            st.warning(f"Row {index}: Missing VARIATION!")
            data.at[index, 'Status'] = 'Rejected'
            data.at[index, 'Reason'] = '1000007 - Other Reason'
            data.at[index, 'Comment'] = 'Please provide the product variation'

    return data

# Function to process the uploaded CSV
def main():
    st.title("PIM App")

    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"])

    if uploaded_file is not None:
        # Read CSV file
        data = pd.read_csv(uploaded_file)

        # Display first few rows for user
        st.write("Data Preview:")
        st.dataframe(data.head())

        # Apply flagging and rejection logic
        data = flagging_rejection_logic(data)

        # Show the processed dataframe
        st.write("Processed Data Preview:")
        st.dataframe(data)

        # Option to download the processed file as an Excel file
        def to_excel(df):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Products', index=False)
                writer.save()
            return output.getvalue()

        # Download button
        st.download_button(
            label="Download Processed Data",
            data=to_excel(data),
            file_name=f"processed_data_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if __name__ == "__main__":
    main()
