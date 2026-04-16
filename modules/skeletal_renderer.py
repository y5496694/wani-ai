"""
와니 AI — 스켈레탈 애니메이션 렌더러
See-through AI로 분리된 레이어 이미지 + 뼈대 데이터 기반 2D 애니메이션.
Live2D 없이도 자연스러운 캐릭터 움직임 구현.

작동 방식:
    1. See-through AI가 캐릭터를 레이어 PNG로 분리
    2. bone_config.json에 뼈대 계층 + 레이어 매핑 정의
    3. 이 렌더러가 뼈대 변환(회전/이동/스케일)을 실시간 적용
    4. 감정/립싱크/물리 시뮬을 파라미터로 제어
"""

import json
import logging
import math
import os
import time
from pathlib import Path
from typing import Optional

import pygame

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, TARGET_FPS,
    WINDOW_TITLE, BACKGROUND_COLOR, LIVE2D_MODEL_DIR,
    EMOTION_MAP, AppState
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────
# 뼈대 (Bone) 시스템
# ─────────────────────────────────────────────────

class Bone:
    """2D 뼈대 노드"""

    def __init__(self, name: str, x: float = 0, y: float = 0,
                 angle: float = 0, scale_x: float = 1, scale_y: float = 1,
                 parent: Optional['Bone'] = None):
        self.name = name
        # 로컬 변환 (기본 포즈)
        self.rest_x = x
        self.rest_y = y
        self.rest_angle = angle
        self.rest_scale_x = scale_x
        self.rest_scale_y = scale_y

        # 현재 변환 (애니메이션 적용)
        self.local_x = x
        self.local_y = y
        self.local_angle = angle
        self.local_scale_x = scale_x
        self.local_scale_y = scale_y

        # 계층 구조
        self.parent = parent
        self.children: list['Bone'] = []

        # 월드 변환 (계산됨)
        self.world_x = 0.0
        self.world_y = 0.0
        self.world_angle = 0.0
        self.world_scale_x = 1.0
        self.world_scale_y = 1.0

    def add_child(self, child: 'Bone'):
        child.parent = self
        self.children.append(child)

    def reset_to_rest(self):
        """기본 포즈로 리셋"""
        self.local_x = self.rest_x
        self.local_y = self.rest_y
        self.local_angle = self.rest_angle
        self.local_scale_x = self.rest_scale_x
        self.local_scale_y = self.rest_scale_y

    def update_world_transform(self):
        """부모 변환을 반영하여 월드 좌표 계산"""
        if self.parent:
            p = self.parent
            rad = math.radians(p.world_angle)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            self.world_x = p.world_x + (self.local_x * cos_a - self.local_y * sin_a) * p.world_scale_x
            self.world_y = p.world_y + (self.local_x * sin_a + self.local_y * cos_a) * p.world_scale_y
            self.world_angle = p.world_angle + self.local_angle
            self.world_scale_x = p.world_scale_x * self.local_scale_x
            self.world_scale_y = p.world_scale_y * self.local_scale_y
        else:
            self.world_x = self.local_x
            self.world_y = self.local_y
            self.world_angle = self.local_angle
            self.world_scale_x = self.local_scale_x
            self.world_scale_y = self.local_scale_y

        for child in self.children:
            child.update_world_transform()


# ─────────────────────────────────────────────────
# 레이어 (분리된 캐릭터 파츠 이미지)
# ─────────────────────────────────────────────────

