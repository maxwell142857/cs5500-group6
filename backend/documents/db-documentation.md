# Database Documentation for GuessMaster

## Overview

This document provides detailed information about the database schema used in the GuessMaster, a domain-agnostic guessing game that learns from user interactions. The system utilizes a PostgreSQL database to store questions, game history, and learning patterns that improve the system's guessing accuracy over time.

## Database Schema

The database consists of five primary tables that work together to create an adaptive learning system for guessing entities across various domains.

### Tables

#### 1. questions

Stores the core question bank used by the system.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Unique identifier for each question |
| question_text | TEXT UNIQUE | The actual yes/no question text presented to users |
| feature | TEXT | Categorization of the question type (e.g., "ai_generated", "emergency") |
| ask_count | INTEGER DEFAULT 0 | Number of times this question has been asked |
| success_rate | REAL DEFAULT 0 | Percentage of successful guesses when this question was used |
| last_used | TIMESTAMP | When the question was most recently asked |
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | When the question was first added to the database |

#### 2. game_history

Records details about each completed game session.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Game session identifier (UUID) |
| user_id | INTEGER | Optional identifier for the user who played the game |
| target_entity | TEXT | The entity that was being guessed (provided at the end of the game) |
| domain | TEXT | Category of entity being guessed (e.g., "animal", "movie", "food") |
| was_correct | BOOLEAN | Whether the system correctly guessed the entity |
| questions_count | INTEGER | Number of questions asked during the game |
| duration | INTEGER | How long the game session lasted in seconds |
| completed_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | When the game was completed |

#### 3. game_questions

Links questions to specific game sessions, storing the user's answers.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Unique identifier for each question-answer pair |
| game_id | TEXT | References game_history.id |
| question_id | INTEGER | References questions.id |
| answer | TEXT | User's response to the question (typically "yes", "no", or "unknown") |
| ask_order | INTEGER | The sequence number of this question in the game |
| timestamp | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | When the question was asked |

#### 4. domain_questions

Associates questions with specific domains and tracks their effectiveness.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Unique identifier |
| domain | TEXT | Category that this question-domain association applies to |
| question_id | INTEGER | References questions.id |
| position | INTEGER | Optimal position in the questioning sequence for this domain |
| usage_count | INTEGER DEFAULT 0 | Number of times this question has been used in this domain |
| effectiveness | REAL DEFAULT 0.5 | Measure of how effective this question is for this domain |
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | When this association was created |

#### 5. domain_guesses

Tracks successful and failed guesses for entities in each domain.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Unique identifier |
| domain | TEXT | Category that this entity belongs to |
| entity_name | TEXT | Name of the entity that was guessed |
| success_count | INTEGER DEFAULT 0 | Number of times this entity was correctly guessed |
| fail_count | INTEGER DEFAULT 0 | Number of times this entity was incorrectly guessed |
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | When this record was created |

### Indices

The database uses several indices to optimize query performance:

| Index Name | Table | Columns | Purpose |
|------------|-------|---------|---------|
| idx_domain_questions | domain_questions | (domain, position) | Speeds up retrieval of questions for a specific domain in position order |
| idx_domain_questions_effectiveness | domain_questions | (effectiveness DESC) | Facilitates quick access to the most effective questions first |
| idx_domain_guesses | domain_guesses | (domain) | Improves lookup of guesses by domain |
| idx_domain_guesses_success | domain_guesses | (success_count DESC) | Enables efficient retrieval of the most successfully guessed entities |

## Relationships

The database implements the following relationships:

1. **game_questions to game_history**: Many-to-one relationship where multiple questions can be asked in a single game.
   - Foreign Key: game_questions.game_id → game_history.id

2. **game_questions to questions**: Many-to-one relationship where a question can be used in multiple games.
   - Foreign Key: game_questions.question_id → questions.id

3. **domain_questions to questions**: Many-to-one relationship where a question can be associated with multiple domains.
   - Foreign Key: domain_questions.question_id → questions.id

## Data Flow

