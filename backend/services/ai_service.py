import random
from google import genai
import os

from config import GEMINI_API_KEY, GEMINI_MODELS
from services.rate_limiter import APIRateLimiter
from database.utils import redis_client

# Initialize API rate limiter
api_rate_limiter = APIRateLimiter(
    models_config=GEMINI_MODELS,
    redis_client=redis_client,
    backup_file="api_rate_limiter_backup.json"
)

def initialize_ai_models():
    """Initialize Gemini models"""
    for model in GEMINI_MODELS:
        try:
            model["client"] = genai.Client(api_key=GEMINI_API_KEY)
            print(f"Initialized model: {model['name']}")
        except Exception as e:
            print(f"Error initializing model {model['name']}: {e}")
    
    # Create a backup of the rate limiter state on startup
    api_rate_limiter.create_backup()

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

def generate_question(domain, question_history):
    """Generate a new question using AI"""
    try:
        # Check API rate limits
        if not api_rate_limiter.check_and_increment():
            # If current model is at limit, try to rotate
            if not api_rate_limiter.rotate_model():
                # If all models at limit, use emergency question
                return None, "All API rate limits exceeded"
            
        # Get the new current model after rotation
        current_model = api_rate_limiter.get_current_model()
        
        # Use past Q&A to create context
        context = ""
        for q_record in question_history:
            context += f"Q: {q_record['question']} A: {q_record['answer']}. "
        
        # Generate a new question using AI
        if len(question_history) == 0:
            prompt = f"Ask a single yes/no question to identify or to guess a {domain}. The question must start with 'Is', 'Are', 'Does', 'Do', 'Can', 'Has', or 'Have'."
        else:
            prompt = f"Based on these previous questions and answers: {context} Ask a new yes/no question to identify or to guess a {domain}. The question must start with 'Is', 'Are', 'Does', 'Do', 'Can', 'Has', or 'Have'."
        
        try:
            # Create a chat for the current model if it doesn't exist
            if not current_model.get("chat"):
                current_model["chat"] = current_model["client"].chats.create(model=current_model["name"])
            
            # Send the message to the current model's chat
            response = current_model["chat"].send_message(prompt)
            question_text = response.text.strip()
            
            # Validate the question
            if is_valid_yes_no_question(question_text):
                return question_text, None
            else:
                return None, "Invalid question format generated"
                
        except Exception as e:
            return None, f"Error generating question: {e}"
    
    except Exception as e:
        return None, f"Error using AI model: {e}"

def generate_guess(domain, question_history):
    """Generate a guess using AI"""
    try:
        # Check if we can use the current model
        if not api_rate_limiter.check_and_increment():
            # If current model is at limit, try to rotate
            if not api_rate_limiter.rotate_model():
                # If all models are at limit, use a fallback
                raise Exception("All models at rate limit")
        
        # Get the current model
        current_model = api_rate_limiter.get_current_model()
        
        # Create a chat for the current model if it doesn't exist
        if not current_model.get("chat"):
            current_model["chat"] = current_model["client"].chats.create(model=current_model["name"])
        
        # Create a comprehensive context from all Q&A history
        qa_context = ""
        if question_history:
            for q_record in question_history:
                qa_context += f"Q: {q_record['question']} A: {q_record['answer']}. "
        
        # Create a direct prompt that asks for a specific name
        guess_prompt = f"Based on these yes/no questions and answers about a {domain}: {qa_context} What specific {domain} is it? Just Name the exact {domain}:"
        
        response = current_model["chat"].send_message(guess_prompt)
        guess = response.text.strip()
        
        return guess, None

    except Exception as e:
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
        return guess, f"Error making specific guess: {e}"