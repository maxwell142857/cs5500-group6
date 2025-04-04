import io, base64, speech_recognition as sr

from pydub import AudioSegment
from gtts import gTTS

def process_voice_input(audio_data_base64):
    """
    Process voice input and convert to text answer
    Returns answer text and error message if any
    """
    try:
        # Decode base64 audio data
        audio_data = base64.b64decode(audio_data_base64)
        
        # Convert to WAV format for recognition
        audio = AudioSegment.from_file(io.BytesIO(audio_data))
        wav_data = io.BytesIO()
        audio.export(wav_data, format="wav")
        wav_data.seek(0)
        
        # Use speech recognition
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_data) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
        
        # Process the recognized text to determine yes/no/don't know
        lower_text = text.lower()
        if any(word in lower_text for word in ['yes', 'yeah', 'yep', 'correct']):
            answer = 'yes'
        elif any(word in lower_text for word in ['no', 'nope', 'not']):
            answer = 'no'
        else:
            answer = 'unknown'
            
        return answer, None
        
    except Exception as e:
        return None, f"Error processing voice input: {str(e)}"

def generate_voice_output(text, language='en'):
    """
    Generate voice output from text
    Returns base64 encoded audio data and error message if any
    """
    try:
        # Generate speech using gTTS
        tts = gTTS(text=text, lang=language)
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        
        # Encode as base64
        audio_data = base64.b64encode(mp3_fp.read()).decode('utf-8')
        
        return audio_data, None
        
    except Exception as e:
        return None, f"Error generating speech: {str(e)}"