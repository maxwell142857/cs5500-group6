from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Union
import json
import uuid
from datetime import datetime
import psycopg2
from psycopg2.extras import DictCursor
import redis
import os
import numpy as np
from contextlib import contextmanager
import torch
import random

# Import Hugging Face components
from transformers import (
    AutoModelForSequenceClassification, 
    AutoTokenizer, 
    pipeline
)

# Configure database connection details
DB_NAME = os.environ.get('POSTGRES_DB', 'akinator_db')
DB_USER = os.environ.get('POSTGRES_USER', 'akinator_user')
DB_PASS = os.environ.get('POSTGRES_PASSWORD', 'password')
DB_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
DB_PORT = os.environ.get('POSTGRES_PORT', '5432')

REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))

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

# Initialize NLP models
zero_shot_classifier = None
question_generator = None

def load_models():
    """Load NLP models from Hugging Face"""
    global zero_shot_classifier, question_generator
    
    print("Loading NLP models...")
    
    try:
        # Zero-shot classification for entity property matching
        zero_shot_classifier = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
        )
        
        # Text generation for generating questions
        question_generator = pipeline(
            "text-generation",
            model="distilgpt2",  # Using a smaller model for better focus
            max_length=30
        )
        
        print("NLP models loaded successfully")
    except Exception as e:
        print(f"Error loading models: {e}")
        print("Models will not be available. The system will fall back to standard mode.")

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
    confidence: float
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
    
    # Update information gain for questions
    update_information_gain()
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

def update_information_gain():
    """Update information gain for questions based on completed games"""
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            # Get all questions
            cursor.execute("SELECT id, feature FROM questions")
            questions = cursor.fetchall()
            
            # Get total entity count
            cursor.execute("SELECT COUNT(*) FROM entities")
            total_entities = cursor.fetchone()[0]
            
            if total_entities == 0:
                return
            
            for question in questions:
                # Count entities with and without this feature
                yes_count = 0
                no_count = 0
                
                cursor.execute(
                    "SELECT attributes FROM entities"
                )
                entities = cursor.fetchall()
                
                for entity in entities:
                    attrs = entity['attributes']
                    if isinstance(attrs, str):
                        attrs = json.loads(attrs)
                    
                    # Check if entity has this feature
                    has_feature = False
                    for key, value in attrs.items():
                        if isinstance(value, list) and question['feature'] in value:
                            has_feature = True
                            break
                        elif value == question['feature']:
                            has_feature = True
                            break
                    
                    if has_feature:
                        yes_count += 1
                    else:
                        no_count += 1
                
                # Calculate information gain
                if yes_count == 0 or no_count == 0:
                    information_gain = 0  # Question doesn't split entities
                else:
                    # Calculate entropy reduction
                    p_yes = yes_count / total_entities
                    p_no = no_count / total_entities
                    information_gain = 1 - abs(p_yes - p_no)  # Higher when balanced
                
                # Update question
                cursor.execute(
                    "UPDATE questions SET information_gain = %s WHERE id = %s",
                    (information_gain, question['id'])
                )
            
            conn.commit()


def check_entity_has_feature(entity_name, feature):
    """Check if an entity has a specific feature"""
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            cursor.execute(
                "SELECT attributes FROM entities WHERE name = %s",
                (entity_name,)
            )
            result = cursor.fetchone()
            if not result:
                return False
                
            attributes = result['attributes']
            if isinstance(attributes, str):
                attributes = json.loads(attributes)
            
            # Check if entity has this feature
            for key, value in attributes.items():
                if isinstance(value, list) and feature in value:
                    return True
                elif value == feature:
                    return True
            
            return False

