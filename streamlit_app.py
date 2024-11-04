        # Generate downloadable Excel files
        def generate_excel(dataframe, sheet_name):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
            return output.getvalue()

        if st.button("Download Approved Products Report"):
            st.download_button(
                label="Download Approved Products",
                data=generate_excel(approved_df, 'Approved Products'),
                file_name="approved_products.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        if st.button("Download Rejected Products Report"):
            st.download_button(
                label="Download Rejected Products",
                data=generate_excel(rejected_df, 'Rejected Products'),
                file_name="rejected_products.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        if st.button("Download Combined Report"):
            st.download_button(
                label="Download Combined Report",
                data=generate_excel(final_report_df, 'Combined Report'),
                file_name="combined_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

except Exception as e:
    st.error(f"An error occurred: {e}")
