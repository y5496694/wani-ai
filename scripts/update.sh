#!/bin/bash
# ═══════════════════════════════════════════════
#  🐊 와니 AI — Git 동기화 및 업데이트 도구
# ═══════════════════════════════════════════════

set -e

WANI_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WANI_DIR"

echo "🔄 [1/3] 최신 코드 가져오기 (Git Pull)..."
# 로컬 변경사항이 있을 경우를 대비해 스태시(Stash) 후 풀(Pull) 시도
git stash save "Auto-stash before update" || true
git pull origin main
git stash pop || true

echo ""
echo "📚 [2/3] 파이썬 의존성 업데이트..."
if [ -d "$WANI_DIR/venv" ]; then
    source "$WANI_DIR/venv/bin/activate"
    pip install -r requirements.txt
else
    echo "  ⚠️ 가상환경이 없습니다. setup.sh를 먼저 실행하세요."
fi

echo ""
echo "📁 [3/3] 에셋 상태 확인..."
# 모델 폴더는 .gitignore에 등록되어 있어 git pull로 삭제되지 않습니다.
if [ -d "$WANI_DIR/models/supertonic/assets" ]; then
    echo "  ✅ Supertonic 에셋 보존됨."
else
    echo "  ⚠️ Supertonic 에셋이 없습니다. setup.sh를 실행해 주세요."
fi

echo ""
echo "✅ 업데이트가 완료되었습니다!"
echo "   이제 ./scripts/start.sh 로 다시 시작할 수 있습니다."
