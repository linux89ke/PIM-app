def check_hidden_brand_in_name(data: pd.DataFrame, brands_list: List[str]) -> pd.DataFrame:
    """
    Flags products where Brand is 'Generic' but the FIRST WORD of the Product Name 
    is a real brand name (e.g. "Nike Shoes").
    
    IMPROVED VERSION: Filters out common generic descriptor words to reduce false positives.
    
    Args:
        data: DataFrame with 'NAME' and 'BRAND' columns
        brands_list: List of valid brand names from brands.txt
    
    Returns:
        DataFrame with flagged products
    """
    if not {'NAME', 'BRAND'}.issubset(data.columns) or not brands_list:
        return pd.DataFrame(columns=data.columns)
    
    # ============================================================================
    # BLACKLIST: Common words that should NOT be treated as brand names
    # These words appear in brands.txt but are generic descriptors, not brands
    # ============================================================================
    GENERIC_BLACKLIST = {
        # Quality/Type descriptors
        'handheld', 'lightweight', 'heavy', 'premium', 'quality', 'professional',
        'luxury', 'luxurious', 'original', 'genuine', 'authentic', 'official', 
        'branded', 'new', 'best', 'top', 'high', 'low', 'superior', 'deluxe',
        
        # Quantity/Size
        'multi', 'single', 'double', 'triple', 'large', 'small', 'medium',
        'extra', 'mini', 'midi', 'maxi', 'compact', 'full', 'half',
        
        # Technology/Features
        'electric', 'manual', 'automatic', 'portable', 'foldable', 'adjustable',
        'waterproof', 'wireless', 'rechargeable', 'led', 'digital', 'analog',
        'smart', 'super', 'ultra', 'mega', 'advanced', 'basic',
        
        # Style/Design
        'stylish', 'elegant', 'modern', 'vintage', 'retro', 'classic',
        'contemporary', 'traditional', 'fashionable', 'trendy',
        
        # Material/Quality
        'durable', 'sturdy', 'strong', 'soft', 'comfortable', 'breathable',
        'flexible', 'rigid', 'smooth', 'rough',
        
        # Scope/Coverage
        'universal', 'standard', 'essential', 'complete', 'comprehensive',
        'total', 'whole', 'entire',
        
        # Common product categories (if they appear as brands)
        'spotlight', 'fashion', 'accessories', 'collection', 'series',
        'range', 'line', 'set', 'kit', 'pack', 'bundle',
    }
    
    # 1. Filter for only 'Generic' brand items (Optimization)
    generic_items = data[data['BRAND'].astype(str).str.strip().str.lower() == 'generic'].copy()
    
    if generic_items.empty:
        return pd.DataFrame(columns=data.columns)
    
    # 2. Filter brands list to exclude generic words
    # Sort by length (desc) to match longer brand names first (e.g. "Giorgio Armani" before "Armani")
    filtered_brands = sorted(
        [str(b).strip() for b in brands_list 
         if b 
         and str(b).strip().lower() not in GENERIC_BLACKLIST  # Exclude generic words
         and str(b).strip().lower() != 'generic'               # Exclude 'generic' itself
         and len(str(b).strip()) >= 2                          # Minimum 2 characters
        ],
        key=len, 
        reverse=True
    )
    
    if not filtered_brands:
        return pd.DataFrame(columns=data.columns)
    
    # 3. Build regex pattern
    # ^ : Anchors match to the start of the string (The First Word)
    # \b : Ensures it matches the whole word (e.g. "Apple" matches, "Applepie" does not)
    pattern = re.compile(r'^(' + '|'.join(re.escape(b) for b in filtered_brands) + r')\b', re.IGNORECASE)
    
    # 4. Check if Name starts with any of the filtered brands
    mask = generic_items['NAME'].astype(str).str.strip().str.contains(pattern, regex=True, na=False)
    
    return generic_items[mask].drop_duplicates(subset=['PRODUCT_SET_SID'])
