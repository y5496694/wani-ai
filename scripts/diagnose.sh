#!/bin/bash
# ═══════════════════════════════════════════
#  🐊 와니 AI — 시스템 진단 스크립트
# ═══════════════════════════════════════════
# Pi에서 실행: ./scripts/diagnose.sh
# 모든 구성요소가 정상인지 한눈에 확인

set -e
WANI_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "═══════════════════════════════════════════"
echo "  🐊 와니 AI — 시스템 진단"
echo "═══════════════════════════════════════════"
echo ""

PASS="✅"
FAIL="❌"
WARN="⚠️"
errors=0

# ── 1. 시스템 정보 ──
echo "📊 [시스템 정보]"
echo "  OS: $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '"')"
echo "  아키텍처: $(uname -m)"
echo "  커널: $(uname -r)"

# RAM
total_ram=$(free -m | awk '/Mem:/{print $2}')
free_ram=$(free -m | awk '/Mem:/{print $7}')
echo "  RAM: ${free_ram}MB 사용 가능 / ${total_ram}MB 전체"
if [ "$total_ram" -ge 7000 ]; then
    echo "  $PASS RAM 충분 (8GB)"
else
    echo "  $WARN RAM이 8GB 미만입니다"
fi

# 스왑
swap_total=$(free -m | awk '/Swap:/{print $2}')
echo "  스왑: ${swap_total}MB"
if [ "$swap_total" -ge 2000 ]; then
    echo "  $PASS 스왑 충분"
else
    echo "  $WARN 스왑이 2GB 미만 — setup.sh로 확대 권장"
    ((errors++))
fi

# CPU 온도
if [ -f /sys/class/thermal/thermal_zone0/temp ]; then
    temp=$(($(cat /sys/class/thermal/thermal_zone0/temp) / 1000))
    echo "  CPU 온도: ${temp}°C"
    if [ "$temp" -ge 70 ]; then
        echo "  $WARN CPU 온도가 높습니다! 쿨링 확인"
    else
        echo "  $PASS CPU 온도 정상"
    fi
fi

echo ""

# ── 2. Python ──
echo "🐍 [Python 환경]"
if [ -f "$WANI_DIR/venv/bin/python3" ]; then
    echo "  $PASS 가상환경: $WANI_DIR/venv"
    source "$WANI_DIR/venv/bin/activate"
    echo "  Python: $(python3 --version)"
else
    echo "  $FAIL 가상환경 없음 — setup.sh 실행 필요"
    ((errors++))
fi

# Python 패키지 확인
for pkg in requests pyaudio pygame numpy; do
    if python3 -c "import $pkg" 2>/dev/null; then
        echo "  $PASS $pkg"
    else
        echo "  $FAIL $pkg 미설치"
        ((errors++))
    fi
done

# MeloTTS
if python3 -c "from melo.api import TTS" 2>/dev/null; then
    echo "  $PASS melo-tts"
else
    echo "  $FAIL melo-tts 미설치 — pip install melo-tts"
    ((errors++))
fi

echo ""

# ── 3. Ollama ──
echo "🧠 [Ollama / LLM]"
if command -v ollama &>/dev/null; then
    echo "  $PASS Ollama 설치됨: $(ollama --version 2>/dev/null | head -1)"
else
    echo "  $FAIL Ollama 미설치"
    ((errors++))
fi

if pgrep -x "ollama" > /dev/null; then
    echo "  $PASS Ollama 서비스 실행 중"
else
    echo "  $WARN Ollama 서비스 정지 — sudo systemctl start ollama"
fi

# 모델 확인
if ollama list 2>/dev/null | grep -q "gemma4:e2b"; then
    echo "  $PASS Gemma4 E2B 모델 설치됨"
else
    echo "  $FAIL Gemma4 E2B 모델 없음 — ollama pull gemma4:e2b"
    ((errors++))
fi

echo ""

# ── 4. Whisper.cpp ──
echo "🗣️ [Whisper.cpp / STT]"
if [ -f "$WANI_DIR/whisper.cpp/main" ]; then
    echo "  $PASS Whisper 바이너리 존재"
else
    echo "  $FAIL Whisper 바이너리 없음 — setup.sh 실행 필요"
    ((errors++))
fi

if [ -f "$WANI_DIR/whisper.cpp/models/ggml-tiny.bin" ]; then
    size=$(du -h "$WANI_DIR/whisper.cpp/models/ggml-tiny.bin" | cut -f1)
    echo "  $PASS Whisper tiny 모델 ($size)"
else
    echo "  $FAIL Whisper tiny 모델 없음"
    ((errors++))
fi

echo ""

# ── 5. 오디오 ──
echo "🎤 [오디오 장치]"
# 입력 장치
input_count=$(arecord -l 2>/dev/null | grep -c "card" || echo 0)
if [ "$input_count" -gt 0 ]; then
    echo "  $PASS 입력 장치 ${input_count}개 감지"
    arecord -l 2>/dev/null | grep "card" | while read line; do
        echo "      $line"
    done
else
    echo "  $FAIL 마이크가 감지되지 않음"
    ((errors++))
fi

# 출력 장치
output_count=$(aplay -l 2>/dev/null | grep -c "card" || echo 0)
if [ "$output_count" -gt 0 ]; then
    echo "  $PASS 출력 장치 ${output_count}개 감지"
else
    echo "  $FAIL 스피커가 감지되지 않음"
    ((errors++))
fi

echo ""

# ── 6. 디스플레이 ──
echo "📺 [디스플레이]"
if [ -n "$DISPLAY" ]; then
    echo "  $PASS DISPLAY=$DISPLAY"
else
    echo "  $WARN DISPLAY 환경변수 없음 (headless 모드?)"
fi

echo ""

# ── 7. Live2D 모델 ──
echo "🐊 [Live2D 모델]"
if [ -f "$WANI_DIR/models/wani/wani.model3.json" ]; then
    echo "  $PASS Live2D 모델 발견"
else
    echo "  $WARN Live2D 모델 없음 (스프라이트 모드로 동작)"
fi

if [ -f "$WANI_DIR/models/wani/wani_sprite.png" ]; then
    echo "  $PASS 스프라이트 이미지 발견"
else
    echo "  $WARN 스프라이트 이미지 없음 — 캐릭터 이미지를 wani_sprite.png로 배치"
fi

echo ""

# ── 8. 디스크 ──
echo "💾 [디스크]"
disk_avail=$(df -h "$WANI_DIR" | tail -1 | awk '{print $4}')
echo "  사용 가능: $disk_avail"

# NVMe SSD 확인
if lsblk | grep -q "nvme"; then
    echo "  $PASS NVMe SSD 감지"
else
    echo "  $WARN NVMe SSD 없음 — 성능을 위해 SSD 권장"
fi

echo ""

# ── 결과 ──
echo "═══════════════════════════════════════════"
if [ "$errors" -eq 0 ]; then
    echo "  🎉 모든 검사 통과! 와니를 실행할 준비가 되었습니다."
    echo "  실행: ./scripts/start.sh"
else
    echo "  ⚠️  ${errors}개 문제 발견. 위의 ❌ 항목을 확인하세요."
fi
echo "═══════════════════════════════════════════"
