def check_perfume_price(data, perfumes_df, perfume_category_codes):
    if perfumes_df is None or perfumes_df.empty or not perfume_category_codes:
        return pd.DataFrame()

    perfume_data = data[data['CATEGORY_CODE'].isin(perfume_category_codes)]

    if perfume_data.empty:
        return pd.DataFrame()

    flagged_perfumes = []
    for index, row in perfume_data.iterrows():
        seller_product_name = row['NAME'].strip().lower()
        seller_brand_name = row['BRAND'].strip().lower()
        seller_price = row['GLOBAL_SALE_PRICE'] if pd.notna(row['GLOBAL_SALE_PRICE']) and row['GLOBAL_SALE_PRICE'] > 0 else row['GLOBAL_PRICE']

        if not pd.notna(seller_price) or seller_price <= 0:
            continue

        matched_perfume_row = None # Initialize to None

        # 1. First try to match BRAND and PRODUCT_NAME (more precise)
        for p_index, perfume_row in perfumes_df.iterrows():
            ref_brand = str(perfume_row['BRAND']).strip().lower() # Convert to string
            ref_product_name = str(perfume_row['PRODUCT_NAME']).strip().lower() # Convert to string

            if seller_brand_name == ref_brand and ref_product_name in seller_product_name: # Check for containment
                matched_perfume_row = perfume_row
                break # Found a match, no need to check further

        if matched_perfume_row is None: # If no PRODUCT_NAME match, try KEYWORD
             for p_index, perfume_row in perfumes_df.iterrows():
                ref_brand = str(perfume_row['BRAND']).strip().lower() # Convert to string
                ref_keyword = str(perfume_row['KEYWORD']).strip().lower() # Convert to string
                ref_product_name = str(perfume_row['PRODUCT_NAME']).strip().lower() # Still need product name for reference

                if seller_brand_name == ref_brand and (ref_keyword in seller_product_name or ref_product_name in seller_product_name): # Check for keyword or product name containment
                    matched_perfume_row = perfume_row # Use this row for price check
                    break


        if matched_perfume_row is not None: # If we found a match (either by PRODUCT_NAME or KEYWORD)
            reference_price_dollar = matched_perfume_row['PRICE']
            price_tolerance_percentage = 0.20 # 20% tolerance
            lower_bound = reference_price_dollar * (1 - price_tolerance_percentage)
            upper_bound = reference_price_dollar * (1 + price_tolerance_percentage)

            if not (lower_bound <= seller_price <= upper_bound):
                flagged_perfumes.append(row)

    return pd.DataFrame(flagged_perfumes)