def update_probabilities_with_ai(session_id, question_id, answer):
    """Update entity probabilities using AI and zero-shot classification"""
    state = get_session(session_id)
    if not state or not state.get('use_ai', False) or not zero_shot_classifier:
        # Fall back to standard method if AI is not available/enabled
        return update_probabilities(session_id, question_id, answer)
        
    # Get the question text
    question_text = None
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            cursor.execute(
                "SELECT question_text, feature FROM questions WHERE id = %s",
                (question_id,)
            )
            result = cursor.fetchone()
            if result:
                question_text = result['question_text']
                feature = result['feature']
                # Mark feature as asked
                state['asked_features'].append(feature)
    
    if not question_text:
        return False
    
    # Record the question
    record_question(session_id, question_id, answer)
    
    # If we have no entities yet, we're just collecting initial questions
    if state.get('no_entities', False) or not state['entity_probabilities']:
        # Just record the question and continue
        state['questions_asked'] += 1
        update_session(session_id, state)
        return True
    
    # Get all entities from the state
    entity_names = list(state['entity_probabilities'].keys())
    
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            # Get descriptions for all entities
            entity_descriptions = {}
            for entity_name in entity_names:
                cursor.execute(
                    "SELECT attributes FROM entities WHERE name = %s",
                    (entity_name,)
                )
                result = cursor.fetchone()
                if result:
                    attrs = result['attributes']
                    if isinstance(attrs, str):
                        attrs = json.loads(attrs)
                    
                    # Use description if available, otherwise create one from features
                    if 'description' in attrs:
                        entity_descriptions[entity_name] = attrs['description']
                    elif 'features' in attrs:
                        entity_descriptions[entity_name] = f"{entity_name} is " + ", ".join(attrs['features'])
                    else:
                        entity_descriptions[entity_name] = entity_name
            
            # Use zero-shot classification to determine alignment with answer
            for entity_name in entity_names:
                if entity_name not in entity_descriptions:
                    continue
                
                # Create hypothesis for classification
                hypothesis = (
                    f"The answer to '{question_text}' for {entity_name} is yes." 
                    if answer.lower() in ["yes", "y"] else
                    f"The answer to '{question_text}' for {entity_name} is no."
                )
                
                # Classify the hypothesis against entity description
                try:
                    result = zero_shot_classifier(
                        entity_descriptions[entity_name],
                        [hypothesis, f"Not: {hypothesis}"],
                        hypothesis_template="{}"
                    )
                    
                    # Extract confidence score for the hypothesis
                    score = result['scores'][0] if result['labels'][0] == hypothesis else result['scores'][1]
                    
                    # Update probability based on confidence score
                    # High confidence score = answer aligns with entity
                    current_prob = state['entity_probabilities'][entity_name]
                    state['entity_probabilities'][entity_name] = current_prob * (1.0 + score)
                except Exception as e:
                    print(f"Error classifying {entity_name}: {e}")
                    # Fall back to standard method if classification fails
                    has_feature = check_entity_has_feature(entity_name, feature)
                    current_prob = state['entity_probabilities'][entity_name]
                    if (answer.lower() in ["yes", "y"] and has_feature) or \
                       (answer.lower() in ["no", "n"] and not has_feature):
                        state['entity_probabilities'][entity_name] = current_prob * 2.0
                    else:
                        state['entity_probabilities'][entity_name] = current_prob * 0.5
    
    # Normalize probabilities
    total = sum(state['entity_probabilities'].values())
    if total > 0:
        state['entity_probabilities'] = {
            e: p/total for e, p in state['entity_probabilities'].items()
        }
    
    # Update questions asked counter
    state['questions_asked'] += 1
    
    # Update session
    update_session(session_id, state)
    return True

