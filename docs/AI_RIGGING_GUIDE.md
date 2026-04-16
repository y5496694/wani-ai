# 🤖 와니 AI 리깅 — AI 자동화 가이드

> **See-through AI + 스켈레탈 렌더러**를 사용한 15분 만에 캐릭터 움직이게 만들기

Live2D Cubism 없이, AI로 파츠 분리 → 자동 리깅 → 바로 움직이는 워크플로우입니다.

---

## 📋 필요한 것

| 항목 | 설명 |
|------|------|
| **와니 캐릭터 일러스트** | PNG 1장 (고해상도 권장, 4K+) |
| **PC** (Windows/Mac/Linux) | GPU 있는 PC (See-through 실행용) |
| **ComfyUI** | See-through 노드 실행 환경 |
| 또는 **Google Colab** | GPU 없을 경우 클라우드 실행 |

---

## 🔥 전체 흐름 (3단계)

```
┌─────────────────────┐
│ 1. See-through AI   │  PC에서 실행 (15~30분)
│    일러스트 → PNGs   │  자동 파츠 분리 + 빈 부분 AI 생성
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ 2. 레이어 정리       │  수동 (10~30분)
│    파일명 정리       │  bone_config.json 편집
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ 3. Pi에서 실행       │  복사 후 바로 실행!
│    스켈레탈 렌더러    │  자동 애니메이션 동작
└─────────────────────┘
```

---

## Step 1: See-through AI로 파츠 분리

### 방법 A: ComfyUI (로컬 PC, GPU 필요)

1. ComfyUI 설치 (이미 있다면 건너뛰기)
   ```bash
   git clone https://github.com/comfyanonymous/ComfyUI
   cd ComfyUI
   pip install -r requirements.txt
   ```

2. See-through 노드 설치
   ```bash
   cd custom_nodes
   git clone https://github.com/jtydhr88/ComfyUI-See-through
   cd ComfyUI-See-through
   pip install -r requirements.txt
   ```

3. ComfyUI 실행 → See-through 워크플로우 로드 → 이미지 입력 → 실행
4. 결과: **최대 24개 레이어 PNG** + 순서 정보 → PSD 또는 개별 PNG 출력

### 방법 B: Google Colab (GPU 없을 때)

1. See-through Colab 노트북 검색 (GitHub에서 제공)
2. 이미지 업로드 → 실행 → 레이어 PNG 다운로드

### 방법 C: 수동 분리 (AI 없이)

Photoshop이나 Clip Studio Paint에서 직접 파츠 분리.
자세한 내용은 `RIGGING_GUIDE.md` Step 2 참고.

---

## Step 2: 레이어 정리 + bone_config.json 설정

### 2-1. 파일 배치

See-through 출력물을 아래 구조로 정리합니다:

```
models/wani/
├── bone_config.json     ← 뼈대/레이어 설정 (아래에서 편집)
└── layers/              ← See-through 출력 레이어 PNG들
    ├── hair_back.png
    ├── body.png
    ├── face_base.png
    ├── eye_white_L.png
    ├── eye_iris_L.png
    ├── eyelid_L.png
    ├── eye_white_R.png
    ├── eye_iris_R.png
    ├── eyelid_R.png
    ├── mouth_closed.png
    ├── mouth_open.png
    ├── brow_L.png
    ├── brow_R.png
    ├── nose.png
    ├── cheek_blush.png
    ├── hair_front.png
    ├── hair_side_L.png
    ├── hair_side_R.png
    ├── hood.png
    ├── tail_base.png
    ├── tail_mid.png
    ├── tail_tip.png
    └── skirt.png
```

> 💡 **팁**: See-through가 출력한 레이어 이름이 다를 수 있습니다.
> 파일명을 위 목록에 맞게 바꾸거나, `bone_config.json`의 `image` 필드를 실제 파일명으로 수정하세요.

### 2-2. bone_config.json 편집

처음 실행하면 `bone_config.json`이 자동으로 생성됩니다.
레이어 이미지에 맞게 편집해주세요.

#### 핵심 수정 포인트

**① 레이어 이미지 경로 확인**
```json
{
  "layers": [
    {
      "name": "face_base",
      "image": "face_base.png",    ← 실제 파일명과 일치시키기
      "bone": "head",
      "zOrder": 10
    }
  ]
}
```

**② 위치 튜닝 (display)**
```json
{
  "display": {
    "scale": 0.15,      ← 캐릭터 크기 (키우려면 값 올리기)
    "offsetX": 400,      ← 화면 내 X 위치
    "offsetY": 360       ← 화면 내 Y 위치
  }
}
```

