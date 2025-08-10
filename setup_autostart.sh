#!/bin/bash

# Script para configurar inicialização automática no Raspberry Pi
# Resolve problemas comuns de inicialização

echo "=== Configurando inicialização automática do sistema de detecção de faces ==="

# Verifica se está rodando como usuário pi
if [ "$USER" != "pi" ]; then
    echo "ERRO: Este script deve ser executado como usuário 'pi'"
    echo "Use: su - pi"
    exit 1
fi

# Diretórios e arquivos
PROJECT_DIR="/home/pi/raps"
OLD_SCRIPT="/home/pi/start_faces.sh"
NEW_SCRIPT="/home/pi/start_faces_improved.sh"
LOG_FILE="/home/pi/face_capture_startup.log"

echo "1. Verificando estrutura do projeto..."
if [ ! -d "$PROJECT_DIR" ]; then
    echo "ERRO: Diretório do projeto não encontrado: $PROJECT_DIR"
    echo "Execute 'git clone' primeiro"
    exit 1
fi

echo "2. Copiando script melhorado..."
cp "$PROJECT_DIR/start_faces_improved.sh" "$NEW_SCRIPT"
chmod +x "$NEW_SCRIPT"
echo "Script copiado para: $NEW_SCRIPT"

echo "3. Configurando permissões de câmera..."
# Adiciona usuário ao grupo video se não estiver
if ! groups $USER | grep -q video; then
    echo "Adicionando usuário $USER ao grupo 'video'..."
    sudo usermod -a -G video $USER
    echo "IMPORTANTE: Você precisa fazer logout/login ou reiniciar para as permissões terem efeito"
else
    echo "Usuário já está no grupo 'video'"
fi

echo "4. Removendo crontab antigo..."
crontab -l 2>/dev/null | grep -v "start_faces.sh" | crontab -
echo "Crontab antigo removido"

echo "5. Configurando novo crontab..."
# Cria novo crontab com script melhorado
(
    crontab -l 2>/dev/null | grep -v "start_faces"
    echo "@reboot sleep 30 && $NEW_SCRIPT"
) | crontab -

echo "6. Verificando configuração do crontab..."
echo "Crontab atual:"
crontab -l

echo "7. Desabilitando serviços systemd conflitantes..."
sudo systemctl disable face-capture.service 2>/dev/null || echo "Serviço face-capture.service não encontrado (OK)"
sudo systemctl stop face-capture.service 2>/dev/null || echo "Serviço face-capture.service não estava rodando (OK)"

echo "8. Criando arquivo de log..."
touch "$LOG_FILE"
chmod 664 "$LOG_FILE"

echo "9. Testando script manualmente..."
echo "Você pode testar o script agora com:"
echo "  $NEW_SCRIPT"
echo ""
echo "Para ver os logs de inicialização:"
echo "  tail -f $LOG_FILE"
echo ""
echo "Para verificar se está rodando:"
echo "  ps aux | grep capture_faces"
echo ""
echo "=== Configuração concluída ==="
echo "IMPORTANTE: Reinicie o Raspberry Pi para testar a inicialização automática"
echo "           sudo reboot"