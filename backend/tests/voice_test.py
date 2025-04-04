import requests, base64, pyaudio, wave, io
from pydub import AudioSegment
from pydub.playback import play

# Server URL
BASE_URL = "http://localhost:8000/"  

# 1. Start a game session
def start_game():
    response = requests.post(
        f"{BASE_URL}/api/start-game",
        json={"domain": "animal", "voice_enabled": True, "voice_language": "en"}
    )
    data = response.json()
    print(f"Game started: {data['message']}")
    return data["session_id"]

# 2. Enable voice chat for an existing session
def enable_voice(session_id):
    response = requests.post(
        f"{BASE_URL}/api/toggle-voice",
        params={"session_id": session_id, "enable": True, "language": "en"}
    )
    print(f"Voice enabled: {response.json()}")

# 3. Get a question
def get_question(session_id):
    response = requests.get(f"{BASE_URL}/api/get-question/{session_id}")
    data = response.json()
    print(f"Question: {data['question']}")
    return data

# 4. Record audio for voice input
def record_audio(seconds=5):
    # Record audio using PyAudio
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100
    CHUNK = 1024
    
    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, channels=CHANNELS,
                    rate=RATE, input=True,
                    frames_per_buffer=CHUNK)
    
    print(f"Recording for {seconds} seconds...")
    frames = []
    for i in range(0, int(RATE / CHUNK * seconds)):
        data = stream.read(CHUNK)
        frames.append(data)
    
    print("Recording finished")
    stream.stop_stream()
    stream.close()
    audio.terminate()
    
    # Save to an in-memory WAV file
    buffer = io.BytesIO()
    wf = wave.open(buffer, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(audio.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()
    
    # Convert to MP3 for smaller size
    buffer.seek(0)
    audio_data = AudioSegment.from_wav(buffer)
    mp3_buffer = io.BytesIO()
    audio_data.export(mp3_buffer, format="mp3")
    
    # Return base64 encoded data
    mp3_buffer.seek(0)
    return base64.b64encode(mp3_buffer.read()).decode('utf-8')

# 5. Submit voice input
def submit_voice_input(session_id, audio_data):
    response = requests.post(
        f"{BASE_URL}/api/voice-input",
        json={"session_id": session_id, "audio_data": audio_data}
    )
    data = response.json()
    print(f"Voice input processed: {data}")
    return data

# 6. Get voice output
def get_voice_output(session_id, text):
    response = requests.post(
        f"{BASE_URL}/api/voice-output",
        json={"session_id": session_id, "text": text}
    )
    data = response.json()
    print("Voice output received")
    
    # Decode and play audio
    audio_data = base64.b64decode(data["audio_data"])
    audio = AudioSegment.from_file(io.BytesIO(audio_data), format="mp3")
    play(audio)
    
    return data

# Main test flow
def test_voice_chat():
    # Start a new game
    session_id = start_game()
    
    # Get initial question
    question_data = get_question(session_id)
    
    # Get voice output for the question
    get_voice_output(session_id, question_data["question"])
    
    # Record voice answer (say "yes" or "no")
    print("Please speak your answer (yes/no)...")
    audio_data = record_audio(5)  # Record for 5 seconds
    
    # Submit voice answer
    result = submit_voice_input(session_id, audio_data)
    
    # Get next question if available
    if not result.get("should_guess", False):
        question_data = get_question(session_id)
        get_voice_output(session_id, question_data["question"])

# Run the test
if __name__ == "__main__":
    test_voice_chat()