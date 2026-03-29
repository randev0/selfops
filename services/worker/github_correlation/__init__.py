"""
github_correlation
------------------
GitHub deploy/change correlation adapter for SelfOps incident enrichment.

Entry point: correlate_incident()
"""
from github_correlation.correlator import correlate_incident

__all__ = ["correlate_incident"]
