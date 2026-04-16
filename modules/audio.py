"""
와니 AI — 오디오 관리 모듈
마이크 입력 (VAD), 스피커 출력, 립싱크 데이터 추출
"""

import logging
import struct
import math
import time
import wave
import threading
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    AUDIO_SAMPLE_RATE, AUDIO_CHANNELS, AUDIO_CHUNK_SIZE,
    AUDIO_FORMAT_WIDTH, VAD_SILENCE_THRESHOLD, VAD_SILENCE_DURATION,
    VAD_MIN_SPEECH_DURATION, VAD_MAX_RECORD_DURATION, TMP_DIR
)

logger = logging.getLogger(__name__)


class AudioManager:
    """마이크 녹음 + 스피커 재생 + 립싱크 볼륨 추출"""

    def __init__(self):
        self._pyaudio = None
        self._initialized = False
        self._is_playing = False
        self._current_volume = 0.0  # 립싱크용 현재 볼륨 (0.0 ~ 1.0)
        self._play_lock = threading.Lock()

    def _lazy_init(self):
        """PyAudio 초기화 (lazy)"""
        if self._initialized:
            return

        try:
            import pyaudio
            self._pyaudio = pyaudio.PyAudio()
            self._initialized = True

            # 사용 가능한 오디오 장치 로그
            info = self._pyaudio.get_host_api_info_by_index(0)
            num_devices = info.get("deviceCount", 0)
            input_devices = []
            output_devices = []

            for i in range(num_devices):
                dev = self._pyaudio.get_device_info_by_host_api_device_index(0, i)
                if dev.get("maxInputChannels") > 0:
                    input_devices.append(dev.get("name"))
                if dev.get("maxOutputChannels") > 0:
                    output_devices.append(dev.get("name"))

            logger.info(f"오디오 입력 장치: {input_devices}")
            logger.info(f"오디오 출력 장치: {output_devices}")

        except ImportError:
            logger.error("PyAudio가 설치되지 않았습니다. pip install pyaudio")
            raise

    def _calculate_rms(self, data: bytes) -> float:
        """오디오 데이터의 RMS (볼륨 레벨) 계산"""
        count = len(data) // 2  # 16-bit = 2 bytes per sample
        if count == 0:
            return 0.0
        shorts = struct.unpack(f"<{count}h", data)
        sum_squares = sum(s * s for s in shorts)
        rms = math.sqrt(sum_squares / count)
        return rms

    def _rms_to_normalized(self, rms: float, max_rms: float = 10000.0) -> float:
        """RMS 값을 0.0 ~ 1.0 범위로 정규화 (립싱크용)"""
        return min(1.0, rms / max_rms)

    def record_until_silence(self) -> str | None:
        """
        마이크로 녹음. 음성이 감지되면 시작, 
        VAD_SILENCE_DURATION 만큼 묵음이면 녹음 종료.

        Returns:
            녹음된 WAV 파일 경로. 유효한 음성이 없으면 None.
        """
        import pyaudio

        self._lazy_init()

        stream = self._pyaudio.open(
            format=pyaudio.paInt16,
            channels=AUDIO_CHANNELS,
            rate=AUDIO_SAMPLE_RATE,
            input=True,
            frames_per_buffer=AUDIO_CHUNK_SIZE
        )

        logger.info("🎤 음성 감지 대기 중...")

        frames = []
        is_speaking = False
        silence_start = None
        speech_start = None
        record_start = time.time()

        try:
            while True:
                data = stream.read(AUDIO_CHUNK_SIZE, exception_on_overflow=False)
                rms = self._calculate_rms(data)

                elapsed = time.time() - record_start

                if not is_speaking:
                    # 음성 시작 감지
                    if rms > VAD_SILENCE_THRESHOLD:
                        is_speaking = True
                        speech_start = time.time()
                        silence_start = None
                        frames.append(data)
                        logger.debug(f"🗣️ 음성 감지됨 (RMS: {rms:.0f})")

                    # 대기 시간이 너무 길면 중단 (배터리/CPU 절약)
                    if elapsed > 60:
                        logger.debug("60초 대기 초과, 리셋")
                        record_start = time.time()
                        continue
                else:
                    frames.append(data)

                    if rms < VAD_SILENCE_THRESHOLD:
                        # 묵음 감지
                        if silence_start is None:
                            silence_start = time.time()

                        silence_elapsed = time.time() - silence_start
                        if silence_elapsed >= VAD_SILENCE_DURATION:
                            logger.debug(f"🔇 묵음 감지 ({VAD_SILENCE_DURATION}초)")
                            break
                    else:
                        silence_start = None

                    # 최대 녹음 시간 초과
                    speech_elapsed = time.time() - speech_start
                    if speech_elapsed >= VAD_MAX_RECORD_DURATION:
                        logger.debug(f"⏱️ 최대 녹음 시간 도달 ({VAD_MAX_RECORD_DURATION}초)")
                        break

        except Exception as e:
            logger.error(f"녹음 오류: {e}")
            return None
        finally:
            stream.stop_stream()
            stream.close()

        # 최소 음성 길이 미달 체크
        if speech_start and (time.time() - speech_start) < VAD_MIN_SPEECH_DURATION:
            logger.debug("음성이 너무 짧음, 무시")
            return None

        if not frames:
            return None

        # WAV 파일로 저장
        output_path = str(TMP_DIR / "recorded_input.wav")
        try:
            with wave.open(output_path, "wb") as wf:
                wf.setnchannels(AUDIO_CHANNELS)
                wf.setsampwidth(AUDIO_FORMAT_WIDTH)
                wf.setframerate(AUDIO_SAMPLE_RATE)
                wf.writeframes(b"".join(frames))

            duration = len(frames) * AUDIO_CHUNK_SIZE / AUDIO_SAMPLE_RATE
            logger.info(f"🎤 녹음 완료: {duration:.1f}초 → {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"WAV 저장 실패: {e}")
            return None

    def play_audio(self, filepath: str, on_volume_update=None):
        """
        WAV 파일을 스피커로 재생.

        Args:
            filepath: WAV 파일 경로
            on_volume_update: 재생 중 볼륨 콜백 (립싱크용)
                              콜백 인자: (volume: float 0.0~1.0)
        """
        import pyaudio

        self._lazy_init()

        if not Path(filepath).exists():
            logger.error(f"재생할 파일이 없습니다: {filepath}")
            return

        with self._play_lock:
            self._is_playing = True

        try:
            wf = wave.open(filepath, "rb")
            stream = self._pyaudio.open(
                format=self._pyaudio.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True,
                frames_per_buffer=AUDIO_CHUNK_SIZE
            )

            logger.debug(f"🔊 재생 시작: {filepath}")

            data = wf.readframes(AUDIO_CHUNK_SIZE)
            while data and self._is_playing:
                stream.write(data)

                # 립싱크용 볼륨 계산
                if on_volume_update and len(data) >= 2:
                    rms = self._calculate_rms(data)
                    volume = self._rms_to_normalized(rms)
                    self._current_volume = volume
                    on_volume_update(volume)

                data = wf.readframes(AUDIO_CHUNK_SIZE)

            stream.stop_stream()
            stream.close()
            wf.close()

            # 재생 끝나면 볼륨 0
            self._current_volume = 0.0
            if on_volume_update:
                on_volume_update(0.0)

            logger.debug("🔊 재생 완료")

        except Exception as e:
            logger.error(f"오디오 재생 실패: {e}")
        finally:
            with self._play_lock:
                self._is_playing = False

    def play_audio_async(self, filepath: str, on_volume_update=None, on_complete=None):
        """
        WAV 파일을 백그라운드 스레드에서 재생.

        Args:
            filepath: WAV 파일 경로
            on_volume_update: 볼륨 콜백
            on_complete: 재생 완료 콜백
        """
        def _play():
            self.play_audio(filepath, on_volume_update)
            if on_complete:
                on_complete()

        thread = threading.Thread(target=_play, daemon=True)
        thread.start()
        return thread

    def stop_playback(self):
        """현재 재생 중인 오디오 중단"""
        with self._play_lock:
            self._is_playing = False

    @property
    def current_volume(self) -> float:
        """현재 재생 중인 오디오의 볼륨 (0.0 ~ 1.0, 립싱크용)"""
        return self._current_volume

    @property
    def is_playing(self) -> bool:
        """현재 오디오 재생 중인지"""
        with self._play_lock:
            return self._is_playing

    def cleanup(self):
        """리소스 정리"""
        if self._pyaudio:
            self._pyaudio.terminate()
            logger.info("오디오 리소스 해제 완료")
