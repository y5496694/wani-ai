"""
와니 AI 어시스턴트 — 메인 엔트리포인트
라즈베리파이 5 (8GB) 기반 버츄얼 로컬 AI

실행: python main.py
"""

import logging
import sys
import threading
import time
import signal
from pathlib import Path

from config import AppState, CHARACTER_NAME, TMP_DIR
from modules.llm import LLMEngine
from modules.stt import STTEngine
from modules.tts import TTSEngine, TTSEngineDummy
from modules.audio import AudioManager
from modules.renderer import create_renderer

import sys
import io

# ──────────────────────────────────────────────
# 로깅 설정
# ──────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_FILE = Path(__file__).parent / "wani.log"

# Windows cp949 콘솔 깨짐 방지
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8', line_buffering=True)

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
    ]
)
logger = logging.getLogger("wani")


class WaniAssistant:
    """
    와니 AI 어시스턴트 메인 클래스.

    아키텍처:
    - 메인 스레드: Pygame 렌더링 루프 (캐릭터 표시)
    - 서브 스레드: 음성 대화 파이프라인 (녹음 → STT → LLM → TTS → 재생)
    """

    def __init__(self):
        logger.info(f"═══════════════════════════════════════")
        logger.info(f"  🐊 {CHARACTER_NAME} AI 어시스턴트 시작")
        logger.info(f"═══════════════════════════════════════")

        self.state = AppState.IDLE
        self._shutdown = False

        # 모듈 초기화
        logger.info("모듈 초기화 중...")
        self.audio = AudioManager()
        self.stt = STTEngine()

        # TTS 초기화 (Supertonic 실패 시 espeak 폴백)
        try:
            self.tts = TTSEngine()
        except Exception:
            logger.warning("Supertonic TTS 초기화 실패, espeak-ng 폴백으로 전환")
            self.tts = TTSEngineDummy()

        self.llm = LLMEngine()
        self.renderer = None  # 메인 스레드에서 초기화

        # 시그널 핸들러
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        """Ctrl+C 등 시그널 처리"""
        logger.info("종료 시그널 수신")
        self._shutdown = True

    def _voice_pipeline(self):
        """
        음성 대화 파이프라인 (서브 스레드).
        녹음 → STT → LLM → TTS → 재생을 반복.
        """
        logger.info("🎤 음성 파이프라인 시작")

        # TTS 미리 워밍업 (lazy init 트리거)
        try:
            logger.info("TTS 엔진 워밍업...")
            self.tts.synthesize("안녕", str(TMP_DIR / "warmup.wav"))
            logger.info("TTS 워밍업 완료")
        except Exception as e:
            logger.warning(f"TTS 워밍업 실패 (계속 진행): {e}")

        while not self._shutdown:
            try:
                # ── 1. 대기 ──
                if self.state != AppState.IDLE:
                    time.sleep(0.1)
                    continue

                # ── 2. 녹음 ──
                self.state = AppState.LISTENING
                if self.renderer:
                    self.renderer.set_app_state(AppState.LISTENING)

                audio_file = self.audio.record_until_silence()

                if audio_file is None or self._shutdown:
                    self.state = AppState.IDLE
                    if self.renderer:
                        self.renderer.set_app_state(AppState.IDLE)
                    continue

                # ── 3. STT ──
                self.state = AppState.THINKING
                if self.renderer:
                    self.renderer.set_app_state(AppState.THINKING)

                logger.info("🧠 음성 인식 중...")
                user_text = self.stt.transcribe(audio_file)

                if not user_text.strip():
                    logger.info("인식된 텍스트 없음, 대기로 복귀")
                    self.state = AppState.IDLE
                    if self.renderer:
                        self.renderer.set_app_state(AppState.IDLE)
                    continue

                logger.info(f"👤 사용자: {user_text}")

                # ── 4. LLM 응답 생성 ──
                logger.info("🤔 응답 생성 중...")
                emotion, response_text = self.llm.chat(user_text)

                logger.info(f"🐊 {CHARACTER_NAME} [{emotion}]: {response_text}")

                # ── 5. 감정 반영 ──
                if self.renderer:
                    self.renderer.set_emotion(emotion)

                # ── 6. TTS → 음성 출력 ──
                self.state = AppState.SPEAKING
                if self.renderer:
                    self.renderer.set_app_state(AppState.SPEAKING)

                logger.info("🔊 음성 합성 중...")
                tts_file = self.tts.synthesize(response_text)

                if tts_file:
                    # 립싱크 콜백과 함께 재생
                    def on_volume(vol):
                        if self.renderer:
                            self.renderer.set_mouth_open(vol)

                    self.audio.play_audio(tts_file, on_volume_update=on_volume)

                # ── 7. 대기 복귀 ──
                self.state = AppState.IDLE
                if self.renderer:
                    self.renderer.set_emotion("평온")
                    self.renderer.set_app_state(AppState.IDLE)
                    self.renderer.set_mouth_open(0.0)

                # TTS 임시 파일 정리
                self.tts.cleanup_temp_files()

            except Exception as e:
                logger.error(f"음성 파이프라인 오류: {e}", exc_info=True)
                self.state = AppState.IDLE
                if self.renderer:
                    self.renderer.set_app_state(AppState.IDLE)
                time.sleep(1)

        logger.info("음성 파이프라인 종료")

    def run(self):
        """
        메인 실행.
        - 메인 스레드: Pygame 렌더링 루프
        - 서브 스레드: 음성 대화 파이프라인
        """
        try:
            # ── 렌더러 초기화 (메인 스레드에서) ──
            logger.info("렌더러 초기화...")
            self.renderer = create_renderer()
            logger.info("렌더러 준비 완료")

            # ── 음성 파이프라인 스레드 시작 ──
            voice_thread = threading.Thread(
                target=self._voice_pipeline,
                name="VoicePipeline",
                daemon=True
            )
            voice_thread.start()

            # ── 메인 루프: 렌더링 ──
            logger.info(f"🐊 {CHARACTER_NAME} 준비 완료! 말을 걸어주세요~")

            while self.renderer.running and not self._shutdown:
                # 이벤트 처리
                events = self.renderer.handle_events()
                for event_type, event_data in events:
                    if event_type == "quit":
                        self._shutdown = True
                    elif event_type == "touch":
                        x, y = event_data
                        logger.debug(f"터치: ({x}, {y})")

                # 렌더링
                dt = self.renderer.render_frame()

        except KeyboardInterrupt:
            logger.info("Ctrl+C로 종료")
        except Exception as e:
            logger.error(f"메인 루프 오류: {e}", exc_info=True)
        finally:
            self._shutdown = True
            self._cleanup()

    def _cleanup(self):
        """전체 리소스 정리"""
        logger.info("리소스 정리 중...")

        try:
            self.audio.cleanup()
        except Exception:
            pass

        try:
            self.tts.cleanup_temp_files()
        except Exception:
            pass

        try:
            if self.renderer:
                self.renderer.cleanup()
        except Exception:
            pass

        logger.info(f"🐊 {CHARACTER_NAME} 종료. 또 만나~!")


