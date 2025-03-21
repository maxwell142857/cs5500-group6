from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from psycopg2.extras import DictCursor
from contextlib import contextmanager
from pydub import AudioSegment
from google import genai
from gtts import gTTS 

import json, uuid, psycopg2, redis, io, os, random, base64

import speech_recognition as sr


class APIRateLimiter:
    def __init__(self, rpm_limit=15, rpd_limit=1500, redis_client=None, backup_file="rate_limiter_backup.json"):
        self.rpm_limit = rpm_limit
        self.rpd_limit = rpd_limit
        self.redis = redis_client
        self.backup_file = backup_file
        self.last_backup = datetime.now()
        self.backup_interval = timedelta(minutes=10)  # Backup every 10 minutes
        
        # Try to restore data on startup if Redis is empty
        self.restore_from_backup()
        
    def check_and_increment(self):
        now = datetime.now()
        minute_key = f"api_limit:minute:{now.strftime('%Y-%m-%d-%H-%M')}"
        day_key = f"api_limit:day:{now.strftime('%Y-%m-%d')}"
        
        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()
        
        # Get current counts
        pipe.get(minute_key)
        pipe.get(day_key)
        minute_count_str, day_count_str = pipe.execute()
        
        # Convert to integers (default to 0 if None)
        minute_count = int(minute_count_str) if minute_count_str else 0
        day_count = int(day_count_str) if day_count_str else 0

        # Check limits
        if minute_count >= self.rpm_limit:
            raise HTTPException(status_code=429, detail="API rate limit exceeded (per minute)")
        
        if day_count >= self.rpd_limit:
            raise HTTPException(status_code=429, detail="API rate limit exceeded (per day)")
        
        # Increment and set expiry
        pipe.incr(minute_key)
        pipe.incr(day_key)
        
        # Set expiry for minute counter (2 minutes to be safe)
        pipe.expire(minute_key, 120)
        
        # Set expiry for day counter (48 hours to be safe)
        pipe.expire(day_key, 172800)
        
        pipe.execute()
        
        # Create backup periodically
        if now - self.last_backup > self.backup_interval:
            self.create_backup()
            self.last_backup = now
            
        return True
        
    def create_backup(self):
        """Create a backup of the current rate limiting data"""
        try:
            # Get all rate limiter keys from Redis
            minute_pattern = "api_limit:minute:*"
            day_pattern = "api_limit:day:*"
            
            minute_keys = self.redis.keys(minute_pattern)
            day_keys = self.redis.keys(day_pattern)
            
            backup_data = {
                "timestamp": datetime.now().isoformat(),
                "minute_limits": {},
                "day_limits": {}
            }
            
            # Get all minute counters
            for key in minute_keys:
                value = self.redis.get(key)
                if value:
                    backup_data["minute_limits"][key] = int(value)
            
            # Get all day counters
            for key in day_keys:
                value = self.redis.get(key)
                if value:
                    backup_data["day_limits"][key] = int(value)
            
            # Write to file
            with open(self.backup_file, 'w') as f:
                json.dump(backup_data, f)
                
            print(f"Rate limiter backup created at {datetime.now().isoformat()}")
            
        except Exception as e:
            print(f"Error creating rate limiter backup: {e}")
    
    def restore_from_backup(self):
        """Restore rate limiting data from backup file if Redis is empty"""
        try:
            # Check if Redis already has rate limiting data
            has_data = bool(self.redis.keys("api_limit:*"))
            
            if not has_data and os.path.exists(self.backup_file):
                with open(self.backup_file, 'r') as f:
                    backup_data = json.load(f)
                
                # Check if backup is not too old (within 1 day)
                backup_time = datetime.fromisoformat(backup_data["timestamp"])
                if datetime.now() - backup_time < timedelta(days=1):
                    pipe = self.redis.pipeline()
                    
                    # Restore minute counters that are still relevant
                    now = datetime.now()
                    current_minute = now.strftime('%Y-%m-%d-%H-%M')
                    
                    for key, value in backup_data["minute_limits"].items():
                        key_time = key.split(":")[-1]
                        if key_time == current_minute:  # Only restore current minute
                            pipe.set(key, value)
                            pipe.expire(key, 120)  # 2 minute expiry
                    
                    # Restore day counters
                    current_day = now.strftime('%Y-%m-%d')
                    for key, value in backup_data["day_limits"].items():
                        key_day = key.split(":")[-1]
                        if key_day == current_day:  # Only restore current day
                            pipe.set(key, value)
                            pipe.expire(key, 172800)  # 48 hour expiry
                    
                    pipe.execute()
                    print(f"Rate limiter data restored from backup created at {backup_data['timestamp']}")
                else:
                    print("Backup file too old, not restoring")
                    
        except Exception as e:
            print(f"Error restoring rate limiter from backup: {e}")


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
    voice_enabled: Optional[bool] = False
    voice_language: Optional[str] = 'en'

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

