#!/usr/bin/env python3
"""
Performance monitoring script for the Product Validation Tool.
Run this to check system resources and get optimization recommendations.
"""

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("Note: Install 'pip install psutil' for detailed system monitoring")

import os
import sys

def get_system_info():
    """Get basic system information."""
    print("=== System Information ===")
    if HAS_PSUTIL:
        print(f"CPU Cores: {psutil.cpu_count()}")
        print(f"Total RAM: {psutil.virtual_memory().total / (1024**3):.1f} GB")
        print(f"Available RAM: {psutil.virtual_memory().available / (1024**3):.1f} GB")
    else:
        print("CPU Cores: Unknown (install psutil for details)")
        print("RAM: Unknown (install psutil for details)")
    print(f"Python Version: {sys.version}")
    print()

def check_app_requirements():
    """Check if all required packages are installed."""
    print("=== Dependency Check ===")
    required_packages = [
        'streamlit', 'pandas', 'openpyxl', 'xlsxwriter',
        'altair', 'numpy', 'imagehash', 'Pillow', 'requests'
    ]

    missing = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package}")
        except ImportError:
            print(f"✗ {package}")
            missing.append(package)

    if missing:
        print(f"\nMissing packages: {', '.join(missing)}")
        print("Run: pip install -r requirements.txt")
    else:
        print("\nAll dependencies installed!")
    print()

def performance_recommendations():
    """Provide performance optimization recommendations."""
    print("=== Performance Recommendations ===")
    print("1. For large datasets (>10,000 products):")
    print("   - Disable image hashing in the sidebar")
    print("   - Process data in smaller batches if possible")
    print()

    print("2. Memory optimization:")
    print("   - Clear image cache between runs")
    print("   - Close browser tabs when not using the app")
    print("   - Restart the app periodically for large datasets")
    print()

    print("3. Network stability:")
    print("   - Ensure stable internet connection")
    print("   - Image hashing may be slow on poor connections")
    print("   - Consider disabling image features for offline work")
    print()

    print("4. File processing:")
    print("   - Use CSV files instead of Excel for better performance")
    print("   - Ensure files are not corrupted")
    print("   - Check file sizes before upload")
    print()

if __name__ == "__main__":
    get_system_info()
    check_app_requirements()
    performance_recommendations()