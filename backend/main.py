from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import uuid
from datetime import datetime
import psycopg2
from psycopg2.extras import DictCursor
import redis
import os
from contextlib import contextmanager
import random

from google import genai


# Configure database connection details
DB_NAME = os.environ.get('POSTGRES_DB', 'akinator_db')
DB_USER = os.environ.get('POSTGRES_USER', 'akinator_user')
DB_PASS = os.environ.get('POSTGRES_PASSWORD', 'password')
DB_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
DB_PORT = os.environ.get('POSTGRES_PORT', '5432')

REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))

client = genai.Client(api_key=os.environ.get('GEMINI_API'))
chat = client.chats.create(model="gemini-2.0-flash")

# Create FastAPI app
app = FastAPI(
    title="Dynamic Learning Akinator API",
    description="A domain-agnostic Akinator-style guessing game that learns from user interactions",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development - specify origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Updated Pydantic model for start game request
class StartGameRequest(BaseModel):
    domain: str  # Make domain required - user must specify what kind of thing they're thinking of
    user_id: Optional[int] = None

class StartGameResponse(BaseModel):
    session_id: str
    message: str


class QuestionResponse(BaseModel):
    session_id: str
    question_id: Optional[int] = None
    question: Optional[str] = None
    questions_asked: int
    should_guess: Optional[bool] = False
    message: Optional[str] = None

class AnswerRequest(BaseModel):
    session_id: str
    question_id: int
    answer: str

class AnswerResponse(BaseModel):
    session_id: str
    should_guess: bool
    top_entities: List[Dict[str, Any]]
    questions_asked: int

class GuessResponse(BaseModel):
    session_id: str
    guess: str
    questions_asked: int

class ResultRequest(BaseModel):
    session_id: str
    was_correct: bool
    actual_entity: Optional[str] = None
    entity_type: Optional[str] = None

class ResultResponse(BaseModel):
    status: str
    message: str

class HealthResponse(BaseModel):
    status: str
    version: str
    models_loaded: bool

# Database connection helpers
@contextmanager
def get_db_connection():
    """Get a PostgreSQL connection with automatic closing"""
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT
    )
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def get_db_cursor(conn):
    """Get a cursor with automatic closing"""
    cursor = conn.cursor(cursor_factory=DictCursor)
    try:
        yield cursor
    finally:
        cursor.close()

# Redis client - configure for connection pooling
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True,
    socket_timeout=5
)

# Session timeout (in seconds)
SESSION_TIMEOUT = int(os.environ.get('SESSION_TIMEOUT', 3600))

