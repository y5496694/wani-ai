"""
와니 AI — Live2D 렌더러 모듈
Pygame + OpenGL + live2d-py 기반 캐릭터 렌더링

Live2D 모델이 없을 때는 스프라이트 기반 폴백 렌더러 사용.
"""

import logging
import math
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, TARGET_FPS,
    WINDOW_TITLE, BACKGROUND_COLOR, LIVE2D_MODEL_DIR,
    EMOTION_MAP, AppState
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Live2D 렌더러 (live2d-py 사용)
# ──────────────────────────────────────────────

class Live2DRenderer:
    """
    live2d-py + Pygame/OpenGL 기반 캐릭터 렌더러.
    Live2D 모델 파일(.model3.json)이 필요합니다.
    """

    def __init__(self):
        self.screen = None
        self.clock = None
        self.model = None
        self.running = False

        # 현재 상태
        self._current_emotion = "평온"
        self._mouth_open = 0.0
        self._app_state = AppState.IDLE
        self._idle_timer = 0.0

    def initialize(self) -> bool:
        """Pygame + Live2D 초기화"""
        try:
            import pygame
            from pygame.locals import DOUBLEBUF, OPENGL

            pygame.init()
            self.screen = pygame.display.set_mode(
                (SCREEN_WIDTH, SCREEN_HEIGHT),
                DOUBLEBUF | OPENGL
            )
            pygame.display.set_caption(WINDOW_TITLE)
            self.clock = pygame.time.Clock()

            # Live2D 초기화
            import live2d.v3 as live2d_lib
            live2d_lib.init()

            # 모델 로드
            model_json = LIVE2D_MODEL_DIR / "wani.model3.json"
            if not model_json.exists():
                logger.error(f"Live2D 모델 파일이 없습니다: {model_json}")
                return False

            self.model = live2d_lib.LAppModel()
            self.model.LoadModelJson(str(model_json))
            self.model.Resize(SCREEN_WIDTH, SCREEN_HEIGHT)

            self.running = True
            logger.info("Live2D 렌더러 초기화 완료")
            return True

        except ImportError as e:
            logger.error(f"Live2D 의존성 누락: {e}")
            return False
        except Exception as e:
            logger.error(f"Live2D 초기화 실패: {e}")
            return False

    def set_emotion(self, emotion: str):
        """감정에 따른 표정/모션 적용"""
        if emotion == self._current_emotion:
            return

        self._current_emotion = emotion
        emotion_data = EMOTION_MAP.get(emotion, EMOTION_MAP["평온"])

        if self.model is None:
            return

        try:
            # 파라미터 오버라이드 적용
            for param, value in emotion_data.get("param_overrides", {}).items():
                self.model.SetParameterValue(param, value)

            logger.debug(f"감정 전환: {emotion}")
        except Exception as e:
            logger.warning(f"감정 적용 실패: {e}")

    def set_mouth_open(self, value: float):
        """
        입 열기 값 설정 (립싱크용).
        Args:
            value: 0.0 (닫힘) ~ 1.0 (열림)
        """
        self._mouth_open = max(0.0, min(1.0, value))
        if self.model:
            try:
                self.model.SetParameterValue("ParamMouthOpenY", self._mouth_open)
            except Exception:
                pass

    def set_app_state(self, state: str):
        """앱 상태 업데이트 (idle, listening, thinking, speaking)"""
        self._app_state = state

    def update(self, dt: float):
        """매 프레임 업데이트"""
        import live2d.v3 as live2d_lib

        if self.model is None:
            return

        self._idle_timer += dt

        # 아이들 상태일 때 자연스러운 미세 움직임
        if self._app_state == AppState.IDLE:
            # 호흡 (사인파)
            breath = math.sin(self._idle_timer * 2.0) * 0.3
            self.model.SetParameterValue("ParamBreath", breath)

            # 자동 눈 깜빡임 (약 3~5초 간격)
            blink_cycle = self._idle_timer % 4.0
            if 3.7 < blink_cycle < 4.0:
                blink_val = 1.0 - ((blink_cycle - 3.7) / 0.15)
                if blink_cycle > 3.85:
                    blink_val = (blink_cycle - 3.85) / 0.15
                blink_val = max(0.0, min(1.0, blink_val))
                self.model.SetParameterValue("ParamEyeLOpen", blink_val)
                self.model.SetParameterValue("ParamEyeROpen", blink_val)

        elif self._app_state == AppState.LISTENING:
            # 듣는 중: 고개 약간 기울임
            tilt = math.sin(self._idle_timer * 1.5) * 5.0
            self.model.SetParameterValue("ParamAngleZ", tilt)

        elif self._app_state == AppState.THINKING:
            # 생각 중: 고개 갸우뚱
            self.model.SetParameterValue("ParamAngleZ", 10.0)
            self.model.SetParameterValue("ParamEyeBallX", 0.5)

        # 렌더링
        live2d_lib.clearBuffer(*BACKGROUND_COLOR, 255)
        self.model.Update(dt)
        self.model.Draw()

    def render_frame(self) -> float:
        """한 프레임 렌더링 후 dt 반환"""
        import pygame

        dt = self.clock.tick(TARGET_FPS) / 1000.0
        self.update(dt)
        pygame.display.flip()
        return dt

    def handle_events(self) -> list:
        """
        Pygame 이벤트 처리.
        Returns: 처리된 이벤트 리스트 (종료 이벤트 등)
        """
        import pygame
        events = []
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                events.append(("quit", None))
            elif event.type == pygame.MOUSEBUTTONDOWN:
                x, y = event.pos
                events.append(("touch", (x, y)))
                # Live2D 터치 반응
                if self.model:
                    try:
                        self.model.Touch(x, y)
                    except Exception:
                        pass
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                    events.append(("quit", None))
        return events

    def cleanup(self):
        """리소스 정리"""
        import pygame
        try:
            import live2d.v3 as live2d_lib
            live2d_lib.dispose()
        except Exception:
            pass
        pygame.quit()
        logger.info("Live2D 렌더러 종료")


