import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime
import re
import logging
from typing import Dict, List, Optional
import traceback

# -------------------------------------------------
# Config
# -------------------------------------------------
st.set_page_config(page_title="Product Validation Tool", layout="wide")
st.title("Product Validation Tool – Jersey 1000030 ACTIVE")
st.sidebar.success("Suspected counterfeit Jerseys (1000030) is ACTIVE")

# -------------------------------------------------
# File loaders (cached)
# -------------------------------------------------
@st.cache_data(ttl=3600)
def load_txt(filename: str) -> List[str]:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]
    except FileNotFoundError:
        st.warning(f"{filename} not found")
        return []

@st.cache_data(ttl=3600)
def load_excel(filename: str, column: Optional[str] = None):
    try:
        df = pd.read_excel(filename)
        df.columns = df.columns.str.strip()
        if column and column in df.columns:
            return df[column].astype(str).str.strip().tolist()
        return df
    except:
        return [] if column else pd.DataFrame()

@st.cache_data(ttl=3600)
def load_support_files():
    return {
        "sensitive_words": load_txt("sensitive_words.txt"),
        "prohibited_ke": load_txt("prohibited_productsKE.txt"),
        "prohibited_ug": load_txt("prohibited_productsUG.txt"),
        "book_cats": load_excel("Books_cat.xlsx", "CategoryCode"),
        "book_sellers": load_excel("Books_Approved_Sellers.xlsx", "SellerName"),
        "perfume_cats": load_txt("Perfume_cat.txt"),
        "perfume_brands": load_txt("sensitive_perfumes.txt"),
        "perfume_sellers": load_excel("perfumeSellers.xlsx", "SellerName"),
        "sneaker_cats": load_txt("Sneakers_Cat.txt"),
        "sneaker_brands": load_txt("Sneakers_Sensitive.txt"),
        "colors": load_txt("colors.txt"),
        "color_cats": load_txt("color_cats.txt"),
        "fas_cats": load_excel("category_FAS.xlsx", "ID"),
        "perfumes_ref": load_excel("perfumes.xlsx"),
        "jerseys_ref": load_excel("Jerseys.xlsx"),          # NEW
        "reasons": load_excel("reasons.xlsx"),
        "flags_mapping": {
            "Sensitive words": ("1000001 - Brand NOT Allowed", "Banned brand in title"),
            "BRAND name repeated in NAME": ("1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name", "..."),
            "Missing COLOR": ("1000005 - Kindly confirm the actual product colour", "..."),
            "Duplicate product": ("1000007 - Other Reason", "Duplicate product"),
            "Prohibited products": ("1000007 - Other Reason", "Prohibited keyword found"),
            "Single-word NAME": ("1000008 - Kindly Improve Product Name Description", "Title has only one word"),
            "Generic BRAND Issues": ("1000014 - Kindly request for the creation...", "Generic brand in fashion"),
            "Seller Approve to sell books": ("1000028 - Kindly Contact Jumia Seller Support...", "Not approved for books"),
            "Seller Approved to Sell Perfume": ("1000028 - Kindly Contact Jumia Seller Support...", "Not approved for perfume"),
            "Perfume Price Check": ("1000029 - Kindly Contact Jumia Seller Support To Verify...", "Price too low"),
            "Counterfeit Sneakers": ("1000023 - Confirmation of counterfeit product...", "Suspected fake sneaker"),
            "Suspected counterfeit Jerseys": ("1000030 - Suspected Counterfeit/Fake Product", "Jersey suspected counterfeit"),
        },
    }

files = load_support_files()

# -------------------------------------------------
# Helper
# -------------------------------------------------
def regex_pattern(words: List[str]) -> Optional[re.Pattern]:
    if not words:
        return None
    return re.compile("|".join(r"\b" + re.escape(w) + r"\b" for w in words), re.IGNORECASE)

