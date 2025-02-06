import pandas as pd
import streamlit as st
from io import BytesIO
from datetime import datetime

# Function to load the uploaded CSV file
def load_file(uploaded_file):
    return pd.read_csv(uploaded_file)

# Function to flag the products based on your logic
def flagging_rejection_logic(data):
    # Load Books categories
    books_categories = pd.read_csv("Books_cat.txt", header=None)
    books_categories = books_categories[0].tolist()

    # Flags and reasons
    flagged_data = []
    
    for _, row in data.iterrows():
        flag_reason = None
        
        # Check for exempted books (skip flagging for books)
        if row['CATEGORY_CODE'] in books_categories:
            flagged_data.append({'Row': row, 'Reason': 'Exempted - Book Category'})
            continue
        
        # Missing color flag
        if pd.isnull(row['COLOR']):
            flagged_data.append({'Row': row, 'Reason': 'Missing COLOR'})
        
        # Single-word name flag
        elif len(str(row['NAME']).split()) <= 1:
            flagged_data.append({'Row': row, 'Reason': 'Single-word NAME'})
        
        # More flags can be added here (e.g., Generic brand, Blacklisted word in name, etc.)

    return flagged_data

# Function to convert flagged data into an Excel file
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Products', index=False)
        writer.save()
    return output.getvalue()

# Streamlit app logic
def main():
    st.title("Product Data Flagging App")

    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"])

    if uploaded_file is not None:
        try:
            # Load the CSV file
            data = load_file(uploaded_file)
            st.write("Data Preview:")
            st.dataframe(data.head())

            # Apply the flagging logic
            flagged_data = flagging_rejection_logic(data)
            
            if flagged_data:
                st.write("Flagged Products:")
                for flag in flagged_data:
                    st.write(f"Product: {flag['Row']['NAME']}, Reason: {flag['Reason']}")
            
            # Allow the user to download the processed file with the flags
            st.download_button(
                label="Download Processed Data",
                data=to_excel(data),
                file_name=f"processed_data_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        except Exception as e:
            st.error(f"Error loading file: {e}")

if __name__ == "__main__":
    main()
