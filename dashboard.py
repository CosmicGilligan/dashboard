import streamlit as st
from datetime import datetime, timedelta
import json
import os
import pickle
import time
import requests
import random
import pytz  # ✅ FIX: needed for timezone handling
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Configure Streamlit page
st.set_page_config(
    page_title="Personal Dashboard",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Google Calendar API setup
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

class GoogleCalendarService:
    def __init__(self):
        self.service = None
        self.credentials = None
        self.authenticated = False
    
    def authenticate(self):
        """Authenticate with Google Calendar API"""
        creds = None
        
        # Load existing credentials
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        # If there are no valid credentials, request authorization
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    st.error(f"Token refresh failed: {e}")
                    # Delete invalid token and re-authenticate
                    if os.path.exists('token.pickle'):
                        os.remove('token.pickle')
                    return self._new_authentication()
            else:
                return self._new_authentication()
        
        self.credentials = creds
        self.service = build('calendar', 'v3', credentials=creds)
        self.authenticated = True
        return True
    
    def _new_authentication(self):
        """Handle new authentication flow"""
        if os.path.exists('credentials.json'):
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0, open_browser=True)
                
                # Save credentials for next run
                with open('token.pickle', 'wb') as token:
                    pickle.dump(creds, token)
                
                self.credentials = creds
                self.service = build('calendar', 'v3', credentials=creds)
                self.authenticated = True
                return True
            except Exception as e:
                st.error(f"Authentication failed: {e}")
                return False
        else:
            st.error("Please add your Google Calendar credentials.json file to the app directory")
            st.info("Download from: https://console.cloud.google.com/apis/credentials")
            return False

    # ✅ FIX: method moved into the class
    def get_today_events(self, calendar_id='primary'):
        """Get today's calendar events from specified calendar with proper timezone handling"""
        if not self.service or not self.authenticated:
            return []
        
        try:
            # Get local timezone - you can change this to your specific timezone
            try:
                # Try to detect system timezone
                import time as _time
                local_tz = pytz.timezone(_time.tzname[0])
            except:
                # Fallback - change this to your timezone (e.g., 'America/New_York', etc.)
                local_tz = pytz.timezone('America/Los_Angeles')  # CHANGE THIS TO YOUR TIMEZONE
            
            # Get today in local timezone
            now = datetime.now(local_tz)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Format with proper timezone (RFC3339)
            time_min = today_start.isoformat()
            time_max = today_end.isoformat()
            
            # First attempt with timezone
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=50,
                singleEvents=True,
                orderBy='startTime',
                timeZone=str(local_tz)  # Explicitly set timezone
            ).execute()
            
            events = events_result.get('items', [])
            return events
            
        except Exception:
            # Fallback to a wider time window; filter to today
            try:
                today = datetime.now()
                start_of_range = (today - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
                end_of_range = (today + timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
                
                time_min = start_of_range.isoformat()
                time_max = end_of_range.isoformat()
                
                events_result = self.service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=100,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                all_events = events_result.get('items', [])
                # ✅ Use the global helper that checks "today"
                today_events = [event for event in all_events if is_today_event(event)]
                return today_events
                
            except Exception:
                return []

    # ✅ FIX: method moved into the class
    def get_calendar_list(self):
        """Get list of available calendars"""
        if not self.service or not self.authenticated:
            return []
        
        try:
            calendar_list = self.service.calendarList().list().execute()
            return calendar_list.get('items', [])
        except Exception as e:
            st.error(f"Error fetching calendar list: {e}")
            return []

# Also update your format_event_time function to handle timezone better
def format_event_time(event):
    """Format event time for display with better timezone handling"""
    start = event.get('start', {})
    end = event.get('end', {})
    
    if 'dateTime' in start:
        try:
            # Parse the datetime strings properly
            start_dt_str = start['dateTime']
            end_dt_str = end.get('dateTime')
            if not end_dt_str:
                return "All Day"
            
            # Handle different datetime formats from Google Calendar
            if 'T' in start_dt_str:
                # More robust parsing - handle timezone info properly
                try:
                    # Try parsing with timezone info
                    start_time = datetime.fromisoformat(start_dt_str.replace('Z', '+00:00'))
                    end_time = datetime.fromisoformat(end_dt_str.replace('Z', '+00:00'))
                    
                    # Convert to local time if needed
                    if start_time.tzinfo:
                        try:
                            local_tz = pytz.timezone('America/Los_Angeles')  # CHANGE TO YOUR TIMEZONE
                            start_time = start_time.astimezone(local_tz)
                            end_time = end_time.astimezone(local_tz)
                        except:
                            pass  # Use original time if conversion fails
                    
                    # Format times nicely
                    start_formatted = start_time.strftime('%I:%M %p').lstrip('0').replace(' 0', ' ')
                    end_formatted = end_time.strftime('%I:%M %p').lstrip('0').replace(' 0', ' ')
                    
                    return f"{start_formatted} - {end_formatted}"
                    
                except Exception:
                    # Fallback to simpler parsing
                    start_clean = start_dt_str.split('T')[0] + 'T' + start_dt_str.split('T')[1].split('+')[0].split('-')[0].split('Z')[0]
                    end_clean = end_dt_str.split('T')[0] + 'T' + end_dt_str.split('T')[1].split('+')[0].split('-')[0].split('Z')[0]
                    
                    start_time = datetime.fromisoformat(start_clean)
                    end_time = datetime.fromisoformat(end_clean)
                    
                    start_formatted = start_time.strftime('%I:%M %p').lstrip('0').replace(' 0', ' ')
                    end_formatted = end_time.strftime('%I:%M %p').lstrip('0').replace(' 0', ' ')
                    
                    return f"{start_formatted} - {end_formatted}"
                    
        except Exception:
            # Final fallback - extract just hour and minute
            try:
                if 'T' in start.get('dateTime', ''):
                    time_part = start['dateTime'].split('T')[1]
                    hour = int(time_part[:2])
                    minute = int(time_part[3:5])
                    
                    # Convert to 12-hour format
                    if hour == 0:
                        return f"12:{minute:02d} AM"
                    elif hour < 12:
                        return f"{hour}:{minute:02d} AM"
                    elif hour == 12:
                        return f"12:{minute:02d} PM"
                    else:
                        return f"{hour-12}:{minute:02d} PM"
            except:
                pass

    return "All Day"

# ✅ Keep a SINGLE global helper
def is_today_event(event):
    """Check if an event is actually today with better timezone handling"""
    try:
        today = datetime.now().date()
        
        start = event.get('start', {})
        if 'dateTime' in start:
            start_dt_str = start['dateTime']
            if 'T' in start_dt_str:
                dt = datetime.fromisoformat(start_dt_str.replace('Z', '+00:00'))
                return dt.date() == today
        elif 'date' in start:
            event_date = datetime.fromisoformat(start['date']).date()
            return event_date == today
            
        # Also check end date for events that might span midnight
        end = event.get('end', {})
        if 'dateTime' in end:
            end_dt_str = end['dateTime']
            if 'T' in end_dt_str:
                dt = datetime.fromisoformat(end_dt_str.replace('Z', '+00:00'))
                return dt.date() == today
        elif 'date' in end:
            end_date = datetime.fromisoformat(end['date']).date()
            return end_date == today
            
    except Exception:
        # If we can't parse the date, include the event to be safe
        return True
    
    return False

# ---------------------
# The rest of your code
# ---------------------

# Initialize Google Calendar service
if 'calendar_service' not in st.session_state:
    st.session_state.calendar_service = GoogleCalendarService()

# Initialize session state for checklist
if 'checklist' not in st.session_state:
    st.session_state.checklist = {
        'Medical': [
            {'task': 'Take morning medications', 'done': False},
            {'task': 'Check if prescription refills are needed', 'done': False},
            {'task': 'Drink 8 glasses of water', 'done': False},
        ],
        'Financial': [
            {'task': 'Check bank account balance', 'done': False},
            {'task': 'Review any pending bills', 'done': False},
            {'task': 'Update expense tracking', 'done': False},
        ],
        'Personal': [
            {'task': 'Call family/friends', 'done': False},
            {'task': 'Practice gratitude - write 3 things', 'done': False},
            {'task': 'Tidy up living space', 'done': False},
        ],
        'Work': [
            {'task': 'Review today\'s priorities', 'done': False},
            {'task': 'Check and respond to important emails', 'done': False},
            {'task': 'Plan tomorrow\'s schedule', 'done': False},
        ]
    }

# Initialize session state for schedule
if 'schedule' not in st.session_state:
    st.session_state.schedule = []

# Inspirational quotes
QUOTES = [
    "The way to get started is to quit talking and begin doing. - Walt Disney",
    "Life is what happens to you while you're busy making other plans. - John Lennon",
    "The future belongs to those who believe in the beauty of their dreams. - Eleanor Roosevelt",
    "It is during our darkest moments that we must focus to see the light. - Aristotle",
    "The only impossible journey is the one you never begin. - Tony Robbins",
    "Success is not final, failure is not fatal: it is the courage to continue that counts. - Winston Churchill",
    "The only way to do great work is to love what you do. - Steve Jobs",
    "Innovation distinguishes between a leader and a follower. - Steve Jobs",
    "Your time is limited, don't waste it living someone else's life. - Steve Jobs",
    "Stay hungry, stay foolish. - Steve Jobs",
    "Believe you can and you're halfway there. - Theodore Roosevelt",
    "The best time to plant a tree was 20 years ago. The second best time is now. - Chinese Proverb",
    "Don't watch the clock; do what it does. Keep going. - Sam Levenson",
    "Everything you've ever wanted is on the other side of fear. - George Addair",
    "Hardships often prepare ordinary people for an extraordinary destiny. - C.S. Lewis"
]

def get_cached_quote_filename():
    """Get today's quote cache filename"""
    today = datetime.now()
    return f"quote_cache_{today.strftime('%Y-%m-%d')}.json"

def load_cached_quote():
    """Load today's cached quote if it exists"""
    cache_file = get_cached_quote_filename()
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                return cache_data.get('quote', ''), cache_data.get('source', '')
        except:
            pass
    return None, None

def save_quote_to_cache(quote, source):
    """Save quote to today's cache file"""
    cache_file = get_cached_quote_filename()
    cache_data = {
        'quote': quote,
        'source': source,
        'timestamp': datetime.now().isoformat()
    }
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)
    except:
        pass  # Fail silently if can't save cache

def cleanup_old_quote_caches():
    """Clean up quote cache files older than 7 days"""
    try:
        for file in os.listdir('.'):
            if file.startswith('quote_cache_') and file.endswith('.json'):
                try:
                    # Extract date from filename
                    date_str = file.replace('quote_cache_', '').replace('.json', '')
                    file_date = datetime.strptime(date_str, '%Y-%m-%d')
                    
                    # Delete if older than 7 days
                    if (datetime.now() - file_date).days > 7:
                        os.remove(file)
                except:
                    pass  # Skip problematic files
    except:
        pass  # Fail silently if cleanup fails

def get_daily_quote():
    """Get a daily quote from alternating sources with caching"""
    # Check for cached quote first
    cached_quote, cached_source = load_cached_quote()
    if cached_quote:
        return cached_quote, cached_source
    
    # Clean up old cache files
    cleanup_old_quote_caches()
    
    today = datetime.now()
    
    # Determine which source to use based on day of year
    day_of_year = today.timetuple().tm_yday
    source = day_of_year % 3  # Rotate between 3 sources
    
    quote = None
    source_name = ""
    
    if source == 0:
        # API Ninjas
        quote = get_api_ninjas_quote()
        source_name = "API Ninjas"
    elif source == 1:
        # ZenQuotes
        quote = get_zenquotes_quote()
        source_name = "ZenQuotes"
    else:
        # Local fallback
        quote = get_local_quote()
        source_name = "Local Collection"
    
    # Save to cache
    if quote:
        save_quote_to_cache(quote, source_name)
    
    return quote, source_name

def get_api_ninjas_quote():
    """Get quote from API Ninjas"""
    try:
        API_KEY = "oBX0KVLhIg/7yjR8BwTGWg==tNwMQ9FnO4JY2gHK"
        url = "https://api.api-ninjas.com/v1/quotes"
        headers = {"X-Api-Key": API_KEY}
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        quotes = response.json()
        
        if quotes and len(quotes) > 0:
            quote = quotes[0]["quote"]
            author = quotes[0]["author"]
            return f'"{quote}" — {author}'
    except Exception:
        pass
    
    # Fallback to local quote
    return get_local_quote()

def get_zenquotes_quote():
    """Get quote from ZenQuotes"""
    try:
        url = "https://zenquotes.io/api/today"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data and len(data) > 0:
            quote = data[0]["q"]
            author = data[0]["a"]
            return f'"{quote}" — {author}'
    except Exception:
        pass
    
    # Fallback to local quote
    return get_local_quote()

def get_local_quote():
    """Get quote from local collection"""
    today = datetime.now()
    quote_index = (today.year + today.month + today.day) % len(QUOTES)
    return QUOTES[quote_index]

def get_greeting():
    """Get time-appropriate greeting"""
    current_hour = datetime.now().hour
    
    if current_hour < 12:
        return "Good Morning"
    elif current_hour < 17:
        return "Good Afternoon"
    elif current_hour < 21:
        return "Good Evening"
    else:
        return "Good Night"

def load_config():
    """Load configuration settings"""
    default_config = {
        'journal_path': '/mnt/c/Users/drkei/Nextcloud/Teaching/TeachingVault/CosmicDB/CosmicDB/Primary/Personal/Dashboard Journal',
        'user_name': 'Prof. Cosmic',
        'logo_path': 'logo.png'
    }
    
    if os.path.exists('dashboard_config.json'):
        try:
            with open('dashboard_config.json', 'r') as f:
                config = json.load(f)
                return {**default_config, **config}  # Merge with defaults
        except:
            pass
    
    return default_config

def save_config(config):
    """Save configuration settings"""
    with open('dashboard_config.json', 'w') as f:
        json.dump(config, f, indent=2)

def get_today_filename():
    """Get today's journal filename"""
    today = datetime.now()
    return f"{today.strftime('%Y-%m-%d')}-journal.md"

def load_today_journal():
    """Load today's journal content"""
    config = load_config()
    journal_path = config.get('journal_path', '')
    
    if not journal_path:
        return ""
    
    filename = get_today_filename()
    full_path = os.path.join(journal_path, filename)
    
    try:
        # Convert Windows path to WSL path if needed
        if full_path.startswith('/mnt/c/'):
            wsl_path = full_path
        else:
            wsl_path = full_path.replace('C:\\', '/mnt/c/').replace('\\', '/')
        
        if os.path.exists(wsl_path):
            with open(wsl_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        st.error(f"Error loading journal: {e}")
    
    return ""

def save_journal(content):
    """Save journal content to markdown file"""
    config = load_config()
    journal_path = config.get('journal_path', '')
    
    if not journal_path:
        st.error("Please configure journal path in settings")
        return False
    
    filename = get_today_filename()
    
    try:
        # Convert Windows path to WSL path if needed
        if journal_path.startswith('/mnt/c/'):
            wsl_path = journal_path
        else:
            wsl_path = journal_path.replace('C:\\', '/mnt/c/').replace('\\', '/')
        
        # Create directory if it doesn't exist
        os.makedirs(wsl_path, exist_ok=True)
        
        full_path = os.path.join(wsl_path, filename)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return True
    except Exception as e:
        st.error(f"Error saving journal: {e}")
        return False

def save_data():
    """Save checklist and schedule data to file"""
    data = {
        'checklist': st.session_state.checklist,
        'schedule': st.session_state.schedule,
        'last_saved': datetime.now().isoformat()
    }
    with open('dashboard_data.json', 'w') as f:
        json.dump(data, f, indent=2)

def load_data():
    """Load checklist and schedule data from file"""
    if os.path.exists('dashboard_data.json'):
        try:
            with open('dashboard_data.json', 'r') as f:
                data = json.load(f)
                st.session_state.checklist = data.get('checklist', st.session_state.checklist)
                st.session_state.schedule = data.get('schedule', [])
        except:
            pass  # If file is corrupted, use defaults

def main():
    # Load saved data
    load_data()
    
    # Initialize journal session state
    if 'journal_content' not in st.session_state:
        st.session_state.journal_content = ""

    if 'journal_loaded' not in st.session_state:
        st.session_state.journal_loaded = False

    if 'config' not in st.session_state:
        st.session_state.config = load_config()
    
    # Header with dynamic greeting and logo
    user_name = st.session_state.config.get('user_name', 'Prof. Cosmic')
    greeting = get_greeting()
    
    # Create header with logo and greeting
    col_logo, col_greeting = st.columns([1, 4])
    
    with col_logo:
        # Load logo from config
        logo_path = st.session_state.config.get('logo_path', 'logo.png')
        
        try:
            if os.path.exists(logo_path):
                st.image(logo_path, width=80)
            else:
                # Fallback to tree emoji if logo file not found
                st.markdown("""
                <div style="text-align: center; padding: 10px;">
                    <div style="font-size: 60px; line-height: 1;">🌳</div>
                </div>
                """, unsafe_allow_html=True)
        except Exception as e:
            # Fallback to tree emoji if image loading fails
            st.markdown("""
            <div style="text-align: center; padding: 10px;">
                <div style="font-size: 60px; line-height: 1;">🌳</div>
            </div>
            """, unsafe_allow_html=True)
    
    with col_greeting:
        st.markdown(f"# {greeting}, {user_name}! 🌟")
        st.markdown(f"**Today is {datetime.now().strftime('%A, %B %d, %Y')}**")
    
    # Daily quote
    st.markdown("---")
    quote, source_name = get_daily_quote()
    st.markdown(f"### 💭 Quote of the Day")
    
    # Show quote and source
    col_quote, col_source = st.columns([4, 1])
    with col_quote:
        st.markdown(f"*{quote}*")
    with col_source:
        # Map source names to icons
        source_icons = {
            "API Ninjas": "🌐",
            "ZenQuotes": "🧘", 
            "Local Collection": "📚"
        }
        icon = source_icons.get(source_name, "📚")
        st.caption(f"{icon} {source_name}")
    
    st.markdown("---")
    
    # Create two main columns
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("### 📅 Today's Schedule")
        
        # Auto-connect to Google Calendar
        if not st.session_state.calendar_service.authenticated:
            with st.spinner("🔐 Connecting to Google Calendar..."):
                auth_success = st.session_state.calendar_service.authenticate()
                if auth_success:
                    st.success("✅ Connected to Google Calendar!")
                    time.sleep(1)
                    st.rerun()
        
        # Display calendar events
        if st.session_state.calendar_service.authenticated:
            # Add refresh button and calendar selector
            col_refresh, col_calendar = st.columns([1, 2])
            
            with col_refresh:
                if st.button("🔄 Refresh", help="Refresh calendar events"):
                    # Clear any cached event data and force refresh
                    if 'cached_events' in st.session_state:
                        del st.session_state['cached_events']
                    # Update refresh time
                    st.session_state['last_refresh_time'] = datetime.now()
                    st.rerun()
            
            with col_calendar:
                # Get available calendars
                calendars = st.session_state.calendar_service.get_calendar_list()
                if calendars:
                    calendar_options = [(cal['summary'], cal['id']) for cal in calendars]
                    calendar_names = [cal[0] for cal in calendar_options]
                    calendar_ids = [cal[1] for cal in calendar_options]
                    
                    # Find default selection (prefer "Personal" if it exists)
                    default_index = 0
                    for i, name in enumerate(calendar_names):
                        if name.lower() == 'personal':
                            default_index = i
                            break
                    
                    selected_calendar_name = st.selectbox(
                        "📅 Calendar:", 
                        calendar_names, 
                        index=default_index,
                        key="calendar_selector"
                    )
                    
                    # Get the calendar ID for the selected calendar
                    selected_calendar_id = calendar_ids[calendar_names.index(selected_calendar_name)]
                else:
                    selected_calendar_id = 'primary'
            
            # Get and display events from selected calendar
            events = st.session_state.calendar_service.get_today_events(selected_calendar_id)
            
            # Store refresh time for display
            if 'last_refresh_time' not in st.session_state:
                st.session_state.last_refresh_time = datetime.now()
            
            if events:
                # Filter events to only today's events with debug info
                today_events = []
                excluded_events = []
                
                for event in events:
                    if is_today_event(event):
                        today_events.append(event)
                    else:
                        excluded_events.append(event)
                
                if today_events:
                    # Show last refresh time
                    refresh_time = st.session_state.last_refresh_time.strftime("%I:%M %p")
                    st.caption(f"Last updated: {refresh_time} | Showing {len(today_events)} events for today")
                    
                    # Debug: Show excluded events if any
                    if excluded_events and len(excluded_events) > 0:
                        with st.expander(f"🔍 Debug: {len(excluded_events)} events filtered out", expanded=False):
                            for event in excluded_events:
                                event_title = event.get('summary', 'Untitled')
                                start_time = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', 'Unknown'))
                                st.text(f"- {event_title}: {start_time}")
                    
                    st.markdown("#### 🗓️ From Google Calendar:")
                    for event in today_events:
                        event_title = event.get('summary', 'Untitled Event')
                        event_time = format_event_time(event)
                        location = event.get('location', '')
                        
                        # Compact display with minimal spacing
                        st.markdown(f"""
                        <div style="background-color: #f8f9fa; padding: 8px; margin: 4px 0; border-radius: 4px; border-left: 3px solid #007bff;">
                            <div style="font-weight: bold; font-size: 14px; margin-bottom: 2px;">⏰ {event_time}</div>
                            <div style="font-size: 16px; margin-bottom: 2px;">🔸 {event_title}</div>
                            {f'<div style="font-size: 12px; color: #6c757d;">📍 {location}</div>' if location else ''}
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("No Google Calendar events for today! 🎉")
                    # Debug: Show all events if none match today
                    if excluded_events:
                        with st.expander(f"🔍 Debug: All {len(excluded_events)} events were filtered out", expanded=True):
                            for event in excluded_events:
                                event_title = event.get('summary', 'Untitled')
                                start_time = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', 'Unknown'))
                                st.text(f"- {event_title}: {start_time}")
            else:
                st.info("No Google Calendar events for today! 🎉")
            
            # Manual events section
            st.markdown("#### ➕ Additional Events")
        else:
            st.info("Connect to Google Calendar to see your schedule")
            st.markdown("#### 📅 Manual Schedule")
        
        # Add new event form (manual events)
        with st.expander("➕ Add Manual Event", expanded=False):
            event_time = st.text_input("Time (e.g., 9:00 AM, 2:30 PM)", key="event_time")
            event_title = st.text_input("Event Title", key="event_title")
            event_location = st.text_input("Location (optional)", key="event_location")
            
            if st.button("Add Event") and event_time and event_title:
                new_event = {
                    'time': event_time,
                    'title': event_title,
                    'location': event_location,
                    'id': len(st.session_state.schedule),
                    'manual': True
                }
                st.session_state.schedule.append(new_event)
                save_data()
                st.rerun()
        
        # Display manual schedule
        if st.session_state.schedule:
            st.markdown("#### 📝 Manual Events:")
            for i, event in enumerate(st.session_state.schedule):
                with st.container():
                    col_time, col_delete = st.columns([0.8, 0.2])
                    
                    with col_time:
                        st.markdown(f"**⏰ {event['time']}**")
                        st.markdown(f"📌 {event['title']}")
                        if event.get('location'):
                            st.markdown(f"📍 {event['location']}")
                    
                    with col_delete:
                        if st.button("🗑️", key=f"del_event_{i}", help="Delete event"):
                            st.session_state.schedule.pop(i)
                            save_data()
                            st.rerun()
                    
                    st.markdown("---")
        elif not st.session_state.calendar_service.authenticated:
            st.info("Add manual events above or connect to Google Calendar! 📝")
        
        # Daily Journal Section (PROPERLY PLACED WITHIN col1)
        st.markdown("---")
        st.markdown("### 📝 Daily Journal")

        # Load today's journal if not already loaded
        if not st.session_state.journal_loaded:
            st.session_state.journal_content = load_today_journal()
            st.session_state.journal_loaded = True

        # Set up periodic auto-save HERE (after loading journal)
        setup_periodic_autosave()

        # Display current journal file info and timestamp button
        col_filename, col_timestamp = st.columns([3, 1])

        with col_filename:
            today_filename = get_today_filename()
            st.markdown(f"**Today's Journal:** `{today_filename}`")

        with col_timestamp:
            if st.button("🕐 Insert Time", help="Insert current timestamp on new line"):
                current_time = datetime.now().strftime("%I:%M %p")
                timestamp_text = f"\n\n**{current_time}**\n"
                
                # Add timestamp to current content
                if st.session_state.journal_content:
                    st.session_state.journal_content += timestamp_text
                else:
                    st.session_state.journal_content = timestamp_text.strip()
                
                st.rerun()

        # Enhanced journal editor with auto-save on Ctrl+Enter
        st.markdown("""
        <style>
        .journal-container {
            position: relative;
        }
        .save-indicator {
            position: absolute;
            top: -5px;
            right: 10px;
            background: #28a745;
            color: white;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 12px;
            display: none;
            z-index: 1000;
        }
        .save-indicator.show {
            display: block;
        }
        </style>
        """, unsafe_allow_html=True)

        # Container for journal with save indicator
        st.markdown('<div class="journal-container">', unsafe_allow_html=True)

        # Save indicator (initially hidden)
        st.markdown('<div id="save-indicator" class="save-indicator">💾 Saved!</div>', unsafe_allow_html=True)

        # JavaScript for Ctrl+Enter auto-save
        save_js = """
        <script>
        function setupJournalAutoSave() {
            const textareas = document.querySelectorAll('textarea');
            let journalTextarea = null;
            
            for (let textarea of textareas) {
                if (textarea.placeholder && textarea.placeholder.includes('Write your thoughts')) {
                    journalTextarea = textarea;
                    break;
                }
            }
            
            if (journalTextarea) {
                journalTextarea.removeEventListener('keydown', handleJournalKeydown);
                journalTextarea.addEventListener('keydown', handleJournalKeydown);
            }
        }

        function handleJournalKeydown(event) {
            if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                event.preventDefault();
                saveJournal();
            }
        }

        function saveJournal() {
            const indicator = document.getElementById('save-indicator');
            if (indicator) {
                indicator.classList.add('show');
                setTimeout(() => {
                    indicator.classList.remove('show');
                }, 2000);
            }
            
            const buttons = document.querySelectorAll('button');
            for (let button of buttons) {
                if (button.textContent.includes('💾 Quick Save')) {
                    button.click();
                    break;
                }
            }
        }

        document.addEventListener('DOMContentLoaded', setupJournalAutoSave);
        const observer = new MutationObserver(setupJournalAutoSave);
        observer.observe(document.body, { childList: true, subtree: true });
        setTimeout(setupJournalAutoSave, 1000);
        </script>
        """

        # Add the JavaScript
        st.markdown(save_js, unsafe_allow_html=True)

        # Journal editor with enhanced help text
        journal_content = st.text_area(
            "Write your thoughts, notes, and reflections for today:",
            value=st.session_state.journal_content,
            height=300,
            help="💡 Press Ctrl+Enter to quickly save your journal! Use markdown formatting like **bold**, *italic*, # headers, etc. Click 'Insert Time' to add timestamps.",
            key="journal_editor"
        )

        # Update session state if content changed
        if journal_content != st.session_state.journal_content:
            st.session_state.journal_content = journal_content

        # Quick save button triggered by JavaScript
        col_quick_save, col_preview = st.columns([1, 1])

        with col_quick_save:
            if st.button("💾 Quick Save", help="Save journal (or press Ctrl+Enter in the editor)", key="journal_quick_save"):
                if st.session_state.journal_content.strip():
                    journal_saved = save_journal(st.session_state.journal_content)
                    if journal_saved:
                        st.success("📝 Journal saved successfully!")
                    else:
                        st.error("❌ Journal save failed!")
                else:
                    st.info("📝 Journal is empty - nothing to save.")

        with col_preview:
            # Journal preview
            if journal_content.strip():
                with st.expander("📖 Preview", expanded=False):
                    st.markdown(journal_content)

        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown("### ✅ Daily Checklist")
        
        # Editable checklist by category
        for category, items in st.session_state.checklist.items():
            completed_count = sum(1 for item in items if item['done'])
            total_count = len(items)
            
            with st.expander(f"{category} ({completed_count}/{total_count} completed)", expanded=True):
                for i, item in enumerate(items):
                    col_check, col_task, col_delete = st.columns([0.1, 0.7, 0.2])
                    
                    with col_check:
                        new_status = st.checkbox(
                            f"Complete {item['task']}", 
                            value=item['done'], 
                            key=f"{category}_{i}_check",
                            label_visibility="collapsed"
                        )
                        if new_status != item['done']:
                            st.session_state.checklist[category][i]['done'] = new_status
                            save_data()
                    
                    with col_task:
                        if item['done']:
                            st.markdown(f"~~{item['task']}~~")
                        else:
                            st.markdown(item['task'])
                    
                    with col_delete:
                        if st.button("🗑️", key=f"{category}_{i}_delete", help="Delete item"):
                            st.session_state.checklist[category].pop(i)
                            save_data()
                            st.rerun()
                
                # Add new item
                new_item_key = f"{category}_new"
                new_item = st.text_input(f"Add new {category.lower()} item:", key=new_item_key)
                if st.button(f"Add to {category}", key=f"{category}_add") and new_item:
                    st.session_state.checklist[category].append({'task': new_item, 'done': False})
                    save_data()
                    st.rerun()
    
    # Progress summary
    st.markdown("---")
    st.markdown("### 📊 Daily Progress")
    
    progress_cols = st.columns(len(st.session_state.checklist))
    
    for i, (category, items) in enumerate(st.session_state.checklist.items()):
        completed = sum(1 for item in items if item['done'])
        total = len(items)
        progress = completed / total if total > 0 else 0
        
        with progress_cols[i]:
            st.markdown(f"**{category}**")
            st.progress(progress)
            st.markdown(f"{completed}/{total} completed")
    
    # Data management
    st.markdown("---")
    col_save, col_reset, col_calendar, col_settings = st.columns([1, 1, 1, 1])
    
    with col_save:
        if st.button("💾 Save All Data"):
            save_data()
            # Save journal content
            if st.session_state.journal_content.strip():
                journal_saved = save_journal(st.session_state.journal_content)
                if journal_saved:
                    st.success("Data and journal saved successfully!")
                else:
                    st.warning("Data saved, but journal save failed!")
            else:
                st.success("Data saved successfully!")
    
    with col_reset:
        if st.button("🔄 Reset Today's Progress"):
            for category in st.session_state.checklist:
                for item in st.session_state.checklist[category]:
                    item['done'] = False
            st.session_state.schedule = []
            save_data()
            st.success("Progress reset for new day!")
    
    with col_calendar:
        if st.button("🔐 Reconnect Calendar"):
            # Clear existing authentication
            if os.path.exists('token.pickle'):
                os.remove('token.pickle')
            st.session_state.calendar_service = GoogleCalendarService()
            st.info("Calendar disconnected. Refresh page to reconnect.")
    
    with col_settings:
        if st.button("⚙️ Settings"):
            st.session_state.show_settings = not st.session_state.get('show_settings', False)
    
    # Settings panel
    if st.session_state.get('show_settings', False):
        st.markdown("---")
        st.markdown("### ⚙️ Settings")
        
        # Personal settings
        st.markdown("#### 👤 Personal Settings")
        current_name = st.session_state.config.get('user_name', 'Prof. Cosmic')
        new_name = st.text_input(
            "Display Name:",
            value=current_name,
            help="This name will appear in the greeting (e.g., 'Good Morning, [Name]')"
        )
        
        current_logo = st.session_state.config.get('logo_path', 'logo.png')
        new_logo = st.text_input(
            "Logo Path:",
            value=current_logo,
            help="Path to your logo image file (e.g., logo.png, images/my-logo.jpg)"
        )
        
        # Logo preview
        if new_logo and os.path.exists(new_logo):
            st.markdown("**Logo Preview:**")
            try:
                st.image(new_logo, width=60)
            except:
                st.error("Unable to display logo preview")
        elif new_logo:
            st.warning("Logo file not found at specified path")
        
        # Journal path configuration
        st.markdown("#### 📝 Journal Configuration")
        
        current_path = st.session_state.config.get('journal_path', '')
        
        # Show current path
        if current_path:
            st.markdown(f"**Current path:** `{current_path}`")
        
        # Path input
        new_path = st.text_input(
            "Journal save path:",
            value=current_path,
            help="Windows path (e.g., C:\\Users\\username\\Documents\\Journal) will be converted to WSL path automatically"
        )
        
        col_save_config, col_test_path = st.columns([1, 1])
        
        with col_save_config:
            if st.button("💾 Save Settings"):
                settings_updated = False
                if new_name and new_name != current_name:
                    st.session_state.config['user_name'] = new_name
                    settings_updated = True
                if new_logo and new_logo != current_logo:
                    st.session_state.config['logo_path'] = new_logo
                    settings_updated = True
                if new_path and new_path != current_path:
                    st.session_state.config['journal_path'] = new_path
                    settings_updated = True
                
                if settings_updated:
                    save_config(st.session_state.config)
                    st.success("Settings saved!")
                    st.rerun()
                else:
                    st.info("No changes to save.")
        
        with col_test_path:
            if st.button("🧪 Test Path") and new_path:
                try:
                    # Convert to WSL path for testing
                    test_path = new_path.replace('C:\\', '/mnt/c/').replace('\\', '/') if not new_path.startswith('/mnt/c/') else new_path
                    
                    if os.path.exists(test_path) or os.access(os.path.dirname(test_path), os.W_OK):
                        st.success("✅ Path is accessible!")
                    else:
                        st.error("❌ Path not accessible!")
                except Exception as e:
                    st.error(f"❌ Path test failed: {e}")
        
        # Journal files list
        if current_path:
            st.markdown("#### 📁 Recent Journal Files")
            try:
                wsl_path = current_path.replace('C:\\', '/mnt/c/').replace('\\', '/') if not current_path.startswith('/mnt/c/') else current_path
                if os.path.exists(wsl_path):
                    files = [f for f in os.listdir(wsl_path) if f.endswith('-journal.md')]
                    files.sort(reverse=True)  # Most recent first
                    
                    if files:
                        for file in files[:5]:  # Show last 5 files
                            st.markdown(f"- `{file}`")
                    else:
                        st.info("No journal files found yet.")
                else:
                    st.warning("Journal directory doesn't exist yet.")
            except Exception as e:
                st.error(f"Error reading journal directory: {e}")


# Add these helper functions OUTSIDE the main() function:

def save_journal_enhanced(content):
    """Enhanced save journal function with better error handling and feedback"""
    config = load_config()
    journal_path = config.get('journal_path', '')
    
    if not journal_path:
        return False, "Please configure journal path in settings"
    
    filename = get_today_filename()
    
    try:
        # Convert Windows path to WSL path if needed
        if journal_path.startswith('/mnt/c/'):
            wsl_path = journal_path
        else:
            wsl_path = journal_path.replace('C:\\', '/mnt/c/').replace('\\', '/')
        
        # Create directory if it doesn't exist
        os.makedirs(wsl_path, exist_ok=True)
        
        full_path = os.path.join(wsl_path, filename)
        
        # Create backup of existing file if it exists
        if os.path.exists(full_path):
            backup_path = full_path + '.bak'
            import shutil
            shutil.copy2(full_path, backup_path)
        
        # Write the new content
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Verify the file was written correctly
        with open(full_path, 'r', encoding='utf-8') as f:
            saved_content = f.read()
            if saved_content == content:
                return True, f"Journal saved to {filename}"
            else:
                return False, "File verification failed after save"
        
    except Exception as e:
        return False, f"Error saving journal: {e}"

def setup_periodic_autosave():
    """Set up periodic auto-save for journal content"""
    if 'last_autosave' not in st.session_state:
        st.session_state.last_autosave = datetime.now()
    
    # Auto-save every 2 minutes if content has changed
    current_time = datetime.now()
    time_since_last_save = (current_time - st.session_state.last_autosave).total_seconds()
    
    if time_since_last_save > 120:  # 2 minutes
        if st.session_state.journal_content.strip():
            success, message = save_journal_enhanced(st.session_state.journal_content)
            if success:
                st.session_state.last_autosave = current_time
                # Show subtle notification
                st.sidebar.success("📝 Auto-saved journal")

if __name__ == "__main__":
    main()
