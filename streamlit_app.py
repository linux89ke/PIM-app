import streamlit as st
import pandas as pd
import numpy as np

# --- Data Loading and Cleaning ---
@st.cache_data
def load_and_clean_data(file_path):
    """Loads the data, cleans it, and returns a Pandas DataFrame with flags."""
    df = pd.read_csv(file_path, sep=";")

    # Data type conversion and handling missing values
    df['GLOBAL_SALE_PRICE'] = pd.to_numeric(df['GLOBAL_SALE_PRICE'], errors='coerce')
    df['GLOBAL_PRICE'] = pd.to_numeric(df['GLOBAL_PRICE'], errors='coerce')
    df['CATEGORY_CODE'] = pd.to_numeric(df['CATEGORY_CODE'], errors='coerce')

    # Fill missing values in 'COLOR' with 'Unknown'
    df['COLOR'] = df['COLOR'].fillna('Unknown')

    # --- Add Data Quality Flags ---
    df['HAS_MISSING_COLOR'] = df['COLOR'] == 'Unknown'  # Flag missing color values
    df['INCONSISTENT_COLOR_SPACING'] = df['COLOR'].str.contains(r'^\s+|\s+$', regex=True) # Regex to flag leading or trailing spaces.
    #More flags will be placed here


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
                    "Missing Color",
                    "Inconsistent Color Spacing",
                    # Add your flags here as well.
                ],
                'Count': [
                    filtered_df['HAS_MISSING_COLOR'].sum(),
                    filtered_df['INCONSISTENT_COLOR_SPACING'].sum(),
                    #Sum each flag's colunm
                ]
            })

            st.dataframe(flag_summary)
            st.write("Rows that were summed represent all flags marked `True` for any reason")

        # --- Display Data ---
        st.header("Filtered Data")
        st.dataframe(filtered_df)  # Display the filtered DataFrame


        # --- Basic Metrics ---
        st.header("Key Metrics")
        st.write(f"Number of Products: {len(filtered_df)}")

        average_price = filtered_df['GLOBAL_PRICE'].mean()
        st.write(f"Average Price: {average_price:.2f}")


        # --- Visualizations (Example) ---
        st.header("Visualizations")

        # Category Counts Bar Chart (Example)
        st.subheader("Product Count by Category")
        category_counts = filtered_df['CATEGORY'].value_counts()
        st.bar_chart(category_counts)

        # Seller Counts Bar Chart (Example)
        st.subheader("Product Count by Seller")
        seller_counts = filtered_df['SELLER_NAME'].value_counts()
        st.bar_chart(seller_counts)

if __name__ == "__main__":
    main()