# -------------------------------------------------
# ALL VALIDATION FUNCTIONS
# -------------------------------------------------
def check_sensitive_words(df: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    return df[df["NAME"].str.contains(pattern, case=False, na=False)] if pattern else pd.DataFrame()

def check_prohibited_products(df: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    return df[df["NAME"].str.contains(pattern, case=False, na=False)] if pattern else pd.DataFrame()

def check_missing_color(df: pd.DataFrame, pattern: re.Pattern, cats: List[str]) -> pd.DataFrame:
    if not pattern: return pd.DataFrame()
    sub = df[df["CATEGORY_CODE"].isin(cats)].copy()
    name_ok = sub["NAME"].str.contains(pattern, case=False, na=False)
    color_ok = sub["COLOR"].astype(str).str.contains(pattern, case=False, na=False)
    return sub[~(name_ok | color_ok)]

def check_brand_in_name(df: pd.DataFrame) -> pd.DataFrame:
    mask = df.apply(lambda r: str(r["BRAND"]).lower() in str(r["NAME"]).lower(), axis=1)
    return df[mask]

def check_duplicate_products(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ["NAME", "BRAND", "SELLER_NAME", "COLOR"] if c in df.columns]
    return df[df.duplicated(subset=cols, keep=False)] if len(cols) >= 3 else pd.DataFrame()

def check_single_word_name(df: pd.DataFrame, book_cats: List[str]) -> pd.DataFrame:
    non_books = df[~df["CATEGORY_CODE"].isin(book_cats)]
    return non_books[non_books["NAME"].str.split().str.len() == 1]

def check_generic_brand_issues(df: pd.DataFrame, fas_cats: List[str]) -> pd.DataFrame:
    return df[df["CATEGORY_CODE"].isin(fas_cats) & (df["BRAND"].str.lower() == "generic")]

def check_seller_approved_for_books(df: pd.DataFrame, cats: List[str], sellers: List[str]) -> pd.DataFrame:
    books = df[df["CATEGORY_CODE"].isin(cats)]
    return books[~books["SELLER_NAME"].isin(sellers)] if not books.empty and sellers else pd.DataFrame()

def check_seller_approved_for_perfume(df: pd.DataFrame, cats: List[str], sellers: List[str], brands: List[str]) -> pd.DataFrame:
    perf = df[df["CATEGORY_CODE"].isin(cats)].copy()
    if perf.empty: return pd.DataFrame()
    perf["B"] = perf["BRAND"].str.lower()
    perf["N"] = perf["NAME"].str.lower()
    sensitive = perf["B"].isin(brands)
    fake = perf["B"].isin(["generic", "fashion", "original", "designer", "smart collection", "designers collection"])
    name_has = perf["N"].apply(lambda x: any(b in x for b in brands))
    # FIXED SYNTAX ERROR HERE
    return perf[(sensitive | (fake & name_has)) & (~perf["SELLER_NAME"].isin(sellers))]

def check_counterfeit_sneakers(df: pd.DataFrame, cats: List[str], brands: List[str]) -> pd.DataFrame:
    sn = df[df["CATEGORY_CODE"].isin(cats)].copy()
    if sn.empty: return pd.DataFrame()
    fake_brand = sn["BRAND"].str.lower().isin(["generic", "fashion"])
    name_has = sn["NAME"].str.lower().apply(lambda x: any(b in x for b in brands))
    return sn[fake_brand & name_has]

def check_perfume_price(df: pd.DataFrame, ref_df: pd.DataFrame, cats: List[str]) -> pd.DataFrame:
    if ref_df.empty: return pd.DataFrame()
    perf = df[df["CATEGORY_CODE"].isin(cats)].copy()
    if perf.empty: return pd.DataFrame()
    price = perf["GLOBAL_SALE_PRICE"].fillna(perf["GLOBAL_PRICE"])
    price_usd = price.where(perf.get("CURRENCY", "KES").str.upper() != "KES", price / 132)
    merged = perf.merge(ref_df, left_on=perf["BRAND"].str.lower(), right_on=ref_df["BRAND"].str.lower(), how="left")
    flagged = merged[merged["PRICE_USD"] - price_usd >= 30]
    return flagged[df.columns].drop_duplicates("PRODUCT_SET_SID")

def check_suspected_counterfeit_jerseys(df: pd.DataFrame, jerseys_df: pd.DataFrame) -> pd.DataFrame:
    if jerseys_df.empty: return pd.DataFrame()
    cats = jerseys_df["Categories"].dropna().astype(str).tolist()
    keywords = [str(k).strip().lower() for k in jerseys_df.get("Checklist", pd.Series()).dropna()]
    exempt = jerseys_df.get("Exempted", pd.Series()).dropna().astype(str).tolist()
    sub = df[df["CATEGORY_CODE"].isin(cats)].copy()
    if exempt:
        sub = sub[~sub["SELLER_NAME"].isin(exempt)]
    if not keywords:
        return pd.DataFrame()
    pattern = re.compile("|".join(r"\b" + re.escape(k) + r"\b" for k in keywords), re.IGNORECASE)
    return sub[sub["NAME"].str.contains(pattern, na=False)]

# -------------------------------------------------
# Main validation
# -------------------------------------------------
def run_validation(data: pd.DataFrame, country: str):
    code = "KE" if country == "Kenya" else "UG"
    skip = ["Seller Approve to sell books", "Perfume Price Check", "Seller Approved to Sell Perfume", "Counterfeit Sneakers"] if country == "Uganda" else []

    patterns = {
        "sensitive": regex_pattern(files["sensitive_words"]),
        "prohibited": regex_pattern(files["prohibited_ke"] if country == "Kenya" else files["prohibited_ug"]),
        "color": regex_pattern(files["colors"]),
    }

    checks = [
        ("Sensitive words", check_sensitive_words, {"pattern": patterns["sensitive"]}),
        ("Prohibited products", check_prohibited_products, {"pattern": patterns["prohibited"]}),
        ("Missing COLOR", check_missing_color, {"pattern": patterns["color"], "cats": files["color_cats"]}),
        ("BRAND name repeated in NAME", check_brand_in_name, {}),
        ("Duplicate product", check_duplicate_products, {}),
        ("Single-word NAME", check_single_word_name, {"book_cats": files["book_cats"]}),
        ("Generic BRAND Issues", check_generic_brand_issues, {"fas_cats": [str(x) for x in files["fas_cats"]]}),
        ("Seller Approve to sell books", check_seller_approved_for_books, {"cats": files["book_cats"], "sellers": files["book_sellers"]}),
        ("Perfume Price Check", check_perfume_price, {"ref_df": files["perfumes_ref"], "cats": files["perfume_cats"]}),
        ("Seller Approved to Sell Perfume", check_seller_approved_for_perfume, {"cats": files["perfume_cats"], "sellers": files["perfume_sellers"], "brands": files["perfume_brands"]}),
        ("Counterfeit Sneakers", check_counterfeit_sneakers, {"cats": files["sneaker_cats"], "brands": files["sneaker_brands"]}),
        ("Suspected counterfeit Jerseys", check_suspected_counterfeit_jerseys, {"jerseys_df": files["jerseys_ref"]}),
    ]
    checks = [c for c in checks if c[0] not in skip]

    progress = st.progress(0)
    results = {}
    for i, (name, func, kwargs) in enumerate(checks):
        st.caption(f"Running {name}...")
        try:
            if name == "Generic BRAND Issues":
                results[name] = func(data, [str(x) for x in files["fas_cats"]])
            else:
                results[name] = func(data, **kwargs)
        except Exception as e:
            st.warning(f"{name} error: {e}")
            results[name] = pd.DataFrame()
        progress.progress((i + 1) / len(checks))

    # Build final report
    rejected_sids = set()
    rows = []
    for name, flagged in results.items():
        if flagged.empty or "PRODUCT_SET_SID" not in flagged.columns:
            continue
        reason, comment = files["flags_mapping"].get(name, ("1000007 - Other Reason", name))
        for sid in flagged["PRODUCT_SET_SID"].unique():
            if sid in rejected_sids:
                continue
            rejected_sids.add(sid)
            r = flagged[flagged["PRODUCT_SET_SID"] == sid].iloc[0]
            rows.append({
                "ProductSetSid": sid,
                "ParentSKU": r.get("PARENTSKU", ""),
                "Status": "Rejected",
                "Reason": reason,
                "Comment": comment,
                "FLAG": name,
                "SellerName": r.get("SELLER_NAME", ""),
            })

    approved = data[~data["PRODUCT_SET_SID"].isin(rejected_sids)]
    for _, r in approved.iterrows():
        rows.append({
            "ProductSetSid": r["PRODUCT_SET_SID"],
            "ParentSKU": r.get("PARENTSKU", ""),
            "Status": "Approved",
            "Reason": "", "Comment": "", "FLAG": "", "SellerName": r.get("SELLER_NAME", ""),
        })

    return pd.DataFrame(rows), results

# -------------------------------------------------
# Export
# -------------------------------------------------
def export_report(df: pd.DataFrame) -> BytesIO:
    out = BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        df[["ProductSetSid", "ParentSKU", "Status", "Reason", "Comment", "FLAG", "SellerName"]].to_excel(writer, index=False, sheet_name="ProductSets")
    out.seek(0)
    return out

# -------------------------------------------------
# UI
# -------------------------------------------------
country = st.selectbox("Country", ["Kenya", "Uganda"])
uploaded = st.file_uploader("Upload CSV (semicolon-separated)", type="csv")

if uploaded:
    try:
        df = pd.read_csv(uploaded, sep=";", encoding="ISO-8859-1", dtype=str).fillna("")
        if "ACTIVE_STATUS_COUNTRY" in df.columns:
            df = df[df["ACTIVE_STATUS_COUNTRY"].str.upper().str.contains("KE" if country == "Kenya" else "UG")]

        if df.empty:
            st.error("No products for selected country")
            st.stop()

        with st.spinner("Validating products..."):
            final_report, flag_details = run_validation(df, country)

        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total", len(df))
        col2.metric("Approved", len(final_report[final_report["Status"] == "Approved"]))
        col3.metric("Rejected", len(final_report[final_report["Status"] == "Rejected"]))
        col4.metric("Rejection Rate", f"{len(final_report[final_report['Status']=='Rejected'])/len(df)*100:.1f}%")

        # Flag results
        st.markdown("### Validation Flags")
        for flag, flagged_df in flag_details.items():
            count = len(flagged_df)
            with st.expander(f"{flag} – {count} products", expanded=count>0):
                if count:
                    st.dataframe(flagged_df[["PRODUCT_SET_SID", "NAME", "BRAND", "SELLER_NAME", "CATEGORY_CODE"]].head(100))
                else:
                    st.success("No issues")

        # Download
        st.download_button(
            "Download Final Report",
            export_report(final_report).getvalue(),
            f"Jumia_Validation_{'KE' if country=='Kenya' else 'UG'}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error("Error occurred")
        with st.expander("Details"):
            st.code(traceback.format_exc())
else:
    st.info("Upload your product CSV to start")
