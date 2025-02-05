import streamlit as st
import pandas as pd
import os

def load_excel(file_path):
    """Load an Excel file and return a DataFrame."""
    try:
        return pd.read_excel(file_path)
    except Exception as e:
        st.error(f"Error loading {file_path}: {e}")
        return pd.DataFrame()

def validate_data(df, category_fas, wrong_brands, perfumes, check_variation, blacklisted):
    """Perform all validation checks on the uploaded data."""
    flagged_products = []
    
    # Convert reference files to sets for quick lookup
    category_fas_set = set(category_fas['ID'])
    wrong_brands_set = set(wrong_brands['Brand'])
    perfumes_dict = perfumes.set_index('PRODUCT_NAME')['PRICE'].to_dict()
    check_variation_set = set(check_variation['ID'])
    blacklisted_set = set(blacklisted['Word'])
    
    for _, row in df.iterrows():
        reason = []
        
        # Category and Brand validation
        if row['CATEGORY_CODE'] in category_fas_set and row['BRAND'] == 'Generic':
            reason.append("Kindly use Fashion as Brand name for fashion items.")
        
        # Brand name check
        if row['BRAND'] in wrong_brands_set:
            reason.append("Incorrect Brand Name")
        
        # Price validation
        product_name = row['NAME']
        if product_name in perfumes_dict:
            price_diff = abs(row['GLOBAL_SALE_PRICE'] - perfumes_dict[product_name])
            if price_diff < (0.3 * perfumes_dict[product_name]):
                reason.append("Perfume price too low")
        
        # Variation check
        if row['CATEGORY_CODE'] in check_variation_set and pd.isna(row['VARIATION']):
            reason.append("Variation required but missing")
        
        # Blacklisted words
        if any(word in row['NAME'].split() for word in blacklisted_set):
            reason.append("Blacklisted word in NAME")
        
        if reason:
            flagged_products.append({
                'ProductSetSid': row['PRODUCT_SET_SID'],
                'ParentSKU': row['PARENTSKU'],
                'Status': 'Rejected',
                'Reason': ", ".join(reason),
                'Comment': ", ".join(reason)
            })
    
    return pd.DataFrame(flagged_products)

def main():
    st.title("Product Validation Tool")
    
    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"])
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        
        # Load reference data
        category_fas = load_excel("pages/category_FAS.xlsx")
        wrong_brands = load_excel("pages/wrong_brands.xlsx")
        perfumes = load_excel("pages/perfumes.xlsx")
        check_variation = load_excel("pages/check_variation.xlsx")
        blacklisted = load_excel("pages/blacklisted.xlsx")
        
        # Validate data
        flagged_df = validate_data(df, category_fas, wrong_brands, perfumes, check_variation, blacklisted)
        
        # Display results
        if not flagged_df.empty:
            st.write("### Flagged Products")
            st.dataframe(flagged_df)
            
            # Download option
            csv = flagged_df.to_csv(index=False).encode('utf-8')
            st.download_button("Download Flagged Products", csv, "flagged_products.csv", "text/csv")
        else:
            st.success("No issues found!")
    
if __name__ == "__main__":
    main()
