#!/usr/bin/env python3
"""
Stream de câmera ao vivo via web
Disponibiliza o feed da câmera em tempo real através de uma URL
"""

import cv2
import time
import threading
from flask import Flask, Response, render_template_string
import os
import platform

app = Flask(__name__)

# Variáveis globais
camera = None
frame_lock = threading.Lock()
latest_frame = None
is_streaming = False

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
    """Thread para capturar frames continuamente"""
    global camera, latest_frame, is_streaming
    
    while is_streaming:
        if camera is None:
            time.sleep(1)
            continue
        
        ret, frame = camera.read()
        if ret and frame is not None:
            with frame_lock:
                latest_frame = frame.copy()
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

if __name__ == '__main__':
    try:
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
            print("="*50)
            
            # Inicia o servidor Flask
            app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
        else:
            print("❌ Falha ao iniciar o sistema de stream")
    
    except KeyboardInterrupt:
        print("\n🛑 Parando servidor...")
        stop_camera()
        print("✅ Servidor parado com sucesso")
    
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        stop_camera()