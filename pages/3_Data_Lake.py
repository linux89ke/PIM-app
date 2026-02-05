import streamlit as st
import pandas as pd
from io import BytesIO
import os

st.set_page_config(page_title="Jumia Data Merger", layout="wide")
st.title("📊 Jumia Kenya Data Merger")
st.markdown("""
Upload multiple Excel files (like `KE_Full_Data_YYYY-MM-DD.xlsx`) containing **ProductSets** and **Sellers Data** sheets.  
The app will:
- Merge all **ProductSets** rows (with a `Data_Date` column extracted from filename if possible)
- Aggregate **Sellers Data** (sum Rejected + Approved per seller, then re-rank)
- Provide a downloadable merged Excel file
""")

uploaded_files = st.file_uploader(
    "Upload one or more Excel files",
    type=["xlsx"],
    accept_multiple_files=True
)

if uploaded_files:
    product_dfs = []
    sellers_agg = {}

    for uploaded_file in uploaded_files:
        try:
            # Extract potential date from filename (format: KE_Full_Data_2026-02-05.xlsx)
            filename = uploaded_file.name
            date_str = "Unknown"
            if "_" in filename and "." in filename:
                parts = filename.rsplit("_", 2)  # Split from right to handle varying prefixes
                if len(parts) >= 2:
                    potential_date = parts[-1].split(".")[0]
                    if len(potential_date) == 10 and potential_date.count("-") == 2:
                        date_str = potential_date

            # Read sheets
            xl = pd.ExcelFile(uploaded_file)

            # === ProductSets ===
            if "ProductSets" in xl.sheet_names:
                df_prod = pd.read_excel(uploaded_file, sheet_name="ProductSets")
                df_prod["Data_Date"] = date_str
                df_prod["Source_File"] = filename
                product_dfs.append(df_prod)
                st.success(f"✓ Loaded ProductSets from {filename} ({len(df_prod)} rows)")

            # === Sellers Data ===
            if "Sellers Data" in xl.sheet_names:
                # Skip the title row (row 1 is usually "Sellers Summary...")
                df_sell = pd.read_excel(uploaded_file, sheet_name="Sellers Data", skiprows=1)
                # Clean empty rows
                df_sell = df_sell.dropna(subset=["SELLER_NAME"])
                # Ensure numeric columns
                df_sell["Rejected"] = pd.to_numeric(df_sell["Rejected"], errors="coerce").fillna(0).astype(int)
                df_sell["Approved"] = pd.to_numeric(df_sell["Approved"], errors="coerce").fillna(0).astype(int)

                for _, row in df_sell.iterrows():
                    seller = str(row["SELLER_NAME"]).strip()
                    if seller and seller != "nan":
                        if seller not in sellers_agg:
                            sellers_agg[seller] = {"SELLER_NAME": seller, "Rejected": 0, "Approved": 0}
                        sellers_agg[seller]["Rejected"] += row["Rejected"]
                        sellers_agg[seller]["Approved"] += row["Approved"]

                st.success(f"✓ Loaded Sellers Data from {filename}")

        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}")

    # === Merge ProductSets ===
    if product_dfs:
        merged_products = pd.concat(product_dfs, ignore_index=True)
        st.subheader(f"Merged ProductSets ({len(merged_products):,} rows)")
        st.dataframe(merged_products)
    else:
        merged_products = pd.DataFrame()
        st.warning("No ProductSets data found in uploaded files.")

    # === Aggregate Sellers ===
    if sellers_agg:
        merged_sellers = pd.DataFrame.from_dict(sellers_agg, orient="index")
        merged_sellers = merged_sellers[["SELLER_NAME", "Rejected", "Approved"]]
        merged_sellers["Total"] = merged_sellers["Rejected"] + merged_sellers["Approved"]
        merged_sellers = merged_sellers.sort_values("Total", ascending=False).reset_index(drop=True)
        merged_sellers.insert(0, "Rank", merged_sellers.index + 1)
        merged_sellers = merged_sellers.drop(columns=["Total"])  # Optional: remove helper column
        st.subheader(f"Aggregated Sellers Data ({len(merged_sellers)} sellers)")
        st.dataframe(merged_sellers)
    else:
        merged_sellers = pd.DataFrame(columns=["Rank", "SELLER_NAME", "Rejected", "Approved"])
        st.warning("No Sellers Data found in uploaded files.")

    # === Download merged file ===
    if len(merged_products) > 0 or len(merged_sellers) > 0:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            merged_products.to_excel(writer, sheet_name="ProductSets", index=False)
            merged_sellers.to_excel(writer, sheet_name="Sellers Data", index=False)
        output.seek(0)

        st.download_button(
            label="📥 Download Merged Excel File",
            data=output,
            file_name=f"Merged_Jumia_Data_{pd.Timestamp('today').strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.success("Merged file ready for download!")
    else:
        st.error("No data to merge.")

else:
    st.info("Please upload at least one Excel file to begin.")
