import json, redis

from config import REDIS_HOST, REDIS_PORT, REDIS_DB, SESSION_TIMEOUT

# Redis client - configure for connection pooling
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True,
    socket_timeout=5
)

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

def calculate_pattern_similarity(pattern1, pattern2):
    """
    Calculate similarity between two question-answer patterns
    Returns a score between 0.0 and 1.0
    """
    # Find common question IDs
    common_questions = set(pattern1.keys()) & set(pattern2.keys())
    
    if not common_questions:
        return 0.0
    
    # Count matching answers for common questions
    matches = sum(1 for q_id in common_questions if pattern1[q_id].lower() == pattern2[q_id].lower())
    
    # Calculate similarity score - weighted by number of questions
    similarity = matches / len(common_questions)
    
    # Apply a bonus for having more common questions
    coverage = len(common_questions) / max(len(pattern1), len(pattern2))
    
    # Weighted average of matching answers and coverage (70/30 split)
    final_score = (similarity * 0.7) + (coverage * 0.3)
    
    return final_score