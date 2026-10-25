import os

# Base directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Data directory
DATA_DIR = os.path.join(BASE_DIR, "data")

# Default paths
DEFAULT_SESSION_FILE = os.path.join(DATA_DIR, "jetra_session.json")
DEFAULT_DB_FILE = os.path.join(DATA_DIR, "jetra_local.db")
DEFAULT_GROUPS_FILE = os.path.join(DATA_DIR, "groups_only.json")
