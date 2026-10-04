"""
WSGI entry point for PythonAnywhere (or any WSGI server).
FastAPI is ASGI, so we wrap it with a2wsgi.ASGIMiddleware.

In PythonAnywhere web app settings point WSGI configuration file to this file:
  /home/YOUR_USERNAME/portfolio-site/portfolio-site/wsgi.py
"""
import sys
from pathlib import Path

# Ensure project root is on Python path so `src.main` imports correctly.
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from a2wsgi import ASGIMiddleware
from src.main import auth_app as application

# PythonAnywhere looks for the variable named `application`.
application = ASGIMiddleware(application)
