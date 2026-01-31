from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
import os
from datetime import datetime
from google.cloud import speech_v1
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from io import BytesIO
import string
import re

# Configuration
GOOGLE_SHEET_ID = '1YjT7Etx4xtzvkOchAy6rWT7p17pINBLZG29lIePnoN4'
GOOGLE_SHEET_NAME = 'common'

# Get credentials
CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', os.path.join(os.path.dirname(__file__), '..', 'credentials.json'))
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')

if GOOGLE_CREDENTIALS_JSON:
    import json
    creds = Credentials.from_service_account_info(json.loads(GOOGLE_CREDENTIALS_JSON), scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/cloud-platform'])
else:
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = CREDENTIALS_PATH
    creds = Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/cloud-platform']
    )

def parse_voice_input(text):
    """
    Parse the voice input to extract storage, shelf, and keywords.
    Looks for keywords 'storage', 'shelf', 'keywords' and takes all words after each until a dot (.) or the next keyword.
    Returns dict with values or error.
    """
    words = text.split()
    lower_words = [word.strip(string.punctuation).lower() for word in words]
    storage = None
    shelf = None
    keywords = None
    
    try:
        # Recognize both 'keyword' and 'keywords' for the keywords field
        keyword_variants = ['keyword', 'keywords']
        if 'storage' in lower_words:
            idx = lower_words.index('storage')
            start = idx + 1
            end = len(words)
            for i in range(start, len(words)):
                if lower_words[i] == 'shelf' or lower_words[i] in keyword_variants or '.' in words[i]:
                    end = i + (1 if '.' in words[i] else 0)
                    break
            storage_words = words[start:end]
            storage = ' '.join(word.strip(string.punctuation) for word in storage_words).strip()

        if 'shelf' in lower_words:
            idx = lower_words.index('shelf')
            start = idx + 1
            end = len(words)
            for i in range(start, len(words)):
                if lower_words[i] in keyword_variants or '.' in words[i]:
                    end = i + (1 if '.' in words[i] else 0)
                    break
            shelf_words = words[start:end]
            shelf = ' '.join(word.strip(string.punctuation) for word in shelf_words).strip()

        # Find the first occurrence of either 'keyword' or 'keywords'
        keyword_idx = None
        for variant in keyword_variants:
            if variant in lower_words:
                keyword_idx = lower_words.index(variant)
                break
        if keyword_idx is not None:
            start = keyword_idx + 1
            end = len(words)
            for i in range(start, len(words)):
                if '.' in words[i]:
                    end = i + 1
                    break
            keywords_words = words[start:end]
            keywords = ' '.join(word.strip(string.punctuation) for word in keywords_words).strip()
    except ValueError:
        pass
    
    missing = []
    invalid_values = {}
    
    if not storage:
        missing.append('storage')
    if not shelf:
        missing.append('shelf')
    elif not re.match(r'^[A-Z]\d+$', shelf.upper()):
        invalid_values['shelf'] = shelf
    if not keywords:
        missing.append('keywords')
    
    if missing or invalid_values:
        error_parts = []
        if missing:
            error_parts.append(f'Missing values for: {", ".join(missing)}.')
        if invalid_values:
            for field, value in invalid_values.items():
                if field == 'shelf':
                    error_parts.append(f'Invalid shelf format: "{value}". Shelf must be like A1, B5 (letter followed by number).')
        return {
            'error': ' '.join(error_parts),
            'parsed_text': text
        }
    
    return {
        'storage': storage,
        'shelf': shelf,
        'keywords': keywords,
        'parsed_text': text
    }

def index(request):
    with open('index.html', 'r') as file:
        html_content = file.read()
    return HttpResponse(html_content)

