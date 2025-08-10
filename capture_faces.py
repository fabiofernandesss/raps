import cv2
import sqlite3
import base64
import time
from datetime import datetime
import os
import sys
import shutil
import tempfile
import requests
from typing import List, Tuple

DB_PATH = os.path.join(os.path.dirname(__file__), "faces.db")

# Configurações Supabase: permite override por ambiente, mas define padrão com sua URL/anon key
SUPABASE_URL = os.environ.get("SUPABASE_URL") or ""
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY") or ""
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "captures")
DEVICE_ID = os.environ.get("DEVICE_ID") or os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "raspi-01"


def init_db(db_path: str = DB_PATH):
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
    if len(faces) == 0:
        return None
    # faces are (x, y, w, h); pick largest area
    x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
    return (x, y, w, h)


def crop_with_margin(img, rect, margin_ratio: float = 0.1):
    h, w = img.shape[:2]
    x, y, fw, fh = rect
    pad = int(max(fw, fh) * margin_ratio)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(w, x + fw + pad)
    y2 = min(h, y + fh + pad)
    return img[y1:y2, x1:x2]


def encode_image_to_base64(img_bgr, target_size=(160, 160), quality: int = 80) -> str:
    # Resize for storage efficiency
    resized = cv2.resize(img_bgr, target_size, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError("Falha ao codificar a imagem para JPEG.")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def check_usb_devices():
    """Verifica se há dispositivos USB conectados (especialmente câmeras)"""
    import platform
    import subprocess
    
    system = platform.system().lower()
    
    if system == "linux":
        try:
            # Verifica dispositivos USB
            result = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
            usb_devices = result.stdout.lower()
            
            # Verifica dispositivos de vídeo
            video_result = subprocess.run(['ls', '/dev/video*'], capture_output=True, text=True, timeout=5)
            video_devices = video_result.stdout
            
            print(f"📹 Dispositivos de vídeo encontrados: {video_devices.strip() if video_devices else 'Nenhum'}")
            
            # Procura por câmeras USB comuns
            camera_keywords = ['camera', 'webcam', 'usb', 'video', 'capture']
            has_camera = any(keyword in usb_devices for keyword in camera_keywords)
            
            return len(video_devices.strip()) > 0 or has_camera
            
        except Exception as e:
            print(f"⚠️ Erro ao verificar dispositivos USB: {e}")
            return True  # Assume que há dispositivos se não conseguir verificar
    
    return True  # Para Windows, assume que há dispositivos


def wait_for_usb_devices(max_wait=30, check_interval=2):
    """Aguarda dispositivos USB serem detectados"""
    print("🔍 Verificando dispositivos USB...")
    
    for attempt in range(max_wait // check_interval):
        if check_usb_devices():
            print("✅ Dispositivos USB detectados!")
            return True
        
        print(f"⏳ Aguardando dispositivos USB... ({attempt + 1}/{max_wait // check_interval})")
        time.sleep(check_interval)
    
    print("⚠️ Timeout aguardando dispositivos USB")
    return False


def try_open_camera(width=320, height=240, fps=15, retry_delay=2.0):
    print("Abrindo webcam...")
    # Detecta sistema operacional para usar APIs apropriadas
    import platform
    system = platform.system().lower()
    
    if system == "windows":
        # APIs para Windows
        api_prefs = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    else:
        # APIs para Linux/Raspberry Pi
        api_prefs = [cv2.CAP_V4L2, cv2.CAP_ANY]
    
    indices = [0, 1, 2]
    
    # Aguarda um pouco para dispositivos USB se estabilizarem após boot
    if retry_delay > 0:
        print(f"Aguardando {retry_delay}s para dispositivos USB se estabilizarem...")
        time.sleep(retry_delay)
    
    for api in api_prefs:
        for idx in indices:
            print(f"Tentando índice {idx} com API {api}...")
            cap = cv2.VideoCapture(idx, api)
            if not cap.isOpened():
                cap.release()
                continue
            # Configurações leves
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, fps)
            time.sleep(0.15)
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"✅ Webcam aberta no índice {idx} usando API {api}.")
                return cap
            else:
                cap.release()
    
    # Se não conseguiu abrir, tenta sem especificar API
    print("Tentando abrir câmera sem especificar API...")
    for idx in indices:
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"✅ Webcam aberta no índice {idx} (sem API específica).")
                return cap
            cap.release()
    
    return None


def reconnect_camera(cap, width=320, height=240, fps=15):
    """Tenta reconectar a câmera quando há falha na leitura"""
    print("⚠️ Falha na câmera detectada. Tentando reconectar...")
    if cap:
        cap.release()
    time.sleep(1.0)  # Aguarda um pouco antes de tentar reconectar
    return try_open_camera(width, height, fps, retry_delay=0)


