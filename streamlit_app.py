import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# Set page config
st.set_page_config(page_title="Product Validation Tool", layout="centered")

# Function to load blacklisted words from a file
def load_blacklisted_words():
    try:
        with open('blacklisted.txt', 'r') as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        st.error("blacklisted.txt file not found!")
        return []
    except Exception as e:
        st.error(f"Error loading blacklisted words: {e}")
        return []

# Load configuration files
def load_config_files():
    config_files = {
        'flags': 'flags.xlsx',
        'check_variation': 'check_variation.xlsx',
        'category_fas': 'category_FAS.xlsx',
        'perfumes': 'perfumes.xlsx',
        'reasons': 'reasons.xlsx'
    }
    data = {}
    for key, filename in config_files.items():
        try:
            df = pd.read_excel(filename).rename(columns=lambda x: x.strip())
            data[key] = df
        except Exception as e:
            st.error(f"❌ Error loading {filename}: {e}")
            if key == 'flags':  # Stop if critical file is missing
                st.stop()
    return data

# Initialize the app
st.title("Product Validation Tool")

# Tabs for organizing content
tab1, tab2, tab3 = st.tabs(["Upload File", "Images", "Export Data"])  # Renamed second tab to "Images"

# Load configuration files
config_data = load_config_files()

# Tab 1: File upload
with tab1:
    uploaded_file = st.file_uploader("Upload your CSV file", type='csv')

# Process uploaded file and validate data
if uploaded_file is not None:
    try:
        data = pd.read_csv(uploaded_file, sep=';', encoding='ISO-8859-1')

        if data.empty:
            st.warning("The uploaded file is empty.")
            st.stop()

        # Placeholder for tab content
        results = {}  # Store validation results for display in Tab 2

        # Validation checks (example: Missing COLOR)
        missing_color = data[data['COLOR'].isna() | (data['COLOR'] == '')]
        results["Missing COLOR"] = missing_color

        # Other validation checks can be added similarly...

        # Save validation results for the next tab
        with tab2:
            st.write("### Images")  # Content for "Images" tab
            st.write("This tab is reserved for images.")  # Placeholder content

        # Export data
        with tab3:
            st.write("### Export Validated Data")
            def to_excel(df1, df2, sheet1_name="ProductSets", sheet2_name="RejectionReasons"):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df1.to_excel(writer, index=False, sheet_name=sheet1_name)
                    df2.to_excel(writer, index=False, sheet_name=sheet2_name)
                output.seek(0)
                return output

            # Example export: Placeholder data
            final_report_df = pd.DataFrame({
                'ProductSetSid': data['PRODUCT_SET_SID'],
                'Status': ['Approved'] * len(data)  # Placeholder statuses
            })

            current_date = datetime.now().strftime("%Y-%m-%d")
            final_report_excel = to_excel(final_report_df, config_data['reasons'])
            st.download_button(
                label="Download Final Report",
                data=final_report_excel,
                file_name=f"Final_Report_{current_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Error processing the uploaded file: {e}")
