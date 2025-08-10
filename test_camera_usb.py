#!/usr/bin/env python3
"""
Script de teste para diagnóstico de câmera USB no Raspberry Pi
Este script ajuda a identificar problemas de detecção de câmera após reinicialização
"""

import cv2
import time
import subprocess
import platform
import os

def check_system_info():
    """Mostra informações do sistema"""
    print("=" * 50)
    print("📋 INFORMAÇÕES DO SISTEMA")
    print("=" * 50)
    print(f"Sistema: {platform.system()} {platform.release()}")
    print(f"Arquitetura: {platform.machine()}")
    print(f"Python: {platform.python_version()}")
    print(f"OpenCV: {cv2.__version__}")
    print()

def check_usb_devices():
    """Verifica dispositivos USB conectados"""
    print("=" * 50)
    print("🔌 DISPOSITIVOS USB")
    print("=" * 50)
    
    try:
        result = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            print(f"Total de dispositivos USB: {len(lines)}")
            print("\nDispositivos encontrados:")
            for i, line in enumerate(lines, 1):
                print(f"  {i}. {line}")
                # Destaca possíveis câmeras
                if any(keyword in line.lower() for keyword in ['camera', 'webcam', 'video', 'capture', 'usb']):
                    print("     ⭐ Possível câmera USB")
        else:
            print("❌ Erro ao executar lsusb")
    except Exception as e:
        print(f"❌ Erro ao verificar dispositivos USB: {e}")
    print()

