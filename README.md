# 🐊 와니 AI — 라즈베리파이 5 버츄얼 로컬 AI 어시스턴트

> 7인치 터치 LCD 위에 Live2D 악어 캐릭터가 움직이며 한국어로 대화하는 완전 오프라인 AI

![wani concept](assets/concept.png)

## 🎯 특징

- **완전 오프라인**: 인터넷 없이 동작 (초기 설치 후)
- **한국어 음성 대화**: 말하면 알아듣고 음성으로 대답
- **Live2D 캐릭터**: 감정에 따라 표정이 변하고, 말할 때 입이 움직임 (립싱크)
- **감정 표현**: 기쁨, 슬픔, 놀람, 분노, 평온, 부끄러움 6가지 감정
- **터치 반응**: LCD 터치 시 캐릭터가 반응

## 🏗️ 아키텍처

```
[마이크] → [Whisper.cpp STT] → [Gemma4 E2B LLM] → [MeloTTS] → [스피커]
                                       ↓
                              [감정 태그 파싱]
                                       ↓
                              [Live2D 표정 전환]
                                       ↓
                              [7인치 LCD 표시]
```

## 📋 요구사항

### 하드웨어
| 부품 | 사양 |
|------|------|
| Raspberry Pi 5 | 8GB RAM |
| LCD 터치스크린 | 7인치, 800×480 |
| NVMe SSD | 256GB+ (PCIe HAT 필요) |
| USB 마이크 | 아무거나 |
| 스피커 | USB 또는 3.5mm |
| 액티브 쿨러 | Pi 5 전용 |

### 소프트웨어
- Raspberry Pi OS 64-bit (Bookworm)
- Python 3.11+
- Ollama + Gemma4 E2B
- Whisper.cpp
- MeloTTS

## 🚀 설치

```bash
# 1. 프로젝트 클론 (또는 복사)
git clone <repo-url> ~/wani-ai
cd ~/wani-ai

# 2. 초기 설정 (인터넷 필요, 최초 1회)
chmod +x scripts/setup.sh
./scripts/setup.sh

# 3. Live2D 모델 배치
# models/wani/ 디렉토리에 .model3.json, .moc3, textures/ 등 배치
# 또는 테스트용으로 models/wani/wani_sprite.png 배치

# 4. 실행
./scripts/start.sh
```

## 📖 사용법

### 실행 모드

```bash
# 전체 모드 (LCD + 음성)
./scripts/start.sh

# CLI 모드 (텍스트 대화, SSH 테스트용)
./scripts/start.sh --mode cli

# 음성 모드 (렌더링 없이 음성만)
./scripts/start.sh --mode voice

# 디버그 모드
./scripts/start.sh --debug
```

### 대화 예시

```
👤 나: 안녕 와니야!
🐊 와니 [기쁨]: 안녕! 오늘도 반가워~ 악어악어! 🐊

👤 나: 오늘 날씨가 어떨까?
🐊 와니 [평온]: 음~ 나는 밖에 나갈 수 없어서 모르겠지만, 
               네가 나가서 확인해보는 건 어때?
```

## 📁 프로젝트 구조

```
wani-ai/
├── main.py              # 메인 앱 (3가지 실행 모드)
├── config.py            # 모든 설정값
├── requirements.txt     # Python 패키지
├── modules/
│   ├── llm.py          # Gemma4 E2B 연동
│   ├── stt.py          # Whisper.cpp 래퍼
│   ├── tts.py          # MeloTTS 래퍼
│   ├── audio.py        # 마이크/스피커 관리
│   └── renderer.py     # Live2D & 스프라이트 렌더러
├── models/wani/        # Live2D 모델 파일
├── scripts/
│   ├── setup.sh        # 초기 환경 설정
│   └── start.sh        # 실행 스크립트
└── assets/             # 배경, 효과음 등
```

## ⚙️ 설정

`config.py`에서 모든 설정 변경 가능:

- `CHARACTER_NAME` — 캐릭터 이름 (기본: "와니")
- `SYSTEM_PROMPT` — 성격/말투 설정
- `OLLAMA_MODEL` — LLM 모델 (기본: "gemma4:e2b")
- `LLM_CONTEXT_LENGTH` — 컨텍스트 길이 (기본: 2048)
- `VAD_SILENCE_THRESHOLD` — 묵음 감지 임계값
- `USE_WAKE_WORD` — 호출어 사용 여부
- `TARGET_FPS` — 렌더링 FPS (기본: 30)

## 🎨 Live2D 캐릭터 제작

1. **파츠 분리**: Photoshop/Clip Studio Paint에서 일러스트를 레이어별로 분리
2. **리깅**: Live2D Cubism Editor에서 메쉬, 디포머, 파라미터 설정
3. **Export**: `.model3.json` + `.moc3` + 텍스처 → `models/wani/` 에 배치
4. **테스트**: `./scripts/start.sh` 실행하여 확인

## 🐛 트러블슈팅

| 문제 | 해결 |
|------|------|
| "Ollama 서버 연결 실패" | `sudo systemctl start ollama` |
| "Whisper 바이너리 없음" | `./scripts/setup.sh` 재실행 |
| 응답이 너무 느림 | `config.py`에서 `LLM_CONTEXT_LENGTH` 줄이기 |
| 마이크 감지 안됨 | `arecord -l`로 장치 확인, PulseAudio 설정 |
| 화면이 안 나옴 | `DISPLAY=:0` 환경변수 확인 |
| 메모리 부족 | 스왑 확인: `free -h`, 4GB 이상 권장 |

## 📄 라이선스

개인 프로젝트
