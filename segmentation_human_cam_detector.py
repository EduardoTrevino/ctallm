import cv2
import mediapipe as mp
import numpy as np
import datetime
import time

# Initialize MediaPipe Selfie Segmentation
mp_selfie_segmentation = mp.solutions.selfie_segmentation
segmentor = mp_selfie_segmentation.SelfieSegmentation(model_selection=1)  # 1 for landscape mode, better for webcam

# Function to detect if a human is present using segmentation
def detect_human(frame):
    # Process the frame with MediaPipe
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = segmentor.process(rgb_frame)
    
    if results.segmentation_mask is None:
        return False
    
    # Get the segmentation mask (probability map)
    mask = results.segmentation_mask
    
    # Threshold the mask to binary (human foreground if > 0.5)
    binary_mask = (mask > 0.5).astype(np.uint8)
    
    # Calculate the proportion of human pixels
    human_pixels = np.sum(binary_mask)
    total_pixels = binary_mask.size
    proportion = human_pixels / total_pixels
    
    # Return True if human proportion is above a threshold (e.g., 5% of frame)
    return proportion > 0.05  # Adjust based on your setup; lower for sensitivity

# Main function to handle webcam capture and logging
def main():
    # Open the webcam (0 for default camera)
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return
    
    # Initial state: no human present
    human_present = False
    
    # Debounce counters to prevent flickering
    presence_threshold = 3   # Frames to confirm presence
    absence_threshold = 100   # Frames to confirm absence
    presence_counter = 0
    absence_counter = 0
    
    print("Starting webcam human detection (using MediaPipe Selfie Segmentation). Press 'q' to quit.")
    
    while True:
        # Capture frame-by-frame
        ret, frame = cap.read()
        
        if not ret:
            print("Error: Failed to capture frame.")
            break
        
        # Detect human in the current frame
        is_human_detected = detect_human(frame)
        
        # Update counters
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
        
        # Log if state changes
        if state_changed:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            status = "present" if human_present else "not present"
            print(f"{current_time}: Human is {status}")
        
        # For visualization: Apply green tint to human segmentation
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = segmentor.process(rgb_frame)
        if results.segmentation_mask is not None:
            mask = (results.segmentation_mask > 0.5)[:, :, np.newaxis].astype(np.uint8)
            green_bg = np.zeros_like(frame) + [0, 255, 0]  # Green overlay
            segmented = frame * (1 - mask) + green_bg * mask
            segmented = segmented.astype(np.uint8)  # Ensure uint8 for cv2.imshow
            cv2.imshow('Webcam - Human Detection', segmented)
        else:
            cv2.imshow('Webcam - Human Detection', frame)
        
        # Break if 'q' pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        
        time.sleep(0.03)  # ~30 fps
    
    cap.release()
    cv2.destroyAllWindows()
    print("Webcam closed.")

if __name__ == "__main__":
    main()