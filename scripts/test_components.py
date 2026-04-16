#!/usr/bin/env python3
"""
와니 AI — 컴포넌트 단위 테스트
Pi에서 각 모듈을 개별적으로 테스트합니다.

사용법:
    python3 scripts/test_components.py --all
    python3 scripts/test_components.py --llm
    python3 scripts/test_components.py --stt
    python3 scripts/test_components.py --tts
    python3 scripts/test_components.py --audio
    python3 scripts/test_components.py --render
"""

import argparse
import sys
import time
import os

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_llm():
    """LLM (Gemma4 E2B via Ollama) 테스트"""
    print("\n🧠 ═══ LLM 테스트 ═══")
    from modules.llm import LLMEngine

    llm = LLMEngine()

    # 서버 연결 확인
    if not llm._check_server():
        print("❌ Ollama 서버에 연결할 수 없습니다.")
        print("   → sudo systemctl start ollama")
        return False

    print("✅ Ollama 서버 연결 OK")

    # 대화 테스트
    print("\n📨 테스트 질문: '안녕! 자기소개 해줘'")
    start = time.time()
    emotion, response = llm.chat("안녕! 자기소개 해줘")
    elapsed = time.time() - start

    print(f"📬 감정: [{emotion}]")
    print(f"📬 응답: {response}")
    print(f"⏱️ 소요 시간: {elapsed:.1f}초")

    if response and len(response) > 5:
        print("✅ LLM 테스트 통과!")
        return True
    else:
        print("❌ LLM 응답이 너무 짧거나 없음")
        return False


def test_stt():
    """STT (Whisper.cpp) 테스트"""
    print("\n🗣️ ═══ STT 테스트 ═══")
    from modules.stt import STTEngine
    from modules.audio import AudioManager

    stt = STTEngine()

    # 바이너리 확인
    if not os.path.exists(stt.whisper_bin):
        print(f"❌ Whisper 바이너리 없음: {stt.whisper_bin}")
        return False
    print("✅ Whisper 바이너리 OK")

    if not os.path.exists(stt.model_path):
        print(f"❌ Whisper 모델 없음: {stt.model_path}")
        return False
    print("✅ Whisper 모델 OK")

    # 녹음 + 인식 테스트
    print("\n🎤 3초간 한국어로 말씀해주세요...")
    audio = AudioManager()

    # 간단한 녹음 (3초)
    import pyaudio
    import wave

    audio._lazy_init()
    stream = audio._pyaudio.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        frames_per_buffer=1024
    )

    frames = []
    for _ in range(int(16000 / 1024 * 3)):  # 3초
        data = stream.read(1024, exception_on_overflow=False)
        frames.append(data)
    stream.stop_stream()
    stream.close()

    # WAV 저장
    test_wav = "/tmp/wani_stt_test.wav"
    with wave.open(test_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"".join(frames))

    print("🔄 음성 인식 중...")
    start = time.time()
    text = stt.transcribe(test_wav)
    elapsed = time.time() - start

    print(f"📝 인식 결과: '{text}'")
    print(f"⏱️ 소요 시간: {elapsed:.1f}초")

    if text:
        print("✅ STT 테스트 통과!")
        return True
    else:
        print("⚠️ 인식된 텍스트 없음 (말을 안 했거나 인식 실패)")
        return False


def test_tts():
    """TTS (MeloTTS) 테스트"""
    print("\n🔊 ═══ TTS 테스트 ═══")

    test_text = "안녕하세요! 나는 와니, 귀여운 악어 소녀야!"
    output_file = "/tmp/wani_tts_test.wav"

    print(f"📝 합성 텍스트: '{test_text}'")

    try:
        from modules.tts import TTSEngine
        tts = TTSEngine()

        print("🔄 MeloTTS 로딩 + 합성 중... (첫 실행 시 30초 이상 소요)")
        start = time.time()
        result = tts.synthesize(test_text, output_file)
        elapsed = time.time() - start

        if result and os.path.exists(result):
            size = os.path.getsize(result) / 1024
            print(f"✅ TTS 합성 완료: {size:.0f}KB, {elapsed:.1f}초")

            # 재생
            print("🔊 재생 중...")
            from modules.audio import AudioManager
            audio = AudioManager()
            audio.play_audio(result)
            print("✅ TTS 테스트 통과!")
            return True
        else:
            print("❌ TTS 합성 실패")
            return False

    except ImportError as e:
        print(f"❌ MeloTTS 미설치: {e}")
        print("   → pip install melo-tts")

        # espeak 폴백 테스트
        print("\n🔄 espeak-ng 폴백 테스트...")
        try:
            from modules.tts import TTSEngineDummy
            tts = TTSEngineDummy()
            result = tts.synthesize(test_text, output_file)
            if result:
                print("✅ espeak-ng 폴백 동작 (음질 낮음)")
                return True
        except Exception:
            pass

        return False


