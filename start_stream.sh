#!/bin/bash

# Script para iniciar o servidor de stream da câmera
# Uso: ./start_stream.sh [porta]

set -e

# Configurações
PROJECT_DIR="/home/pi/raps"
LOG_DIR="$PROJECT_DIR/logs"
STREAM_LOG="$LOG_DIR/stream.log"
PORT=${1:-5000}  # Porta padrão 5000, ou primeira argumento

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Iniciando Servidor de Stream da Câmera${NC}"
echo "==========================================="
echo "📅 $(date)"
echo "📁 Diretório: $PROJECT_DIR"
echo "🌐 Porta: $PORT"
echo

# Verifica se está no diretório correto
if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${RED}❌ Erro: Diretório do projeto não encontrado: $PROJECT_DIR${NC}"
    echo "💡 Verifique se o projeto está instalado corretamente"
    exit 1
fi

cd "$PROJECT_DIR"

# Cria diretório de logs se não existir
mkdir -p "$LOG_DIR"

# Verifica se o arquivo do stream existe
if [ ! -f "camera_stream.py" ]; then
    echo -e "${RED}❌ Erro: Arquivo camera_stream.py não encontrado${NC}"
    echo "💡 Certifique-se de que todos os arquivos foram copiados corretamente"
    exit 1
fi

# Verifica se o ambiente virtual existe
if [ ! -d ".venv" ]; then
    echo -e "${RED}❌ Erro: Ambiente virtual não encontrado${NC}"
    echo "💡 Execute primeiro: python -m venv .venv"
    exit 1
fi

# Ativa o ambiente virtual
echo -e "${YELLOW}🔧 Ativando ambiente virtual...${NC}"
source .venv/bin/activate

# Verifica se o Flask está instalado
if ! python -c "import flask" 2>/dev/null; then
    echo -e "${YELLOW}📦 Instalando dependências...${NC}"
    pip install -r requirements.txt
fi

# Verifica se a câmera está disponível
echo -e "${YELLOW}📹 Verificando câmera...${NC}"
if ls /dev/video* >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Dispositivos de vídeo encontrados:${NC}"
    ls /dev/video*
else
    echo -e "${RED}⚠️ Nenhum dispositivo de vídeo encontrado${NC}"
    echo "💡 Verifique se a câmera está conectada"
    echo "💡 Execute: python test_camera_usb.py para diagnóstico"
fi

# Verifica se a porta está em uso
if netstat -tuln | grep -q ":$PORT "; then
    echo -e "${RED}⚠️ Porta $PORT já está em uso${NC}"
    echo "💡 Parando processos existentes na porta $PORT..."
    sudo fuser -k $PORT/tcp 2>/dev/null || true
    sleep 2
fi

# Obtém o IP local
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo
echo -e "${GREEN}🌐 Iniciando servidor de stream...${NC}"
echo "📡 URLs de acesso:"
echo "   • Local: http://localhost:$PORT"
echo "   • Rede: http://$LOCAL_IP:$PORT"
echo "   • Stream direto: http://$LOCAL_IP:$PORT/video_feed"
echo
echo -e "${YELLOW}💡 Para parar o servidor: Ctrl+C${NC}"
echo -e "${YELLOW}📋 Logs salvos em: $STREAM_LOG${NC}"
echo

# Inicia o servidor e salva logs
echo "$(date): Iniciando servidor de stream na porta $PORT" >> "$STREAM_LOG"

# Executa o servidor com logs
python camera_stream.py 2>&1 | tee -a "$STREAM_LOG"

echo
echo -e "${BLUE}🛑 Servidor de stream parado${NC}"
echo "$(date): Servidor de stream parado" >> "$STREAM_LOG"