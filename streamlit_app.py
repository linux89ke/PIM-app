import streamlit as st
import pandas as pd
import numpy as np
import re  # Import the regular expression module

# --- Data Loading and Cleaning ---
@st.cache_data
def load_and_clean_data(file_path):
    """Loads the data, cleans it, and returns a Pandas DataFrame with flags."""
    df = pd.read_csv(file_path, sep=";")

    # Data type conversion and handling missing values
    df['GLOBAL_SALE_PRICE'] = pd.to_numeric(df['GLOBAL_SALE_PRICE'], errors='coerce')
    df['GLOBAL_PRICE'] = pd.to_numeric(df['GLOBAL_PRICE'], errors='coerce')
    df['CATEGORY_CODE'] = pd.to_numeric(df['CATEGORY_CODE'], errors='coerce')

    # **CLEANING THE 'COLOR' Column (Before Flagging)**

    #Handle any empty string/ nan, NaN entries. Use regex for additional cases with \s

    #Flag the original count for reporting's sake, if either missing initially or after data cleanup

    #Flag any blank initial entries: these are important to monitor since the cleaned results will then show all flags together
    df['ORIGINAL_HAS_MISSING_COLOR'] = df['COLOR'].isna()


    #Fill all the nan empty space objects, this is required for downstream string parsing

    df['COLOR'] = df['COLOR'].fillna('')

    #Standardise ALL values, must account that "nan" from empty entries is handled, so a non nan data point
    # Remove leading/trailing whitespace
    df['COLOR'] = df['COLOR'].str.strip()
    # Replace multiple spaces with a single space ( \s means whitespace, + mean one or more)
    df['COLOR'] = df['COLOR'].str.replace(r'\s+', ' ', regex=True)
    # Convert to lowercase for consistent comparison (now safe, nan string are accounted for!)
    df['COLOR'] = df['COLOR'].str.lower()


    # --- Add Data Quality Flags --- after preprocessing
    df['HAS_WRONG_OR_MISSING_COLOR'] = (df['COLOR'] == '') | (df['COLOR'].str.contains(r'^\s+|\s+$', regex=True))| df['COLOR'].str.contains(r'\s{2,}', regex =True)

    return df

# --- Main App ---
def main():
    st.title("Jumia Product Set Explorer")

    # File Upload
    file_path = st.file_uploader("Upload your product data (CSV file)", type=["csv"])

    if file_path is not None:
        # Load and Clean the Data
        df = load_and_clean_data(file_path)

        st.success("Data loaded successfully!")

        # --- Sidebar for Filters and Options ---
        st.sidebar.header("Filters & Options")

        # Type Filter
        unique_types = df['TYPE'].unique()
        selected_types = st.sidebar.multiselect("Product Type:", unique_types, default=unique_types)
        filtered_df = df[df['TYPE'].isin(selected_types)]

        # Brand Filter
        unique_brands = df['BRAND'].unique()
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
                    "Wrong / Missing Color", #This replaces all prior values with the now all encompasing flag
                    # Add your flags here as well.
                ],
                'Count': [
                    filtered_df['HAS_WRONG_OR_MISSING_COLOR'].sum(),
                    #Sum each flag's colunm
                ]
            })

            st.dataframe(flag_summary)
            st.write("Rows that were summed represent all flags marked `True` for any reason")

        # --- Display Data ---
        st.header("Filtered Data")
        st.dataframe(filtered_df)  # Display the filtered DataFrame

if __name__ == "__main__":
    main()