def check_video_devices():
    """Verifica dispositivos de vídeo disponíveis"""
    print("=" * 50)
    print("📹 DISPOSITIVOS DE VÍDEO")
    print("=" * 50)
    
    try:
        result = subprocess.run(['ls', '/dev/video*'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            devices = result.stdout.strip().split('\n')
            print(f"Dispositivos de vídeo encontrados: {len(devices)}")
            for device in devices:
                if device.strip():
                    print(f"  📹 {device}")
                    
                    # Tenta obter informações do dispositivo
                    try:
                        info_result = subprocess.run(['v4l2-ctl', '--device', device, '--info'], 
                                                   capture_output=True, text=True, timeout=5)
                        if info_result.returncode == 0:
                            print(f"     ℹ️ Info: {info_result.stdout.strip()[:100]}...")
                    except:
                        pass
        else:
            print("❌ Nenhum dispositivo de vídeo encontrado em /dev/video*")
    except Exception as e:
        print(f"❌ Erro ao verificar dispositivos de vídeo: {e}")
    print()

def test_camera_opencv(max_index=5):
    """Testa abertura da câmera com OpenCV"""
    print("=" * 50)
    print("🎥 TESTE DE CÂMERA COM OPENCV")
    print("=" * 50)
    
    # APIs para testar
    apis = [
        (cv2.CAP_V4L2, "V4L2"),
        (cv2.CAP_ANY, "ANY"),
        (0, "DEFAULT")
    ]
    
    working_cameras = []
    
    for api_code, api_name in apis:
        print(f"\n🔍 Testando API: {api_name} ({api_code})")
        
        for idx in range(max_index):
            print(f"  Testando índice {idx}...", end=" ")
            
            try:
                if api_code == 0:
                    cap = cv2.VideoCapture(idx)
                else:
                    cap = cv2.VideoCapture(idx, api_code)
                
                if cap.isOpened():
                    # Tenta ler um frame
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        height, width = frame.shape[:2]
                        print(f"✅ SUCESSO! Resolução: {width}x{height}")
                        working_cameras.append((idx, api_name, width, height))
                    else:
                        print("⚠️ Abriu mas não conseguiu ler frame")
                else:
                    print("❌ Não conseguiu abrir")
                
                cap.release()
                
            except Exception as e:
                print(f"❌ Erro: {e}")
            
            time.sleep(0.1)  # Pequeno delay entre tentativas
    
    print(f"\n📊 RESUMO: {len(working_cameras)} câmera(s) funcionando")
    for idx, api, width, height in working_cameras:
        print(f"  ✅ Índice {idx} com {api}: {width}x{height}")
    
    return working_cameras

def test_camera_capture(camera_info):
    """Testa captura contínua de uma câmera específica"""
    if not camera_info:
        print("❌ Nenhuma câmera disponível para teste")
        return
    
    idx, api_name, width, height = camera_info[0]
    
    print("=" * 50)
    print(f"🎬 TESTE DE CAPTURA CONTÍNUA - Câmera {idx}")
    print("=" * 50)
    
    try:
        if api_name == "V4L2":
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        elif api_name == "ANY":
            cap = cv2.VideoCapture(idx, cv2.CAP_ANY)
        else:
            cap = cv2.VideoCapture(idx)
        
        if not cap.isOpened():
            print("❌ Não conseguiu abrir a câmera")
            return
        
        print("📹 Capturando 10 frames...")
        success_count = 0
        
        for i in range(10):
            ret, frame = cap.read()
            if ret and frame is not None:
                success_count += 1
                print(f"  Frame {i+1}: ✅ OK ({frame.shape})")
            else:
                print(f"  Frame {i+1}: ❌ FALHA")
            
            time.sleep(0.5)
        
        cap.release()
        
        print(f"\n📊 Resultado: {success_count}/10 frames capturados com sucesso")
        if success_count >= 8:
            print("✅ Câmera funcionando bem!")
        elif success_count >= 5:
            print("⚠️ Câmera com problemas intermitentes")
        else:
            print("❌ Câmera com problemas sérios")
            
    except Exception as e:
        print(f"❌ Erro durante teste de captura: {e}")

def check_permissions():
    """Verifica permissões de acesso à câmera"""
    print("=" * 50)
    print("🔐 VERIFICAÇÃO DE PERMISSÕES")
    print("=" * 50)
    
    # Verifica se o usuário está no grupo video
    try:
        result = subprocess.run(['groups'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            groups = result.stdout.strip()
            print(f"Grupos do usuário: {groups}")
            if 'video' in groups:
                print("✅ Usuário está no grupo 'video'")
            else:
                print("❌ Usuário NÃO está no grupo 'video'")
                print("   Execute: sudo usermod -a -G video $USER")
                print("   Depois reinicie o sistema")
    except Exception as e:
        print(f"❌ Erro ao verificar grupos: {e}")
    
    # Verifica permissões dos dispositivos de vídeo
    try:
        result = subprocess.run(['ls', '-la', '/dev/video*'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("\nPermissões dos dispositivos:")
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    print(f"  {line}")
    except Exception as e:
        print(f"❌ Erro ao verificar permissões: {e}")
    
    print()

def main():
    """Função principal do diagnóstico"""
    print("🚀 INICIANDO DIAGNÓSTICO DE CÂMERA USB")
    print("Este script irá verificar a detecção e funcionamento da câmera")
    print()
    
    # Executa todas as verificações
    check_system_info()
    check_usb_devices()
    check_video_devices()
    check_permissions()
    
    # Testa câmeras com OpenCV
    working_cameras = test_camera_opencv()
    
    # Se encontrou câmeras, testa captura
    if working_cameras:
        test_camera_capture(working_cameras)
    
    print("=" * 50)
    print("🏁 DIAGNÓSTICO CONCLUÍDO")
    print("=" * 50)
    
    if working_cameras:
        print("✅ Pelo menos uma câmera foi detectada e testada")
        print("\n💡 Se o script principal ainda não funcionar:")
        print("   1. Tente desconectar e reconectar a câmera USB")
        print("   2. Tente uma porta USB diferente")
        print("   3. Reinicie o sistema")
        print("   4. Execute este diagnóstico novamente")
    else:
        print("❌ Nenhuma câmera foi detectada")
        print("\n🔧 Soluções sugeridas:")
        print("   1. Verifique se a câmera está conectada: lsusb")
        print("   2. Adicione usuário ao grupo video: sudo usermod -a -G video $USER")
        print("   3. Instale ferramentas: sudo apt install v4l-utils fswebcam")
        print("   4. Reinicie o sistema")
        print("   5. Tente outra câmera USB")

if __name__ == "__main__":
    main()