# ──────────────────────────────────────────────
# 스프라이트 기반 폴백 렌더러
# (Live2D 모델이 없을 때 사용)
# ──────────────────────────────────────────────

class SpriteRenderer:
    """
    Live2D 없이 간단한 스프라이트 기반 캐릭터 렌더러.
    단일 이미지 + 눈 깜빡임 + 입 열기 오버레이.
    Live2D 리깅 전 테스트용.
    """

    def __init__(self):
        self.screen = None
        self.clock = None
        self.running = False
        self._current_emotion = "평온"
        self._mouth_open = 0.0
        self._app_state = AppState.IDLE
        self._idle_timer = 0.0
        self._char_image = None
        self._font = None

    def initialize(self) -> bool:
        """Pygame 초기화 (일반 2D 모드)"""
        try:
            import pygame

            pygame.init()
            self.screen = pygame.display.set_mode(
                (SCREEN_WIDTH, SCREEN_HEIGHT)
            )
            pygame.display.set_caption(f"{WINDOW_TITLE} (스프라이트 모드)")
            self.clock = pygame.time.Clock()

            # 캐릭터 이미지 로드 시도
            char_path = LIVE2D_MODEL_DIR / "wani_sprite.png"
            if char_path.exists():
                self._char_image = pygame.image.load(str(char_path)).convert_alpha()
                # 화면에 맞게 스케일
                img_h = int(SCREEN_HEIGHT * 0.85)
                aspect = self._char_image.get_width() / self._char_image.get_height()
                img_w = int(img_h * aspect)
                self._char_image = pygame.transform.smoothscale(
                    self._char_image, (img_w, img_h)
                )
                logger.info(f"스프라이트 이미지 로드: {char_path}")
            else:
                logger.warning(f"스프라이트 이미지가 없습니다: {char_path}")

            # 폰트 로드
            try:
                self._font = pygame.font.Font(None, 24)
            except Exception:
                self._font = pygame.font.SysFont("sans", 20)

            self.running = True
            logger.info("스프라이트 렌더러 초기화 완료")
            return True

        except Exception as e:
            logger.error(f"스프라이트 렌더러 초기화 실패: {e}")
            return False

    def set_emotion(self, emotion: str):
        self._current_emotion = emotion

    def set_mouth_open(self, value: float):
        self._mouth_open = max(0.0, min(1.0, value))

    def set_app_state(self, state: str):
        self._app_state = state

    def update(self, dt: float):
        """매 프레임 렌더링"""
        import pygame

        self._idle_timer += dt

        # 배경
        self.screen.fill(BACKGROUND_COLOR)

        # 캐릭터 이미지 표시
        if self._char_image:
            # 호흡 효과 (약간의 상하 움직임)
            breath_offset = math.sin(self._idle_timer * 2.0) * 3
            img_x = (SCREEN_WIDTH - self._char_image.get_width()) // 2
            img_y = int((SCREEN_HEIGHT - self._char_image.get_height()) // 2 + breath_offset)
            self.screen.blit(self._char_image, (img_x, img_y))

        # 상태 표시 UI
        status_colors = {
            AppState.IDLE: (100, 200, 100),
            AppState.LISTENING: (100, 150, 255),
            AppState.THINKING: (255, 200, 100),
            AppState.SPEAKING: (255, 100, 150),
            AppState.ERROR: (255, 80, 80),
        }
        status_texts = {
            AppState.IDLE: "💤 대기 중...",
            AppState.LISTENING: "🎤 듣는 중...",
            AppState.THINKING: "🤔 생각 중...",
            AppState.SPEAKING: "🔊 말하는 중...",
            AppState.ERROR: "⚠️ 오류",
        }

        color = status_colors.get(self._app_state, (200, 200, 200))
        text = status_texts.get(self._app_state, "")

        # 상태 바 (하단)
        bar_height = 40
        bar_rect = pygame.Rect(0, SCREEN_HEIGHT - bar_height, SCREEN_WIDTH, bar_height)
        bar_surface = pygame.Surface((SCREEN_WIDTH, bar_height), pygame.SRCALPHA)
        bar_surface.fill((0, 0, 0, 180))
        self.screen.blit(bar_surface, bar_rect)

        if self._font:
            # 상태 텍스트
            try:
                text_surface = self._font.render(text, True, color)
                self.screen.blit(text_surface, (15, SCREEN_HEIGHT - bar_height + 10))
            except Exception:
                pass

            # 감정 표시
            try:
                emotion_text = f"감정: {self._current_emotion}"
                emotion_surface = self._font.render(emotion_text, True, (200, 200, 200))
                self.screen.blit(
                    emotion_surface,
                    (SCREEN_WIDTH - emotion_surface.get_width() - 15,
                     SCREEN_HEIGHT - bar_height + 10)
                )
            except Exception:
                pass

        # 입 열기 시각화 (말하는 중일 때 간단한 볼륨 바)
        if self._app_state == AppState.SPEAKING and self._mouth_open > 0:
            vol_width = int(self._mouth_open * 100)
            vol_rect = pygame.Rect(
                SCREEN_WIDTH // 2 - 50,
                SCREEN_HEIGHT - bar_height - 15,
                vol_width, 8
            )
            pygame.draw.rect(self.screen, (100, 255, 150), vol_rect, border_radius=4)

    def render_frame(self) -> float:
        """한 프레임 렌더링 후 dt 반환"""
        import pygame
        dt = self.clock.tick(TARGET_FPS) / 1000.0
        self.update(dt)
        pygame.display.flip()
        return dt

    def handle_events(self) -> list:
        """Pygame 이벤트 처리"""
        import pygame
        events = []
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                events.append(("quit", None))
            elif event.type == pygame.MOUSEBUTTONDOWN:
                events.append(("touch", event.pos))
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                    events.append(("quit", None))
        return events

    def cleanup(self):
        """정리"""
        import pygame
        pygame.quit()
        logger.info("스프라이트 렌더러 종료")


def create_renderer():
    """
    적절한 렌더러를 생성하여 반환.
    우선순위: Live2D (.model3.json) > 스켈레탈 (bone_config.json) > 스프라이트 (wani_sprite.png)
    """
    model_json = LIVE2D_MODEL_DIR / "wani.model3.json"
    bone_config = LIVE2D_MODEL_DIR / "bone_config.json"

    # 1순위: Live2D 모델
    if model_json.exists():
        logger.info("Live2D 모델 발견 — Live2D 렌더러 사용")
        renderer = Live2DRenderer()
        if renderer.initialize():
            return renderer
        logger.warning("Live2D 초기화 실패, 다음 렌더러 시도")

    # 2순위: 스켈레탈 (AI 리깅, See-through 레이어)
    if bone_config.exists() or (LIVE2D_MODEL_DIR / "layers").exists():
        try:
            from modules.skeletal_renderer import SkeletalRenderer
            logger.info("스켈레탈 모델 발견 — AI 리깅 렌더러 사용")
            renderer = SkeletalRenderer()
            if renderer.initialize():
                return renderer
            logger.warning("스켈레탈 초기화 실패, 스프라이트로 전환")
        except ImportError as e:
            logger.warning(f"스켈레탈 렌더러 임포트 실패: {e}")

    # 3순위: 스프라이트 폴백
    logger.info("스프라이트 렌더러로 대체")
    renderer = SpriteRenderer()
    if renderer.initialize():
        return renderer

    raise RuntimeError("렌더러를 초기화할 수 없습니다")
