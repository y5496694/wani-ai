"""
와니 AI — LLM 모듈
Gemma4 E2B via Ollama API 연동
"""

import json
import logging
import re
import requests
from typing import Generator

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
from config import (
    OLLAMA_HOST, OLLAMA_MODEL, LLM_CONTEXT_LENGTH,
    LLM_TEMPERATURE, LLM_MAX_HISTORY, SYSTEM_PROMPT
)

logger = logging.getLogger(__name__)


class LLMEngine:
    """Gemma4 E2B 기반 대화 엔진"""

    def __init__(self):
        self.api_url = f"{OLLAMA_HOST}/api/chat"
        self.model = OLLAMA_MODEL
        self.conversation_history: list[dict] = []
        self._system_message = {"role": "system", "content": SYSTEM_PROMPT}
        logger.info(f"LLM 엔진 초기화: {self.model}")

    def _check_server(self) -> bool:
        """Ollama 서버가 실행 중인지 확인"""
        try:
            resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
            return resp.status_code == 200
        except requests.ConnectionError:
            return False

    def _trim_history(self):
        """대화 기록을 LLM_MAX_HISTORY 개수로 제한 (메모리 관리)"""
        if len(self.conversation_history) > LLM_MAX_HISTORY:
            # 가장 오래된 대화부터 제거 (시스템 프롬프트는 별도)
            excess = len(self.conversation_history) - LLM_MAX_HISTORY
            self.conversation_history = self.conversation_history[excess:]
            logger.debug(f"대화 기록 트리밍: {excess}개 제거")

    def _parse_emotion(self, text: str) -> tuple[str, str]:
        """
        응답에서 감정 태그를 파싱.
        "[기쁨] 안녕!" → ("기쁨", "안녕!")
        "안녕!" → ("평온", "안녕!")
        """
        pattern = r"^\[(\w+)\]\s*(.*)"
        match = re.match(pattern, text, re.DOTALL)
        if match:
            emotion = match.group(1)
            content = match.group(2).strip()
            valid_emotions = {"기쁨", "슬픔", "놀람", "분노", "평온", "부끄러움"}
            if emotion in valid_emotions:
                return emotion, content
        return "평온", text.strip()

    def chat(self, user_input: str) -> tuple[str, str]:
        """
        사용자 입력에 대한 응답 생성 (동기 방식).

        Args:
            user_input: 사용자가 말한 텍스트

        Returns:
            (감정, 응답텍스트) 튜플
        """
        if not self._check_server():
            logger.error("Ollama 서버에 연결할 수 없습니다")
            return "슬픔", "으으... 지금 뇌가 작동을 안 해..."

        # 대화 기록에 사용자 메시지 추가
        self.conversation_history.append({
            "role": "user",
            "content": user_input
        })
        self._trim_history()

        # 요청 빌드
        messages = [self._system_message] + self.conversation_history

        try:
            response = requests.post(self.api_url, json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "num_ctx": LLM_CONTEXT_LENGTH,
                    "temperature": LLM_TEMPERATURE,
                }
            }, timeout=60)

            if response.status_code != 200:
                logger.error(f"Ollama API 오류: {response.status_code}")
                return "슬픔", "미안, 뭔가 잘못됐어..."

            data = response.json()
            full_text = data.get("message", {}).get("content", "")
            logger.info(f"LLM 원본 응답: {full_text[:100]}...")

            # 감정 파싱
            emotion, clean_text = self._parse_emotion(full_text)

            # 대화 기록에 어시스턴트 응답 추가
            self.conversation_history.append({
                "role": "assistant",
                "content": full_text
            })

            return emotion, clean_text

        except requests.Timeout:
            logger.error("LLM 응답 타임아웃")
            return "슬픔", "으... 생각이 너무 오래 걸렸어..."
        except Exception as e:
            logger.error(f"LLM 요청 실패: {e}")
            return "슬픔", "미안, 뭔가 문제가 생겼어..."

    def chat_stream(self, user_input: str) -> Generator[tuple[str | None, str], None, None]:
        """
        사용자 입력에 대한 응답을 스트리밍으로 생성.
        첫 번째 yield에서 감정 태그를 반환하고,
        이후 yield에서는 텍스트 청크를 반환.
        TTS 스트리밍 파이프라인에 사용.

        Yields:
            (감정 또는 None, 텍스트 청크)
        """
        if not self._check_server():
            yield "슬픔", "으으... 지금 뇌가 작동을 안 해..."
            return

        self.conversation_history.append({
            "role": "user",
            "content": user_input
        })
        self._trim_history()
        messages = [self._system_message] + self.conversation_history

        try:
            response = requests.post(self.api_url, json={
                "model": self.model,
                "messages": messages,
                "stream": True,
                "options": {
                    "num_ctx": LLM_CONTEXT_LENGTH,
                    "temperature": LLM_TEMPERATURE,
                }
            }, stream=True, timeout=120)

            full_text = ""
            emotion_parsed = False
            sentence_buffer = ""

            for line in response.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                full_text += token

                if not emotion_parsed:
                    # 감정 태그가 완성될 때까지 버퍼링
                    if "]" in full_text:
                        emotion, text_start = self._parse_emotion(full_text)
                        emotion_parsed = True
                        yield emotion, ""
                        sentence_buffer = text_start
                else:
                    sentence_buffer += token

                # 문장 단위로 yield (TTS가 문장 단위로 처리)
                if emotion_parsed and sentence_buffer:
                    # 문장 구분자 체크
                    for sep in [".", "!", "?", "~", "。", "！", "？"]:
                        if sep in sentence_buffer:
                            parts = sentence_buffer.split(sep, 1)
                            complete_sentence = parts[0] + sep
                            sentence_buffer = parts[1] if len(parts) > 1 else ""
                            yield None, complete_sentence.strip()
                            break

            # 남은 버퍼 전송
            if sentence_buffer.strip():
                if not emotion_parsed:
                    emotion, text = self._parse_emotion(sentence_buffer)
                    yield emotion, text
                else:
                    yield None, sentence_buffer.strip()

            # 대화 기록에 추가
            self.conversation_history.append({
                "role": "assistant",
                "content": full_text
            })

        except Exception as e:
            logger.error(f"LLM 스트리밍 실패: {e}")
            yield "슬픔", "미안, 뭔가 문제가 생겼어..."

    def clear_history(self):
        """대화 기록 초기화"""
        self.conversation_history.clear()
        logger.info("대화 기록이 초기화되었습니다")

    def get_history_length(self) -> int:
        """현재 대화 기록 수"""
        return len(self.conversation_history)
