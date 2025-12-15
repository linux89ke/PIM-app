def validate_products(data: pd.DataFrame, support_files: Dict, country_validator: CountryValidator, data_has_warranty_cols: bool, common_sids: Optional[set] = None):
    flags_mapping = support_files['flags_mapping']
    
    # ORDER MATTERS: Priority from highest to lowest
    validations = [
        ("Suspected Fake product", check_suspected_fake_products, {'suspected_fake_df': support_files['suspected_fake'], 'fx_rate': FX_RATE}),
        ("Seller Not approved to sell Refurb", check_refurb_seller_approval, {
            'approved_sellers_ke': support_files['approved_refurb_sellers_ke'],
            'approved_sellers_ug': support_files['approved_refurb_sellers_ug'],
            'country_code': country_validator.code
        }),
        ("Product Warranty", check_product_warranty, {'warranty_category_codes': support_files['warranty_category_codes']}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {'book_category_codes': support_files['book_category_codes'], 'approved_book_sellers': support_files['approved_book_sellers']}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {'perfume_category_codes': support_files['perfume_category_codes'], 'approved_perfume_sellers': support_files['approved_perfume_sellers'], 'sensitive_perfume_brands': support_files['sensitive_perfume_brands']}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {'sneaker_category_codes': support_files['sneaker_category_codes'], 'sneaker_sensitive_brands': support_files['sneaker_sensitive_brands']}),
        ("Suspected counterfeit Jerseys", check_counterfeit_jerseys, {'jerseys_df': support_files['jerseys_config']}),
        ("Prohibited products", check_prohibited_products, {'pattern': compile_regex_patterns(country_validator.load_prohibited_products())}),
        ("Unnecessary words in NAME", check_unnecessary_words, {'pattern': compile_regex_patterns(support_files['unnecessary_words'])}),
        ("Single-word NAME", check_single_word_name, {'book_category_codes': support_files['book_category_codes']}),
        ("Generic BRAND Issues", check_generic_brand_issues, {}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Missing COLOR", check_missing_color, {'pattern': compile_regex_patterns(support_files['colors']), 'color_categories': support_files['color_categories'], 'country_code': country_validator.code}),
        ("Duplicate product", check_duplicate_products, {}),
    ]

    progress_bar = st.progress(0)
    status_text = st.empty()
    results = {}  # Will store expanded flagged DataFrames for final report logic

    # --- Build duplicate groups ---
    duplicate_groups = {}
    cols_for_dup = [c for c in ['NAME','BRAND','SELLER_NAME','COLOR'] if c in data.columns]
    if len(cols_for_dup) == 4:
        data_temp = data.copy()
        data_temp['dup_key'] = data_temp[cols_for_dup].apply(
            lambda r: tuple(str(v).strip().lower() for v in r), axis=1
        )
        dup_counts = data_temp.groupby('dup_key')['PRODUCT_SET_SID'].apply(list).to_dict()
        for dup_key, sid_list in dup_counts.items():
            if len(sid_list) > 1:
                for sid in sid_list:
                    duplicate_groups[sid] = sid_list

    for i, (name, func, kwargs) in enumerate(validations):
        # Skip country-specific validations
        if name != "Seller Not approved to sell Refurb" and country_validator.should_skip_validation(name):
            continue

        ckwargs = {'data': data, **kwargs}

        # Special handling for Product Warranty
        if name == "Product Warranty":
            if not data_has_warranty_cols:
                results[name] = pd.DataFrame(columns=data.columns)
                progress_bar.progress((i + 1) / len(validations))
                continue
            check_data = data.copy()
            if common_sids is not None and len(common_sids) > 0:
                check_data = check_data[check_data['PRODUCT_SET_SID'].isin(common_sids)]
                if check_data.empty:
                    results[name] = pd.DataFrame(columns=data.columns)
                    progress_bar.progress((i + 1) / len(validations))
                    continue
            ckwargs['data'] = check_data

        # Special args
        if name == "Generic BRAND Issues":
            fas = support_files.get('category_fas', pd.DataFrame())
            ckwargs['valid_category_codes_fas'] = fas['ID'].astype(str).tolist() if not fas.empty and 'ID' in fas.columns else []

        status_text.text(f"Running: {name}")

        try:
            res = func(**ckwargs)

            if not res.empty and 'PRODUCT_SET_SID' in res.columns:
                flagged_sids = set(res['PRODUCT_SET_SID'].unique())
                expanded_sids = set()

                # Expand to all duplicates
                for sid in flagged_sids:
                    if sid in duplicate_groups:
                        expanded_sids.update(duplicate_groups[sid])
                    else:
                        expanded_sids.add(sid)

                # Get full data rows for all affected SIDs
                expanded_df = data[data['PRODUCT_SET_SID'].isin(expanded_sids)].copy()

                # Store expanded result — this is critical for final report
                results[name] = expanded_df
            else:
                results[name] = pd.DataFrame(columns=data.columns)

        except Exception as e:
            logger.error(f"Error in {name}: {e}\n{traceback.format_exc()}")
            results[name] = pd.DataFrame(columns=data.columns)

        progress_bar.progress((i + 1) / len(validations))

    status_text.text("Finalizing report...")
    
    rows = []
    processed = set()

    # Process in priority order — highest first
    for name, _, _ in validations:
        if name not in results or results[name].empty:
            continue
        res = results[name]
        if 'PRODUCT_SET_SID' not in res.columns:
            continue

        reason_info = flags_mapping.get(name, ("1000007 - Other Reason", f"Flagged by {name}"))

        # Use only unique SIDs to avoid double-processing
        flagged_sids_df = res[['PRODUCT_SET_SID']].drop_duplicates()
        merged = pd.merge(flagged_sids_df, data, on='PRODUCT_SET_SID', how='left')

        for _, r in merged.iterrows():
            sid = r['PRODUCT_SET_SID']
            if sid in processed:
                continue
            processed.add(sid)
            rows.append({
                'ProductSetSid': sid,
                'ParentSKU': r.get('PARENTSKU', ''),
                'Status': 'Rejected',
                'Reason': reason_info[0],
                'Comment': reason_info[1],
                'FLAG': name,
                'SellerName': r.get('SELLER_NAME', '')
            })

    # Approved products
    approved = data[~data['PRODUCT_SET_SID'].isin(processed)]
    for _, r in approved.iterrows():
        sid = r['PRODUCT_SET_SID']
        if sid not in processed:
            rows.append({
                'ProductSetSid': sid,
                'ParentSKU': r.get('PARENTSKU', ''),
                'Status': 'Approved',
                'Reason': "",
                'Comment': "",
                'FLAG': "",
                'SellerName': r.get('SELLER_NAME', '')
            })
            processed.add(sid)

    final_report_df = country_validator.ensure_status_column(pd.DataFrame(rows))

    # --- Build flag_dfs for expanders (now consistent with final report) ---
    flag_dfs = {}
    for name in [v[0] for v in validations]:
        if name in results and not results[name].empty:
            flag_dfs[name] = results[name]
        else:
            flag_dfs[name] = pd.DataFrame(columns=data.columns)

    progress_bar.empty()
    status_text.empty()

    return final_report_df, flag_dfs
