import uuid

def generate_unique_id():
    """Generate a unique ID for sessions, games, etc."""
    return str(uuid.uuid4())

def parse_answer(answer_text):
    """
    Parse user answer text to determine yes/no/unknown
    Returns standardized answer string
    """
    if not answer_text:
        return "unknown"
        
    answer_lower = answer_text.lower().strip()
    
    if any(word in answer_lower for word in ['yes', 'yeah', 'yep', 'correct', 'true', 'right', 'sure']):
        return 'yes'
    elif any(word in answer_lower for word in ['no', 'nope', 'not', 'false', 'wrong', 'nah']):
        return 'no'
    else:
        return 'unknown'