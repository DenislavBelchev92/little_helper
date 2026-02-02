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
# Set DEBUG to True for development, False for production
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

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
    # Use regex to extract fields: match after keyword up to next keyword or end, non-greedy
    storage = None
    shelf = None
    keywords = None
    # Storage: after 'storage' up to 'shelf', 'keyword(s)', punctuation, or end
    storage_match = re.search(r'storage\s+(.*?)(?=\b(shelf|keywords?)\b|[.?!,;]|$)', text, re.IGNORECASE)
    if storage_match:
        storage = storage_match.group(1).strip(' .,:;\n\t') or None
    # Shelf: after 'shelf' (optionally followed by punctuation or end), up to next keyword, punctuation, or end
    shelf_match = re.search(r'shelf(?:\s+|[.?!,;])?(.*?)(?=\b(storage|keywords?)\b|[.?!,;]|$)', text, re.IGNORECASE)
    if shelf_match:
        shelf = shelf_match.group(1).strip(' .,:;\n\t') or None
    # Keywords: after 'keyword' or 'keywords' up to 'storage', 'shelf', punctuation, or end
    keyword_match = re.search(r'key(?:word|words)\s+(.*?)(?=\b(storage|shelf)\b|[.?!,;]|$)', text, re.IGNORECASE)
    if keyword_match:
        keywords = keyword_match.group(1).strip(' .,:;\n\t') or None

    # Add debug info for _match variables
    debug_matches = None
    if DEBUG:
        debug_matches = {
            'storage_match': storage_match.group(0) if storage_match else None,
            'shelf_match': shelf_match.group(0) if shelf_match else None,
            'keyword_match': keyword_match.group(0) if keyword_match else None,
            'text': text,
            'storage': storage,
            'shelf': shelf,
            'keywords': keywords
        }
    
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
        resp = {
            'error': ' '.join(error_parts),
            'parsed_text': text
        }
        if DEBUG:
            resp['debug_matches'] = debug_matches
        return resp

    resp = {
        'storage': storage,
        'shelf': shelf,
        'keywords': keywords,
        'parsed_text': text
    }
    if DEBUG:
        resp['debug_matches'] = debug_matches
    return resp

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
            enable_automatic_punctuation=False,
            use_enhanced=True,
            model="latest_short",
            max_alternatives=3,
            alternative_language_codes=["en-GB", "en-AU", "en-CA"],
            speech_contexts=[
                speech_v1.SpeechContext(
                    phrases=[
                        "storage", "shelf", "keyword", "keywords", "revert",
                        "terrace", "basement", "small house", "house", "Bracigovo",
                        "barrack", "basement apartment", "basement house", "attic"

                        "box", "electronics", "cables", "tools", "toys",
                        "clothes", "books", "furniture", "kitchen", "shoes", "bags",
                        
                         "A0", "A1", "A2", "A3", "A4", "A5",
                            "B0", "B1", "B2", "B3", "B4", "B5",
                            "C0", "C1", "C2", "C3", "C4", "C5",
                            "D0", "D1", "D2", "D3", "D4", "D5",
                    ],
                    boost=15.0
                )
            ]
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
    """Upload transcribed text to Google Sheets or revert last entry, or just parse and merge fields if requested. Optionally upload an image to the 'picture' cell."""
    try:
        # Support both JSON and multipart/form-data
        if request.content_type and request.content_type.startswith('multipart/'):
            text = request.POST.get('text')
            current_state = json.loads(request.POST.get('current_state', '{}'))
            do_upload = request.POST.get('do_upload', 'true').lower() in ('true', '1', 'yes')
            image_file = request.FILES.get('image')
        else:
            data = json.loads(request.body)
            text = data.get('text')
            current_state = data.get('current_state', {})
            do_upload = data.get('do_upload', True)
            image_file = None

        if not text:
            return JsonResponse({
                'success': False,
                'error': 'Missing text'
            })

        # Check if it's a revert command
        words = [word.strip(string.punctuation).lower() for word in text.split()]
        if 'revert' in words:
            return revert_last_entry()

        # Parse the voice input (may be partial)
        parsed = parse_voice_input(text)
        debug_matches = parsed.get('debug_matches', {})

        # Only update a field if its _match variable is present in the new parse; otherwise, keep previous value
        merged = {
            'storage': current_state.get('storage', ''),
            'shelf': current_state.get('shelf', ''),
            'keywords': current_state.get('keywords', ''),
            'debug_matches': debug_matches
        }
        # Only update if new value is not None and not empty string
        if debug_matches.get('storage_match') and parsed.get('storage') not in (None, ''):
            merged['storage'] = parsed.get('storage')
        if debug_matches.get('shelf_match') and parsed.get('shelf') not in (None, ''):
            merged['shelf'] = parsed.get('shelf')
        if debug_matches.get('keyword_match') and parsed.get('keywords') not in (None, ''):
            merged['keywords'] = parsed.get('keywords')
        merged['parsed_text'] = f"Storage {merged['storage']}. Shelf {merged['shelf']}. Keywords {merged['keywords']}"

        # Only check for missing/invalid fields if actually uploading

        missing = []
        invalid_values = {}
        if do_upload:
            if not merged['storage']:
                missing.append('storage')
            if not merged['shelf']:
                missing.append('shelf')
            elif not re.match(r'^[A-Z]\d+$', merged['shelf'].upper()):
                invalid_values['shelf'] = merged['shelf']
            if not merged['keywords']:
                missing.append('keywords')

            if missing or invalid_values:
                error_parts = []
                if missing:
                    error_parts.append(f'Missing values for: {", ".join(missing)}.')
                if invalid_values:
                    for field, value in invalid_values.items():
                        if field == 'shelf':
                            error_parts.append(f'Invalid shelf format: "{value}". Shelf must be like A1, B5 (letter followed by number).')
                return JsonResponse({
                    'success': False,
                    'error': ' '.join(error_parts),
                    'parsed_text': merged['parsed_text'],
                    'debug_matches': debug_matches
                })

        if not do_upload:
            # Just return the merged result for preview
            return JsonResponse({
                'success': True,
                **merged
            })

        # Otherwise, upload to sheet
        storage = merged['storage']
        shelf = merged['shelf']
        keywords = merged['keywords']
        picture_url = ''

        # If image is present, upload to Imgur and get URL
        if image_file:
            import requests
            IMGUR_CLIENT_ID = os.getenv('IMGUR_CLIENT_ID')
            if not IMGUR_CLIENT_ID:
                return JsonResponse({'success': False, 'error': 'IMGUR_CLIENT_ID not set in environment.'})
            img_data = image_file.read()
            headers = {'Authorization': f'Client-ID {IMGUR_CLIENT_ID}'}
            response = requests.post('https://api.imgur.com/3/image', headers=headers, files={'image': img_data})
            if response.status_code == 200:
                picture_url = response.json()['data']['link']
            else:
                return JsonResponse({'success': False, 'error': 'Image upload failed: ' + response.text})

        # Load credentials
        if not GOOGLE_CREDENTIALS_JSON and not os.path.exists(CREDENTIALS_PATH):
            return JsonResponse({
                'success': False,
                'error': f'Credentials file not found at {CREDENTIALS_PATH}. Please add your credentials.json file or set GOOGLE_CREDENTIALS_JSON.'
            })

        # Build Sheets API service
        service = build('sheets', 'v4', credentials=creds)

        # Append data to sheet, now with picture_url as 4th column
        values = [[storage, shelf, keywords, picture_url]]
        body = {
            'values': values
        }

        result = service.spreadsheets().values().append(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=f"{GOOGLE_SHEET_NAME}!A:D",
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()

        return JsonResponse({
            'success': True,
            'message': 'Data uploaded successfully',
            'storage': storage,
            'shelf': shelf,
            'keywords': keywords,
            'picture_url': picture_url,
            'parsed_text': merged['parsed_text'],
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