"""Unit tests use explicit local defaults, independently of deployed credentials.

Access/security tests enable and override their own settings. Runtime services
and database integration scripts are not affected by this pytest configuration.
"""
import os

os.environ["ENVIRONMENT"] = "development"
os.environ["AUTH_ENABLED"] = "false"
os.environ["AUTH_COOKIE_SECURE"] = "false"
os.environ["AI_EXECUTION_MODE"] = "inline"
os.environ["AI_ANALYSIS_ENABLED"] = "false"
os.environ["AI_WORKER_TOKEN_SHA256"] = ""
