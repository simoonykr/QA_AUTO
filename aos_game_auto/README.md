# AOS Game QA Automation MVP

Template capture GUI usage: see `TEMPLATE_CAPTURE_GUI.md`.

ADB로 Android 단말 화면을 캡처하고, OpenCV template matching으로 화면 상태를 인식한 뒤, JSON에 정의된 액션을 실행하는 CLI 기반 QA 자동화 MVP입니다.

이 프로젝트는 AI 자동 플레이가 아니라 반복 QA 검증을 위한 안정적인 이미지 기반 자동화를 목표로 합니다.

## 폴더 구조

```text
aos_game_auto/
 ├─ main.py
 ├─ requirements.txt
 ├─ README.md
 ├─ adb/
 │   └─ adb_controller.py
 ├─ vision/
 │   └─ image_matcher.py
 ├─ actions/
 │   └─ action_runner.py
 ├─ config/
 │   └─ scenarios.json
 ├─ templates/
 ├─ logs/
 └─ screenshots/
```

## 설치 방법

Python 3.10 이상 사용을 권장합니다.

```powershell
cd aos_game_auto
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## ADB 설치 및 환경변수

1. Android SDK Platform Tools를 설치합니다.
   - https://developer.android.com/tools/releases/platform-tools
2. 압축 해제한 `platform-tools` 폴더를 Windows 환경변수 `PATH`에 추가합니다.
3. 새 PowerShell을 열고 아래 명령으로 확인합니다.

```powershell
adb version
adb devices
```

단말에서는 개발자 옵션과 USB 디버깅을 켜야 합니다. `adb devices` 결과에 `unauthorized`가 보이면 단말 화면에서 USB 디버깅 허용 팝업을 승인하세요.

## scenarios.json 작성 방법

기본 설정 파일은 `config/scenarios.json`입니다.

```json
{
  "app": {
    "package": "com.example.game",
    "activity": "com.example.game.MainActivity"
  },
  "loop": {
    "interval_seconds": 1,
    "max_iterations": 300
  },
  "scenarios": [
    {
      "name": "start_button",
      "template": "templates/start_button.png",
      "threshold": 0.85,
      "action": {
        "type": "tap",
        "offset_x": 0,
        "offset_y": 0
      }
    }
  ]
}
```

Multi-template scenarios are also supported. Use `templates` when one UI target needs several captured samples:

```json
{
  "name": "start_button",
  "template": "templates/start_button/start_button_001.png",
  "templates": [
    "templates/start_button/start_button_001.png",
    "templates/start_button/start_button_002.png",
    "templates/start_button/start_button_003.png"
  ],
  "threshold": 0.85,
  "action": {
    "type": "tap"
  }
}
```

The automation checks every path in `templates` and uses the highest scoring match for that scenario. The single `template` field is kept for backward compatibility and for logs.

OCR scenarios are optional and require Tesseract OCR to be installed on Windows. If OCR is not installed, image template scenarios still work.

If `tesseract.exe` is not in `PATH`, pass it explicitly:

```powershell
python main.py --tesseract-cmd "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

```json
{
  "name": "confirm_by_text",
  "script": "default",
  "match": {
    "type": "ocr",
    "text": "확인",
    "threshold": 0.6,
    "lang": "kor+eng",
    "contains": true
  },
  "action": {
    "type": "tap"
  }
}
```

Hybrid matching is also supported. The scenario succeeds when either image or OCR matching succeeds:

```json
{
  "name": "login_button",
  "script": "default",
  "match_any": [
    {
      "type": "template",
      "templates": [
        "templates/login/login_001.png",
        "templates/login/login_002.png"
      ],
      "threshold": 0.85
    },
    {
      "type": "ocr",
      "text": "로그인",
      "threshold": 0.6,
      "lang": "kor+eng"
    }
  ],
  "action": {
    "type": "tap"
  }
}
```

`scenarios`는 위에서 아래 순서대로 검사합니다. threshold 이상으로 매칭된 첫 번째 scenario의 action만 실행됩니다.

지원 action:

- `tap`: 매칭 center 좌표를 터치합니다. `offset_x`, `offset_y`를 추가할 수 있습니다.
- `double_tap`: 같은 좌표를 두 번 터치합니다. `interval_seconds`로 간격을 지정할 수 있습니다.
- `swipe`: `x1`, `y1`, `x2`, `y2`, `duration_ms` 값을 사용합니다.
- `wait`: `seconds` 동안 대기합니다.
- `save_screenshot`: 현재 스크린샷을 별도 파일로 저장합니다.
- `stop`: 루프를 종료합니다.
- `stop_and_save`: 현재 스크린샷을 저장하고 루프를 종료합니다.

## 실행 방법

```powershell
python main.py
```

다른 설정 파일을 쓰려면:

```powershell
python main.py --config .\config\my_scenarios.json
```

특정 단말을 지정하려면:

```powershell
python main.py --device DEVICE_ID
```

앱 실행 단계 없이 현재 화면에서만 테스트하려면:

```powershell
python main.py --skip-start-app
```

