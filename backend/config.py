import os

# Database Configuration
DB_NAME = os.environ.get('POSTGRES_DB', 'akinator_db')
DB_USER = os.environ.get('POSTGRES_USER', 'akinator_user')
DB_PASS = os.environ.get('POSTGRES_PASSWORD', 'password')
DB_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
DB_PORT = os.environ.get('POSTGRES_PORT', '5432')

# Redis Configuration
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))

# Session Configuration
SESSION_TIMEOUT = int(os.environ.get('SESSION_TIMEOUT', 3600))

# Gemini API Configuration
GEMINI_API_KEY = os.environ.get('GEMINI_API')

# Define available Gemini models with their rate limits
GEMINI_MODELS = [
    {
        "name": "gemma-3-27b-it",  
        "rpm_limit": 30,
        "rpd_limit": 14400,
        "client": None  # Will be initialized on startup
    },
    {
        "name": "gemini-2.0-flash",
        "rpm_limit": 15,
        "rpd_limit": 1500,
        "client": None
    },
    {
        "name": "gemini-2.0-flash-lite",
        "rpm_limit": 30,
        "rpd_limit": 1500,
        "client": None
    },
    {
        "name": "gemini-1.5-flash",
        "rpm_limit": 15,
        "rpd_limit": 1500,
        "client": None
    }
]