# Initialize database schema
def init_db():
    """Initialize database schema"""
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            # Entities table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS entities (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE,
                attributes JSONB,
                domain TEXT,
                guess_count INTEGER DEFAULT 0,
                correct_guess_count INTEGER DEFAULT 0,
                last_updated TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Questions table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS questions (
                id SERIAL PRIMARY KEY,
                question_text TEXT UNIQUE,
                feature TEXT,
                information_gain REAL DEFAULT 0,
                ask_count INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 0,
                last_used TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Users table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE,
                preferences JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Game history table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_history (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                target_entity TEXT,
                domain TEXT,
                was_correct BOOLEAN,
                questions_count INTEGER,
                duration INTEGER,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            ''')
            
            # Game questions table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_questions (
                id SERIAL PRIMARY KEY,
                game_id TEXT,
                question_id INTEGER,
                answer TEXT,
                ask_order INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (game_id) REFERENCES game_history (id),
                FOREIGN KEY (question_id) REFERENCES questions (id)
            )
            ''')
            
            # Create indices
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_domain ON entities (domain)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_name ON entities (name)')
            
            conn.commit()

# Database operations
def get_entities(domain=None):
    """Get entities, optionally filtered by domain"""
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            if domain:
                cursor.execute(
                    "SELECT name, attributes FROM entities WHERE domain = %s",
                    (domain,)
                )
            else:
                cursor.execute("SELECT name, attributes FROM entities")
            
            results = cursor.fetchall()
            return {row['name']: row['attributes'] for row in results}

def get_questions():
    """Get all questions ordered by information gain"""
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            cursor.execute(
                "SELECT id, question_text, feature, information_gain FROM questions "
                "ORDER BY information_gain DESC"
            )
            return cursor.fetchall()

def create_session(domain=None, user_id=None, use_ai=True):
    """Create a new game session"""
    session_id = str(uuid.uuid4())
    
    # Get entities, optionally filtered by domain
    entities = get_entities(domain)
    
    # For a dynamic learning system, we need to handle the case where there are no entities yet
    entity_probabilities = {}
    if entities:
        entity_probabilities = {entity: 1.0/len(entities) for entity in entities}
    
    state = {
        'domain': domain,
        'user_id': user_id,
        'use_ai': use_ai,
        'questions_asked': 0,
        'entity_probabilities': entity_probabilities,
        'asked_features': [],
        'question_history': [],
        'no_entities': len(entities) == 0,  # Flag to indicate if we're starting with no entities
        'start_time': datetime.now().timestamp()
    }
    
    # Store in Redis with expiration
    redis_client.setex(
        f"session:{session_id}", 
        SESSION_TIMEOUT,
        json.dumps(state)
    )
    
    return session_id

def get_session(session_id):
    """Get session state"""
    state_json = redis_client.get(f"session:{session_id}")
    if state_json:
        return json.loads(state_json)
    return None

def update_session(session_id, state):
    """Update session state"""
    redis_client.setex(
        f"session:{session_id}", 
        SESSION_TIMEOUT,
        json.dumps(state)
    )

def record_question(session_id, question_id, answer):
    """Record a question asked during a session"""
    state = get_session(session_id)
    if not state:
        return False
    
    # Add to question history
    question_record = {
        'question_id': question_id,
        'answer': answer,
        'timestamp': datetime.now().timestamp()
    }
    state['question_history'].append(question_record)
    
    # Update question stats
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            cursor.execute(
                "UPDATE questions SET ask_count = ask_count + 1, last_used = %s WHERE id = %s",
                (datetime.now(), question_id)
            )
            conn.commit()
    
    # Update session
    update_session(session_id, state)
    return True

def end_session(session_id, target_entity, was_correct, entity_type=None):
    """End a game session and record results"""
    state = get_session(session_id)
    if not state:
        return False
    
    # Calculate duration
    duration = int(datetime.now().timestamp() - state['start_time'])
    
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            # Record game in history
            cursor.execute(
                "INSERT INTO game_history (id, user_id, target_entity, domain, was_correct, "
                "questions_count, duration) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (session_id, state.get('user_id'), target_entity, 
                state.get('domain'), was_correct, state['questions_asked'], duration)
            )
            
            # Record questions
            for i, q_record in enumerate(state['question_history']):
                cursor.execute(
                    "INSERT INTO game_questions (game_id, question_id, answer, ask_order, timestamp) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (session_id, q_record['question_id'], q_record['answer'], i, 
                    datetime.fromtimestamp(q_record['timestamp']))
                )
            
            # Update entity stats or create new entity
            cursor.execute(
                "SELECT id FROM entities WHERE name = %s",
                (target_entity,)
            )
            entity_result = cursor.fetchone()
            
            if entity_result:
                # Entity exists, update stats
                cursor.execute(
                    "UPDATE entities SET guess_count = guess_count + 1, "
                    "correct_guess_count = correct_guess_count + %s, "
                    "last_updated = %s WHERE id = %s",
                    (1 if was_correct else 0, datetime.now(), entity_result[0])
                )
            else:
                # New entity, create it based on the yes answers
                attributes = extract_attributes_from_history(state['question_history'])
                cursor.execute(
                    "INSERT INTO entities (name, attributes, domain, last_updated) VALUES (%s, %s, %s, %s)",
                    (target_entity, json.dumps(attributes), state.get('domain') or entity_type, datetime.now())
                )
            
            conn.commit()
    
    # Remove session from Redis
    redis_client.delete(f"session:{session_id}")
    
    return True