class Layer:
    """하나의 캐릭터 파츠 레이어"""

    def __init__(self, name: str, image_path: str, bone_name: str,
                 offset_x: float = 0, offset_y: float = 0,
                 pivot_x: float = 0.5, pivot_y: float = 0.5,
                 z_order: int = 0, visible: bool = True):
        self.name = name
        self.bone_name = bone_name
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.pivot_x = pivot_x  # 0~1, 이미지 내 회전 중심
        self.pivot_y = pivot_y
        self.z_order = z_order
        self.visible = visible
        self.opacity = 255  # 0~255

        # 이미지 로드
        self.original_image: Optional[pygame.Surface] = None
        self.image_path = image_path

    def load_image(self):
        """이미지 로드"""
        if os.path.exists(self.image_path):
            self.original_image = pygame.image.load(self.image_path).convert_alpha()
            logger.debug(f"레이어 로드: {self.name} ({self.original_image.get_size()})")
        else:
            logger.warning(f"레이어 이미지 없음: {self.image_path}")

    def render(self, screen: pygame.Surface, bone: Bone,
               global_scale: float = 1.0, global_offset: tuple = (0, 0)):
        """뼈대 변환을 적용하여 레이어 렌더링"""
        if not self.visible or self.original_image is None:
            return

        img = self.original_image

        # 스케일 적용
        sx = bone.world_scale_x * global_scale
        sy = bone.world_scale_y * global_scale
        scaled_w = int(img.get_width() * abs(sx))
        scaled_h = int(img.get_height() * abs(sy))

        if scaled_w <= 0 or scaled_h <= 0:
            return

        scaled = pygame.transform.smoothscale(img, (scaled_w, scaled_h))

        # 좌우 반전
        if sx < 0:
            scaled = pygame.transform.flip(scaled, True, False)
        if sy < 0:
            scaled = pygame.transform.flip(scaled, False, True)

        # 회전 적용
        angle = -bone.world_angle  # Pygame은 반시계 방향이 양수
        rotated = pygame.transform.rotate(scaled, angle)

        # 투명도 적용
        if self.opacity < 255:
            rotated.set_alpha(self.opacity)

        # 피벗 기준으로 위치 계산 (Untrimmed 레이어의 경우 모두 0.5로 고정되어 화면 중심에서 완벽히 겹칩니다)
        pivot_px = self.pivot_x * scaled_w
        pivot_py = self.pivot_y * scaled_h

        # 회전 후 피벗 보정 (단순 Bounding Box 중앙 기준)
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        rotated_pivot_x = pivot_px * cos_a - pivot_py * sin_a
        rotated_pivot_y = pivot_px * sin_a + pivot_py * cos_a

        # 최종 위치 (모든 파츠가 Bounding Box 중심으로 정렬됨)
        final_x = bone.world_x + self.offset_x * global_scale + global_offset[0] - rotated.get_width() / 2
        final_y = bone.world_y + self.offset_y * global_scale + global_offset[1] - rotated.get_height() / 2

        if not hasattr(self, '_debug_logged_layers'):
            self._debug_logged_layers = set()
        if self.name not in self._debug_logged_layers:
            print(f"DEBUG RENDER [{self.name}]: bone={bone.name} world=({bone.world_x:.1f}, {bone.world_y:.1f}) size={rotated.get_size()} final=({final_x:.1f}, {final_y:.1f})")
            self._debug_logged_layers.add(self.name)

        screen.blit(rotated, (int(final_x), int(final_y)))


# ─────────────────────────────────────────────────
# 스켈레탈 애니메이션 렌더러 (메인)
# ─────────────────────────────────────────────────

