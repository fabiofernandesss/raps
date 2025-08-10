import cv2
import mediapipe as mp
import os
from datetime import datetime
import time

mp_face_detection = mp.solutions.face_detection
mp_drawing = mp.solutions.drawing_utils

def detect_faces():
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
    
    if not os.path.exists('faces'):
        os.makedirs('faces')
    
    last_save = 0
    save_interval = 0.5
    
    with mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.7) as face_detection:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
            
            small_frame = cv2.resize(frame, (960, 540))
            rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            results = face_detection.process(rgb_frame)
            
            current_time = time.time()
            
            if results.detections:
                for detection in results.detections:
                    bbox = detection.location_data.relative_bounding_box
                    h, w = 540, 960
                    x = int(bbox.xmin * w)
                    y = int(bbox.ymin * h)
                    width = int(bbox.width * w)
                    height = int(bbox.height * h)
                    
                    x_full = int(x * 2)
                    y_full = int(y * 2)
                    width_full = int(width * 2)
                    height_full = int(height * 2)
                    
                    cv2.rectangle(frame, (x_full, y_full), (x_full + width_full, y_full + height_full), (0, 255, 0), 2)
                    
                    if current_time - last_save > save_interval:
                        face = frame[y_full:y_full+height_full, x_full:x_full+width_full]
                        if face.size > 0:
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
                            cv2.imwrite(f'faces/face_{timestamp}.jpg', face)
                            last_save = current_time
            
            cv2.imshow('Face Detection', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    detect_faces()