def test_audio():
    """오디오 입출력 테스트"""
    print("\n🎤 ═══ 오디오 테스트 ═══")
    from modules.audio import AudioManager

    audio = AudioManager()

    # 장치 확인
    print("🔄 오디오 장치 확인...")
    audio._lazy_init()
    print("✅ PyAudio 초기화 OK")

    # 녹음 테스트
    print("\n🎤 VAD 테스트 — 아무 말이나 해주세요 (5초 후 타임아웃)...")
    print("   (묵음이면 None 반환)")

    # 임시로 최대 녹음 시간을 짧게
    import config
    original_max = config.VAD_MAX_RECORD_DURATION
    config.VAD_MAX_RECORD_DURATION = 5.0

    result = audio.record_until_silence()
    config.VAD_MAX_RECORD_DURATION = original_max

    if result:
        size = os.path.getsize(result) / 1024
        print(f"✅ 녹음 성공: {size:.0f}KB → {result}")
    else:
        print("⚠️ 음성이 감지되지 않음 (정상일 수 있음)")

    audio.cleanup()
    print("✅ 오디오 테스트 완료")
    return True


def test_renderer():
    """렌더러 테스트 (5초간 화면 표시)"""
    print("\n🐊 ═══ 렌더러 테스트 ═══")

    from modules.renderer import create_renderer
    from config import AppState

    try:
        renderer = create_renderer()
        print(f"✅ 렌더러 초기화: {type(renderer).__name__}")

        print("📺 5초간 렌더링 테스트...")
        start = time.time()

        emotions = ["평온", "기쁨", "슬픔", "놀람", "부끄러움"]
        emotion_idx = 0

        while time.time() - start < 5.0 and renderer.running:
            events = renderer.handle_events()
            for et, ed in events:
                if et == "quit":
                    renderer.running = False

            # 1초마다 감정 전환
            new_idx = int(time.time() - start) % len(emotions)
            if new_idx != emotion_idx:
                emotion_idx = new_idx
                renderer.set_emotion(emotions[emotion_idx])
                renderer.set_app_state(
                    [AppState.IDLE, AppState.LISTENING, AppState.THINKING,
                     AppState.SPEAKING, AppState.IDLE][emotion_idx]
                )
                print(f"  감정: {emotions[emotion_idx]}")

            renderer.render_frame()

        renderer.cleanup()
        print("✅ 렌더러 테스트 통과!")
        return True

    except Exception as e:
        print(f"❌ 렌더러 오류: {e}")
        return False


def test_all():
    """전체 테스트"""
    print("🐊 와니 AI — 전체 컴포넌트 테스트")
    print("═══════════════════════════════════════════")

    results = {}

    results["LLM"] = test_llm()
    results["Audio"] = test_audio()
    results["STT"] = test_stt()
    results["TTS"] = test_tts()

    # 렌더러는 DISPLAY가 있을 때만
    if os.environ.get("DISPLAY"):
        results["Renderer"] = test_renderer()
    else:
        print("\n📺 ═══ 렌더러 테스트 ═══")
        print("⚠️ DISPLAY 환경변수 없음 — 렌더러 테스트 건너뜀")
        results["Renderer"] = None

    # 결과 요약
    print("\n═══════════════════════════════════════════")
    print("📋 테스트 결과 요약:")
    for name, result in results.items():
        if result is True:
            print(f"  ✅ {name}")
        elif result is False:
            print(f"  ❌ {name}")
        else:
            print(f"  ⏭️ {name} (건너뜀)")
    print("═══════════════════════════════════════════")

    return all(v is not False for v in results.values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="🐊 와니 AI 컴포넌트 테스트")
    parser.add_argument("--all", action="store_true", help="전체 테스트")
    parser.add_argument("--llm", action="store_true", help="LLM 테스트")
    parser.add_argument("--stt", action="store_true", help="STT 테스트")
    parser.add_argument("--tts", action="store_true", help="TTS 테스트")
    parser.add_argument("--audio", action="store_true", help="오디오 테스트")
    parser.add_argument("--render", action="store_true", help="렌더러 테스트")

    args = parser.parse_args()

    if args.llm:
        test_llm()
    elif args.stt:
        test_stt()
    elif args.tts:
        test_tts()
    elif args.audio:
        test_audio()
    elif args.render:
        test_renderer()
    else:
        test_all()