class VoiceInputRequest(BaseModel):
    session_id: str
    audio_data: str  # Base64 encoded audio data

class VoiceOutputRequest(BaseModel):
    session_id: str
    text: str

class VoiceOutputResponse(BaseModel):
    audio_data: str  # Base64 encoded audio data
    mime_type: str = "audio/mp3"

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

api_rate_limiter = APIRateLimiter(
    rpm_limit=15, 
    rpd_limit=1500,
    redis_client=redis_client,
    backup_file="api_rate_limiter_backup.json"
)

# Session timeout (in seconds)
SESSION_TIMEOUT = int(os.environ.get('SESSION_TIMEOUT', 3600))

# Initialize database schema
def init_db():
    """Initialize database schema"""
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
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
            
            # Game history table - removed users foreign key
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_history (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                target_entity TEXT,
                domain TEXT,
                was_correct BOOLEAN,
                questions_count INTEGER,
                duration INTEGER,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            
            # Domain questions table for caching
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS domain_questions (
                id SERIAL PRIMARY KEY,
                domain TEXT,
                question_id INTEGER,
                position INTEGER,
                usage_count INTEGER DEFAULT 0,
                effectiveness REAL DEFAULT 0.5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (question_id) REFERENCES questions (id)
            )
            ''')
            
            # Domain guesses table for caching successful guesses
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS domain_guesses (
                id SERIAL PRIMARY KEY,
                domain TEXT,
                entity_name TEXT,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Create indices
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_domain_questions ON domain_questions (domain, position)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_domain_questions_effectiveness ON domain_questions (effectiveness DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_domain_guesses ON domain_guesses (domain)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_domain_guesses_success ON domain_guesses (success_count DESC)')
            
            conn.commit()

# Database operations
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


# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
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
        'voice_enabled': request.voice_enabled,
        'voice_language': request.voice_language,
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
    """Get the next question for a session, prioritizing cached questions"""
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get domain and tracking data
    domain = state.get('domain', 'thing')
    asked_questions = state.get('asked_questions', [])
    questions_asked = state['questions_asked']
    
    # Try to use cached questions first
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            # Look for appropriate cached questions for this domain and position
            cursor.execute(
                """SELECT dq.question_id, q.question_text 
                FROM domain_questions dq
                JOIN questions q ON dq.question_id = q.id
                WHERE dq.domain = %s 
                AND dq.position = %s
                AND q.question_text NOT IN %s
                ORDER BY dq.effectiveness DESC, dq.usage_count DESC
                LIMIT 1""",
                (domain, questions_asked, tuple(asked_questions) if asked_questions else ('',))
            )
            cached_question = cursor.fetchone()
            
            if cached_question:
                # Use cached question
                question_id = cached_question['question_id']
                question_text = cached_question['question_text']
                
                # Update usage count
                cursor.execute(
                    "UPDATE domain_questions SET usage_count = usage_count + 1 WHERE question_id = %s AND domain = %s",
                    (question_id, domain)
                )
                conn.commit()
                
                # Update state
                state['asked_questions'] = state.get('asked_questions', []) + [question_text]
                state['current_question_id'] = question_id
                update_session(session_id, state)
                
                return {
                    "session_id": session_id,
                    "question_id": question_id,
                    "question": question_text,
                    "questions_asked": questions_asked,
                    "should_guess": questions_asked >= 8
                }
    
    # Try to generate using AI with proper fallbacks
    try:
        # Check API rate limits
        api_rate_limiter.check_and_increment()
        
        # Use past Q&A to create context
        context = ""
        for q_record in state['question_history']:
            context += f"Q: {q_record['question']} A: {q_record['answer']}. "
        
        # Generate a new question using AI
        if len(state['question_history']) == 0:
            prompt = f"Ask a single yes/no question to identify a {domain}. The question must start with 'Is', 'Are', 'Does', 'Do', 'Can', 'Has', or 'Have'."
        else:
            prompt = f"Based on these previous questions and answers: {context} Ask a new yes/no question to identify a {domain}. The question must start with 'Is', 'Are', 'Does', 'Do', 'Can', 'Has', or 'Have'."
        
        try:
            response = chat.send_message(prompt)
            question_text = response.text.strip()
            
            # Validate and clean up the question
            if is_valid_yes_no_question(question_text):
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
                        
                        # Store in domain_questions for future use
                        cursor.execute(
                            "INSERT INTO domain_questions (domain, question_id, position) VALUES (%s, %s, %s)",
                            (domain, question_id, questions_asked)
                        )
                        
                        conn.commit()
                
                # Update state to track this question was asked
                state['asked_questions'] = state.get('asked_questions', []) + [question_text]
                state['current_question_id'] = question_id
                update_session(session_id, state)
                
                return {
                    "session_id": session_id,
                    "question_id": question_id,
                    "question": question_text,
                    "questions_asked": questions_asked,
                    "should_guess": questions_asked >= 8
                }
        except Exception as e:
            print(f"Error generating question: {e}")
    except HTTPException as e:
        if e.status_code == 429:
            # Rate limiting handled correctly
            print("Reached API usage limit")
        else:
            raise e
    except Exception as e:
        print(f"Unexpected error in get_question: {e}")
    
    # FALLBACK: Use emergency question for any issue
    emergency_question = create_emergency_question(domain, len(asked_questions))
    
    # Make sure even the emergency question isn't a repeat
    while emergency_question in asked_questions:
        emergency_question = create_emergency_question(domain, len(asked_questions) + random.randint(1, 100))
    
    # Store the emergency question in database
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            cursor.execute(
                "SELECT id FROM questions WHERE question_text = %s",
                (emergency_question,)
            )
            existing_question = cursor.fetchone()
            
            if existing_question:
                question_id = existing_question['id']
            else:
                cursor.execute(
                    "INSERT INTO questions (question_text, feature, last_used) VALUES (%s, %s, %s) RETURNING id",
                    (emergency_question, "emergency", datetime.now())
                )
                question_id = cursor.fetchone()[0]
            
            cursor.execute(
                "INSERT INTO domain_questions (domain, question_id, position) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (domain, question_id, questions_asked)
            )
            
            conn.commit()
    
    # Update state
    state['asked_questions'] = state.get('asked_questions', []) + [emergency_question]
    state['current_question_id'] = question_id
    update_session(session_id, state)
    
    # Always ensure a valid response is returned
    return {
        "session_id": session_id,
        "question_id": question_id,
        "question": emergency_question,
        "questions_asked": questions_asked,
        "should_guess": questions_asked >= 8,
        "message": "Using fallback question due to generation issues."
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

    # Create answer pattern for lookup
    answer_pattern = {}
    for q_record in state['question_history']:
        answer_pattern[q_record['question_id']] = q_record['answer']
    
    # Try to find a similar pattern in previous successful games
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            # Get successful guesses for this domain
            cursor.execute(
                """SELECT entity_name, success_count 
                FROM domain_guesses 
                WHERE domain = %s 
                ORDER BY success_count DESC
                LIMIT 5""",
                (domain,)
            )
            cached_guesses = cursor.fetchall()
            
            if cached_guesses:
                # Use the most successful guess
                guess = cached_guesses[0]['entity_name']
                
                return {
                    "session_id": session_id,
                    "guess": guess,
                    "questions_asked": state['questions_asked']
                }
    
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
    was_correct = request.was_correct
    actual_entity = request.actual_entity
    
    # Get session before deleting
    state = get_session(session_id)
    
    if state:
        domain = state.get('domain', 'thing')
        
        # Update question effectiveness based on result
        with get_db_connection() as conn:
            with get_db_cursor(conn) as cursor:
                # Update question effectiveness for each asked question
                for q_record in state['question_history']:
                    cursor.execute(
                        """UPDATE domain_questions 
                        SET effectiveness = effectiveness + %s 
                        WHERE domain = %s AND question_id = %s""",
                        (0.1 if was_correct else -0.05, domain, q_record['question_id'])
                    )
                
                # Update or insert guess statistics
                if was_correct:
                    # Get the current guess that was correct
                    cursor.execute(
                        """SELECT id FROM domain_guesses 
                        WHERE domain = %s AND entity_name = %s""",
                        (domain, actual_entity)
                    )
                    existing_guess = cursor.fetchone()
                    
                    if existing_guess:
                        cursor.execute(
                            """UPDATE domain_guesses 
                            SET success_count = success_count + 1 
                            WHERE id = %s""",
                            (existing_guess['id'],)
                        )
                    else:
                        cursor.execute(
                            """INSERT INTO domain_guesses 
                            (domain, entity_name, success_count) 
                            VALUES (%s, %s, 1)""",
                            (domain, actual_entity)
                        )
                else:
                    # If we know what the correct answer was
                    if actual_entity:
                        cursor.execute(
                            """SELECT id FROM domain_guesses 
                            WHERE domain = %s AND entity_name = %s""",
                            (domain, actual_entity)
                        )
                        existing_guess = cursor.fetchone()
                        
                        if existing_guess:
                            # We guessed it before but failed this time
                            pass
                        else:
                            # New entity we've never seen before
                            cursor.execute(
                                """INSERT INTO domain_guesses 
                                (domain, entity_name, success_count) 
                                VALUES (%s, %s, 0)""",
                                (domain, actual_entity)
                            )
                
                conn.commit()
    
    # End the session in Redis
    redis_client.delete(f"session:{session_id}")
    
    return {
        "status": "success",
        "message": "Thank you for playing!"
    }

@app.post("/api/toggle-voice")
async def toggle_voice(session_id: str, enable: bool = True, language: str = 'en'):
    """Enable or disable voice chat for a session"""
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    state['voice_enabled'] = enable
    state['voice_language'] = language
    update_session(session_id, state)
    
    return {"status": "success", "voice_enabled": enable}

@app.post("/api/voice-input", response_model=QuestionResponse)
async def process_voice_input(request: VoiceInputRequest):
    """Process voice input and convert to text answer"""
    session_id = request.session_id
    
    # Get session state
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Process audio data
    try:
        # Decode base64 audio data
        audio_data = base64.b64decode(request.audio_data)
        
        # Convert to WAV format for recognition
        audio = AudioSegment.from_file(io.BytesIO(audio_data))
        wav_data = io.BytesIO()
        audio.export(wav_data, format="wav")
        wav_data.seek(0)
        
        # Use speech recognition
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_data) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
        
        # Process the recognized text to determine yes/no/don't know
        lower_text = text.lower()
        if any(word in lower_text for word in ['yes', 'yeah', 'yep', 'correct']):
            answer = 'yes'
        elif any(word in lower_text for word in ['no', 'nope', 'not']):
            answer = 'no'
        else:
            answer = 'unknown'
        
        # Get the current question
        current_question_id = state.get('current_question_id')
        
        if not current_question_id:
            raise HTTPException(status_code=400, detail="No current question to answer")
        
        # Create an answer request to reuse existing logic
        answer_request = AnswerRequest(
            session_id=session_id,
            question_id=current_question_id,
            answer=answer
        )
        
        # Process the answer using the existing endpoint
        return await submit_answer(answer_request)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing voice input: {str(e)}")

@app.post("/api/voice-output", response_model=VoiceOutputResponse)
async def generate_voice_output(request: VoiceOutputRequest):
    """Generate voice output from text"""
    session_id = request.session_id
    
    # Get session state for language preference
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get language from session state
    language = state.get('voice_language', 'en')
    
    try:
        # Generate speech using gTTS
        tts = gTTS(text=request.text, lang=language)
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        
        # Encode as base64
        audio_data = base64.b64encode(mp3_fp.read()).decode('utf-8')
        
        return {"audio_data": audio_data, "mime_type": "audio/mp3"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating speech: {str(e)}")

@app.on_event("shutdown")
async def startup_event():
    """Initialize database on startup"""
    # Initialize database
    api_rate_limiter.create_backup()