#!/bin/bash
# ═══════════════════════════════════════════════
#  🐊 와니 AI — Raspberry Pi 5 통합 환경 설정
# ═══════════════════════════════════════════════
# 사용법: chmod +x scripts/setup.sh && ./scripts/setup.sh
# 주의: 인터넷 연결 상태에서 실행 (모델 다운로드 약 2~3GB 필요)

set -e

echo "═══════════════════════════════════════════"
echo "  🐊 와니 AI — 통합 환경 설정 시작"
echo "═══════════════════════════════════════════"

WANI_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WANI_DIR"

# ── 1. 시스템 패키지 ──
echo ""
echo "📦 [1/8] 시스템 패키지 설치..."
sudo apt update
sudo apt install -y \
    python3-venv python3-pip python3-dev \
    portaudio19-dev libsndfile1-dev \
    ffmpeg espeak-ng \
    libasound2-dev libpulse-dev \
    cmake build-essential git git-lfs \
    libgl1-mesa-dev libgles2-mesa-dev \
    alsa-utils pulseaudio

# Git LFS 초기화
git lfs install

# ── 2. 스왑 확대 ──
echo ""
echo "💾 [2/8] 스왑 공간 확대 (4GB)..."
sudo dphys-swapfile swapoff || true
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=4096/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
echo "  스왑 크기: $(free -h | grep Swap | awk '{print $2}')"

# ── 3. GPU 메모리 ──
echo ""
echo "🖥️ [3/8] GPU 메모리 설정..."
if ! grep -q "gpu_mem=" /boot/firmware/config.txt 2>/dev/null; then
    echo "gpu_mem=64" | sudo tee -a /boot/firmware/config.txt
    echo "  gpu_mem=64 설정 완료 (재부팅 후 적용)"
fi

# ── 4. Python 가상환경 ──
echo ""
echo "🐍 [4/8] Python 가상환경 생성..."
if [ ! -d "$WANI_DIR/venv" ]; then
    python3 -m venv "$WANI_DIR/venv"
fi
source "$WANI_DIR/venv/bin/activate"
pip install --upgrade pip

# ── 5. Python 패키지 설치 ──
echo ""
echo "📚 [5/8] Python 패키지 설치..."
pip install -r "$WANI_DIR/requirements.txt"

# ── 6. Whisper.cpp 빌드 ──
echo ""
echo "🗣️ [6/8] Whisper.cpp 빌드..."
if [ ! -d "$WANI_DIR/whisper.cpp" ]; then
    git clone https://github.com/ggerganov/whisper.cpp "$WANI_DIR/whisper.cpp"
fi
cd "$WANI_DIR/whisper.cpp"
make clean
make -j$(nproc)

# 한국어 tiny 모델 다운로드
if [ ! -f "$WANI_DIR/whisper.cpp/models/ggml-tiny.bin" ]; then
    echo "  Whisper tiny 모델 다운로드..."
    bash models/download-ggml-model.sh tiny
fi

cd "$WANI_DIR"

# ── 7. Ollama 설치 & 모델 다운로드 ──
echo ""
echo "🧠 [7/8] Ollama 설치 및 Gemma4 E2B 다운로드..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Ollama 서비스 시작
sudo systemctl enable ollama
sudo systemctl start ollama || true
sleep 3

# Gemma4 E2B 모델 다운로드
echo "  Gemma4 E2B 모델 다운로드 (잠시만 기다려주세요)..."
ollama pull gemma4:e2b

# ── 8. Supertonic TTS 에셋 ──
echo ""
echo "🔊 [8/8] Supertonic TTS 에셋 다운로드..."
mkdir -p "$WANI_DIR/models/supertonic"
if [ ! -d "$WANI_DIR/models/supertonic/assets" ]; then
    # Git LFS를 사용하여 에셋 클론
    git clone https://huggingface.co/Supertone/supertonic-2 "$WANI_DIR/models/supertonic/assets"
else
    echo "  이미 에셋이 존재합니다."
fi

# ── 디렉토리 구조 확인 ──
echo ""
echo "📁 디렉토리 구조 생성..."
mkdir -p "$WANI_DIR/models/wani/textures"
mkdir -p "$WANI_DIR/models/wani/motions"
mkdir -p "$WANI_DIR/models/wani/expressions"
mkdir -p "$WANI_DIR/assets/backgrounds"
mkdir -p "$WANI_DIR/assets/sounds"

# ── 완료 ──
echo ""
echo "═══════════════════════════════════════════"
echo "  ✅ 모든 통합 환경 설정 완료!"
echo "═══════════════════════════════════════════"
echo ""
echo "  다음 단계:"
echo "  1. Live2D 모델을 models/wani/ 에 배치"
echo "  2. 실행: ./scripts/start.sh"
echo "  3. 테스트: python scratch/test_supertonic.py"
echo ""
echo "  📌 재부팅 후 GPU 메모리 설정이 적용됩니다."
echo ""
