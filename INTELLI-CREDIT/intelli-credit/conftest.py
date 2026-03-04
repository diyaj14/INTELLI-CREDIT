"""
conftest.py — pytest configuration
Adds the project root to sys.path so all module imports work from any test file.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))