def try_open_camera_with_retries(width=320, height=240, fps=15, max_retries=5, base_delay=5):
    """Tenta abrir a câmera com múltiplas tentativas e delays crescentes"""
    for attempt in range(max_retries):
        print(f"🔄 Tentativa {attempt + 1}/{max_retries} de abrir a câmera...")
        
        # Verifica dispositivos USB antes de cada tentativa
        if attempt > 0:
            check_usb_devices()
        
        # Delay crescente: 3s, 5s, 8s, 12s, 18s
        retry_delay = 3.0 if attempt == 0 else base_delay + (attempt * 3)
        
        cap = try_open_camera(width, height, fps, retry_delay)
        if cap is not None:
            return cap
        
        if attempt < max_retries - 1:
            wait_time = base_delay + (attempt * 2)
            print(f"⏳ Aguardando {wait_time}s antes da próxima tentativa...")
            print("💡 Dica: Se a câmera não for detectada, tente desconectar e reconectar o cabo USB")
            time.sleep(wait_time)
    
    return None


# ============== SUPABASE SYNC ==============

def _fetch_pending(limit: int = 20) -> List[Tuple[int, str, str, str]]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, date, time, image_base64 FROM captures ORDER BY id ASC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def _delete_local(ids: List[int]):
    if not ids:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    qmarks = ",".join(["?"] * len(ids))
    cur.execute(f"DELETE FROM captures WHERE id IN ({qmarks})", ids)
    conn.commit()
    conn.close()


def sync_supabase(max_batch: int = 20):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        # Variáveis não setadas: apenas pula o sync
        return
    rows = _fetch_pending(limit=max_batch)
    if not rows:
        return

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{SUPABASE_TABLE}"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
        "X-Client-Info": "ia_rasp/1.0",
    }

    payload = []
    local_ids = []
    for _id, date_str, time_str, img_b64 in rows:
        local_ids.append(_id)
        payload.append({
            "device_id": DEVICE_ID,
            "date": date_str,
            "time": time_str,
            "image_base64": img_b64,
        })

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=20)
        if 200 <= resp.status_code < 300:
            _delete_local(local_ids)
            print(f"[Sync] Enviado {len(local_ids)} registro(s) ao Supabase e removidos do banco local.")
            return
        else:
            print(f"[Sync] Falha em lote ({resp.status_code}). Tentando envio individual...")
    except Exception as e:
        print(f"[Sync] Erro ao conectar ao Supabase (lote): {e}. Tentando individual...")

    # Fallback: tentar registro a registro para não travar limpeza
    sent = 0
    for (_id, date_str, time_str, img_b64) in rows:
        single_payload = {
            "device_id": DEVICE_ID,
            "date": date_str,
            "time": time_str,
            "image_base64": img_b64,
        }
        try:
            r = requests.post(url, json=single_payload, headers=headers, timeout=15)
            if 200 <= r.status_code < 300:
                _delete_local([_id])
                sent += 1
            else:
                print(f"[Sync] Erro ao enviar id={_id}: {r.status_code} - {r.text}")
        except Exception as ex:
            print(f"[Sync] Exceção ao enviar id={_id}: {ex}")

    if sent:
        print(f"[Sync] Registros enviados individualmente: {sent}/{len(rows)}. Correspondentes removidos localmente.")
    else:
        print("[Sync] Falha ao enviar registros ao Supabase (tentativa individual).")


