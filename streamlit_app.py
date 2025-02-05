import streamlit as st
import pandas as pd
import numpy as np
import re
import os  # Import the os module

# --- Data Loading and Cleaning ---
@st.cache_data
def load_and_clean_data(file_path):
    """Loads the data, cleans it, and returns a Pandas DataFrame with flags."""
    df = pd.read_csv(file_path, sep=";", encoding='ISO-8859-1')

    # Data type conversion and handling missing values
    df['GLOBAL_SALE_PRICE'] = pd.to_numeric(df['GLOBAL_SALE_PRICE'], errors='coerce')
    df['GLOBAL_PRICE'] = pd.to_numeric(df['GLOBAL_PRICE'], errors='coerce')
    df['CATEGORY_CODE'] = pd.to_numeric(df['CATEGORY_CODE'], errors='coerce')

    # Cleaning
    df['COLOR'] = df['COLOR'].fillna('').str.strip().str.lower().str.replace(r'\s+', ' ', regex=True)
    df['BRAND'] = df['BRAND'].fillna('').str.strip()
    df['NAME'] = df['NAME'].fillna('').str.strip()

    return df

# --- Data Quality Flags ---
def apply_validation_checks(df, book_category_codes):
    """Applies validation checks and creates flags."""

    df['FLAG_MISSING_COLOR'] = df['COLOR'] == '' # Check if value now has nothing and is not useful
    df['FLAG_MISSING_BRAND_OR_NAME'] = (df['BRAND'] == '') | (df['NAME'] == '')  # Missing BRAND or NAME


    df['FLAG_SINGLE_WORD_NAME'] = (df['NAME'].str.split().str.len() == 1) & (~df['CATEGORY_CODE'].isin(book_category_codes))  # Only flag if not category codes.

    df['HAS_MULTIPLE_ISSUES'] = df[['FLAG_MISSING_COLOR', 'FLAG_MISSING_BRAND_OR_NAME', 'FLAG_SINGLE_WORD_NAME']].any(axis=1) #If any single issue present flag now for has issues. Can be used and monitored as needed or sliced
    return df

def load_book_category_codes(file_path):
    """Loads category codes from Books_cat.txt"""

    try:
        with open(file_path, 'r') as f:
            book_category_codes = set(int(line.strip()) for line in f)
        return book_category_codes
    except FileNotFoundError:
        st.error(f"File not found: {file_path}")
        return set()  # Return an empty set
    except Exception as e:
        st.error(f"Error reading {file_path}: {e}")
        return set() # or [] an empty set as fail safe

def main():
    st.title("Jumia Product Set Explorer")

    # File Upload for Main Data
    file_path = st.file_uploader("Upload your product data (CSV file)", type=["csv"])

    # Determine the location with function! for pathing
    current_dir = os.path.dirname(os.path.abspath(__file__))
    book_cat_path = os.path.join(current_dir, "Books_cat.txt")
    #Load the local text file with this. We do type handling here for easy control with type check


    if file_path is not None and os.path.exists(book_cat_path) :
      try:
          # Load the categories
          book_category_codes = load_book_category_codes(book_cat_path)
          df = load_and_clean_data(file_path)
          df = apply_validation_checks(df, book_category_codes)  # Use list here

          #Display file data

          st.subheader ("File content overview")

          st.dataframe (df)

          # Summaries
          st.subheader ("File Quality")
          st.write("If multiple issues exist it warrents an look!")
          with st.expander("Flagged Rows Summary-READ ME TO VALIDATE ALL COLUMNS MEET QUALITY", expanded=True):

                quality = pd.DataFrame({
                    'Flag': [
                        "HAS Multiple Issues",
                    ],
                    'Count': [
                        df['HAS_MULTIPLE_ISSUES'].sum(),
                    ]
                })

                st.dataframe (quality)

          #More controls or what not come here..

      except Exception as e:
          st.error(f"Oh no error again! here is description: {e}")

    #We'll report it didnt open so people use the tools correctly:
    elif file_path is None or  not os.path.exists(book_cat_path): #Or else report the error, not just pass and break functionality (make consumers more away of status on there loading).

      st.warning (f"load text at default:{book_cat_path}\" Please load a dataset CSV")

#Ensuring for script and only its purpose runs only during loading of page.
if __name__ == "__main__":
    main()
