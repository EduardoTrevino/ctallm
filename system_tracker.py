import json
import os
import time
import datetime
import threading
import pygetwindow as gw
import pyautogui
import pynput
import psutil
import pyperclip
import cv2
import numpy as np
from PIL import Image

# Directories and files
LOG_FILE = 'session_log.jsonl'
SCREENSHOT_DIR = 'screenshots'
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# Global variables for tracking
current_window = None
window_start_time = None
last_clipboard = pyperclip.paste()

# Function to log to JSONL
def log_entry(entry):
    with open(LOG_FILE, 'a') as f:
        f.write(json.dumps(entry) + '\n')

# Function to get current timestamp
def get_timestamp():
    return datetime.datetime.now().isoformat()

# Function to get window details
def get_window_details(window):
    if window is None:
        return None
    try:
        pid = gw.getWindowThreadProcessId(window._hWnd)[1]  # For Windows
        process = psutil.Process(pid)
        process_name = process.name()
        bounds = (window.left, window.top, window.width, window.height)
        # App metadata: For browsers, try to extract URL from title (simple)
        metadata = {}
        if 'chrome' in process_name.lower() or 'firefox' in process_name.lower():
            # Simple: Assume title has URL, but for better, could use uiautomation
            metadata['url'] = window.title.split(' - ')[0] if ' - ' in window.title else None
        elif 'notepad' in process_name.lower() or 'code' in process_name.lower():
            metadata['file_path'] = window.title.split(' - ')[0] if ' - ' in window.title else None
        return {
            'title': window.title,
            'process_name': process_name,
            'pid': pid,
            'bounds': bounds,
            'metadata': metadata
        }
    except Exception as e:
        return {'error': str(e)}

# Function to take screenshot with optional highlight
def take_screenshot(highlight_pos=None):
    try:
        screenshot = pyautogui.screenshot()
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        if highlight_pos:
            x, y = highlight_pos
            cv2.circle(img, (x, y), 20, (0, 0, 255), 2)  # Red circle for click
        ts = get_timestamp().replace(':', '-')
        path = os.path.join(SCREENSHOT_DIR, f'screenshot_{ts}.png')
        cv2.imwrite(path, img)
        return path
    except Exception as e:
        return str(e)

# Mouse listener callbacks
def on_click(x, y, button, pressed):
    if pressed:
        ts = get_timestamp()
        window_details = get_window_details(gw.getActiveWindow())
        screenshot_path = take_screenshot((x, y))
        entry = {
            'timestamp': ts,
            'type': 'mouse_click',
            'details': {
                'button': str(button),
                'position': (x, y),
                'window': window_details,
                'screenshot': screenshot_path
            }
        }
        log_entry(entry)

def on_scroll(x, y, dx, dy):
    ts = get_timestamp()
    entry = {
        'timestamp': ts,
        'type': 'mouse_scroll',
        'details': {
            'position': (x, y),
            'delta': (dx, dy),
            'window': get_window_details(gw.getActiveWindow())
        }
    }
    log_entry(entry)

def on_move(x, y):
    # Log hovers periodically to avoid flood; here, skip or implement timer
    pass  # For now, not logging every move; can add if needed

# Keyboard listener
def on_press(key):
    ts = get_timestamp()
    entry = {
        'timestamp': ts,
        'type': 'key_press',
        'details': {
            'key': str(key),
            'window': get_window_details(gw.getActiveWindow())
        }
    }
    log_entry(entry)

# Periodic tasks: Window tracking, clipboard, network (simple)
def periodic_tracker():
    global current_window, window_start_time, last_clipboard
    while True:
        active_window = gw.getActiveWindow()
        ts = get_timestamp()
        
        # Window change
        if active_window != current_window:
            if current_window and window_start_time:
                duration = (datetime.datetime.now() - window_start_time).total_seconds()
                entry = {
                    'timestamp': ts,
                    'type': 'window_time_spent',
                    'details': {
                        'window': get_window_details(current_window),
                        'duration_seconds': duration,
                        'start_time': window_start_time.isoformat(),
                        'end_time': ts
                    }
                }
                log_entry(entry)
            
            # Log new window open/focus
            screenshot_path = take_screenshot()
            entry = {
                'timestamp': ts,
                'type': 'window_change',
                'details': {
                    'window': get_window_details(active_window),
                    'action': 'focus' if current_window else 'open',
                    'screenshot': screenshot_path
                }
            }
            log_entry(entry)
            
            current_window = active_window
            window_start_time = datetime.datetime.now()
        
        # Clipboard change
        current_clipboard = pyperclip.paste()
        if current_clipboard != last_clipboard:
            entry = {
                'timestamp': ts,
                'type': 'clipboard_change',
                'details': {
                    'new_content': current_clipboard  # Note: May contain sensitive data
                }
            }
            log_entry(entry)
            last_clipboard = current_clipboard
        
        # Network activity: Simple, check if browser and log title as proxy for URL
        window_details = get_window_details(active_window)
        if window_details and 'metadata' in window_details and 'url' in window_details['metadata']:
            entry = {
                'timestamp': ts,
                'type': 'network_activity',
                'details': {
                    'url': window_details['metadata']['url'],
                    'window': window_details
                }
            }
            log_entry(entry)
        
        time.sleep(1)  # Check every second

# Main function
def main():
    print("Starting monitoring. Press Ctrl+C to stop.")
    
    # Start listeners
    mouse_listener = pynput.mouse.Listener(on_click=on_click, on_scroll=on_scroll, on_move=on_move)
    keyboard_listener = pynput.keyboard.Listener(on_press=on_press)
    mouse_listener.start()
    keyboard_listener.start()
    
    # Start periodic tracker
    tracker_thread = threading.Thread(target=periodic_tracker)
    tracker_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping monitoring.")
        mouse_listener.stop()
        keyboard_listener.stop()
        # Log final window time
        if current_window and window_start_time:
            ts = get_timestamp()
            duration = (datetime.datetime.now() - window_start_time).total_seconds()
            entry = {
                'timestamp': ts,
                'type': 'window_time_spent',
                'details': {
                    'window': get_window_details(current_window),
                    'duration_seconds': duration,
                    'start_time': window_start_time.isoformat(),
                    'end_time': ts
                }
            }
            log_entry(entry)

if __name__ == "__main__":
    main()