from database import get_db_connection, get_db_cursor

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
                ask_count INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 0,
                last_used TIMESTAMP,
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