@csrf_exempt
@require_http_methods(["POST"])
def transcribe(request):
    """Convert audio to text using Google Cloud Speech-to-Text"""
    try:
        audio_file = request.FILES.get('audio')
        if not audio_file:
            return JsonResponse({
                'success': False,
                'error': 'No audio file provided'
            })
        
        # Read audio data
        audio_content = audio_file.read()
        
        # Initialize Speech-to-Text client
        client = speech_v1.SpeechClient(credentials=creds)
        
        # Configure audio
        audio = speech_v1.RecognitionAudio(content=audio_content)
        config = speech_v1.RecognitionConfig(
            encoding=speech_v1.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            sample_rate_hertz=48000,
            language_code="en-US",
            enable_automatic_punctuation=True,
        )
        
        # Perform transcription
        response = client.recognize(config=config, audio=audio)
        
        # Extract transcript
        transcript = ""
        for result in response.results:
            if result.alternatives:
                transcript += result.alternatives[0].transcript + " "
        
        transcript = transcript.strip()
        
        if not transcript:
            return JsonResponse({
                'success': False,
                'error': 'Could not transcribe audio'
            })
        
        return JsonResponse({
            'success': True,
            'transcript': transcript
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@csrf_exempt
@require_http_methods(["POST"])
def upload_to_sheet(request):
    """Upload transcribed text to Google Sheets or revert last entry"""
    try:
        data = json.loads(request.body)
        text = data.get('text')
        
        if not text:
            return JsonResponse({
                'success': False,
                'error': 'Missing text'
            })
        
        # Check if it's a revert command
        words = [word.strip(string.punctuation).lower() for word in text.split()]
        if 'revert' in words:
            return revert_last_entry()
        
        # Parse the voice input
        parsed = parse_voice_input(text)
        
        if 'error' in parsed:
            return JsonResponse({
                'success': False,
                'error': parsed['error'],
                'parsed_text': parsed['parsed_text']
            })
        
        storage = parsed['storage']
        shelf = parsed['shelf']
        keywords = parsed['keywords']
        
        # Load credentials
        if not GOOGLE_CREDENTIALS_JSON and not os.path.exists(CREDENTIALS_PATH):
            return JsonResponse({
                'success': False,
                'error': f'Credentials file not found at {CREDENTIALS_PATH}. Please add your credentials.json file or set GOOGLE_CREDENTIALS_JSON.'
            })
        
        # Build Sheets API service
        service = build('sheets', 'v4', credentials=creds)
        
        # Append data to sheet
        values = [[storage, shelf, keywords]]
        body = {
            'values': values
        }
        
        result = service.spreadsheets().values().append(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=f"{GOOGLE_SHEET_NAME}!A:C",
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        return JsonResponse({
            'success': True,
            'message': 'Data uploaded successfully',
            'storage': storage,
            'shelf': shelf,
            'keywords': keywords,
            'parsed_text': parsed['parsed_text'],
            'result': result.get('updates', {})
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

def revert_last_entry():
    """Revert the last entry in the Google Sheet"""
    try:
        # Load credentials
        if not GOOGLE_CREDENTIALS_JSON and not os.path.exists(CREDENTIALS_PATH):
            return JsonResponse({
                'success': False,
                'error': f'Credentials file not found at {CREDENTIALS_PATH}. Please add your credentials.json file or set GOOGLE_CREDENTIALS_JSON.',
                'parsed_text': 'revert'
            })
        
        # Build Sheets API service
        service = build('sheets', 'v4', credentials=creds)
        
        # Get all values to find the last row
        result = service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=f"{GOOGLE_SHEET_NAME}!A:Z"
        ).execute()
        
        values = result.get('values', [])
        
        if not values or len(values) == 0:
            return JsonResponse({
                'success': False,
                'error': 'No entries to revert',
                'parsed_text': 'revert'
            })
        
        # Find the last non-empty row (in case there are empty rows)
        last_row = len(values)
        
        # Clear the last row
        range_to_clear = f"{GOOGLE_SHEET_NAME}!A{last_row}:C{last_row}"
        service.spreadsheets().values().clear(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=range_to_clear
        ).execute()
        
        return JsonResponse({
            'success': True,
            'message': 'Last entry reverted successfully',
            'parsed_text': 'revert'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'parsed_text': 'revert'
        })