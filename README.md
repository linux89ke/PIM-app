# 🎈 Product Validation Tool

A Streamlit app for validating product data with duplicate detection and compliance checking.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://blank-app-template.streamlit.app/)

### Performance Optimization Tips

**For Faster Processing:**
- **Disable Image Hashing**: Uncheck "Enable Image Hashing" in the sidebar for large datasets (>10k products)
- **Clear Cache**: Use the "🧹 Clear Image Cache" button to free memory between runs
- **Large Datasets**: For datasets >500MB, disable image hashing and consider processing in smaller batches

**Memory Management:**
- The app caches image hashes to avoid re-downloading
- Image cache is automatically cleared after processing when image hashing is disabled
- Manual cache clearing is available in the sidebar

**Network Stability:**
- Increased timeouts and retry logic for image downloads
- Reduced concurrent connections to prevent network overload
- Better error handling for connection issues

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```

### Performance Monitoring

Run the performance check script to diagnose issues:

```
$ python performance_check.py
```

This will check your system resources and provide optimization recommendations.
