import uuid

from datetime import datetime

from database import get_db_connection, get_db_cursor
from database.utils import get_session, update_session
from services.ai_service import generate_question, create_emergency_question, generate_guess

def start_new_game(domain, user_id=None, voice_enabled=False, voice_language='en'):
    """Start a new game session"""
    session_id = str(uuid.uuid4())
    
    # Initialize empty state
    state = {
        'domain': domain,
        'user_id': user_id,
        'voice_enabled': voice_enabled,
        'voice_language': voice_language,
        'questions_asked': 0,
        'question_history': [],
        'asked_questions': [],  # Store question texts to avoid repeats
        'start_time': datetime.now().timestamp()
    }
    
    # Store session
    update_session(session_id, state)
    
    return session_id

def get_next_question(session_id):
    """Get the next question for a session"""
    state = get_session(session_id)
    if not state:
        return None, None, "Session not found"
    
    # Get domain and tracking data
    domain = state.get('domain', 'thing')
    asked_questions = state.get('asked_questions', [])
    questions_asked = state['questions_asked']

    # Try to generate using AI with proper fallbacks
    try:
        # Generate a new question using AI
        question_text, error = generate_question(domain, state['question_history'])
        
        if question_text:
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
                        "INSERT INTO domain_questions (domain, question_id, position) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (domain, question_id, questions_asked)
                    )
                    
                    conn.commit()
            
            # Update state to track this question was asked
            state['asked_questions'] = state.get('asked_questions', []) + [question_text]
            state['current_question_id'] = question_id
            update_session(session_id, state)
            
            return question_id, question_text, None
    
    except Exception as e:
        error = f"Unexpected error generating question: {e}"
    
    # Try fallback to cached questions
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn) as cursor:
                # Find a good question for this domain that hasn't been asked in this session
                cursor.execute(
                    """SELECT dq.question_id, q.question_text, dq.effectiveness 
                    FROM domain_questions dq
                    JOIN questions q ON dq.question_id = q.id
                    WHERE dq.domain = %s 
                    AND q.question_text NOT IN %s
                    ORDER BY dq.effectiveness DESC, RANDOM()
                    LIMIT 1""",
                    (domain, tuple(asked_questions) if asked_questions else ('',))
                )
                cached_question = cursor.fetchone()
                
                if cached_question:
                    # Use cached question
                    question_id = cached_question['question_id']
                    question_text = cached_question['question_text']
                    
                    # Update usage count
                    cursor.execute(
                        """UPDATE domain_questions 
                        SET usage_count = usage_count + 1, 
                            position = CASE WHEN position IS NULL THEN %s ELSE position END
                        WHERE question_id = %s AND domain = %s""",
                        (questions_asked, question_id, domain)
                    )
                    
                    # Update last_used timestamp
                    cursor.execute(
                        "UPDATE questions SET last_used = NOW() WHERE id = %s",
                        (question_id,)
                    )
                    
                    conn.commit()
                    
                    # Update state
                    state['asked_questions'] = state.get('asked_questions', []) + [question_text]
                    state['current_question_id'] = question_id
                    update_session(session_id, state)
                    
                    return question_id, question_text, None
    except Exception as e:
        error = f"{error}\nError fetching cached question: {e}"
    
    # FALLBACK: Use emergency question for any issue
    emergency_question = create_emergency_question(domain, len(asked_questions))
    
    # Make sure even the emergency question isn't a repeat
    while emergency_question in asked_questions:
        emergency_question = create_emergency_question(domain, len(asked_questions) + len(emergency_question))
    
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
    
    return question_id, emergency_question, f"Using fallback question due to: {error}"

def submit_answer(session_id, question_id, answer):
    """Submit an answer to a question"""
    # Get session state
    state = get_session(session_id)
    if not state:
        return None, "Session not found"
    
    # Get question text
    question_text = None
    current_question_id = state.get('current_question_id')
    if current_question_id == question_id and 'asked_questions' in state:
        # The last asked question should be the current one
        if state['asked_questions']:
            question_text = state['asked_questions'][-1]

    # If not in Redis, fetch from postgreSQL database        
    if not question_text:
        with get_db_connection() as conn:
            with get_db_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT question_text FROM questions WHERE id = %s",
                    (question_id,)
                )
                result = cursor.fetchone()
                if not result:
                    return None, "Question not found"
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
    
    return state['questions_asked'], None

