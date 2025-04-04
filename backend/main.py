import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models.pydantic_models import (
    StartGameRequest, StartGameResponse, 
    QuestionResponse, AnswerRequest, AnswerResponse,
    GuessResponse, ResultRequest, ResultResponse,
    VoiceInputRequest, VoiceOutputRequest, VoiceOutputResponse
)
from database.schemas import init_db
from database.utils import redis_client, get_session, update_session
from services.ai_service import initialize_ai_models
from services.game_service import (
    start_new_game, get_next_question, submit_answer,
    make_guess, submit_game_result
)
from services.voice_service import process_voice_input, generate_voice_output

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

# Initialize on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database and AI models on startup"""
    # Initialize database
    init_db()
    # Initialize AI models
    initialize_ai_models()

# API endpoints
@app.post("/api/start-game", response_model=StartGameResponse)
async def start_game(request: StartGameRequest):
    """Start a new game session with a specific domain"""
    session_id = start_new_game(
        domain=request.domain,
        user_id=request.user_id,
        voice_enabled=request.voice_enabled,
        voice_language=request.voice_language
    )
    
    return {
        "session_id": session_id,
        "message": f"Think of a {request.domain} and I'll try to guess it!"
    }

@app.get("/api/get-question/{session_id}", response_model=QuestionResponse)
async def get_question(session_id: str):
    """Get the next question for a session"""
    question_id, question_text, error = get_next_question(session_id)
    
    if not question_id:
        raise HTTPException(status_code=404, detail=error or "Failed to get question")
    
    # Get state for questions_asked count
    state = get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    questions_asked = state['questions_asked']
    
    return {
        "session_id": session_id,
        "question_id": question_id,
        "question": question_text,
        "questions_asked": questions_asked,
        "should_guess": questions_asked >= 8,  # Make a guess after 8 questions
        "message": error
    }

@app.post("/api/submit-answer", response_model=AnswerResponse)
async def api_submit_answer(request: AnswerRequest):
    """Submit an answer to a question"""
    questions_asked, error = submit_answer(
        session_id=request.session_id,
        question_id=request.question_id,
        answer=request.answer.lower()
    )
    
    if error:
        raise HTTPException(status_code=404, detail=error)
    
    # Check if we should make a guess
    should_guess = questions_asked >= 8  # Make a guess after 8 questions
    
    return {
        "session_id": request.session_id,
        "answer": request.answer.lower(),
        "should_guess": should_guess,
        "questions_asked": questions_asked
    }

@app.get("/api/make-guess/{session_id}", response_model=GuessResponse)
async def api_make_guess(session_id: str):
    """Make a guess based on question history"""
    guess, questions_asked, message = make_guess(session_id)
    
    if not guess:
        raise HTTPException(status_code=404, detail=message or "Failed to make guess")
    
    return {
        "session_id": session_id,
        "guess": guess,
        "questions_asked": questions_asked,
        "message": message
    }

@app.post("/api/submit-result", response_model=ResultResponse)
async def api_submit_result(request: ResultRequest):
    """Submit the final result of a game"""
    submit_game_result(
        session_id=request.session_id,
        was_correct=request.was_correct,
        actual_entity=request.actual_entity
    )
    
    # End the session in Redis
    redis_client.delete(f"session:{request.session_id}")
    
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

@app.post("/api/voice-input", response_model=AnswerResponse)
async def api_process_voice_input(request: VoiceInputRequest):
    """Process voice input and convert to text answer"""
    # Get session state
    state = get_session(request.session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Process audio data
    answer, error = process_voice_input(request.audio_data)
    if error:
        raise HTTPException(status_code=500, detail=error)
    
    # Get the current question
    current_question_id = state.get('current_question_id')
    if not current_question_id:
        raise HTTPException(status_code=400, detail="No current question to answer")
    
    # Create an answer request to reuse existing logic
    answer_request = AnswerRequest(
        session_id=request.session_id,
        question_id=current_question_id,
        answer=answer
    )
    
    # Process the answer using the existing endpoint
    return await api_submit_answer(answer_request)

@app.post("/api/voice-output", response_model=VoiceOutputResponse)
async def api_voice_output(request: VoiceOutputRequest):
    """Generate voice output from text"""
    # Get session state for language preference
    state = get_session(request.session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get language from session state
    language = state.get('voice_language', 'en')
    
    # Generate speech
    audio_data, error = generate_voice_output(request.text, language)
    if error:
        raise HTTPException(status_code=500, detail=error)
    
    return {"audio_data": audio_data, "mime_type": "audio/mp3"}

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Backup state on shutdown"""
    from services.ai_service import api_rate_limiter
    api_rate_limiter.create_backup()