### Game Session Lifecycle

1. A new game session is created with a specific domain (e.g., "animal").
2. The system selects questions based on:
   - Previous effectiveness for the domain
   - Position in the questioning sequence
   - AI-generated questions for every third position (2, 5, 8)
   
3. User answers are recorded in the question history.
4. After 8 questions (or at user request), the system makes a guess by:
   - Checking for similar answer patterns in successful games
   - Using AI to generate a specific guess if no good pattern match is found
   
5. Game results are recorded, updating:
   - Question effectiveness scores
   - Success/fail counts for the guessed entity
   - Game history and question-answer records

### Learning Mechanism

The system learns through several mechanisms:

1. **Question Effectiveness**: Questions that lead to successful guesses have their effectiveness score increased by 0.1; questions in unsuccessful games have their score decreased by 0.05.

2. **Pattern Matching**: The system records answer patterns from successful games and uses a similarity algorithm to identify when a current game matches a previous pattern.

3. **Domain-Specific Knowledge**: By tracking which questions work best for specific domains and at which positions, the system builds domain-specific knowledge.

4. **Entity Success Tracking**: By tracking successful and failed guesses for each entity, the system gradually builds a model of which entities are more common and identifiable.

## Query Patterns

### Common Read Operations

1. Retrieving cached questions for a domain:
   ```sql
   SELECT dq.question_id, q.question_text 
   FROM domain_questions dq
   JOIN questions q ON dq.question_id = q.id
   WHERE dq.domain = [domain] 
   AND dq.position = [position]
   AND q.question_text NOT IN [already_asked_questions]
   ORDER BY dq.effectiveness DESC, dq.usage_count DESC
   LIMIT 1
   ```

2. Finding similar answer patterns for guessing:
   ```sql
   -- 1. Find successful entities in domain
   SELECT entity_name, success_count 
   FROM domain_guesses 
   WHERE domain = [domain] AND success_count > 0
   ORDER BY success_count DESC
   
   -- 2. For each entity, find successful games
   SELECT id FROM game_history 
   WHERE target_entity = [entity] AND domain = [domain] AND was_correct = TRUE
   
   -- 3. For each game, get question patterns
   SELECT question_id, answer FROM game_questions
   WHERE game_id = [game_id]
   ORDER BY ask_order
   ```

### Common Write Operations

1. Recording a new question:
   ```sql
   INSERT INTO questions (question_text, feature, last_used) 
   VALUES ([question], [feature], CURRENT_TIMESTAMP) 
   RETURNING id
   ```

2. Associating a question with a domain:
   ```sql
   INSERT INTO domain_questions (domain, question_id, position) 
   VALUES ([domain], [question_id], [position])
   ```

3. Updating question effectiveness:
   ```sql
   UPDATE domain_questions 
   SET effectiveness = effectiveness + [adjustment] 
   WHERE domain = [domain] AND question_id = [question_id]
   ```

4. Recording game results:
   ```sql
   INSERT INTO game_history 
   (id, user_id, target_entity, domain, was_correct, questions_count, duration) 
   VALUES ([session_id], [user_id], [entity], [domain], [correct], [count], [duration])
   ```

## Maintenance Considerations

1. **Backup Strategy**: The database should be backed up regularly, with special attention to the effectiveness scores and success counts that represent the system's learned knowledge.

2. **Performance Monitoring**: 
   - As the `domain_questions` and `game_questions` tables grow, query performance should be monitored.
   - Consider additional indices if specific query patterns slow down.

3. **Data Pruning**:
   - Consider archiving or pruning old game history data while preserving the learned effectiveness scores.
   - Questions with very low effectiveness scores might be candidates for removal.

4. **Concurrent Access**:
   - The system uses Redis for session state, which handles concurrent games well.
   - Database operations are generally isolated to specific game sessions, minimizing concurrency issues.

5. **Redis Integration**:
   - The system uses Redis for storing session state and rate limits.
   - Ensure Redis persistence is configured appropriately to prevent session data loss.
