#!/bin/bash

# Script melhorado para inicialização do sistema de detecção de faces
# Resolve problemas de inicialização automática no Raspberry Pi

LOG_FILE="/home/pi/face_capture_startup.log"
PROJECT_DIR="/home/pi/raps"
SCRIPT_NAME="capture_faces.py"

# Função para log com timestamp
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_message "=== Iniciando script de detecção de faces ==="

# Aguarda o sistema se estabilizar completamente
log_message "Aguardando sistema se estabilizar..."
sleep 15

# Verifica se o diretório do projeto existe
if [ ! -d "$PROJECT_DIR" ]; then
    log_message "ERRO: Diretório do projeto não encontrado: $PROJECT_DIR"
    exit 1
fi

# Navega para o diretório do projeto
cd "$PROJECT_DIR" || {
    log_message "ERRO: Não foi possível acessar o diretório: $PROJECT_DIR"
    exit 1
}

log_message "Diretório atual: $(pwd)"

# Verifica se o script Python existe
if [ ! -f "$SCRIPT_NAME" ]; then
    log_message "ERRO: Script não encontrado: $SCRIPT_NAME"
    exit 1
fi

# Verifica se o ambiente virtual existe
if [ ! -d ".venv" ]; then
    log_message "ERRO: Ambiente virtual não encontrado: .venv"
    exit 1
fi

# Define variáveis de ambiente
export SUPABASE_URL="https://uqmwhtpcsaqievcmpgni.supabase.co"
export SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVxbXdodHBjc2FxaWV2Y21wZ25pIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTE1MTcwOTMsImV4cCI6MjA2NzA5MzA5M30.9TOMJu7xZm-YQV51N4TbdjEW3PsKagyAV5jQYf128fQ"
export DEVICE_ID="raspi-01"

log_message "Variáveis de ambiente configuradas"

# Aguarda dispositivos USB se estabilizarem
log_message "Aguardando dispositivos USB se estabilizarem..."
sleep 10

# Verifica se há dispositivos de vídeo disponíveis
if ls /dev/video* 1> /dev/null 2>&1; then
    log_message "Dispositivos de vídeo encontrados: $(ls /dev/video*)"
else
    log_message "AVISO: Nenhum dispositivo de vídeo encontrado em /dev/video*"
fi

# Verifica dispositivos USB
log_message "Dispositivos USB conectados:"
lsusb | tee -a "$LOG_FILE"

# Ativa o ambiente virtual
log_message "Ativando ambiente virtual..."
source .venv/bin/activate || {
    log_message "ERRO: Falha ao ativar ambiente virtual"
    exit 1
}

log_message "Ambiente virtual ativado"

# Verifica se o Python e as dependências estão disponíveis
log_message "Verificando Python e dependências..."
python --version | tee -a "$LOG_FILE"
python -c "import cv2; print(f'OpenCV version: {cv2.__version__}')" 2>&1 | tee -a "$LOG_FILE"

# Executa o script principal
log_message "Iniciando script de detecção de faces..."
python "$SCRIPT_NAME" 2>&1 | tee -a "$LOG_FILE"

# Se chegou aqui, o script terminou
log_message "Script de detecção de faces terminou"