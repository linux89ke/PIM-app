import pandas as pd
import streamlit as st
from io import BytesIO
import yaml  # Import the YAML library

# Load configuration from YAML file
def load_config(config_file='config.yaml'):
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        st.error(f"Config file '{config_file}' not found.")
        st.stop()
    except yaml.YAMLError as e:
        st.error(f"Error parsing config file: {e}")
        st.stop()

# ... (rest of your functions, modified to use config) ...

def load_blacklisted_words(config):
    filename = config['blacklisted_file']
    try:
        with open(filename, 'r') as f:
            return [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        st.error(f"Blacklisted words file '{filename}' not found!")
        return []
    except Exception as e:
        st.error(f"Error loading blacklisted words from '{filename}': {e}")
        return []

def load_sensitive_brands(config):
    filename = config['sensitive_brands_file']
    try:
        sensitive_brands_df = pd.read_excel(filename)
        brand_column = config['sensitive_brands_column']
        return sensitive_brands_df[brand_column].tolist()
    except FileNotFoundError:
        st.error(f"Sensitive brands file '{filename}' not found!")
        return []
    except KeyError:
        st.error(f"Column '{config['sensitive_brands_column']}' not found in '{filename}'")
        return []
    except Exception as e:
        st.error(f"Error loading sensitive brands from '{filename}': {e}")
        return []

# ... (modify other file loading functions similarly) ...

# Load category_FAS.xlsx to get the allowed CATEGORY_CODE values
def load_category_FAS(config):
    filename = config['category_fas_file']
    try:
        category_fas_df = pd.read_excel(filename)
        category_code_column = config['category_code_column']
        return category_fas_df[category_code_column].tolist()  # Assuming 'ID' column contains the category codes
    except FileNotFoundError:
        st.error(f"{filename} file not found!")
        return []
    except Exception as e:
        st.error(f"Error loading category_FAS data: {e}")
        return []
    
def load_config_files(config):
    config_files = config['config_files']

    data = {}
    for key, filename in config_files.items():
        try:
            df = pd.read_excel(filename).rename(columns=lambda x: x.strip())  # Strip spaces from column names
            data[key] = df
        except Exception as e:
            st.error(f"❌ Error loading {filename}: {e}")
            if key == 'flags':  # flags.xlsx is critical
                st.stop()
    return data

# Load and process flags data
def process_flags_data(config, flags_data):
    reasons_dict = {}
    try:
        # Find the correct column names (case-insensitive)
        flag_col = config['flag_column']
        reason_col =  config['reason_column']
        comment_col =  config['comment_column']

        if not all([flag_col, reason_col, comment_col]):
            st.error(f"Missing required columns in flags.xlsx. Required: Flag, Reason, Comment.")
            st.stop()

        for _, row in flags_data.iterrows():
            flag = str(row[flag_col]).strip()
            reason = str(row[reason_col]).strip()
            comment = str(row[comment_col]).strip()
            reason_parts = reason.split(' - ', 1)
            code = reason_parts[0]
            message = reason_parts[1] if len(reason_parts) > 1 else ''
            reasons_dict[flag] = (code, message, comment)
        return reasons_dict
    except Exception as e:
        st.error(f"Error processing flags data: {e}")
        st.stop()
        
# Initialize the app
st.title("Product Validation Tool")

# Load configuration
config = load_config()

# Load configuration files
config_data = load_config_files(config)

# Load category_FAS and sensitive brands
category_FAS_codes = load_category_FAS(config)
sensitive_brands = load_sensitive_brands(config)

# Load blacklisted words
blacklisted_words = load_blacklisted_words(config)

# Load and process flags data
flags_data = config_data['flags']
reasons_dict = process_flags_data(config, flags_data)


# File upload section
uploaded_file = st.file_uploader("Upload your CSV file", type='csv')


# Inside the `if uploaded_file is not None:` block, use the encoding from the config
if uploaded_file is not None:
   try:
       excel_filename = uploaded_file.name  #this gives back a fake path for troubleshooting Streamilt not Pandas
       st.write(f"Uploaded Excel File Name: {excel_filename}")

       encoding = config.get('csv_encoding', 'ISO-8859-1')
       data = pd.read_csv(uploaded_file, sep=';', encoding=encoding) # try read file you uploaded as dataframe
       st.write(data.head())
       st.write(f"Data Shape: {data.shape}")
   except pd.errors.ParserError as e:  # pandas load issue? Let handle here
       st.error(f"Pandas ParserError: {e}") # pandas help back info back error here if load CSV has error with stream format to excel data
       st.stop()
   except Exception as e:  # see if basic reads with system but we have more exception checkings to excel not in the format side and handle those
       st.error(f"Error processing the uploaded CSV file: {e}") # file load see more errors in those if so thanks and again check for load files
       st.stop()

#check 1, see file you select what is excel says by Streamtil after selection what gives and share if comes back or it can connect! Also excel has info side by pandas or gives exception if error. Give report for these side, thnks
