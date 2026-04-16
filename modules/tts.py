"""
와니 AI — TTS (Text-to-Speech) 모듈
Supertone Supertonic 기반 고성능 온디바이스 음성 합성
"""

import logging
import os
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    TTS_ENGINE_TYPE, TTS_SPEED, TTS_OUTPUT_FILE, TMP_DIR,
    SUPERTONIC_ASSETS_DIR, SUPERTONIC_VOICE_STYLE
)

logger = logging.getLogger(__name__)


class TTSEngine:
    """Supertone Supertonic 기반 한국어 음성 합성 엔진"""

    def __init__(self):
        self._engine = None
        self._initialized = False
        
        logger.info(f"TTS 엔진 생성 (타입: {TTS_ENGINE_TYPE}, lazy 초기화)")

    def _lazy_init(self):
        """첫 사용 시 Supertonic 엔진 및 모델 로드"""
        if self._initialized:
            return

        try:
            logger.info("Supertonic TTS 엔진 로딩 중...")
            start = time.time()

            # supertonic 라이브러리 임포트
            from supertonic import TTS, Style

            # 에셋 경로 확인
            if not SUPERTONIC_ASSETS_DIR.exists():
                raise FileNotFoundError(
                    f"Supertonic 에셋을 찾을 수 없습니다: {SUPERTONIC_ASSETS_DIR}\n"
                    "scripts/setup_supertonic.sh를 먼저 실행해주세요."
                )

            # 엔진 초기화 (model_dir 지정)
            self._engine = TTS(model_dir=str(SUPERTONIC_ASSETS_DIR))
            
            # 목소리 스타일 설정 (F2) - 에셋 폴더 내의 .json 파일을 로드
            style_path = SUPERTONIC_ASSETS_DIR / "voice_styles" / f"{SUPERTONIC_VOICE_STYLE}.json"
            if not style_path.exists():
                style_path = SUPERTONIC_ASSETS_DIR / f"{SUPERTONIC_VOICE_STYLE}.json"
            
            self._style = Style(str(style_path))
            
            self._initialized = True
            elapsed = time.time() - start
            logger.info(f"Supertonic 엔진 로드 완료 ({elapsed:.1f}초)")

        except ImportError:
            logger.error("supertonic 패키지가 설치되지 않았습니다. pip install supertonic")
            raise
        except Exception as e:
            logger.error(f"Supertonic 초기화 실패: {e}")
            raise

    def synthesize(self, text: str, output_path: str | None = None) -> str:
        """
        텍스트를 음성 파일로 변환 (Supertonic).

        Args:
            text: 합성할 텍스트
            output_path: 출력 WAV 파일 경로

        Returns:
            생성된 WAV 파일의 절대 경로
        """
        self._lazy_init()

        if not text or not text.strip():
            return ""

        if output_path is None:
            output_path = str(TTS_OUTPUT_FILE)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        try:
            start = time.time()

            # Supertonic 합성 실행
            # voice_style은 'F2'와 같은 문자열 또는 'F2.json' 경로일 수 있음
            # 에셋 디렉토리 내 voice_styles 또는 root에서 보이스 파일 검색
            voice_path = SUPERTONIC_ASSETS_DIR / "voice_styles" / f"{SUPERTONIC_VOICE_STYLE}.json"
            if not voice_path.exists():
                voice_path = SUPERTONIC_ASSETS_DIR / f"{SUPERTONIC_VOICE_STYLE}.json"

            # 합성 수행
            audio = self._engine.synthesize(
                text, 
                style=self._style,
                speed=TTS_SPEED
            )

            # 파일로 저장 (SupertonicAudio 객체에 save 메서드가 있다고 가정하거나, 
            # 직접 scipy/wave로 저장)
            if hasattr(audio, 'save'):
                audio.save(output_path)
            else:
                # 만약 numpy array를 반환한다면 직접 저장 (fallback)
                self._save_wav(audio, output_path)

            elapsed = time.time() - start
            logger.info(f"Supertonic TTS 합성 완료: '{text[:20]}...' → {elapsed:.2f}초")

            return output_path

        except Exception as e:
            logger.error(f"Supertonic TTS 합성 실패: {e}")
            return ""

    def _save_wav(self, audio_data, path):
        """Numpy 형태의 오디오 데이터를 WAV 파일로 저장 (필요 시)"""
        import wave
        import numpy as np
        
        # Supertonic 샘플 레이트는 보통 24000 또는 44100
        # 실제 엔진 설정을 따름 (라이브러리 기본값 24000 가정)
        sample_rate = 24000 
        
        with wave.open(path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            # data를 16-bit PCM으로 변환
            if isinstance(audio_data, np.ndarray):
                pcm_data = (audio_data * 32767).astype(np.int16).tobytes()
                wf.writeframes(pcm_data)

    def synthesize_sentences(self, sentences: list[str]) -> list[str]:
        """여러 문장을 개별 파일로 합성"""
        output_files = []
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue
            output_path = str(TMP_DIR / f"wani_tts_{i:03d}.wav")
            result = self.synthesize(sentence, output_path)
            if result:
                output_files.append(result)
        return output_files

    def cleanup_temp_files(self):
        """임시 파일 삭제"""
        try:
            for f in TMP_DIR.glob("wani_tts_*.wav"):
                os.remove(f)
            if Path(str(TTS_OUTPUT_FILE)).exists():
                os.remove(str(TTS_OUTPUT_FILE))
        except Exception:
            pass

    @property
    def is_ready(self) -> bool:
        return self._initialized


class TTSEngineDummy:
    """Supertone 초기화 실패 시 사용하는 기본 espeak 폴백 엔진"""
    def __init__(self):
        logger.info("더미 TTS 엔진 생성 (espeak-ng 사용)")

    def synthesize(self, text: str, output_path: str | None = None) -> str:
        import os
        if output_path is None:
            output_path = str(TTS_OUTPUT_FILE)
        
        # espeak-ng를 사용하여 단순 합성
        os.system(f"espeak-ng -v ko -s 150 -w {output_path} \"{text}\"")
        return output_path

    def synthesize_sentences(self, sentences: list[str]) -> list[str]:
        output_files = []
        for i, s in enumerate(sentences):
            path = str(TMP_DIR / f"wani_tts_{i:03d}.wav")
            self.synthesize(s, path)
            output_files.append(path)
        return output_files

    def cleanup_temp_files(self):
        try:
            for f in TMP_DIR.glob("wani_tts_*.wav"):
                os.remove(f)
        except Exception:
            pass
