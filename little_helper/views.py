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

# Configuration
GOOGLE_SHEET_ID = '1YjT7Etx4xtzvkOchAy6rWT7p17pINBLZG29lIePnoN4'
GOOGLE_SHEET_NAME = 'Sheet1'

# Get credentials path from environment or use default
CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', os.path.join(os.path.dirname(__file__), '..', 'credentials.json'))
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = CREDENTIALS_PATH

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
        client = speech_v1.SpeechClient()
        
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
    """Upload transcribed text to Google Sheets"""
    try:
        data = json.loads(request.body)
        text = data.get('text')
        
        if not text:
            return JsonResponse({
                'success': False,
                'error': 'Missing text'
            })
        
        # Load credentials
        if not os.path.exists(CREDENTIALS_PATH):
            return JsonResponse({
                'success': False,
                'error': f'Credentials file not found at {CREDENTIALS_PATH}. Please add your credentials.json file.'
            })
        
        creds = Credentials.from_service_account_file(
            CREDENTIALS_PATH,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        
        # Build Sheets API service
        service = build('sheets', 'v4', credentials=creds)
        
        # Append data to sheet
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        values = [[text, timestamp]]
        body = {
            'values': values
        }
        
        result = service.spreadsheets().values().append(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=f"{GOOGLE_SHEET_NAME}!A:B",
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        return JsonResponse({
            'success': True,
            'message': 'Data uploaded successfully',
            'result': result.get('updates', {})
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })