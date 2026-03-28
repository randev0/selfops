"""
conftest.py — adds the analysis-service source directory to sys.path so that
tests can import domain.models, structured_output_parser, and schemas without
installing any packages.
"""
import os
import sys

_SVC = os.path.join(os.path.dirname(__file__), "../../services/analysis-service")
sys.path.insert(0, os.path.abspath(_SVC))
