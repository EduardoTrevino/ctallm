import cv2
import datetime
import time

# Global cascade classifiers (loaded once)
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
profile_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_profileface.xml')
upperbody_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_upperbody.xml')

# Function to detect if a human is present using multiple cascades
def detect_human(frame):
    # Convert frame to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Detect frontal faces
    frontal_faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    
    # Detect profile faces
    profile_faces = profile_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    
    # Flip the image horizontally and detect profile on the other side
    flipped_gray = cv2.flip(gray, 1)
    profile_faces_flipped = profile_cascade.detectMultiScale(flipped_gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    
    # Detect upper body as fallback
    upper_bodies = upperbody_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(60, 60))
    
    # Return True if any detection is found
    return (len(frontal_faces) > 0 or 
            len(profile_faces) > 0 or 
            len(profile_faces_flipped) > 0 or 
            len(upper_bodies) > 0)

# Main function to handle webcam capture and logging
def main():
    # Open the webcam (0 for default camera)
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return
    
    # Initial state: no human present
    human_present = False
    
    # Debounce counters to prevent flickering (require consistent detections)
    presence_threshold = 3  # Frames to confirm presence
    absence_threshold = 5   # Frames to confirm absence (higher to avoid false negatives)
    presence_counter = 0
    absence_counter = 0
    
    print("Starting webcam human detection (multi-cascade for robustness). Press 'q' to quit.")
    
    while True:
        # Capture frame-by-frame
        ret, frame = cap.read()
        
        if not ret:
            print("Error: Failed to capture frame.")
            break
        
        # Detect human in the current frame
        is_human_detected = detect_human(frame)
        
        # Update counters based on detection
        if is_human_detected:
            presence_counter += 1
            absence_counter = 0
        else:
            absence_counter += 1
            presence_counter = 0
        
        # Check if state should change
        state_changed = False
        if presence_counter >= presence_threshold and not human_present:
            human_present = True
            state_changed = True
        elif absence_counter >= absence_threshold and human_present:
            human_present = False
            state_changed = True
        
        # If presence state changes, log the time
        if state_changed:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Accurate to milliseconds
            status = "present" if human_present else "not present"
            print(f"{current_time}: Human is {status}")
        
        # For visualization: Draw bounding boxes for all detections
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        flipped_gray = cv2.flip(gray, 1)
        
        # Frontal faces (blue)
        frontal_faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        for (x, y, w, h) in frontal_faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
        
        # Profile faces (green)
        profile_faces = profile_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        for (x, y, w, h) in profile_faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        
        # Profile faces on flipped (adjust coordinates, green)
        profile_faces_flipped = profile_cascade.detectMultiScale(flipped_gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        for (x, y, w, h) in profile_faces_flipped:
            # Adjust x-coordinate for flip
            adj_x = frame.shape[1] - (x + w)
            cv2.rectangle(frame, (adj_x, y), (adj_x + w, y + h), (0, 255, 0), 2)
        
        # Upper bodies (red)
        upper_bodies = upperbody_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(60, 60))
        for (x, y, w, h) in upper_bodies:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
        
        # Display the resulting frame
        cv2.imshow('Webcam - Human Detection', frame)
        
        # Break the loop if 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        
        # Small delay to control frame rate
        time.sleep(0.03)  # ~30 fps
    
    # Release the capture and close windows
    cap.release()
    cv2.destroyAllWindows()
    print("Webcam closed.")

if __name__ == "__main__":
    main()