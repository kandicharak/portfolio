"""
Centralized Configuration Module
All system-wide variables, constants, and database paths are defined here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directory for the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Project name
PROJECT_NAME = "CrewAI Application"

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

# API Keys and Secrets (loaded from .env file)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")
LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "true").lower() == "true"

# ChromaDB configuration (local vector store)
CHROMADB_PATH = BASE_DIR / "chroma_db"
CHROMADB_PERSIST_DIRECTORY = str(CHROMADB_PATH)

# Logging configuration
LOG_FILE = BASE_DIR / "app.log"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Application settings
DEBUG = ENVIRONMENT == "development"
ALLOWED_HOSTS = ["*"] if DEBUG else [os.getenv("ALLOWED_HOST", "localhost")]