**③ 뼈대 위치 튜닝**
```json
{
  "bones": [
    {
      "name": "head",
      "parent": "body",
      "x": 0,            ← 부모(body) 기준 X 오프셋
      "y": -180           ← 부모(body) 기준 Y 오프셋 (위쪽이 음수)
    }
  ]
}
```

### 2-3. 레이어가 적을 때

See-through가 눈을 분리하지 못했다면? 괜찮습니다!
입을 열어야 하는 mouth_open/mouth_closed만 분리하면 립싱크가 동작합니다.

**최소 레이어** (3개만 있어도 동작):
- `body.png` — 전체 캐릭터
- `mouth_closed.png` — 입 닫힌 상태
- `mouth_open.png` — 입 열린 상태

---

## Step 3: Pi에서 실행

```bash
# 1. 파일 복사
scp -r models/wani/layers/ pi@raspberrypi:~/wani-ai/models/wani/layers/
scp models/wani/bone_config.json pi@raspberrypi:~/wani-ai/models/wani/

# 2. 실행
ssh pi@raspberrypi
cd ~/wani-ai
./scripts/start.sh
```

**자동으로 동작하는 것들:**
- ✅ 호흡 (몸이 약간 위아래)
- ✅ 자동 눈 깜빡임 (3~5초 간격)
- ✅ 립싱크 (mouth_open↔closed 전환)
- ✅ 머리 미세 움직임 (기울기)
- ✅ 꼬리 흔들기 (감정에 따라 속도 변화)
- ✅ 머리카락/꼬리 물리 시뮬 (스프링)
- ✅ 감정별 눈썹/볼/꼬리 변화
- ✅ 상태 표시 (대기/듣는 중/생각 중/말하는 중)

---

## 🔧 고급: bone_config.json 포맷 상세

### bones — 뼈대 정의

```json
{
  "name": "head",        // 고유 이름
  "parent": "body",      // 부모 뼈대 (root면 생략)
  "x": 0,               // 부모 기준 X 위치
  "y": -180,             // 부모 기준 Y 위치
  "angle": 0,            // 기본 회전각 (도)
  "scaleX": 1.0,         // X 스케일
  "scaleY": 1.0          // Y 스케일
}
```

### layers — 레이어 정의

```json
{
  "name": "face_base",       // 고유 이름
  "image": "face_base.png",  // layers/ 안의 파일명
  "bone": "head",            // 따라갈 뼈대 이름
  "offsetX": 0,              // 뼈대 기준 추가 오프셋
  "offsetY": 0,
  "pivotX": 0.5,             // 회전 중심 (0~1, 이미지 비율)
  "pivotY": 0.5,
  "zOrder": 10,              // 그리기 순서 (큰 값 = 앞)
  "visible": true            // 기본 표시 여부
}
```

### drivers — 파라미터 → 뼈대 구동 규칙

```json
{
  "param": "ParamAngleX",    // 제어 파라미터 이름
  "bone": "head",            // 적용할 뼈대
  "property": "angle",       // "x", "y", "angle", "scaleX", "scaleY"
  "scale": 0.5,              // 파라미터 값에 곱하는 배율
  "additive": false          // true면 기존 값에 더함
}
```

### physics — 간이 물리 시뮬레이션

```json
{
  "bone": "hair_front",      // 물리 적용 뼈대
  "property": "angle",       // 물리가 제어할 속성
  "damping": 0.85,           // 감쇠 (1에 가까울수록 오래 흔들림)
  "stiffness": 0.3,          // 강성 (높을수록 빠르게 복원)
  "input": "ParamAngleX"     // 물리 입력 파라미터
}
```

---

## ❓ FAQ

**Q: See-through AI 결과물이 이상해요**
> A: 캐릭터 포즈가 정면이고 팔다리가 겹치지 않을수록 결과가 좋습니다.
> 고해상도(4K+) 이미지를 사용하세요.

**Q: 레이어가 너무 적게 분리돼요**
> A: See-through는 max 24개 레이어를 지원합니다. `--num_layers` 파라미터를 높여보세요.
> 또는 수동으로 추가 분리(눈, 입 등)해도 됩니다.

**Q: 움직임이 어색해요**
> A: `bone_config.json`에서 뼈대 위치(`x`, `y`)와 드라이버 `scale` 값을 조정하세요.
> 시행착오가 필요하지만 코드 수정 없이 JSON만 편집하면 됩니다.

**Q: 나중에 Live2D로 업그레이드하고 싶으면?**
> A: `wani.model3.json`을 `models/wani/`에 넣으면 자동으로 Live2D 렌더러로 전환됩니다.
> 기존 코드 변경 없이 동작합니다 (우선순위: Live2D > Skeletal > Sprite).
