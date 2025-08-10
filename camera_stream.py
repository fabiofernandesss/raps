#!/usr/bin/env python3
"""
Stream de câmera ao vivo via web com detecção facial integrada
Disponibiliza o feed da câmera em tempo real e captura faces automaticamente
"""

import cv2
import time
import threading
from flask import Flask, Response, render_template_string
import os
import platform
import sqlite3
import base64
from datetime import datetime
import shutil
import tempfile
import requests
from typing import List, Tuple

app = Flask(__name__)

# Variáveis globais
camera = None
frame_lock = threading.Lock()
latest_frame = None
is_streaming = False
face_detector = None
detection_enabled = True

# Configurações do banco de dados e Supabase
DB_PATH = os.path.join(os.path.dirname(__file__), "faces.db")
SUPABASE_URL = os.environ.get("SUPABASE_URL") or ""
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY") or ""
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "captures")
DEVICE_ID = os.environ.get("DEVICE_ID") or os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "raspi-01"

# Controle de detecção facial
last_saved_ts = 0.0
cooldown_seconds = 3.0
last_sync_ts = 0.0
sync_interval = 5.0

# Funções do banco de dados e detecção facial
def init_db(db_path: str = DB_PATH):
    """Inicializa o banco de dados SQLite"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS captures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            image_base64 TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

def save_capture(image_b64: str, db_path: str = DB_PATH):
    """Salva uma captura no banco de dados local"""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO captures(date, time, image_base64) VALUES (?, ?, ?)",
        (date_str, time_str, image_b64),
    )
    conn.commit()
    conn.close()

def get_biggest_face(faces):
    """Retorna a maior face detectada"""
    if len(faces) == 0:
        return None
    areas = [w * h for (x, y, w, h) in faces]
    max_idx = areas.index(max(areas))
    return faces[max_idx]

def crop_with_margin(img, rect, margin_ratio: float = 0.1):
    """Recorta a face com margem"""
    x, y, w, h = rect
    margin_w = int(w * margin_ratio)
    margin_h = int(h * margin_ratio)
    x1 = max(0, x - margin_w)
    y1 = max(0, y - margin_h)
    x2 = min(img.shape[1], x + w + margin_w)
    y2 = min(img.shape[0], y + h + margin_h)
    return img[y1:y2, x1:x2]

def encode_image_to_base64(img_bgr, target_size=(160, 160), quality: int = 80) -> str:
    """Codifica imagem para base64"""
    img_resized = cv2.resize(img_bgr, target_size)
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    _, buffer = cv2.imencode('.jpg', img_resized, encode_param)
    img_b64 = base64.b64encode(buffer).decode('utf-8')
    return img_b64

def _fetch_pending(limit: int = 20) -> List[Tuple[int, str, str, str]]:
    """Busca registros pendentes no banco local"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, date, time, image_base64 FROM captures LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def _delete_local(ids: List[int]):
    """Remove registros do banco local"""
    if not ids:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    placeholders = ','.join(['?'] * len(ids))
    cur.execute(f"DELETE FROM captures WHERE id IN ({placeholders})", ids)
    conn.commit()
    conn.close()