Repeat a script a fixed number of times:

```powershell
python main.py --script default --runs 5
```

Run as a monitoring loop for a duration:

```powershell
python main.py --script default --monitor-hours 2
python main.py --script default --monitor-minutes 30
```

Run mode:

```powershell
python main.py --script default --run-mode sequence
python main.py --script default --run-mode scan
```

- `sequence`: script steps move forward after a match. This is best for ordered QA flows.
- `scan`: every loop checks all scenarios from the beginning. This is best for always-on popup/error handling.
- When `--script` is used and no mode is provided, `sequence` is used by default.

## Windows 실행파일 빌드

PyInstaller로 `aos_game_auto.exe`를 만들 수 있습니다.

```powershell
cd aos_game_auto
.\build_exe.ps1
```

빌드 결과는 `dist/aos_game_auto_package/`에 생성됩니다.

```text
dist/aos_game_auto_package/
 ├─ aos_game_auto.exe
 ├─ config/
 ├─ templates/
 ├─ logs/
 └─ screenshots/
```

실행파일은 같은 폴더의 `config/scenarios.json`과 `templates/`를 사용합니다.

```powershell
cd dist\aos_game_auto_package
.\aos_game_auto.exe
```

ADB가 PATH에 없으면 `platform-tools` 폴더를 `aos_game_auto.exe` 옆에 두거나 아래처럼 직접 지정합니다.

```powershell
.\aos_game_auto.exe --adb .\platform-tools\adb.exe
```

`templates/`에 실제 PNG 파일이 없으면 프로그램은 루프를 시작하지 않고 어떤 파일이 빠졌는지 로그에 남깁니다. 템플릿 없이 ADB 캡처 흐름만 강제로 확인하려면 아래 옵션을 사용할 수 있습니다.

```powershell
.\aos_game_auto.exe --allow-missing-templates
```

템플릿 제작용 기준 스크린샷만 한 장 저장하려면:

```powershell
.\aos_game_auto.exe --capture-only
```

## Template 이미지 준비 방법

1. 단말 해상도와 같은 환경에서 기준 화면을 캡처합니다.
2. 버튼, 팝업, 로딩 아이콘 등 인식할 영역만 작게 잘라 PNG로 저장합니다.
3. `templates/` 폴더에 저장하고 `scenarios.json`의 `template` 경로에 입력합니다.
4. 처음에는 `threshold`를 `0.8`에서 `0.9` 사이로 조정해보세요.

Template은 너무 넓은 화면 전체보다 특징이 분명한 작은 UI 영역이 안정적입니다. 애니메이션, 반투명 효과, 날짜/숫자처럼 자주 바뀌는 영역은 피하는 편이 좋습니다.

In `template_capture_gui.exe`, use the `Burst` button or `B` key to switch between `1`, `3`, `5`, and `10` captures. Burst mode saves multiple PNG files under `templates/{name}/` and registers them as a `templates` array in `scenarios.json`.

## 로그

실행 로그는 `logs/`에 저장됩니다.

- `run_YYYYMMDD_HHMMSS.log`: 콘솔 로그와 동일한 일반 실행 로그
- `results_YYYYMMDD_HHMMSS.csv`: iteration별 QA 결과 로그

CSV에는 시간, iteration 번호, scenario name, template path, match score, match 좌표, action, 성공 여부, screenshot path, 별도 저장 screenshot path가 기록됩니다.

캡처 이미지는 `screenshots/`에 저장됩니다.

## 자주 발생하는 오류

### `adb executable was not found`

ADB가 설치되어 있지 않거나 PATH에 없습니다. Android Platform Tools를 설치하고 `platform-tools` 폴더를 PATH에 추가하세요.

### `No connected adb device found`

USB 연결, USB 디버깅 설정, 케이블 상태를 확인하세요. `adb devices`로 단말이 `device` 상태인지 확인합니다.

### `unauthorized`

단말 화면에서 USB 디버깅 허용 팝업을 승인해야 합니다. 필요하면 `adb kill-server`, `adb start-server` 후 다시 연결하세요.

### 앱 실행 실패

`package` 또는 `activity` 값이 틀렸을 수 있습니다. 설치된 패키지 목록은 아래 명령으로 확인할 수 있습니다.

```powershell
adb shell pm list packages
```

### template 매칭이 되지 않음

- template 경로가 맞는지 확인합니다.
- 단말 해상도, UI 스케일, 언어 설정이 template을 만들 때와 같은지 확인합니다.
- threshold를 낮춰 테스트합니다.
- template에 움직이는 배경이나 숫자처럼 자주 변하는 영역이 포함되어 있지 않은지 확인합니다.

## 개발 메모

- ADB 제어는 `adb/adb_controller.py`
- 이미지 매칭은 `vision/image_matcher.py`
- 액션 실행은 `actions/action_runner.py`
- CLI 실행 흐름은 `main.py`

GUI를 추가할 때는 이 모듈들을 그대로 호출하고, 설정 편집과 실행 상태 표시만 UI 계층에서 담당하도록 확장하면 됩니다.
