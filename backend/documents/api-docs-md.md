# API Documentation

## Endpoints

### Start Game
```
POST /api/start-game
```

Start a new game session with a specific domain.

**Request Body:**
```json
{
  "domain": "animal",
  "user_id": 123,
  "voice_enabled": false,
  "voice_language": "en"
}
```

**Response:**
```json
{
  "session_id": "f8e7d6c5-b4a3-2c1d-0e9f-8g7h6i5j4k3l",
  "message": "Think of an animal and I'll try to guess it!"
}
```

### Get Question
```
GET /api/get-question/{session_id}
```

Get the next question for the session.

**Response:**
```json
{
  "session_id": "f8e7d6c5-b4a3-2c1d-0e9f-8g7h6i5j4k3l",
  "question_id": 42,
  "question": "Is it a mammal?",
  "questions_asked": 1,
  "should_guess": false,
  "message": null
}
```

### Submit Answer
```
POST /api/submit-answer
```

Submit an answer to a question.

**Request Body:**
```json
{
  "session_id": "f8e7d6c5-b4a3-2c1d-0e9f-8g7h6i5j4k3l",
  "question_id": 42,
  "answer": "yes"
}
```

**Response:**
```json
{
  "session_id": "f8e7d6c5-b4a3-2c1d-0e9f-8g7h6i5j4k3l",
  "answer": "yes",
  "should_guess": false,
  "questions_asked": 1
}
```

### Make Guess
```
GET /api/make-guess/{session_id}
```

Get the system's guess based on answers so far.

**Response:**
```json
{
  "session_id": "f8e7d6c5-b4a3-2c1d-0e9f-8g7h6i5j4k3l",
  "guess": "Dog",
  "questions_asked": 8,
  "message": "Using AI to generate guess"
}
```

### Submit Result
```
POST /api/submit-result
```

Submit the final result of a game (correct/incorrect).

**Request Body:**
```json
{
  "session_id": "f8e7d6c5-b4a3-2c1d-0e9f-8g7h6i5j4k3l",
  "was_correct": false,
  "actual_entity": "Wolf"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Thank you for playing!"
}
```

### Toggle Voice
```
POST /api/toggle-voice?session_id={session_id}&enable={true|false}&language={language_code}
```

Enable or disable voice features for a session.

**Response:**
```json
{
  "status": "success",
  "voice_enabled": true
}
```

### Voice Input
```
POST /api/voice-input
```

Process voice input and convert to text answer.

**Request Body:**
```json
{
  "session_id": "f8e7d6c5-b4a3-2c1d-0e9f-8g7h6i5j4k3l",
  "audio_data": "base64_encoded_audio"
}
```

**Response:**
```json
{
  "session_id": "f8e7d6c5-b4a3-2c1d-0e9f-8g7h6i5j4k3l",
  "answer": "yes",
  "should_guess": false,
  "questions_asked": 2
}
```

### Voice Output
```
POST /api/voice-output
```

Generate voice output from text.

**Request Body:**
```json
{
  "session_id": "f8e7d6c5-b4a3-2c1d-0e9f-8g7h6i5j4k3l",
  "text": "Is it a mammal?"
}
```

**Response:**
```json
{
  "audio_data": "base64_encoded_audio",
  "mime_type": "audio/mp3"
}
```

## Error Responses

All endpoints return standard HTTP status codes:

- `200 OK`: Request successful
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: Session, question, or resource not found
- `429 Too Many Requests`: API rate limit exceeded
- `500 Internal Server Error`: Server error

Error responses include a detail message:

```json
{
  "detail": "Session not found"
}
```