def sync_supabase(max_batch: int = 20):
    """Sincroniza dados locais com Supabase"""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return
    
    try:
        pending = _fetch_pending(max_batch)
        if not pending:
            return
        
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        
        # Tenta envio em lote
        batch_data = []
        for row_id, date, time, image_base64 in pending:
            batch_data.append({
                "date": date,
                "time": time,
                "device_id": DEVICE_ID,
                "image_base64": image_base64
            })
        
        url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
        response = requests.post(url, json=batch_data, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            # Sucesso no lote: remove todos
            ids_to_delete = [row[0] for row in pending]
            _delete_local(ids_to_delete)
            print(f"✅ Sincronizados {len(pending)} registros em lote")
        else:
            # Falha no lote: tenta individual
            print(f"⚠️ Falha no lote ({response.status_code}), tentando individual...")
            success_ids = []
            for row_id, date, time, image_base64 in pending:
                single_data = {
                    "date": date,
                    "time": time,
                    "device_id": DEVICE_ID,
                    "image_base64": image_base64
                }
                single_response = requests.post(url, json=single_data, headers=headers, timeout=5)
                if single_response.status_code in [200, 201]:
                    success_ids.append(row_id)
            
            if success_ids:
                _delete_local(success_ids)
                print(f"✅ Sincronizados {len(success_ids)}/{len(pending)} registros individualmente")
    
    except Exception as e:
        print(f"❌ Erro na sincronização: {e}")

def init_face_detector():
    """Inicializa o detector de faces"""
    global face_detector
    try:
        cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        face_detector = cv2.CascadeClassifier(cascade_path)
        
        if face_detector.empty():
            # Fallback para caminhos com acentos
            tmp_dir = tempfile.gettempdir()
            tmp_cascade = os.path.join(tmp_dir, "haarcascade_frontalface_default.xml")
            if not os.path.exists(tmp_cascade):
                shutil.copyfile(cascade_path, tmp_cascade)
            face_detector = cv2.CascadeClassifier(tmp_cascade)
        
        if face_detector.empty():
            print("❌ Erro: não foi possível carregar o classificador Haar Cascade")
            return False
        
        print("✅ Detector de faces carregado com sucesso")
        return True
    except Exception as e:
        print(f"❌ Erro ao carregar detector de faces: {e}")
        return False

def test_resolution(cap, width, height, fps=30):
    """Testa se uma resolução específica funciona na câmera"""
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        time.sleep(0.2)  # Aguarda estabilização
        
        # Testa captura de frame
        ret, frame = cap.read()
        if ret and frame is not None:
            actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = int(cap.get(cv2.CAP_PROP_FPS))
            
            # Verifica se a resolução foi aplicada (com tolerância)
            if actual_width >= width * 0.8 and actual_height >= height * 0.8:
                return True, actual_width, actual_height, actual_fps
        
        return False, 0, 0, 0
    except Exception as e:
        print(f"   ❌ Erro ao testar resolução {width}x{height}: {e}")
        return False, 0, 0, 0

def try_open_camera(target_width=640, target_height=480, fps=30):
    """Tenta abrir a câmera com a melhor resolução possível"""
    print("🎥 Abrindo câmera para streaming...")
    
    # Usa a mesma abordagem que funciona no test_camera_usb.py
    indices = [0, 1, 2]
    apis = [("ANY", cv2.CAP_ANY), ("V4L2", cv2.CAP_V4L2), ("DEFAULT", None)]
    
    print("Tentando abrir câmera com diferentes APIs...")
    for idx in indices:
        for api_name, api_code in apis:
            print(f"Tentando índice {idx} com API {api_name}...")
            
            try:
                if api_code is not None:
                    cap = cv2.VideoCapture(idx, api_code)
                else:
                    cap = cv2.VideoCapture(idx)
                
                if not cap.isOpened():
                    cap.release()
                    continue
                
                # Testa captura simples primeiro (como no diagnóstico)
                ret, test_frame = cap.read()
                if ret and test_frame is not None:
                    print(f"✅ Câmera funcionando no índice {idx} com API {api_name}")
                    print(f"   Resolução detectada: {test_frame.shape[1]}x{test_frame.shape[0]}")
                    
                    # Configura resolução básica (160x120 que sabemos que funciona)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 160)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 120)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    
                    # Testa novamente após configuração
                    ret2, test_frame2 = cap.read()
                    if ret2 and test_frame2 is not None:
                        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        print(f"   ✅ Configuração aplicada: {actual_w}x{actual_h}")
                        return cap, actual_w, actual_h
                
                cap.release()
                
            except Exception as e:
                print(f"   ❌ Erro com índice {idx} API {api_name}: {e}")
                if 'cap' in locals():
                    cap.release()
    
    print("❌ Erro: não foi possível acessar a webcam")
    print("💡 Dicas:")
    print("   - Verifique se a câmera está conectada")
    print("   - Tente desconectar e reconectar a câmera USB")
    print("   - Execute: python test_camera_usb.py para diagnóstico")
    return None, 0, 0

def capture_frames():
    """Thread para capturar frames continuamente com detecção facial"""
    global camera, latest_frame, is_streaming, face_detector
    global last_saved_ts, last_sync_ts
    
    while is_streaming:
        if camera is None:
            time.sleep(1)
            continue
        
        ret, frame = camera.read()
        if ret and frame is not None:
            # Cria uma cópia para processamento
            display_frame = frame.copy()
            
            # Detecção facial se o detector estiver carregado
            if face_detector is not None and detection_enabled:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_detector.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=(30, 30)
                )
                
                # Desenha retângulos nas faces detectadas
                for (x, y, w, h) in faces:
                    cv2.rectangle(display_frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                
                # Salva captura se faces foram detectadas e passou o cooldown
                current_time = time.time()
                if len(faces) > 0 and (current_time - last_saved_ts) >= cooldown_seconds:
                    try:
                        biggest_face = get_biggest_face(faces)
                        if biggest_face is not None:
                            face_crop = crop_with_margin(frame, biggest_face)
                            image_b64 = encode_image_to_base64(face_crop)
                            save_capture(image_b64)
                            last_saved_ts = current_time
                            print(f"💾 Face capturada e salva ({len(faces)} faces detectadas)")
                    except Exception as e:
                        print(f"❌ Erro ao salvar captura: {e}")
                
                # Sincronização periódica com Supabase
                if (current_time - last_sync_ts) >= sync_interval:
                    try:
                        sync_supabase()
                        last_sync_ts = current_time
                    except Exception as e:
                        print(f"❌ Erro na sincronização: {e}")
            
            with frame_lock:
                latest_frame = display_frame.copy()
        else:
            print("⚠️ Falha na leitura da câmera")
            time.sleep(0.1)
        
        time.sleep(0.033)  # ~30 FPS

def generate_frames():
    """Gera frames para o stream MJPEG"""
    global latest_frame
    
    while True:
        with frame_lock:
            if latest_frame is not None:
                frame = latest_frame.copy()
            else:
                # Frame preto se não há imagem
                frame = cv2.imread('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==', cv2.IMREAD_COLOR)
                if frame is None:
                    frame = cv2.zeros((480, 640, 3), dtype=cv2.uint8)
                    cv2.putText(frame, 'Camera not available', (50, 240), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Adiciona timestamp
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        cv2.putText(frame, timestamp, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Codifica frame como JPEG
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ret:
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        time.sleep(0.033)  # ~30 FPS

@app.route('/')
def index():
    """Página principal com o player de vídeo"""
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>📹 Stream da Câmera - Raspberry Pi</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-align: center;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 30px;
                backdrop-filter: blur(10px);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            }
            h1 {
                margin-bottom: 30px;
                font-size: 2.5em;
                text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
            }
            .video-container {
                position: relative;
                display: inline-block;
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
                margin-bottom: 20px;
            }
            #videoStream {
                max-width: 100%;
                height: auto;
                display: block;
            }
            .info {
                background: rgba(255, 255, 255, 0.2);
                border-radius: 10px;
                padding: 20px;
                margin-top: 20px;
                text-align: left;
            }
            .status {
                display: inline-block;
                padding: 5px 15px;
                background: #4CAF50;
                border-radius: 20px;
                font-weight: bold;
                margin-bottom: 15px;
            }
            .controls {
                margin-top: 20px;
            }
            button {
                background: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 16px;
                margin: 5px;
                transition: background 0.3s;
            }
            button:hover {
                background: #45a049;
            }
            .url-info {
                background: rgba(0, 0, 0, 0.3);
                padding: 15px;
                border-radius: 8px;
                margin-top: 15px;
                font-family: monospace;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📹 Stream da Câmera ao Vivo</h1>
            
            <div class="status">🟢 Online</div>
            
            <div class="video-container">
                <img id="videoStream" src="{{ url_for('video_feed') }}" alt="Stream da Câmera">
            </div>
            
            <div class="controls">
                <button onclick="location.reload()">🔄 Recarregar</button>
                <button onclick="toggleFullscreen()">🔍 Tela Cheia</button>
            </div>
            
            <div class="info">
                <h3>ℹ️ Informações do Stream</h3>
                <p><strong>📡 URL do Stream:</strong> <span id="streamUrl"></span></p>
                <p><strong>🎥 Formato:</strong> MJPEG</p>
                <p><strong>📐 Resolução:</strong> 640x480</p>
                <p><strong>⚡ Taxa de Quadros:</strong> ~30 FPS</p>
                <p><strong>🕒 Atualização:</strong> Tempo real</p>
                
                <div class="url-info">
                    <strong>🔗 URLs de Acesso:</strong><br>
                    • Interface Web: <span id="webUrl"></span><br>
                    • Stream Direto: <span id="directUrl"></span><br>
                    • Para VLC/OBS: <span id="vlcUrl"></span>
                </div>
            </div>
        </div>
        
        <script>
            // Atualiza URLs dinamicamente
            const baseUrl = window.location.origin;
            document.getElementById('streamUrl').textContent = baseUrl + '/video_feed';
            document.getElementById('webUrl').textContent = baseUrl;
            document.getElementById('directUrl').textContent = baseUrl + '/video_feed';
            document.getElementById('vlcUrl').textContent = baseUrl + '/video_feed';
            
            function toggleFullscreen() {
                const video = document.getElementById('videoStream');
                if (video.requestFullscreen) {
                    video.requestFullscreen();
                } else if (video.webkitRequestFullscreen) {
                    video.webkitRequestFullscreen();
                } else if (video.msRequestFullscreen) {
                    video.msRequestFullscreen();
                }
            }
            
            // Auto-reload em caso de erro
            document.getElementById('videoStream').onerror = function() {
                console.log('Erro no stream, tentando reconectar...');
                setTimeout(() => {
                    this.src = this.src;
                }, 3000);
            };
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

@app.route('/video_feed')
def video_feed():
    """Endpoint do stream de vídeo"""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    """Endpoint para verificar status da câmera"""
    global camera, is_streaming
    
    status_info = {
        'camera_connected': camera is not None and camera.isOpened(),
        'streaming': is_streaming,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    return status_info

def start_camera():
    """Inicia a câmera e o thread de captura"""
    global camera, is_streaming
    
    print("🚀 Iniciando sistema de stream...")
    
    # Tenta abrir a câmera
    camera, width, height = try_open_camera(target_width=640, target_height=480, fps=30)
    
    if camera is None:
        print("❌ Falha ao iniciar o sistema de stream")
        return False
    
    print(f"✅ Câmera inicializada com sucesso: {width}x{height}")
    
    # Inicia thread de captura
    is_streaming = True
    capture_thread = threading.Thread(target=capture_frames, daemon=True)
    capture_thread.start()
    
    print("✅ Sistema de stream iniciado com sucesso!")
    return True

def stop_camera():
    """Para a câmera e o streaming"""
    global camera, is_streaming
    
    print("🛑 Parando sistema de stream...")
    is_streaming = False
    
    if camera:
        camera.release()
        camera = None
    
    print("✅ Sistema de stream parado")

def main():
    """Função principal"""
    global camera, last_saved_ts, last_sync_ts
    
    print("🎥 Iniciando sistema de stream da câmera com detecção facial...")
    
    # Inicializa banco de dados
    print("📊 Inicializando banco de dados...")
    init_db()
    
    # Inicializa detector de faces
    print("🔍 Carregando detector de faces...")
    if not init_face_detector():
        print("⚠️ Continuando sem detecção facial")
    
    # Inicializa timestamps
    current_time = time.time()
    last_saved_ts = current_time
    last_sync_ts = current_time
    
    if start_camera():
        print("\n" + "="*50)
        print("🌐 SERVIDOR DE STREAM INICIADO")
        print("="*50)
        print("📱 Interface Web: http://localhost:5000")
        print("📡 Stream Direto: http://localhost:5000/video_feed")
        print("📊 Status: http://localhost:5000/status")
        print("\n💡 Para acessar de outros dispositivos na rede:")
        print("   Substitua 'localhost' pelo IP do Raspberry Pi")
        print("   Exemplo: http://192.168.1.100:5000")
        print("\n🔧 Para parar o servidor: Ctrl+C")
        print("🎯 Detecção facial ativa - faces serão capturadas automaticamente")
        print("="*50)
        
        # Inicia o servidor Flask
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    else:
        print("❌ Falha ao iniciar o sistema de stream")

if __name__ == '__main__':
    try:
        main()
    
    except KeyboardInterrupt:
        print("\n🛑 Parando servidor...")
        stop_camera()
        # Sincronização final
        try:
            sync_supabase()
            print("✅ Sincronização final concluída")
        except:
            pass
        print("✅ Servidor parado com sucesso")
    
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        stop_camera()