# ──────────────────────────────────────────────
# CLI 모드 (렌더링 없이 텍스트만)
# ──────────────────────────────────────────────

def run_cli_mode():
    """
    렌더링 없이 텍스트 기반 대화 모드.
    디버깅이나 SSH 원격 테스트용.
    """
    logger.info("CLI 모드로 실행")
    llm = LLMEngine()

    print(f"\n🐊 {CHARACTER_NAME} AI (CLI 모드)")
    print("'quit'으로 종료, 'clear'로 대화 초기화\n")

    while True:
        try:
            user_input = input("👤 나: ").strip()
            if not user_input:
                continue
            if user_input.lower() == "quit":
                break
            if user_input.lower() == "clear":
                llm.clear_history()
                print("대화 기록이 초기화되었습니다.\n")
                continue

            emotion, response = llm.chat(user_input)
            print(f"🐊 {CHARACTER_NAME} [{emotion}]: {response}\n")

        except (KeyboardInterrupt, EOFError):
            break

    print(f"\n🐊 {CHARACTER_NAME}: 잘 가~ 또 와!")


# ──────────────────────────────────────────────
# 음성 전용 모드 (렌더링 없이 음성만)
# ──────────────────────────────────────────────

def run_voice_only_mode():
    """
    Pygame 렌더링 없이 음성 대화만 수행.
    헤드리스(모니터 없음) 환경 테스트용.
    """
    logger.info("음성 전용 모드 (렌더링 없음)")

    audio = AudioManager()
    stt = STTEngine()
    llm = LLMEngine()

    try:
        tts = TTSEngine()
    except Exception:
        tts = TTSEngineDummy()

    print(f"\n🐊 {CHARACTER_NAME} AI (음성 모드, Ctrl+C로 종료)")

    try:
        while True:
            print("\n🎤 말씀하세요...")
            audio_file = audio.record_until_silence()

            if audio_file is None:
                continue

            user_text = stt.transcribe(audio_file)
            if not user_text.strip():
                print("(인식 실패)")
                continue

            print(f"👤 나: {user_text}")

            emotion, response = llm.chat(user_text)
            print(f"🐊 {CHARACTER_NAME} [{emotion}]: {response}")

            tts_file = tts.synthesize(response)
            if tts_file:
                audio.play_audio(tts_file)

    except KeyboardInterrupt:
        pass
    finally:
        audio.cleanup()
        print(f"\n🐊 {CHARACTER_NAME}: 잘 가~!")


# ──────────────────────────────────────────────
# 엔트리포인트
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=f"🐊 {CHARACTER_NAME} AI 어시스턴트"
    )
    parser.add_argument(
        "--mode", choices=["full", "cli", "voice"],
        default="full",
        help="실행 모드: full(전체), cli(텍스트만), voice(음성만, 렌더링 없음)"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="디버그 로그 활성화"
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.mode == "cli":
        run_cli_mode()
    elif args.mode == "voice":
        run_voice_only_mode()
    else:
        app = WaniAssistant()
        app.run()
