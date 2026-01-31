# Voice to Google Sheets - Setup Guide

This application records voice, converts it to text using Google Cloud Speech-to-Text, and uploads it to a Google Sheet.

## Prerequisites

1. Python 3.8+
2. A Google Cloud project with APIs enabled
3. A Google Sheet

## Step 1: Set Up Google Cloud Project

### Enable Required APIs:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable these APIs:
   - **Cloud Speech-to-Text API**
   - **Google Sheets API**

### Create Service Account:
1. Go to **Service Accounts** page in Google Cloud Console
2. Click "Create Service Account"
3. Name: `little-helper`
4. Grant roles:
   - `Editor` (for development) or more specific roles for production
5. Create JSON key:
   - Go to Keys tab
   - Click "Add Key" → "Create new key"
   - Choose JSON format
   - Save the file as `credentials.json` in your project root

### Create Google Sheet:
1. Go to [Google Sheets](https://sheets.google.com)
2. Create a new sheet
3. Copy the Sheet ID from the URL:
   ```
   https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit
   ```
4. Share the sheet with the service account email (from `credentials.json`)
   - Copy the `client_email` from the credentials file
   - Share the sheet with that email (Editor access)

## Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 3: Configure Credentials

1. Place your `credentials.json` in the project root directory
2. Update the paths in `little_helper/views.py`:
   - Line 12: Change `'path/to/your/credentials.json'` to your actual path
   - Line 42: Same for the second occurrence

## Step 4: Run the Server

```bash
python manage.py runserver
```

Access the application at: `http://localhost:8000`

## Step 5: Using the Application

1. **Enter Sheet ID**: Paste your Google Sheet ID
2. **Enter Sheet Name**: Name of the sheet tab (default: "Sheet1")
3. **Click Record**: Start speaking (microphone access will be requested)
4. **Click Stop**: Stop recording
5. **Text will appear**: Your speech will be transcribed
6. **Click Submit**: Upload to Google Sheets

The text will be appended to column A with a timestamp in column B.

## Troubleshooting

### "No audio file provided"
- Make sure you allowed microphone access
- Try a different browser (Chrome/Firefox recommended)

### "Could not transcribe audio"
- Check if your audio was clear
- Make sure you're speaking English (language is set to US English)
- Verify Google Cloud Speech-to-Text API is enabled

### "Failed to authenticate"
- Verify `credentials.json` path is correct
- Check if the service account email has access to the Google Sheet
- Make sure the JSON file contains valid credentials

### Microphone not working
- Grant microphone permissions in browser settings
- Use HTTPS in production (self-signed cert for testing)
- Test microphone on other websites

## Production Deployment

For production:
1. Use environment variables for credentials path:
   ```bash
   export GOOGLE_CREDENTIALS_PATH="/path/to/credentials.json"
   ```
2. Set `DEBUG = False` in `settings.py`
3. Add your domain to `ALLOWED_HOSTS` in `settings.py`
4. Use HTTPS (required for microphone access in production)
5. Consider using more restrictive service account permissions

## Security Notes

- **Never commit `credentials.json` to version control**
- Add `credentials.json` to `.gitignore`
- Use environment variables in production
- Restrict service account permissions to specific sheets
- Use OAuth2 for user authentication instead of service account in production

## Support

For issues with:
- **Google Cloud APIs**: Check [Google Cloud Documentation](https://cloud.google.com/docs)
- **Django**: Visit [Django Documentation](https://docs.djangoproject.com/)
- **Web Audio API**: See [MDN Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)
