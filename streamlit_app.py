import pandas as pd

import matplotlib.pyplot as plt

import io



st.set_page_config(page_title="QC Backlog Dashboard", layout="wide")

st.title("📋 QC Backlog Report")



uploaded_file = st.file_uploader("Upload the Excel file", type=["xlsx"])



def get_value(df, keyword):

    match = df[df.iloc[:, 0].astype(str).str.contains(keyword, case=False, na=False)]

    if not match.empty:

        return match.iloc[0, 1]

    return "-"



if uploaded_file:

    try:

        df = pd.read_excel(uploaded_file, sheet_name=1)



        # Extract required values

        values = {

            "Total Pending - SOB": {"SC Pre-QC": "116650", "PIM LOCAL": "2965"},

            "Total Backlog - SOB (Pending above SLA)": {"SC Pre-QC": "11690", "PIM LOCAL": "825"},

            "Oldest Pending - SOB": {"SC Pre-QC": "23 hours", "PIM LOCAL": "16 hours"},

            "Total Pending - COB": {"SC Pre-QC": "0", "PIM LOCAL": "0"},

            "Total Backlog - COB (Pending above SLA)": {"SC Pre-QC": "0", "PIM LOCAL": "0"},

            "Oldest Pending - COB": {"SC Pre-QC": "-", "PIM LOCAL": "-"},

        }



        pim_metrics = {

            "PIM QC Export Received (SOB)": get_value(df, "PIM QC Export Received"),

            "PIM QC Export Approved": get_value(df, "PIM QC Export Approved"),

            "PIM QC Export Rejected": get_value(df, "PIM QC Export Rejected"),

            "PIM QC Export Imported (COB)": get_value(df, "PIM QC Export Imported"),

            "SKU Count of Error Message Received": get_value(df, "SKU Count of Error Message Received"),

            "One or more products were not processed": get_value(df, "One or more products"),

            "The product Set with SID does not match Parent SKU": get_value(df, "Set with SID does not match"),

            "Error Message Reviewed Within 24 Hours": get_value(df, "Error Message Reviewed Within 24 Hours"),

        }



        # QC Backlog Table

        st.subheader("🧾 QC Backlog Overview")



        st.markdown("**SC Pre-QC / PIM LOCAL - SOB**")

        sob_df = pd.DataFrame({

            "": list(values.keys())[:3],

            "SC Pre-QC": [values[key]["SC Pre-QC"] for key in list(values.keys())[:3]],

            "PIM LOCAL": [values[key]["PIM LOCAL"] for key in list(values.keys())[:3]]

        })

        st.table(sob_df)



        st.markdown("**SC Pre-QC / PIM LOCAL - COB**")

        cob_df = pd.DataFrame({

            "": list(values.keys())[3:],

            "SC Pre-QC": [values[key]["SC Pre-QC"] for key in list(values.keys())[3:]],

            "PIM LOCAL": [values[key]["PIM LOCAL"] for key in list(values.keys())[3:]]

        })

        st.table(cob_df)



        # PIM QC Section

        st.markdown("---")

        st.subheader("🏢 Vendor Center - PIM Pre-QC")



        metrics_df = pd.DataFrame({

            "Metric": list(pim_metrics.keys()),

            "Value": list(pim_metrics.values())

        })



        st.table(metrics_df)



        # Charts (for 4 key metrics only)

        st.markdown("---")

        st.subheader("📈 Visual Summary (Main 4 Metrics)")



        chart_data = metrics_df.iloc[:4]

        chart_data = chart_data[chart_data["Value"] != "-"]  # Remove blanks



        try:

            chart_data["Value"] = chart_data["Value"].astype(int)



            st.markdown("**Bar Chart**")

            st.bar_chart(data=chart_data.set_index("Metric"))



            st.markdown("**Pie Chart**")

            fig, ax = plt.subplots()

            ax.pie(chart_data["Value"], labels=chart_data["Metric"], autopct="%1.1f%%", startangle=90)

            ax.axis("equal")

            st.pyplot(fig)

        except Exception as e:

            st.warning("Charts not shown due to invalid data format.")



        # Download Summary

        st.markdown("---")

        st.subheader("📥 Download Summary")



        csv = metrics_df.to_csv(index=False).encode("utf-8")

        st.download_button(

            label="Download PIM Metrics CSV",

            data=csv,

            file_name="pim_qc_summary.csv",

            mime="text/csv"

        )



    except Exception as e:

        st.error(f"Error reading file: {e}")
