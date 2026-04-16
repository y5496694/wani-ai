"""
와니 AI — STT (Speech-to-Text) 모듈
Whisper.cpp 기반 한국어 음성 인식
"""

import logging
import subprocess
import tempfile
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    WHISPER_BIN, WHISPER_MODEL, STT_LANGUAGE,
    STT_THREADS, TMP_DIR
)

logger = logging.getLogger(__name__)


class STTEngine:
    """Whisper.cpp 기반 음성 → 텍스트 변환 엔진"""

    def __init__(self):
        self.whisper_bin = str(WHISPER_BIN)
        self.model_path = str(WHISPER_MODEL)
        self.language = STT_LANGUAGE
        self.threads = STT_THREADS
        self._validate_setup()

    def _validate_setup(self):
        """Whisper.cpp 바이너리와 모델이 존재하는지 확인"""
        if not Path(self.whisper_bin).exists():
            logger.warning(
                f"Whisper 바이너리를 찾을 수 없습니다: {self.whisper_bin}\n"
                "setup.sh를 실행하여 whisper.cpp를 빌드하세요."
            )
        if not Path(self.model_path).exists():
            logger.warning(
                f"Whisper 모델을 찾을 수 없습니다: {self.model_path}\n"
                "모델을 다운로드하세요: bash whisper.cpp/models/download-ggml-model.sh tiny"
            )

    def transcribe(self, audio_file: str) -> str:
        """
        WAV 오디오 파일을 한국어 텍스트로 변환.

        Args:
            audio_file: 16kHz, 16-bit, mono WAV 파일 경로

        Returns:
            인식된 한국어 텍스트. 실패 시 빈 문자열.
        """
        if not Path(audio_file).exists():
            logger.error(f"오디오 파일이 없습니다: {audio_file}")
            return ""

        # 윈도우/바이너리 누락 환경을 위한 파이썬 SpeechRecognition 폴백
        if not Path(self.whisper_bin).exists():
            logger.info("Whisper C++ 바이너리 누락. 파이썬 SpeechRecognition(Google API)으로 대체합니다.")
            try:
                import speech_recognition as sr
                r = sr.Recognizer()
                with sr.AudioFile(audio_file) as source:
                    audio = r.record(source)
                # 구글 무료 API 사용 (한국어)
                text = r.recognize_google(audio, language='ko-KR')
                logger.info(f"파이썬 API STT 결과: '{text}'")
                return text
            except Exception as e:
                logger.error(f"파이썬 API STT 실패: {e}")
                return ""

        # 원본 Whisper.cpp 실행 로직
        converted_file = self._ensure_wav_format(audio_file)

        try:
            cmd = [
                self.whisper_bin,
                "-m", self.model_path,
                "-l", self.language,
                "-f", converted_file,
                "--no-timestamps",
                "-t", str(self.threads),
                "--print-special", "false",
                "-otxt",  # 텍스트만 출력
            ]

            logger.debug(f"Whisper 실행: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path(self.whisper_bin).parent)
            )

            if result.returncode != 0:
                logger.error(f"Whisper 오류: {result.stderr}")
                return ""

            # whisper.cpp의 stdout에서 텍스트 추출
            text = result.stdout.strip()
            text = self._clean_output(text)

            logger.info(f"STT 결과: '{text}'")
            return text

        except subprocess.TimeoutExpired:
            logger.error("STT 타임아웃 (30초 초과)")
            return ""
        except FileNotFoundError:
            logger.error(f"Whisper 바이너리를 실행할 수 없습니다: {self.whisper_bin}")
            return ""
        except Exception as e:
            logger.error(f"STT 처리 실패: {e}")
            return ""
        finally:
            if 'converted_file' in locals() and converted_file != audio_file and Path(converted_file).exists():
                try: os.remove(converted_file)
                except: pass

    def _ensure_wav_format(self, audio_file: str) -> str:
        """
        오디오 파일이 whisper.cpp 요구 형식(16kHz, 16-bit, mono)인지 확인.
        필요 시 ffmpeg로 변환.
        """
        try:
            # ffmpeg가 있으면 변환, 없으면 원본 리턴
            output_file = str(TMP_DIR / "stt_input.wav")
            result = subprocess.run([
                "ffmpeg", "-y",
                "-i", audio_file,
                "-ar", "16000",   # 16kHz
                "-ac", "1",       # mono
                "-sample_fmt", "s16",  # 16-bit
                output_file
            ], capture_output=True, timeout=10)

            if result.returncode == 0:
                return output_file
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return audio_file

    def _clean_output(self, text: str) -> str:
        """Whisper.cpp 출력에서 불필요한 문자 제거"""
        import re

        # 타임스탬프 형식 제거: [00:00:00.000 --> 00:00:03.000]
        text = re.sub(r'\[\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}\]\s*', '', text)

        # 특수 토큰 제거
        text = re.sub(r'\[[\w_]+\]', '', text)

        # 여러 줄을 하나로 합치기
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = ' '.join(lines)

        # 앞뒤 공백 제거
        return text.strip()


class STTEngineFallback:
    """
    Whisper.cpp를 사용할 수 없을 때의 대안.
    Gemma4 E2B의 네이티브 오디오 기능 사용 (실험적).
    """

    def __init__(self, ollama_host: str = "http://localhost:11434"):
        self.api_url = f"{ollama_host}/api/generate"
        logger.info("STT 대안 엔진 초기화 (Gemma4 네이티브 오디오)")

    def transcribe(self, audio_file: str) -> str:
        """
        Gemma4 E2B의 네이티브 오디오 인코더를 사용하여 음성 인식.
        (실험적 기능 — Ollama에서 오디오 입력 지원 시 사용 가능)
        """
        import base64
        import requests

        try:
            with open(audio_file, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode()

            response = requests.post(self.api_url, json={
                "model": "gemma4:e2b",
                "prompt": "이 오디오를 한국어로 정확히 받아써줘. 텍스트만 출력해.",
                "audio": [audio_b64],
                "stream": False,
            }, timeout=30)

            if response.status_code == 200:
                data = response.json()
                return data.get("response", "").strip()

        except Exception as e:
            logger.error(f"Gemma4 오디오 STT 실패: {e}")

        return ""