def update_probabilities(session_id, question_id, answer):
    """Update entity probabilities based on an answer (standard method)"""
    state = get_session(session_id)
    if not state:
        return False
        
    # Get the feature for this question
    feature = None
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            cursor.execute(
                "SELECT feature FROM questions WHERE id = %s",
                (question_id,)
            )
            result = cursor.fetchone()
            if result:
                feature = result[0]
    
    if not feature:
        return False
    
    # Mark feature as asked
    state['asked_features'].append(feature)
    
    # Record the question
    record_question(session_id, question_id, answer)
    
    # If we have no entities yet, we're just collecting initial questions
    if state.get('no_entities', False) or not state['entity_probabilities']:
        # Just record the question and continue
        state['questions_asked'] += 1
        update_session(session_id, state)
        return True
    
    # Get all entities from the state
    entity_names = list(state['entity_probabilities'].keys())
    
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            # Update each entity's probability
            for entity_name in entity_names:
                has_feature = check_entity_has_feature(entity_name, feature)
                
                # Update probability
                current_prob = state['entity_probabilities'][entity_name]
                if (answer.lower() in ["yes", "y"] and has_feature) or \
                   (answer.lower() in ["no", "n"] and not has_feature):
                    # Answer matches entity attributes
                    state['entity_probabilities'][entity_name] = current_prob * 2.0
                else:
                    # Answer contradicts entity attributes
                    state['entity_probabilities'][entity_name] = current_prob * 0.5
    
    # Normalize probabilities
    total = sum(state['entity_probabilities'].values())
    if total > 0:
        state['entity_probabilities'] = {
            e: p/total for e, p in state['entity_probabilities'].items()
        }
    
    # Update questions asked counter
    state['questions_asked'] += 1
    
    # Update session
    update_session(session_id, state)
    return True

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database and models on startup"""
    # Initialize database
    init_db()
    
    # Initialize models directly
    try:
        # Load models in-process
        load_models()
    except Exception as e:
        print(f"Error loading models: {e}")
        print("Models will not be available. The system will fall back to standard mode.")

# API endpoints
@app.post("/api/start-game", response_model=StartGameResponse)
async def start_game(request: StartGameRequest):
    """Start a new game session with a specific domain"""
    # Check if AI models are loaded
    if not question_generator:
        raise HTTPException(status_code=503, detail="AI models not loaded. Cannot play without question generation.")
        
    # Create a new session
    session_id = create_session(request.domain, request.user_id)
    
    # Get entity count for this domain to determine if we're in learning or guessing mode
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM entities WHERE domain = %s",
                (request.domain,)
            )
            entity_count = cursor.fetchone()[0]
    
    message = ""
    if entity_count == 0:
        message = f"I don't know any {request.domain} yet. I'll ask some questions to learn about it."
    else:
        message = f"Think of a {request.domain} and I'll try to guess it!"
        
    return {"session_id": session_id, "message": message}

@app.get("/api/get-question/{session_id}", response_model=QuestionResponse)
async def get_question(session_id: str):
    """Get the next question for a session - using AI-only question generation"""
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check if AI models are loaded
    if not question_generator:
        raise HTTPException(status_code=503, detail="AI models not loaded. Cannot generate questions.")
    
    # Create a context prompt using the domain and previous questions/answers
    domain = state.get('domain', 'thing')
    
    # Build context from previous questions and answers
    context = f"Generate a yes/no question about a {domain}. "
    
    if state['question_history']:
        context += "Previous Q&A: "
        for q_record in state['question_history']:
            with get_db_connection() as conn:
                with get_db_cursor(conn) as cursor:
                    cursor.execute(
                        "SELECT question_text FROM questions WHERE id = %s",
                        (q_record['question_id'],)
                    )
                    result = cursor.fetchone()
                    if result:
                        context += f"{result[0]} - {q_record['answer']}. "
    
    # Generate the question with improved parameters
    result = question_generator(
        context, 
        max_length=40,
        num_return_sequences=3,
        temperature=0.7,
        top_p=0.9,
        do_sample=True
    )
    
    # Extract a good question with stricter filtering
    ai_question = None
    for item in result:
        text = item['generated_text'].replace(context, '')
        # Look for sentences ending with a question mark
        for sentence in text.split('.'):
            if '?' in sentence:
                question = sentence.strip().split('?')[0].strip() + '?'
                # Apply stricter filtering criteria
                if (10 < len(question) < 60 and 
                    question.count(' ') < 12 and  # Limit word count
                    any(question.lower().startswith(prefix) for prefix in 
                        ['is ', 'does ', 'can ', 'has ', 'are ', 'do ', 'was ', 'would ', 'will '])):
                    ai_question = question
                    break
        if ai_question:
            break
    
    # If we couldn't generate a good question, try again with a different prompt
    if not ai_question:
        # More direct prompt
        fallback_prompt = f"Ask a yes/no question to identify a {domain}."
        result = question_generator(
            fallback_prompt, 
            max_length=30,
            num_return_sequences=1,
            temperature=0.5
        )
        text = result[0]['generated_text'].replace(fallback_prompt, '')
        
        # Find the first question mark
        if '?' in text:
            end_idx = text.find('?') + 1
            ai_question = text[:end_idx].strip()
        else:
            # Last resort: create a simple question
            ai_question = f"Is it a type of {domain}?"
    
    # Store the generated question in the database
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            # Check if question already exists
            cursor.execute(
                "SELECT id FROM questions WHERE question_text = %s",
                (ai_question,)
            )
            result = cursor.fetchone()
            
            if result:
                # Use existing question
                question_id = result[0]
            else:
                # Create new question with a feature name derived from the question
                # Extract potential feature by removing question words
                feature_text = ai_question.lower()
                for prefix in ['is it ', 'does it ', 'can it ', 'has it ', 'are they ', 'do they ', 'is the ', 'does the ']:
                    feature_text = feature_text.replace(prefix, '')
                
                feature_text = feature_text.replace('?', '').strip()
                
                cursor.execute(
                    "INSERT INTO questions (question_text, feature, last_used) VALUES (%s, %s, %s) RETURNING id",
                    (ai_question, feature_text, datetime.now())
                )
                question_id = cursor.fetchone()[0]
                conn.commit()
    
    message = None
    if state.get('no_entities', False):
        message = "Learning about this new entity. Please answer a few questions."
    
    return {
        "session_id": session_id,
        "question_id": question_id,
        "question": ai_question,
        "questions_asked": state['questions_asked'],
        "should_guess": False,
        "message": message
    }

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
    
    # Use AI-enhanced probability updates if enabled
    if state.get('use_ai', False) and zero_shot_classifier:
        success = update_probabilities_with_ai(session_id, question_id, answer)
    else:
        success = update_probabilities(session_id, question_id, answer)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to process answer")
        
    # Get updated state
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check if we should guess
    should_guess = False
    
    # If we're in learning mode (no entities yet), we should guess after several questions
    if state.get('no_entities', False):
        should_guess = state['questions_asked'] >= 10
    # If we have entities, use probability threshold or question count
    elif state['entity_probabilities']:
        max_prob = max(state['entity_probabilities'].values()) if state['entity_probabilities'] else 0
        should_guess = max_prob > 0.6 or state['questions_asked'] >= 20
    
    # Get top entities
    top_entities = []
    if state['entity_probabilities']:
        top_entities = sorted(
            state['entity_probabilities'].items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:3]
        top_entities = [{"entity": e, "probability": p} for e, p in top_entities]
    
    return {
        "session_id": session_id,
        "should_guess": should_guess,
        "top_entities": top_entities,
        "questions_asked": state['questions_asked']
    }

@app.get("/api/make-guess/{session_id}", response_model=GuessResponse)
async def make_guess(session_id: str):
    """Make a guess based on current probabilities"""
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # If this is the first entity (learning mode), we can't make a real guess
    if state.get('no_entities', False):
        return {
            "session_id": session_id,
            "guess": "I don't know yet! Tell me what you're thinking of.",
            "confidence": 0.0,
            "questions_asked": state['questions_asked']
        }
    
    # If no entity probabilities are available
    if not state['entity_probabilities']:
        raise HTTPException(status_code=400, detail="No entity probabilities available")
    
    # Find top entity
    guess = max(state['entity_probabilities'].items(), key=lambda x: x[1])
    
    return {
        "session_id": session_id,
        "guess": guess[0],
        "confidence": guess[1],
        "questions_asked": state['questions_asked']
    }

@app.post("/api/submit-result", response_model=ResultResponse)
async def submit_result(request: ResultRequest):
    """Submit the final result of a game"""
    session_id = request.session_id
    was_correct = request.was_correct
    actual_entity = request.actual_entity
    entity_type = request.entity_type
    
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Handle the case where this is the first entity being learned
    if state.get('no_entities', False):
        # In learning mode, we need to provide an entity
        if not actual_entity:
            raise HTTPException(status_code=400, detail="Must provide actual_entity for the first item")
        
        # End the session with the provided entity
        success = end_session(session_id, actual_entity, False, entity_type or state.get('domain'))
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to end session")
        
        return {
            "status": "success",
            "message": f"Added {actual_entity} to the knowledge base"
        }
    
    # Normal flow for sessions with existing entities
    # Get the guessed entity
    target_entity = None
    if was_correct:
        if state['entity_probabilities']:
            target_entity = max(state['entity_probabilities'].items(), key=lambda x: x[1])[0]
    else:
        target_entity = actual_entity
    
    if not target_entity:
        raise HTTPException(status_code=400, detail="No target entity provided")
    
    # End the session
    success = end_session(session_id, target_entity, was_correct, entity_type)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to end session")
    
    return {
        "status": "success",
        "message": "Game completed and recorded"
    }

@app.get("/api/healthcheck", response_model=HealthResponse)
async def healthcheck():
    """Simple health check endpoint"""
    return {
        "status": "ok", 
        "version": "1.0.0",
        "models_loaded": bool(zero_shot_classifier and question_generator)
    }
