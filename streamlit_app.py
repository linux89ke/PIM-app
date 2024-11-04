import pandas as pd
import streamlit as st
import datetime

# Load `reasons.xlsx` and `refurb.txt` files for reference
reasons_file = "reasons.xlsx"
refurb_file = "refurb.txt"

# Function to generate an Excel file with the final report
def generate_excel(dataframe, sheet_name):
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"report_{current_date}.xlsx"
    with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
        dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
    return filename

# Streamlit UI
st.title("Product Validation Report")

# File upload for the main CSV
uploaded_file = st.file_uploader("Upload your CSV file", type="csv")
if uploaded_file is not None:
    try:
        # Load the uploaded CSV file
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')
        
        # Check for and rename duplicate columns if any
        if data.columns.duplicated().any():
            data.columns = pd.io.parsers.ParserBase({'names': data.columns})._maybe_dedup_names(data.columns)
            st.warning("Duplicate columns found in the CSV file. They have been renamed to avoid issues.")

        # Load refurb seller list
        with open(refurb_file, "r") as f:
            refurb_sellers = f.read().splitlines()
        
        # Initialize columns for flags
        data["Reason"] = ""
        data["Comment"] = ""
        data["Status"] = "Approved"

        # Define flagging rules and reason messages, with checks for column existence
        flags = []
        
        if "COLOR" in data.columns:
            flags.append(("Missing color", data["COLOR"].isnull(), "1000005 - Kindly confirm the actual product colour"))
        
        if "BRAND" in data.columns and "NAME" in data.columns:
            flags.append(("Missing brand or name", data["BRAND"].isnull() | data["NAME"].isnull(), "1000007 - Other Reason"))
            flags.append(("Single-word names", data["NAME"].str.split().str.len() == 1, "1000008 - Kindly Improve Product Name Description"))
            flags.append(("Generic brands", data["BRAND"].str.lower() == "generic", "1000007 - Other Reason"))
            flags.append(("Brand name repetition in the product name", data["NAME"].str.contains(data["BRAND"], case=False), "1000002 - Kindly Ensure Brand Name Is Not Repeated In Product Name"))
        
        if "GLOBAL_SALE_PRICE" in data.columns and "PRICE" in data.columns:
            flags.append(("Perfume price issues", 
                          (data["GLOBAL_SALE_PRICE"] - data["PRICE"]).abs() < 0.3 * data["PRICE"], 
                          "1000030 - Suspected Counterfeit/Fake Product"))
        
        if "NAME" in data.columns:
            flags.append(("Blacklisted words in names", data["NAME"].str.contains(r'\b(?:blacklisted_words_here)\b', case=False), 
                          "1000033 - Keywords in your content/ Product name / description has been blacklisted"))
            flags.append(("Refurbished check", 
                          data["NAME"].str.contains(r'\b(refurb|refurbished)\b', case=False) & ~data["SELLER_NAME"].isin(refurb_sellers),
                          "1000040 - Unauthorized Refurbished Product"))

        # Apply flags and update `Reason`, `Comment`, and `Status` columns
        for flag_name, condition, reason_message in flags:
            data.loc[condition, "Reason"] = reason_message
            data.loc[condition, "Comment"] = flag_name
            data.loc[condition, "Status"] = "Rejected"
        
        # Show preview of flagged data
        st.write("Flagged Data Preview:")
        st.write(data[data["Status"] == "Rejected"])

        # Generate and offer download link for the report
        if st.button("Download Combined Report"):
            filename = generate_excel(data, "ProductSets")
            with open(filename, "rb") as file:
                st.download_button(label="Download Report", data=file, file_name=filename)
        
    except Exception as e:
        st.error(f"Error loading file: {e}")
else:
    st.write("Please upload a CSV file to continue.")
