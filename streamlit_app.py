import streamlit as st
import pandas as pd
import numpy as np

# --- Data Loading and Cleaning ---
@st.cache_data
def load_and_clean_data(file_path):
    """Loads the data, cleans it, and returns a Pandas DataFrame with flags."""
    df = pd.read_csv(file_path, sep=";", encoding='ISO-8859-1')

    # Data type conversion and handling missing values
    df['GLOBAL_SALE_PRICE'] = pd.to_numeric(df['GLOBAL_SALE_PRICE'], errors='coerce')
    df['GLOBAL_PRICE'] = pd.to_numeric(df['GLOBAL_PRICE'], errors='coerce')
    df['CATEGORY_CODE'] = pd.to_numeric(df['CATEGORY_CODE'], errors='coerce')

    # Cleaning steps
    df['COLOR'] = df['COLOR'].fillna('').str.strip().str.lower().str.replace(r'\s+', ' ', regex=True)
    df['BRAND'] = df['BRAND'].fillna('').str.strip() # fill nan
    df['NAME'] = df['NAME'].fillna('').str.strip()

    return df


def apply_validation_checks(df):
    """Applies specific validation checks and creates flags"""
    df['FLAG_MISSING_COLOR'] = df['COLOR'] == '' # Check if value now has nothing and is not useful
    df['FLAG_MISSING_BRAND_OR_NAME'] = (df['BRAND'] == '') | (df['NAME'] == '')  # Missing BRAND or NAME
    df['FLAG_SINGLE_WORD_NAME'] = (df['NAME'].str.split().str.len() == 1) & (df['BRAND'] != 'Jumia Book')

    df['HAS_MULTIPLE_ISSUES'] = df[['FLAG_MISSING_COLOR', 'FLAG_MISSING_BRAND_OR_NAME', 'FLAG_SINGLE_WORD_NAME']].any(axis=1)
    return df

# --- Main App ---
def main():
    st.title("Jumia Product Set Explorer")

    # File Upload
    file_path = st.file_uploader("Upload your product data (CSV file)", type=["csv"])

    if file_path is not None:
        # Load and Clean the Data
        df = load_and_clean_data(file_path)

        #Apply Validation Checks
        df = apply_validation_checks(df)

        st.success("Data loaded and validated successfully!")

        # --- Sidebar for Filters and Options ---
        st.sidebar.header("Filters & Options")

        # Type Filter
        unique_types = df['TYPE'].unique()
        selected_types = st.sidebar.multiselect("Product Type:", unique_types, default=unique_types)
        filtered_df = df[df['TYPE'].isin(selected_types)]

        # Brand Filter
        unique_brands = filtered_df['BRAND'].unique()
        selected_brands = st.sidebar.multiselect("Brand:", unique_brands, default=unique_brands)
        filtered_df = filtered_df[filtered_df['BRAND'].isin(selected_brands)]

        # Seller Filter
        unique_sellers = filtered_df['SELLER_NAME'].unique()
        selected_sellers = st.sidebar.multiselect("Seller:", unique_sellers, default=unique_sellers)
        filtered_df = filtered_df[filtered_df['SELLER_NAME'].isin(selected_sellers)]

        # Price range
        price_range = st.sidebar.slider("Price Range",
                                         min_value=float(df['GLOBAL_PRICE'].min()),
                                         max_value=float(df['GLOBAL_PRICE'].max()),
                                         value=(float(df['GLOBAL_PRICE'].min()), float(df['GLOBAL_PRICE'].max())))
        filtered_df = filtered_df[(filtered_df['GLOBAL_PRICE'] >= price_range[0]) & (filtered_df['GLOBAL_PRICE'] <= price_range[1])]

        # --- Display Data Quality Flags ---
        st.header("Data Quality Summary")

        with st.expander("Data Quality Flags Details"):
            # Create a summary table of flag counts

            flag_summary = pd.DataFrame({
                'Flag': [
                    "HAS Multiple Issues",
                ],
                'Count': [
                    filtered_df['HAS_MULTIPLE_ISSUES'].sum(),
                ]
            })

            st.dataframe(flag_summary)
            st.write("These Rows may have: Missing/Wrong information and may benefit from review")

        # --- Display Data ---
        st.header("Filtered Data")
        st.dataframe(filtered_df)  # Display the filtered DataFrame

if __name__ == "__main__":
    main()
