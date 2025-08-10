#!/usr/bin/env python3
"""
Script de diagnóstico para câmera no Raspberry Pi
Use este script para identificar problemas com a câmera antes de executar o capture_faces.py
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

def main():
    print("🔧 DIAGNÓSTICO DE CÂMERA - RASPBERRY PI")
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

if __name__ == "__main__":
    main()