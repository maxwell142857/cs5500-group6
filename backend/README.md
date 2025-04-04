# Dynamic Learning Akinator API (Backend)

A domain-agnostic Akinator-style guessing game that learns from user interactions, built with FastAPI and Google's Gemini AI models.

## Overview

This application implements a guessing game where the system asks a series of yes/no questions to identify what the user is thinking of. The system:

1. Uses AI models to generate relevant questions
2. Learns from past games to improve its effectiveness
3. Can operate across multiple domains (animals, movies, foods, etc.)
4. Includes voice input/output capabilities

## Features

- **AI-Powered Questions**: Uses Google's Gemini models to generate contextually relevant yes/no questions
- **Pattern Matching**: Identifies similar answer patterns from past successful games
- **Adaptive Learning**: Improves question quality based on game outcomes
- **Multi-Domain Support**: Can be used for any category of items
- **Voice Interface**: Supports speech-to-text and text-to-speech
- **Sophisticated Rate Limiting**: Manages API usage across multiple AI models

## Technical Architecture

The application is built with the following components:

- **FastAPI**: Web framework for APIs
- **PostgreSQL**: Database for storing questions, games, and patterns
- **Redis**: Session management and rate limiting
- **Google Gemini**: AI models for question generation and entity guessing
- **gTTS and Speech Recognition**: Voice processing

## Project Structure

```
backend/
├── main.py                    # FastAPI app entry point and route definitions
├── config.py                  # Configuration (database, API keys, etc.)
├── database/
│   ├── __init__.py            # Database initialization
│   ├── schemas.py             # Database table definitions
│   └── utils.py               # Database helper functions
├── models/
│   ├── __init__.py
│   ├── pydantic_models.py     # Pydantic models for request/response
├── services/
│   ├── __init__.py
│   ├── ai_service.py          # Google Gemini AI integration
│   ├── game_service.py        # Game logic
│   ├── rate_limiter.py        # API rate limiting
│   ├── voice_service.py       # Voice input/output
└── utils/
    ├── __init__.py
    └── helpers.py             # Misc helper functions
```

## Quick Setup with Docker

We provide a setup script that automates the Docker deployment process.

### Prerequisites

- Docker and Docker Compose installed
- A Google Gemini API key

### Using the Setup Script

1. Go to `backend` folder
2. Make the script executable:
   ```bash
   chmod +x setup.sh
   ```
3. Run the script:
   ```bash
   ./setup.sh
   ```
4. Follow the prompts to:
   - Enter your Google Gemini API key
   - Start the Docker services

The script will:
- Check if Docker and Docker Compose are installed and running
- Create the `.env` file with your API key
- Set up the `docker-compose.yml` file
- Optionally start all the services

Once the services are running, you can access:
- API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

### Docker Commands

- View logs:
  ```bash
  docker compose logs -f
  ```

- Stop services:
  ```bash
  docker compose down
  ```

- Restart services:
  ```bash
  docker compose restart
  ```

## Manual Setup

If you prefer to set up the application manually:

### Prerequisites

- Python 3.9+
- PostgreSQL
- Redis
- Google Cloud API key with access to Gemini models

### Environment Variables

Set up the following environment variables:

```
POSTGRES_DB=akinator_db
POSTGRES_USER=akinator_user
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
GEMINI_API=your_gemini_api_key
```

### Installation

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the application:
   ```
   uvicorn main:app --reload
   ```

## API Endpoints

- `POST /api/start-game`: Start a new game session
- `GET /api/get-question/{session_id}`: Get the next question
- `POST /api/submit-answer`: Submit an answer to a question
- `GET /api/make-guess/{session_id}`: Get the system's guess
- `POST /api/submit-result`: Submit the final result of a game
- `POST /api/toggle-voice`: Enable/disable voice features
- `POST /api/voice-input`: Process voice input
- `POST /api/voice-output`: Generate voice output

## Game Flow

1. User starts a game with a specific domain
2. System asks a yes/no question
3. User answers the question
4. Steps 2-3 repeat until the system has enough information 
5. System makes a guess
6. User indicates if the guess was correct
7. System learns from the outcome to improve future games

## AI Rate Limiting

The system implements a sophisticated rate limiter for Google Gemini API:

- Tracks requests per minute (RPM) and requests per day (RPD)
- Rotates between multiple models when rate limits are approached
- Maintains state across server restarts via backup/restore mechanisms