class SkeletalRenderer:
    """
    See-through AI 레이어 + 뼈대 기반 캐릭터 렌더러.
    bone_config.json에서 뼈대/레이어/애니메이션 정의를 로드.
    """

    def __init__(self):
        self.screen: Optional[pygame.Surface] = None
        self.clock: Optional[pygame.time.Clock] = None
        self.running = False

        # 캐릭터 데이터
        self.bones: dict[str, Bone] = {}
        self.root_bone: Optional[Bone] = None
        self.layers: list[Layer] = []

        # 파라미터 (Live2D 호환 이름)
        self.params: dict[str, float] = {
            "ParamEyeLOpen": 1.0,
            "ParamEyeROpen": 1.0,
            "ParamMouthOpenY": 0.0,
            "ParamMouthForm": 0.0,
            "ParamAngleX": 0.0,
            "ParamAngleY": 0.0,
            "ParamAngleZ": 0.0,
            "ParamBodyAngleX": 0.0,
            "ParamBreath": 0.0,
            "ParamBrowLY": 0.0,
            "ParamBrowRY": 0.0,
            "ParamEyeBallX": 0.0,
            "ParamEyeBallY": 0.0,
            "ParamCheek": 0.0,
            "ParamEyeLSmile": 0.0,
            "ParamEyeRSmile": 0.0,
            "ParamTailSwing": 0.0,
        }

        # 파라미터 → 뼈대 매핑 (구동 규칙)
        self.param_drivers: list[dict] = []

        # 표시 스케일/오프셋
        self.global_scale = 1.0
        self.global_offset = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)

        # 상태
        self._current_emotion = "평온"
        self._app_state = AppState.IDLE
        self._idle_timer = 0.0

        # 물리 시뮬 (간이)
        self._physics_velocities: dict[str, float] = {}
        self._physics_config: list[dict] = []  # JSON에서 로드 후 캐시

        # 상태 표시 폰트
        self._font = None

    def initialize(self) -> bool:
        """Pygame 초기화 + 캐릭터 데이터 로드"""
        try:
            pygame.init()
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
            pygame.display.set_caption(f"{WINDOW_TITLE} (AI 리깅)")
            self.clock = pygame.time.Clock()

            try:
                # 한국어 지원 폰트 (맑은 고딕, 애플 고딕, 일반 산스)
                self._font = pygame.font.SysFont("malgungothic,applehmgotica,sans", 18)
            except Exception:
                self._font = pygame.font.Font(None, 20)

            # 캐릭터 설정 파일 로드
            config_path = LIVE2D_MODEL_DIR / "bone_config.json"
            if config_path.exists():
                self._load_config(str(config_path))
                logger.info(f"스켈레탈 캐릭터 로드: 뼈대 {len(self.bones)}개, 레이어 {len(self.layers)}개")
            else:
                logger.warning(f"bone_config.json 없음, 기본 설정 생성: {config_path}")
                self._create_default_config(str(config_path))
                self._load_config(str(config_path))

            self.running = True
            return True

        except Exception as e:
            logger.error(f"스켈레탈 렌더러 초기화 실패: {e}")
            return False

    def _load_config(self, path: str):
        """bone_config.json 로드"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 뼈대 로드
        self.bones.clear()
        bone_defs = data.get("bones", [])
        for bd in bone_defs:
            bone = Bone(
                name=bd["name"],
                x=bd.get("x", 0),
                y=bd.get("y", 0),
                angle=bd.get("angle", 0),
                scale_x=bd.get("scaleX", 1),
                scale_y=bd.get("scaleY", 1),
            )
            self.bones[bone.name] = bone

        # 부모-자식 연결
        for bd in bone_defs:
            parent_name = bd.get("parent")
            if parent_name and parent_name in self.bones:
                self.bones[parent_name].add_child(self.bones[bd["name"]])

        # 루트 뼈대 찾기
        root_name = data.get("root", bone_defs[0]["name"] if bone_defs else None)
        if root_name:
            self.root_bone = self.bones.get(root_name)

        # 레이어 로드
        self.layers.clear()
        layer_dir = LIVE2D_MODEL_DIR / "layers"
        for ld in data.get("layers", []):
            img_path = str(layer_dir / ld["image"])
            layer = Layer(
                name=ld["name"],
                image_path=img_path,
                bone_name=ld.get("bone", root_name or "root"),
                offset_x=ld.get("offsetX", 0),
                offset_y=ld.get("offsetY", 0),
                pivot_x=ld.get("pivotX", 0.5),
                pivot_y=ld.get("pivotY", 0.5),
                z_order=ld.get("zOrder", 0),
                visible=ld.get("visible", True),
            )
            layer.load_image()
            self.layers.append(layer)

        # z-order 정렬
        self.layers.sort(key=lambda l: l.z_order)

        # 파라미터 → 뼈대 구동 규칙
        self.param_drivers = data.get("drivers", [])

        # 스케일/오프셋
        display = data.get("display", {})
        self.global_scale = display.get("scale", 0.15)
        self.global_offset = (
            display.get("offsetX", SCREEN_WIDTH // 2),
            display.get("offsetY", SCREEN_HEIGHT // 2)
        )

        # 물리 (캐시)
        self._physics_config = data.get("physics", [])
        for phys in self._physics_config:
            self._physics_velocities[f"{phys['bone']}_{phys.get('property', 'angle')}"] = 0.0

    def _create_default_config(self, path: str):
        """기본 bone_config.json 생성 (See-through 출력 전 테스트용)"""
        default = {
            "_comment": "와니 AI 캐릭터 스켈레탈 설정. See-through AI로 레이어 분리 후 이 파일을 수정하세요.",
            "root": "root",
            "bones": [
                {"name": "root", "x": 0, "y": 0},
                {"name": "body", "parent": "root", "x": 0, "y": 0},
                {"name": "head", "parent": "body", "x": 0, "y": -180},
                {"name": "hair_front", "parent": "head", "x": 0, "y": -20},
                {"name": "hair_side_L", "parent": "head", "x": -40, "y": 0},
                {"name": "hair_side_R", "parent": "head", "x": 40, "y": 0},
                {"name": "hood", "parent": "head", "x": 0, "y": -40},
                {"name": "eye_L", "parent": "head", "x": -20, "y": -10},
                {"name": "eye_R", "parent": "head", "x": 20, "y": -10},
                {"name": "mouth", "parent": "head", "x": 0, "y": 15},
                {"name": "brow_L", "parent": "head", "x": -20, "y": -25},
                {"name": "brow_R", "parent": "head", "x": 20, "y": -25},
                {"name": "arm_L", "parent": "body", "x": -60, "y": -100},
                {"name": "arm_R", "parent": "body", "x": 60, "y": -100},
                {"name": "tail", "parent": "body", "x": 50, "y": -60},
                {"name": "tail_mid", "parent": "tail", "x": 30, "y": 0},
                {"name": "tail_tip", "parent": "tail_mid", "x": 25, "y": 5},
                {"name": "skirt", "parent": "body", "x": 0, "y": 30},
            ],
            "layers": [
                {"name": "hair_back", "image": "hair_back.png", "bone": "head", "zOrder": -10},
                {"name": "body", "image": "body.png", "bone": "body", "zOrder": 0},
                {"name": "tail_base", "image": "tail_base.png", "bone": "tail", "zOrder": 1},
                {"name": "tail_mid", "image": "tail_mid.png", "bone": "tail_mid", "zOrder": 2},
                {"name": "tail_tip", "image": "tail_tip.png", "bone": "tail_tip", "zOrder": 3},
                {"name": "skirt", "image": "skirt.png", "bone": "skirt", "zOrder": 5},
                {"name": "face_base", "image": "face_base.png", "bone": "head", "zOrder": 10},
                {"name": "eye_white_L", "image": "eye_white_L.png", "bone": "eye_L", "zOrder": 11},
                {"name": "eye_iris_L", "image": "eye_iris_L.png", "bone": "eye_L", "zOrder": 12},
                {"name": "eye_white_R", "image": "eye_white_R.png", "bone": "eye_R", "zOrder": 11},
                {"name": "eye_iris_R", "image": "eye_iris_R.png", "bone": "eye_R", "zOrder": 12},
                {"name": "eyelid_L", "image": "eyelid_L.png", "bone": "eye_L", "zOrder": 13},
                {"name": "eyelid_R", "image": "eyelid_R.png", "bone": "eye_R", "zOrder": 13},
                {"name": "mouth_closed", "image": "mouth_closed.png", "bone": "mouth", "zOrder": 14},
                {"name": "mouth_open", "image": "mouth_open.png", "bone": "mouth", "zOrder": 14, "visible": False},
                {"name": "brow_L", "image": "brow_L.png", "bone": "brow_L", "zOrder": 15},
                {"name": "brow_R", "image": "brow_R.png", "bone": "brow_R", "zOrder": 15},
                {"name": "cheek_blush", "image": "cheek_blush.png", "bone": "head", "zOrder": 16, "visible": False},
                {"name": "nose", "image": "nose.png", "bone": "head", "zOrder": 14},
                {"name": "hair_front", "image": "hair_front.png", "bone": "hair_front", "zOrder": 20},
                {"name": "hair_side_L", "image": "hair_side_L.png", "bone": "hair_side_L", "zOrder": 19},
                {"name": "hair_side_R", "image": "hair_side_R.png", "bone": "hair_side_R", "zOrder": 19},
                {"name": "hood", "image": "hood.png", "bone": "hood", "zOrder": 25},
            ],
            "drivers": [
                {"param": "ParamAngleX", "bone": "head", "property": "angle", "scale": 0.5},
                {"param": "ParamAngleZ", "bone": "head", "property": "angle", "scale": 0.3, "additive": True},
                {"param": "ParamBodyAngleX", "bone": "body", "property": "angle", "scale": 0.3},
                {"param": "ParamBreath", "bone": "body", "property": "y", "scale": -3},
                {"param": "ParamBrowLY", "bone": "brow_L", "property": "y", "scale": -8},
                {"param": "ParamBrowRY", "bone": "brow_R", "property": "y", "scale": -8},
                {"param": "ParamEyeBallX", "bone": "eye_L", "property": "x", "scale": 3},
                {"param": "ParamEyeBallX", "bone": "eye_R", "property": "x", "scale": 3},
                {"param": "ParamTailSwing", "bone": "tail", "property": "angle", "scale": 25},
                {"param": "ParamAngleX", "bone": "hood", "property": "angle", "scale": 0.2},
            ],
            "physics": [
                {"bone": "hair_front", "property": "angle", "damping": 0.85, "stiffness": 0.3, "input": "ParamAngleX"},
                {"bone": "hair_side_L", "property": "angle", "damping": 0.8, "stiffness": 0.2, "input": "ParamAngleX"},
                {"bone": "hair_side_R", "property": "angle", "damping": 0.8, "stiffness": 0.2, "input": "ParamAngleX"},
                {"bone": "tail_mid", "property": "angle", "damping": 0.75, "stiffness": 0.15, "input": "ParamTailSwing"},
                {"bone": "tail_tip", "property": "angle", "damping": 0.7, "stiffness": 0.1, "input": "ParamTailSwing"},
            ],
            "display": {
                "scale": 0.15,
                "offsetX": 400,
                "offsetY": 360
            }
        }

        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.makedirs(str(LIVE2D_MODEL_DIR / "layers"), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        logger.info(f"기본 bone_config.json 생성: {path}")

    # ─────────────────────────────────────────────
    # 파라미터 제어 (Live2D 호환 API)
    # ─────────────────────────────────────────────

    def set_emotion(self, emotion: str):
        """감정 전환"""
        if emotion == self._current_emotion:
            return
        self._current_emotion = emotion

        emotion_data = EMOTION_MAP.get(emotion, EMOTION_MAP["평온"])
        for param, value in emotion_data.get("param_overrides", {}).items():
            if param in self.params:
                self.params[param] = value

        # 볼 홍조 토글
        for layer in self.layers:
            if layer.name == "cheek_blush":
                layer.visible = emotion == "부끄러움"

        logger.debug(f"감정 전환: {emotion}")

    def set_mouth_open(self, value: float):
        """입 열기 (립싱크) — 0.0~1.0"""
        self.params["ParamMouthOpenY"] = max(0.0, min(1.0, value))

        # 입 레이어 전환
        threshold = 0.3
        for layer in self.layers:
            if layer.name == "mouth_closed":
                layer.visible = value < threshold
            elif layer.name == "mouth_open":
                layer.visible = value >= threshold

    def set_app_state(self, state: str):
        """앱 상태 전환"""
        self._app_state = state

    def SetParameterValue(self, param_id: str, value: float):
        """Live2D 호환 API"""
        if param_id in self.params:
            self.params[param_id] = value

    # ─────────────────────────────────────────────
    # 업데이트 & 렌더링
    # ─────────────────────────────────────────────

    def update(self, dt: float):
        """매 프레임 업데이트"""
        self._idle_timer += dt

        # 1. 자동 애니메이션 (아이들)
        self._update_auto_animation(dt)

        # 2. 모든 뼈대 기본 포즈로 리셋
        for bone in self.bones.values():
            bone.reset_to_rest()

        # 3. 파라미터 → 뼈대 구동
        self._apply_drivers()

        # 4. 눈 깜빡임 (레이어 스케일로 구현)
        self._apply_eye_blink()

        # 5. 간이 물리 시뮬레이션
        self._apply_physics(dt)

        # 6. 뼈대 월드 변환 계산
        if self.root_bone:
            self.root_bone.update_world_transform()

        # 7. 렌더링
        self._render()

    def _update_auto_animation(self, dt: float):
        """자동 아이들 애니메이션"""
        t = self._idle_timer

        if self._app_state == AppState.IDLE:
            # 호흡
            self.params["ParamBreath"] = math.sin(t * 2.0) * 0.5 + 0.5
            # 미세한 머리 움직임
            self.params["ParamAngleX"] = math.sin(t * 0.5) * 3
            self.params["ParamAngleZ"] = math.sin(t * 0.7) * 2

            # 자동 눈 깜빡임 (3~5초 간격)
            blink_cycle = t % 4.0
            if 3.7 < blink_cycle < 4.0:
                progress = (blink_cycle - 3.7) / 0.3
                if progress < 0.5:
                    blink_val = 1.0 - (progress * 2)
                else:
                    blink_val = (progress - 0.5) * 2
                self.params["ParamEyeLOpen"] = blink_val
                self.params["ParamEyeROpen"] = blink_val
            else:
                self.params["ParamEyeLOpen"] = 1.0
                self.params["ParamEyeROpen"] = 1.0

        elif self._app_state == AppState.LISTENING:
            self.params["ParamBreath"] = math.sin(t * 2.0) * 0.5 + 0.5
            self.params["ParamAngleZ"] = math.sin(t * 1.5) * 8

        elif self._app_state == AppState.THINKING:
            self.params["ParamAngleZ"] = 10.0
            self.params["ParamEyeBallX"] = math.sin(t * 2) * 0.5

        elif self._app_state == AppState.SPEAKING:
            self.params["ParamBreath"] = math.sin(t * 2.5) * 0.3 + 0.5

        # 감정별 꼬리 애니메이션
        if self._current_emotion == "기쁨":
            self.params["ParamTailSwing"] = math.sin(t * 6.0) * 0.8
        elif self._current_emotion == "슬픔":
            self.params["ParamTailSwing"] = -0.5 + math.sin(t * 0.5) * 0.1
        elif self._current_emotion == "놀람":
            self.params["ParamTailSwing"] = math.sin(t * 8.0) * 0.5
        else:
            self.params["ParamTailSwing"] = math.sin(t * 1.0) * 0.3

    def _apply_drivers(self):
        """파라미터 → 뼈대 변환 적용"""
        for driver in self.param_drivers:
            param_name = driver["param"]
            bone_name = driver["bone"]
            prop = driver["property"]  # "x", "y", "angle", "scaleX", "scaleY"
            scale = driver.get("scale", 1.0)
            additive = driver.get("additive", False)

            if param_name not in self.params or bone_name not in self.bones:
                continue

            value = self.params[param_name] * scale
            bone = self.bones[bone_name]

            if prop == "x":
                bone.local_x = (bone.rest_x + value) if not additive else (bone.local_x + value)
            elif prop == "y":
                bone.local_y = (bone.rest_y + value) if not additive else (bone.local_y + value)
            elif prop == "angle":
                bone.local_angle = (bone.rest_angle + value) if not additive else (bone.local_angle + value)
            elif prop == "scaleX":
                bone.local_scale_x = bone.rest_scale_x * (1.0 + value) if not additive else bone.local_scale_x * (1.0 + value)
            elif prop == "scaleY":
                bone.local_scale_y = bone.rest_scale_y * (1.0 + value) if not additive else bone.local_scale_y * (1.0 + value)

    def _apply_eye_blink(self):
        """눈 깜빡임 — eyelid 레이어의 Y 오프셋으로 구현"""
        eye_l_open = self.params.get("ParamEyeLOpen", 1.0)
        eye_r_open = self.params.get("ParamEyeROpen", 1.0)

        for layer in self.layers:
            if layer.name == "eyelid_L":
                # 눈을 감으면 eyelid가 아래로 내려와서 눈을 덮음
                layer.offset_y = (1.0 - eye_l_open) * -15
                layer.visible = eye_l_open < 0.95
            elif layer.name == "eyelid_R":
                layer.offset_y = (1.0 - eye_r_open) * -15
                layer.visible = eye_r_open < 0.95

    def _apply_physics(self, dt: float):
        """간이 진자 물리 시뮬레이션"""
        if not self._physics_config:
            return

        for phys in self._physics_config:
            bone_name = phys["bone"]
            prop = phys.get("property", "angle")
            damping = phys.get("damping", 0.85)
            stiffness = phys.get("stiffness", 0.3)
            input_param = phys.get("input", "ParamAngleX")

            if bone_name not in self.bones:
                continue

            bone = self.bones[bone_name]
            vel_key = f"{bone_name}_{prop}"

            if vel_key not in self._physics_velocities:
                self._physics_velocities[vel_key] = 0.0

            # 입력 가속도 (1:1 매핑)
            input_val = self.params.get(input_param, 0.0)
            target = input_val
            current = getattr(bone, f"local_{prop}", 0.0) - getattr(bone, f"rest_{prop}", 0.0)

            # 스프링 물리
            force = (target - current) * stiffness
            self._physics_velocities[vel_key] += force * dt * 60
            self._physics_velocities[vel_key] *= damping
            new_val = current + self._physics_velocities[vel_key]

            if prop == "angle":
                bone.local_angle = bone.rest_angle + new_val
            elif prop == "x":
                bone.local_x = bone.rest_x + new_val
            elif prop == "y":
                bone.local_y = bone.rest_y + new_val

    def _render(self):
        """화면 렌더링"""
        self.screen.fill(BACKGROUND_COLOR)

        # 레이어 렌더링 (z-order 순)
        for layer in self.layers:
            bone = self.bones.get(layer.bone_name)
            if bone:
                layer.render(self.screen, bone, self.global_scale, self.global_offset)

        # 상태 표시 UI
        self._render_status_bar()

    def _render_status_bar(self):
        """하단 상태 바"""
        bar_height = 36
        bar_surface = pygame.Surface((SCREEN_WIDTH, bar_height), pygame.SRCALPHA)
        bar_surface.fill((0, 0, 0, 180))
        self.screen.blit(bar_surface, (0, SCREEN_HEIGHT - bar_height))

        status_map = {
            AppState.IDLE: ("💤 대기 중", (100, 200, 100)),
            AppState.LISTENING: ("🎤 듣는 중", (100, 150, 255)),
            AppState.THINKING: ("🤔 생각 중", (255, 200, 100)),
            AppState.SPEAKING: ("🔊 말하는 중", (255, 100, 150)),
            AppState.ERROR: ("⚠️ 오류", (255, 80, 80)),
        }
        text, color = status_map.get(self._app_state, ("", (200, 200, 200)))

        if self._font:
            try:
                ts = self._font.render(text, True, color)
                self.screen.blit(ts, (12, SCREEN_HEIGHT - bar_height + 9))

                emotion_ts = self._font.render(f"감정: {self._current_emotion}", True, (180, 180, 180))
                self.screen.blit(emotion_ts, (SCREEN_WIDTH - emotion_ts.get_width() - 12, SCREEN_HEIGHT - bar_height + 9))
            except Exception:
                pass

        # 립싱크 볼륨 바
        mouth = self.params.get("ParamMouthOpenY", 0)
        if self._app_state == AppState.SPEAKING and mouth > 0:
            vol_w = int(mouth * 80)
            vol_rect = pygame.Rect(SCREEN_WIDTH // 2 - 40, SCREEN_HEIGHT - bar_height - 10, vol_w, 6)
            pygame.draw.rect(self.screen, (100, 255, 150), vol_rect, border_radius=3)

    # ─────────────────────────────────────────────
    # 메인 루프 인터페이스
    # ─────────────────────────────────────────────

    def render_frame(self) -> float:
        dt = self.clock.tick(TARGET_FPS) / 1000.0
        self.update(dt)
        pygame.display.flip()
        return dt

    def handle_events(self) -> list:
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
        pygame.quit()
        logger.info("스켈레탈 렌더러 종료")
