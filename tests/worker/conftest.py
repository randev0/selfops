"""
Add services/worker to sys.path so github_correlation can be imported.
"""
import sys
import os

sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../services/worker")),
)
