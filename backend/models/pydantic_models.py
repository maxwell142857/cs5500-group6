from pydantic import BaseModel
from typing import Optional

# Request and response models for the API
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
    answer: str
    should_guess: bool
    questions_asked: int

class GuessResponse(BaseModel):
    session_id: str
    guess: str
    questions_asked: int
    message: Optional[str] = None

class ResultRequest(BaseModel):
    session_id: str
    was_correct: bool
    actual_entity: Optional[str] = None
    entity_type: Optional[str] = None

class ResultResponse(BaseModel):
    status: str
    message: str

class VoiceInputRequest(BaseModel):
    session_id: str
    audio_data: str  # Base64 encoded audio data

class VoiceOutputRequest(BaseModel):
    session_id: str
    text: str

class VoiceOutputResponse(BaseModel):
    audio_data: str  # Base64 encoded audio data
    mime_type: str = "audio/mp3"