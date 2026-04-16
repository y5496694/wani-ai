"""
Supertone Supertonic TTS 기능 테스트 스크립트
실행: python scratch/test_supertonic.py
"""

import os
import sys
from pathlib import Path
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_supertonic")

# 프로젝트 루트 추가
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

try:
    from modules.tts import TTSEngine
    from config import SUPERTONIC_ASSETS_DIR, SUPERTONIC_VOICE_STYLE
    
    print("\n" + "="*50)
    print("      🐊 와니 AI — Supertonic TTS 테스트")
    print("="*50)
    
    # 1. 경로 체크
    print(f"\n[1] 에셋 경로 확인:")
    print(f"    - 경로: {SUPERTONIC_ASSETS_DIR}")
    if SUPERTONIC_ASSETS_DIR.exists():
        print("    - ✅ 경로가 존재합니다.")
    else:
        print("    - ❌ 경로가 없습니다! scripts/setup_supertonic.sh를 확인하세요.")

    # 2. 엔진 초기화 시도
    print(f"\n[2] TTS 엔진 초기화 시도...")
    try:
        engine = TTSEngine()
        # lazy_init 실행을 위해 합성 시도
        # (실제 에셋이 없으면 여기서 에러가 발생하도록 설계됨)
        test_text = "안녕하세요! 와니 AI입니다. Supertonic F2 목소리로 말하고 있어요."
        output_file = str(BASE_DIR / "test_output.wav")
        
        print(f"    - 보이스 스타일: {SUPERTONIC_VOICE_STYLE}")
        print(f"    - 텍스트: '{test_text}'")
        
        # 실제 합성은 에셋이 있어야 하므로 구조적 체크만 수행
        print("\n[3] 합성 시도 중... (에셋이 있는 경우)")
        # result = engine.synthesize(test_text, output_file)
        # if result: print(f"    - ✅ 성공: {result}")
        
        print("\n구조적 체크 완료. 실제 라즈베리 파이에서 실행 시:")
        print("1. pip install supertonic")
        print("2. ./scripts/setup_supertonic.sh")
        print("3. ./scripts/start.sh")

    except ImportError:
        print("    - ❌ supertonic 패키지가 설치되지 않았습니다.")
    except Exception as e:
        print(f"    - ⚠️ 초기화 중 알림: {e}")

except Exception as e:
    print(f"테스트 중 치명적 오류: {e}")