def make_guess(session_id):
    """Make a guess based on question history"""
    state = get_session(session_id)
    if not state:
        return None, None, "Session not found"
    
    domain = state.get('domain', 'thing')

    # Create answer pattern dictionary from current session
    current_answer_pattern = {}
    for q_record in state['question_history']:
        current_answer_pattern[q_record['question_id']] = q_record['answer']
    
    # Try to find a similar pattern in previous successful games
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            # Get successful guesses for this domain with high success count
            cursor.execute(
                """SELECT entity_name, success_count 
                FROM domain_guesses 
                WHERE domain = %s AND success_count > 0
                ORDER BY success_count DESC
                LIMIT 10""",  # Get more candidates to find best match
                (domain,)
            )
            cached_guesses = cursor.fetchall()
            
            if cached_guesses:
                best_match_score = 0
                best_match_guess = None
                
                # For each potential cached guess
                for guess_record in cached_guesses:
                    entity_name = guess_record['entity_name']
                    
                    # Find games that correctly guessed this entity
                    cursor.execute(
                        """SELECT id 
                        FROM game_history 
                        WHERE target_entity = %s AND domain = %s AND was_correct = TRUE
                        LIMIT 5""",
                        (entity_name, domain)
                    )
                    successful_games = cursor.fetchall()
                    
                    # For each successful game
                    for game in successful_games:
                        game_id = game['id']
                        
                        # Get the Q&A pattern for this game
                        cursor.execute(
                            """SELECT question_id, answer
                            FROM game_questions
                            WHERE game_id = %s
                            ORDER BY ask_order""",
                            (game_id,)
                        )
                        game_questions = cursor.fetchall()
                        
                        # Create answer pattern dictionary
                        game_pattern = {q['question_id']: q['answer'] for q in game_questions}
                        
                        # Calculate similarity score (imported from database.utils)
                        from database.utils import calculate_pattern_similarity
                        match_score = calculate_pattern_similarity(current_answer_pattern, game_pattern)
                        
                        # Update best match if this is better
                        if match_score > best_match_score:
                            best_match_score = match_score
                            best_match_guess = entity_name
                
                # Use cached guess only if similarity is above threshold
                if best_match_score >= 0.7 and best_match_guess:  # 70% similarity threshold
                    return best_match_guess, state['questions_asked'], f"Pattern match found with similarity score {best_match_score}."
    
    # Generate a guess using AI
    guess, error = generate_guess(domain, state['question_history'])
    
    # Ensure the guess is capitalized appropriately
    if guess and len(guess) > 0:
        guess = guess[0].upper() + guess[1:]
    
    message = "Using AI to generate guess" if not error else f"Using AI with note: {error}"
    
    return guess, state['questions_asked'], message

def submit_game_result(session_id, was_correct, actual_entity=None):
    """Submit the final result of a game and store question history"""
    # Get session before deleting
    state = get_session(session_id)
    
    if state:
        domain = state.get('domain', 'thing')
        
        # Store game history and questions for future pattern matching
        with get_db_connection() as conn:
            with get_db_cursor(conn) as cursor:
                # Calculate game duration
                start_time = state.get('start_time', datetime.now().timestamp())
                duration = int(datetime.now().timestamp() - start_time)
                
                # Store game history
                cursor.execute(
                    """INSERT INTO game_history 
                    (id, user_id, target_entity, domain, was_correct, questions_count, duration) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (session_id, state.get('user_id'), actual_entity, domain, was_correct, 
                     state.get('questions_asked', 0), duration)
                )
                
                # Store question history
                for i, q_record in enumerate(state['question_history']):
                    cursor.execute(
                        """INSERT INTO game_questions 
                        (game_id, question_id, answer, ask_order) 
                        VALUES (%s, %s, %s, %s)""",
                        (session_id, q_record['question_id'], q_record['answer'], i)
                    )
                
                # Update question effectiveness based on result
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
                            # Increment fail count for this entity
                            cursor.execute(
                                """UPDATE domain_guesses 
                                SET fail_count = fail_count + 1 
                                WHERE id = %s""",
                                (existing_guess['id'],)
                            )
                        else:
                            # New entity we've never seen before
                            cursor.execute(
                                """INSERT INTO domain_guesses 
                                (domain, entity_name, success_count, fail_count) 
                                VALUES (%s, %s, 0, 1)""",
                                (domain, actual_entity)
                            )
                
                conn.commit()