def extract_attributes_from_history(question_history):
    """Extract attributes from question history based on 'yes' answers"""
    attributes = {"features": []}
    
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            for record in question_history:
                if record['answer'].lower() in ['yes', 'y']:
                    # Get the feature for this question
                    cursor.execute(
                        "SELECT feature FROM questions WHERE id = %s",
                        (record['question_id'],)
                    )
                    result = cursor.fetchone()
                    if result:
                        attributes["features"].append(result[0])
    
    return attributes

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database and models on startup"""
    # Initialize database
    init_db()
    

# API endpoints
@app.post("/api/start-game", response_model=StartGameResponse)
async def start_game(request: StartGameRequest):
    """Start a new game session with a specific domain, using only AI-generated questions"""
    
    # Create a new session
    session_id = str(uuid.uuid4())
    
    # Initialize empty state
    state = {
        'domain': request.domain,
        'user_id': request.user_id,
        'questions_asked': 0,
        'question_history': [],
        'asked_questions': [],  # Store question texts to avoid repeats
        'start_time': datetime.now().timestamp()
    }
    
    # Store session in Redis with expiration
    redis_client.setex(
        f"session:{session_id}", 
        SESSION_TIMEOUT,
        json.dumps(state)
    )
    
    return {
        "session_id": session_id,
        "message": f"Think of a {request.domain} and I'll try to guess it!"
    }

# Question endpoint that uses only AI to generate questions
@app.get("/api/get-question/{session_id}", response_model=QuestionResponse)
async def get_question(session_id: str):
    """Get the next AI-generated question for a session"""
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get domain
    domain = state.get('domain', 'thing')
    
    # Get all questions that have already been asked in this session
    asked_questions = state.get('asked_questions', [])
    
    # Use past Q&A to create context
    context = ""
    for q_record in state['question_history']:
        context += f"Q: {q_record['question']} A: {q_record['answer']}. "
    
    # Generate a new question using AI
    max_attempts = 5
    for attempt in range(max_attempts):
        # Create an appropriate prompt based on progress
        if len(state['question_history']) == 0:
            # First question should be broad
            prompt = f"Ask a single yes/no question to identify a {domain}. The question must start with 'Is', 'Are', 'Does', 'Do', 'Can', 'Has', or 'Have'."
        else:
            # Later questions should consider previous answers
            prompt = f"Based on these previous questions and answers: {context} Ask a new yes/no question to identify a {domain}. The question must start with 'Is', 'Are', 'Does', 'Do', 'Can', 'Has', or 'Have'."
        
        try:
            response = chat.send_message(prompt)
            question_text = response.text

            # Check if this question already exists in the database
            with get_db_connection() as conn:
                with get_db_cursor(conn) as cursor:
                    cursor.execute(
                        "SELECT id FROM questions WHERE question_text = %s",
                        (question_text,)
                    )
                    existing_question = cursor.fetchone()
                    
                    if existing_question:
                        # Use existing question ID
                        question_id = existing_question['id']
                    else:
                        # Insert new question
                        cursor.execute(
                            "INSERT INTO questions (question_text, feature, last_used) VALUES (%s, %s, %s) RETURNING id",
                            (question_text, "ai_generated", datetime.now())
                        )
                        question_id = cursor.fetchone()[0]
                    
                    conn.commit()
            
            # Update state to track this question was asked
            state['asked_questions'].append(question_text)
            update_session(session_id, state)
            
            return {
                "session_id": session_id,
                "question_id": question_id,
                "question": question_text,
                "questions_asked": state['questions_asked'],
                "should_guess": state['questions_asked'] >= 8  # Make a guess after 8 questions
            }

        except Exception as e:
            print(f"Error generating question, attempt {attempt+1}: {e}")
    
    # If we've exhausted all attempts, create a super-simple emergency question
    emergency_question = create_emergency_question(domain, len(asked_questions))
    
    # Make sure even the emergency question isn't a repeat
    while emergency_question in asked_questions:
        emergency_question = create_emergency_question(domain, len(asked_questions) + random.randint(1, 100))
    
    # Check if emergency question exists in database
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            cursor.execute(
                "SELECT id FROM questions WHERE question_text = %s",
                (emergency_question,)
            )
            existing_question = cursor.fetchone()
            
            if existing_question:
                # Use existing question ID
                question_id = existing_question['id']
            else:
                # Insert new question
                cursor.execute(
                    "INSERT INTO questions (question_text, feature, last_used) VALUES (%s, %s, %s) RETURNING id",
                    (emergency_question, "emergency", datetime.now())
                )
                question_id = cursor.fetchone()[0]
            
            conn.commit()
    
    # Update state to track this question
    state['asked_questions'].append(emergency_question)
    update_session(session_id, state)
    
    return {
        "session_id": session_id,
        "question_id": question_id,
        "question": emergency_question,
        "questions_asked": state['questions_asked'],
        "should_guess": state['questions_asked'] >= 8  # Make a guess after 8 questions
    }

def is_valid_yes_no_question(question):
    """Validate that a question is a proper yes/no question"""
    if not question or len(question) < 5 or not question.endswith('?'):
        return False
    
    # Check for suspicious content
    suspicious_patterns = ['http', 'www', '.com', '.org', '.net', 'video', 'watch', 'youtube']
    if any(pattern in question.lower() for pattern in suspicious_patterns):
        return False
    
    # Check for valid yes/no question starters
    lower_q = question.lower().split()
    if not lower_q:
        return False
        
    valid_starters = ["is", "are", "does", "do", "can", "has", "have", "was", "were", "will", "would", "should", "could"]
    return lower_q[0] in valid_starters

def create_emergency_question(domain, question_number):
    """Create an emergency question if AI generation fails repeatedly"""
    emergency_formats = [
        f"Is this {domain} considered popular?",
        f"Is this {domain} something most people know about?",
        f"Is this {domain} commonly used?",
        f"Has this {domain} existed for more than {10 + question_number} years?",
        f"Is this {domain} found in many countries?"
    ]
    
    return emergency_formats[question_number % len(emergency_formats)]

# Submit answer endpoint simplified
@app.post("/api/submit-answer", response_model=AnswerResponse)
async def submit_answer(request: AnswerRequest):
    """Submit an answer to a question"""
    session_id = request.session_id
    question_id = request.question_id
    answer = request.answer
    
    # Get session state
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get question text
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            cursor.execute(
                "SELECT question_text FROM questions WHERE id = %s",
                (question_id,)
            )
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Question not found")
            question_text = result['question_text']
    
    # Add to question history - store both question ID and full text for context
    question_record = {
        'question_id': question_id,
        'question': question_text,
        'answer': answer,
        'timestamp': datetime.now().timestamp()
    }
    
    state['question_history'].append(question_record)
    
    # Update questions asked counter
    state['questions_asked'] += 1
    
    # Update session
    update_session(session_id, state)
    
    # Check if we should make a guess
    should_guess = state['questions_asked'] >= 8  # Make a guess after 8 questions
    
    return {
        "session_id": session_id,
        "should_guess": should_guess,
        "top_entities": [],  # We'll determine entities at guess time using AI
        "questions_asked": state['questions_asked']
    }

# Use AI to make the guess
@app.get("/api/make-guess/{session_id}", response_model=GuessResponse)
async def make_guess(session_id: str):
    """Use AI to make a specific guess of what the entity is based on the question history"""
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    domain = state.get('domain', 'thing')
    
    # Create a comprehensive context from all Q&A history
    qa_context = ""
    if state['question_history']:
        # Include all Q&A pairs as they're all important for making a specific guess
        for q_record in state['question_history']:
            qa_context += f"Q: {q_record['question']} A: {q_record['answer']}. "
    
    # Use the question generator to make a specific guess

    try:
        # Create a direct prompt that asks for a specific name
        guess_prompt = f"Based on these yes/no questions and answers about a {domain}: {qa_context} What specific {domain} is it? Name the exact {domain}:"
        
        response = chat.send_message(guess_prompt)
        guess = response.text

    except Exception as e:
        print(f"Error making specific guess: {e}")
        # Create a simple fallback
        common_items = {
            "animal": "dog",
            "food": "pizza",
            "movie": "Avatar",
            "book": "Harry Potter",
            "sport": "soccer",
            "country": "France",
            "car": "Toyota",
            "technology": "smartphone",
            "game": "chess"
        }
        
        # Check if we have a common fallback for this domain
        guess = common_items.get(domain.lower(), f"popular {domain}")
    
    # Ensure the guess is capitalized appropriately
    if guess and len(guess) > 0:
        guess = guess[0].upper() + guess[1:]
    
    return {
        "session_id": session_id,
        "guess": guess,
        "questions_asked": state['questions_asked']
    }

# Submit result endpoint 
@app.post("/api/submit-result", response_model=ResultResponse)
async def submit_result(request: ResultRequest):
    """Submit the final result of a game"""
    session_id = request.session_id
    
    # End the session in Redis
    redis_client.delete(f"session:{session_id}")
    
    return {
        "status": "success",
        "message": "Thank you for playing!"
    }