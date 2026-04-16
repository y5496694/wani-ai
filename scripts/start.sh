#!/bin/bash
# ═══════════════════════════════════════════
#  🐊 와니 AI — 실행 스크립트
# ═══════════════════════════════════════════
# 사용법:
#   ./scripts/start.sh              # 전체 모드 (Live2D + 음성)
#   ./scripts/start.sh --mode cli   # 텍스트 대화만
#   ./scripts/start.sh --mode voice # 음성만 (렌더링 없음)
#   ./scripts/start.sh --debug      # 디버그 모드

WANI_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# 가상환경 활성화
source "$WANI_DIR/venv/bin/activate"

# Ollama 서비스 확인
if ! pgrep -x "ollama" > /dev/null; then
    echo "⚠️  Ollama 서비스가 실행 중이 아닙니다. 시작합니다..."
    sudo systemctl start ollama
    sleep 3
fi

# 환경 변수 (Ollama 최적화)
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1

# 실행
echo "🐊 와니 AI 시작..."
python3 "$WANI_DIR/main.py" "$@"