def main():
    print("Inicializando banco de dados...")
    init_db(DB_PATH)

    print("Carregando modelo Haar Cascade de detecção facial (leve)...")
    cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")

    # Fallback para lidar com caminhos com acentos no Windows
    tmp_cascade = None
    face_detector = cv2.CascadeClassifier(cascade_path)
    if face_detector.empty():
        try:
            tmp_dir = tempfile.gettempdir()
            tmp_cascade = os.path.join(tmp_dir, "haarcascade_frontalface_default.xml")
            if not os.path.exists(tmp_cascade):
                shutil.copyfile(cascade_path, tmp_cascade)
            face_detector = cv2.CascadeClassifier(tmp_cascade)
        except Exception as e:
            print("Erro: não foi possível carregar o classificador Haar Cascade.")
            print(f"Caminho tentado: {cascade_path}")
            print(f"Tentativa de fallback em: {tmp_cascade} falhou: {e}")
            sys.exit(1)

    if face_detector.empty():
        print("Erro: não foi possível carregar o classificador Haar Cascade.")
        print(f"Caminho tentado: {cascade_path}")
        if tmp_cascade:
            print(f"Também tentei: {tmp_cascade}")
        sys.exit(1)

    # Aguarda dispositivos USB serem detectados (especialmente importante na inicialização)
    wait_for_usb_devices(max_wait=30, check_interval=2)
    
    # Abrir câmera com múltiplas tentativas e delays crescentes
    cap = try_open_camera_with_retries(width=320, height=240, fps=15, max_retries=5, base_delay=5)
    if cap is None:
        import platform
        system = platform.system().lower()
        
        print("❌ Erro: não foi possível acessar a webcam.")
        print("\n🔧 Dicas para solução:")
        
        if system == "windows":
            print(" - Feche aplicativos que possam estar usando a câmera (Teams, Zoom, Chrome, etc.)")
            print(" - Verifique as permissões de Câmera no Windows: Configurações > Privacidade > Câmera")
            print(" - Tente outra porta USB ou outro índice de dispositivo (0, 1, 2)")
        else:
            print(" - Verifique se a câmera está conectada: lsusb")
            print(" - Verifique dispositivos de vídeo: ls /dev/video*")
            print(" - Teste a câmera manualmente: fswebcam test.jpg")
            print(" - Instale dependências: sudo apt install fswebcam v4l-utils")
            print(" - Verifique permissões: sudo usermod -a -G video $USER")
            print(" - Reinicie após adicionar ao grupo video")
            print(" - Tente desconectar e reconectar a câmera USB")
            print(" - Tente outra porta USB")
            print(" - Verifique se outro processo está usando a câmera")
        
        sys.exit(1)

    last_saved_ts = 0.0
    cooldown_seconds = 3.0  # evita salvar imagens demais
    last_sync_ts = 0.0
    sync_interval = 5.0  # sincroniza pendências a cada 5s

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print("[Aviso] SUPABASE_URL/SUPABASE_ANON_KEY não configurados. Registros ficarão locais até configurar.")

    print("Rodando. Pressione Ctrl+C para sair.")
    consecutive_failures = 0
    max_failures = 10  # Máximo de falhas consecutivas antes de tentar reconectar
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                consecutive_failures += 1
                print(f"⚠️ Falha na leitura da câmera ({consecutive_failures}/{max_failures})")
                
                # Se muitas falhas consecutivas, tenta reconectar
                if consecutive_failures >= max_failures:
                    print("🔄 Muitas falhas consecutivas. Tentando reconectar câmera...")
                    new_cap = reconnect_camera(cap, width=320, height=240, fps=15)
                    if new_cap is not None:
                        cap = new_cap
                        consecutive_failures = 0
                        print("✅ Câmera reconectada com sucesso!")
                    else:
                        print("❌ Falha na reconexão. Aguardando 10s antes de tentar novamente...")
                        time.sleep(10)
                        consecutive_failures = 0  # Reset para tentar novamente
                
                # Tentativa de sync mesmo sem frame, para não acumular
                if (time.time() - last_sync_ts) >= sync_interval:
                    sync_supabase(max_batch=50)
                    last_sync_ts = time.time()
                time.sleep(0.5)  # Aguarda um pouco mais quando há falhas
                continue
            
            # Reset contador de falhas quando consegue ler frame
            consecutive_failures = 0

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Parâmetros mais leves: maior scaleFactor reduz custo, minNeighbors equilibrado
            faces = face_detector.detectMultiScale(
                gray,
                scaleFactor=1.2,
                minNeighbors=5,
                minSize=(30, 30),
                flags=cv2.CASCADE_SCALE_IMAGE,
            )

            if len(faces) > 0 and (time.time() - last_saved_ts) >= cooldown_seconds:
                biggest = get_biggest_face(faces)
                face_img = crop_with_margin(frame, biggest, margin_ratio=0.15)
                try:
                    img_b64 = encode_image_to_base64(face_img, target_size=(160, 160), quality=80)
                    save_capture(img_b64, DB_PATH)
                    last_saved_ts = time.time()
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[Salvo] Rosto detectado em {now}.")
                except Exception as e:
                    print(f"Erro ao salvar imagem: {e}")

            # Sincroniza periodicamente com o Supabase e limpa local ao concluir
            if (time.time() - last_sync_ts) >= sync_interval:
                sync_supabase(max_batch=50)
                last_sync_ts = time.time()

            # Pequena espera para aliviar CPU no loop
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        try:
            # Tenta enviar pendências finais antes de sair
            sync_supabase(max_batch=200)
        except Exception:
            pass
        cap.release()
        print("Recursos liberados. Tchau!")


if __name__ == "__main__":
    main()