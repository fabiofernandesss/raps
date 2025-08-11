import cv2
import mediapipe as mp
import os
from datetime import datetime
import time

mp_face_detection = mp.solutions.face_detection
mp_drawing = mp.solutions.drawing_utils

def detect_faces():
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    
    # Verificar se a câmera foi aberta corretamente
    if not cap.isOpened():
        print("ERRO: Não foi possível abrir a câmera!")
        return
    
    print("Câmera aberta com sucesso!")
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 520)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 520)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
    
    # Verificar as configurações da câmera
    actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Configurações da câmera: {actual_width}x{actual_height} @ {actual_fps}fps")
    
    if not os.path.exists('faces'):
        os.makedirs('faces')
    
    last_save_time = 0
    save_interval = 0.5
    
    with mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.8) as face_detection:
        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                print("ERRO: Não foi possível capturar frame da câmera!")
                continue
            
            frame_count += 1
            if frame_count % 30 == 0:  # Log a cada 30 frames
                print(f"Frame {frame_count} capturado - Tamanho: {frame.shape}")
            
            # Processar diretamente no frame original (520x520)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_detection.process(rgb_frame)
            
            current_time = time.time()
            
            if results.detections:
                for detection in results.detections:
                    # Verificar se a confiança da detecção é alta o suficiente
                    confidence = detection.score[0]
                    if confidence < 0.85:
                        continue
                    
                    bbox = detection.location_data.relative_bounding_box
                    h, w = frame.shape[:2]
                    x = int(bbox.xmin * w)
                    y = int(bbox.ymin * h)
                    width = int(bbox.width * w)
                    height = int(bbox.height * h)
                    
                    # Validar tamanho mínimo e máximo do rosto
                    if width < 20 or height < 20 or width > 300 or height > 300:
                        continue
                    
                    # Validar proporção do rosto (deve ser aproximadamente quadrado)
                    aspect_ratio = width / height
                    if aspect_ratio < 0.6 or aspect_ratio > 1.4:
                        continue
                    
                    # Garantir que as coordenadas estão dentro dos limites da imagem
                    x = max(0, x)
                    y = max(0, y)
                    x_end = min(w, x + width)
                    y_end = min(h, y + height)
                    
                    cv2.rectangle(frame, (x, y), (x_end, y_end), (0, 255, 0), 2)
                    cv2.putText(frame, f"Face: {confidence:.2f}", (x, y-10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                    
                    if current_time - last_save_time >= save_interval:
                        face_roi = frame[y:y_end, x:x_end]
                        if face_roi.size > 0 and face_roi.shape[0] > 30 and face_roi.shape[1] > 30:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                            filename = f"faces/face_{timestamp}_conf{confidence:.2f}.jpg"
                            cv2.imwrite(filename, face_roi)
                            print(f"Face salva: {filename} (confiança: {confidence:.2f})")
                            last_save_time = current_time
            
            cv2.imshow('Face Detection', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    detect_faces()