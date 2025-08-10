#!/usr/bin/env python3
"""
Script de diagnóstico melhorado para problemas de câmera e inicialização no Raspberry Pi
Verifica dispositivos, permissões, testa abertura da câmera e diagnostica problemas de boot
"""

import cv2
import os
import subprocess
import sys

def run_command(cmd):
    """Executa um comando e retorna a saída"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return "", str(e)

def check_usb_devices():
    """Verifica dispositivos USB conectados"""
    print("🔍 Verificando dispositivos USB...")
    stdout, stderr = run_command("lsusb")
    if stdout:
        print(stdout)
        # Procura por câmeras comuns
        if "camera" in stdout.lower() or "webcam" in stdout.lower() or "video" in stdout.lower():
            print("✅ Possível câmera USB detectada!")
        else:
            print("⚠️  Nenhuma câmera USB óbvia detectada")
    else:
        print("❌ Erro ao executar lsusb:", stderr)
    print()

def check_video_devices():
    """Verifica dispositivos de vídeo disponíveis"""
    print("🔍 Verificando dispositivos de vídeo...")
    stdout, stderr = run_command("ls /dev/video*")
    if stdout:
        devices = stdout.split('\n')
        print(f"✅ Dispositivos encontrados: {', '.join(devices)}")
        return devices
    else:
        print("❌ Nenhum dispositivo /dev/video* encontrado")
        print("Erro:", stderr)
        return []
    print()

def check_v4l_info():
    """Verifica informações detalhadas dos dispositivos V4L2"""
    print("🔍 Verificando informações V4L2...")
    stdout, stderr = run_command("v4l2-ctl --list-devices")
    if stdout:
        print(stdout)
    else:
        print("❌ v4l2-ctl não disponível. Instale com: sudo apt install v4l-utils")
        print("Erro:", stderr)
    print()

def check_user_groups():
    """Verifica se o usuário está no grupo video"""
    print("🔍 Verificando grupos do usuário...")
    stdout, stderr = run_command("groups")
    if stdout:
        groups = stdout.split()
        if "video" in groups:
            print("✅ Usuário está no grupo 'video'")
        else:
            print("⚠️  Usuário NÃO está no grupo 'video'")
            print("Execute: sudo usermod -a -G video $USER")
            print("Depois reinicie ou faça logout/login")
        print(f"Grupos atuais: {', '.join(groups)}")
    else:
        print("❌ Erro ao verificar grupos:", stderr)
    print()

def test_opencv_camera():
    """Testa abertura da câmera com OpenCV"""
    print("🔍 Testando abertura da câmera com OpenCV...")
    
    # APIs para testar
    apis = [
        (cv2.CAP_V4L2, "V4L2"),
        (cv2.CAP_ANY, "ANY"),
    ]
    
    for idx in range(3):  # Testa índices 0, 1, 2
        print(f"\n📹 Testando índice {idx}:")
        
        for api_code, api_name in apis:
            try:
                print(f"  Tentando {api_name}...", end=" ")
                cap = cv2.VideoCapture(idx, api_code)
                
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        h, w = frame.shape[:2]
                        print(f"✅ SUCESSO! Resolução: {w}x{h}")
                        cap.release()
                        return True
                    else:
                        print("❌ Abriu mas não conseguiu ler frame")
                else:
                    print("❌ Não conseguiu abrir")
                
                cap.release()
            except Exception as e:
                print(f"❌ Erro: {e}")
        
        # Tenta sem especificar API
        try:
            print(f"  Tentando sem API específica...", end=" ")
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    print(f"✅ SUCESSO! Resolução: {w}x{h}")
                    cap.release()
                    return True
                else:
                    print("❌ Abriu mas não conseguiu ler frame")
            else:
                print("❌ Não conseguiu abrir")
            cap.release()
        except Exception as e:
            print(f"❌ Erro: {e}")
    
    print("\n❌ Nenhuma câmera funcional encontrada com OpenCV")
    return False

def test_fswebcam():
    """Testa captura com fswebcam"""
    print("🔍 Testando captura com fswebcam...")
    stdout, stderr = run_command("which fswebcam")
    if not stdout:
        print("❌ fswebcam não instalado. Instale com: sudo apt install fswebcam")
        return False
    
    # Tenta capturar uma imagem de teste
    cmd = "fswebcam -r 320x240 --no-banner /tmp/test_camera.jpg"
    stdout, stderr = run_command(cmd)
    
    if os.path.exists("/tmp/test_camera.jpg"):
        print("✅ fswebcam conseguiu capturar imagem!")
        # Remove arquivo de teste
        os.remove("/tmp/test_camera.jpg")
        return True
    else:
        print("❌ fswebcam falhou")
        if stderr:
            print("Erro:", stderr)
        return False

def check_autostart_config():
    """Verifica configuração de inicialização automática"""
    print("\n🚀 VERIFICANDO CONFIGURAÇÃO DE INICIALIZAÇÃO AUTOMÁTICA")
    print("-" * 50)
    
    import subprocess
    import os
    
    # Verifica crontab
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        if result.returncode == 0:
            crontab_content = result.stdout
            if 'start_faces' in crontab_content:
                print("✅ Crontab configurado:")
                for line in crontab_content.split('\n'):
                    if 'start_faces' in line:
                        print(f"   {line}")
            else:
                print("❌ Nenhuma entrada de start_faces encontrada no crontab")
        else:
            print("❌ Erro ao verificar crontab ou crontab vazio")
    except Exception as e:
        print(f"❌ Erro ao verificar crontab: {e}")
    
    # Verifica scripts de inicialização
    scripts_to_check = [
        '/home/pi/start_faces.sh',
        '/home/pi/start_faces_improved.sh'
    ]
    
    for script_path in scripts_to_check:
        if os.path.exists(script_path):
            print(f"✅ Script encontrado: {script_path}")
            # Verifica permissões
            if os.access(script_path, os.X_OK):
                print(f"   ✅ Permissão de execução OK")
            else:
                print(f"   ❌ Sem permissão de execução")
        else:
            print(f"❌ Script não encontrado: {script_path}")
    
    # Verifica logs de inicialização
    log_files = [
        '/home/pi/face_capture_startup.log',
        '/var/log/syslog'
    ]
    
    for log_file in log_files:
        if os.path.exists(log_file):
            print(f"✅ Log encontrado: {log_file}")
            try:
                # Mostra últimas linhas relevantes
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    relevant_lines = [line for line in lines[-20:] if 'face' in line.lower() or 'camera' in line.lower()]
                    if relevant_lines:
                        print("   Últimas entradas relevantes:")
                        for line in relevant_lines[-5:]:
                            print(f"   {line.strip()}")
            except Exception as e:
                print(f"   ❌ Erro ao ler log: {e}")
        else:
            print(f"❌ Log não encontrado: {log_file}")


def check_process_status():
    """Verifica se o processo está rodando atualmente"""
    print("\n🔄 VERIFICANDO STATUS DO PROCESSO")
    print("-" * 50)
    
    import subprocess
    
    try:
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            face_processes = [line for line in lines if 'capture_faces' in line and 'grep' not in line]
            
            if face_processes:
                print("✅ Processo de detecção de faces encontrado:")
                for process in face_processes:
                    print(f"   {process}")
            else:
                print("❌ Nenhum processo de detecção de faces rodando")
        else:
            print("❌ Erro ao verificar processos")
    except Exception as e:
        print(f"❌ Erro ao verificar processos: {e}")


def check_environment_variables():
    """Verifica variáveis de ambiente necessárias"""
    print("\n🌍 VERIFICANDO VARIÁVEIS DE AMBIENTE")
    print("-" * 50)
    
    import os
    
    required_vars = {
        'SUPABASE_URL': 'URL do Supabase',
        'SUPABASE_ANON_KEY': 'Chave anônima do Supabase',
        'DEVICE_ID': 'ID do dispositivo'
    }
    
    for var_name, description in required_vars.items():
        value = os.environ.get(var_name)
        if value:
            # Mostra apenas parte da chave por segurança
            if 'KEY' in var_name and len(value) > 20:
                display_value = value[:10] + '...' + value[-10:]
            else:
                display_value = value
            print(f"✅ {var_name}: {display_value}")
        else:
            print(f"❌ {var_name}: Não configurada ({description})")


def main():
    print("🔍 DIAGNÓSTICO COMPLETO - RASPBERRY PI")
    print("=" * 50)
    print()
    
    # Verifica se está rodando no Linux
    if os.name != 'posix':
        print("⚠️  Este script foi feito para Linux/Raspberry Pi")
        print()
    
    # Executa todos os testes
    check_usb_devices()
    video_devices = check_video_devices()
    check_v4l_info()
    check_user_groups()
    
    # Verifica variáveis de ambiente
    check_environment_variables()
    
    # Verifica configuração de inicialização
    check_autostart_config()
    
    # Verifica status do processo
    check_process_status()
    
    opencv_ok = test_opencv_camera()
    fswebcam_ok = test_fswebcam()
    
    print("\n" + "=" * 50)
    print("📋 RESUMO DO DIAGNÓSTICO:")
    print(f"  OpenCV: {'✅ OK' if opencv_ok else '❌ FALHOU'}")
    print(f"  fswebcam: {'✅ OK' if fswebcam_ok else '❌ FALHOU'}")
    print(f"  Dispositivos /dev/video*: {len(video_devices)} encontrado(s)")
    
    if opencv_ok:
        print("\n🎉 Câmera funcionando! O capture_faces.py deve funcionar.")
    else:
        print("\n❌ Problemas detectados. Verifique as dicas acima.")
        print("\n🔧 Comandos úteis para solução:")
        print("  sudo apt update && sudo apt install fswebcam v4l-utils")
        print("  sudo usermod -a -G video $USER")
        print("  sudo reboot")
        print("\n🔧 Se não inicia automaticamente:")
        print("  - Execute: bash setup_autostart.sh")
        print("  - Verifique logs: tail -f /home/pi/face_capture_startup.log")

if __name__ == "__main__":
    main()