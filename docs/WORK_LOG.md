# 작업 로그 — ComfyUI + Ollama 번역 연동 (2026-11-20)

## 목표

`app.py`(구버전)를 기반으로, 다음 플로우를 구현하고 VM 배포 환경에서 end-to-end로 동작 확인:

```
사용자가 웹 폼에 한국어 프롬프트 입력 → Enter
  → "영어로 번역해줘" 붙여서 Ollama로 전송
  → Ollama의 영어 번역 응답을 받음
  → 그 응답을 ComfyUI에 이미지 생성 프롬프트로 전송
  → 생성된 이미지를 응답받아 app.py 프론트(HTML)에 표시
```

> `app2.py`(신버전)는 참고만 하고 덮어쓰지 않음 — 수업용 구버전(`app.py`) 로직을 그대로 유지하면서 기능만 추가.

## 아키텍처

```
[VM: 192.168.26.188]              [로컬 PC: 192.168.24.115, RTX 3080]
  comfy-web (Flask, Docker)  ──►    comfyui (Docker, :8188)
     브라우저 프론트 요청/응답         ollama (Docker, :11434, gemma4:e2b)
```

- 브라우저는 VM의 Flask 서버에만 접근하고, Flask가 로컬 PC의 ComfyUI/Ollama를 내부적으로 호출(proxy)하는 구조.
- 기존 `VM_배포가이드.md`에 적힌 "교수님 PC(192.168.24.135)" 구조는 더 이상 사용하지 않음 — 현재는 본인 로컬 PC가 GPU 서버 역할.

## `app.py` 변경 사항

1. **Ollama 번역 함수 추가** — `translate_to_english()`
   - 입력 프롬프트에 `"영어로 번역해줘. 번역된 문장만 출력해."`를 붙여 `/api/generate` 호출
   - `gemma4:e2b` 모델은 콜드 로딩에 몇 분씩 걸릴 수 있어, **타임아웃 300초 + 재시도 없이 한 번만 길게 대기**
     - 처음엔 짧은 타임아웃 + 재시도 로직을 넣었다가, 짧은 타임아웃으로 연결이 끊기면 서버 쪽 모델 로딩 자체가 취소되어(`client connection closed before llama-server finished loading, aborting load`) 재시도할수록 계속 처음부터 콜드 로딩되는 역효과가 있다는 걸 로그로 확인 → 제거
   - `keep_alive: "30m"`으로 모델을 좀 더 오래 메모리에 유지
2. **ComfyUI VRAM 선제 해제** — `free_comfy_vram()`
   - 번역 요청 전에 ComfyUI `/free` 엔드포인트(`unload_models`, `free_memory`)를 호출해 VRAM을 비워 Ollama가 로딩할 공간을 확보
3. **ComfyUI 제출 타임아웃 연장** — `submit_prompt()` 의 `/prompt` 타임아웃을 10초 → 120초로 증가 (체크포인트 최초 로딩 시 지연 대응)
4. **프론트 기본 예시 프롬프트 변경**
   - positive: `"멋진 집과 뒤로 보이는 산 풍경"`
   - negative: `"사람"`
5. **번역 결과 노출** — `templates/image.html`에 번역된 영어 프롬프트를 화면에 표시하는 블록 추가

## 디버깅: Ollama가 계속 응답 없음/타임아웃

증상: `/api/generate` 호출이 간헐적이 아니라 지속적으로 타임아웃됨.

원인 조사 순서 (각각 배제):
1. 본인 터미널에서 띄워둔 `ollama run` CLI 세션의 큐 경쟁 — 종료해도 문제 지속 → 배제
2. 이전 내가 실수로 만든 좀비 연결(백그라운드 안에 백그라운드를 또 돌려 추적 안 된 프로세스)이 Ollama의 단일 요청 큐(`OLLAMA_NUM_PARALLEL=1`)를 막음 — `docker restart ollama` 후에도 지속 → 배제
3. ComfyUI가 들고 있는 체크포인트가 VRAM을 차지 — `free_comfy_vram()` 추가, `/free` 정상 응답 확인했지만 그래도 지속 → 완전한 원인은 아님(그래도 안전장치로 유지)
4. **최종 원인**: 컨테이너 안이 아니라 **Windows 호스트에서 직접** `nvidia-smi`를 실행해보니, RTX 3080(10GB) VRAM의 94%(9643MiB)를 일반 GUI 앱들이 점유 중이었음 — Chrome 2개, Edge/webview2 다수, Teams 2개, 한글/Office 7개, GitHub Desktop, VS Code, **Epic Games Launcher + EpicWebHelper**, Claude 데스크톱 앱 2개, ChatGPT 데스크톱 앱 2개, Docker Desktop, Termius 등
   - Windows WDDM이 창을 띄운 앱마다 GPU 메모리를 할당하는데, 열려 있는 GUI 앱이 너무 많아 ComfyUI + Ollama가 쓸 CUDA 메모리가 거의 안 남아 모델 로딩이 계속 멈춤
   - 작업 관리자(Ctrl+Shift+Esc)에서 "작업 끝내기"로 불필요한 앱들을 정리(창의 X 버튼만 누르면 트레이로 숨는 앱도 있어 완전히 종료되지 않는 경우가 있었음)
   - 정리 후 `/api/generate` 테스트 → 4.3초 내 정상 응답 확인

## 최종 결과

- VM에서 띄운 프론트에서 요청 → 번역 → ComfyUI 이미지 생성 → 화면 표시까지 전체 플로우 정상 동작 확인 (`되더라`)

## VM 배포 (FileZilla)

전송 대상 파일:
- `app.py`
- `requirements.txt`
- `Dockerfile`
- `templates/image.html`
- `static/test.json`

(불필요: `app2.py`, `VM_배포가이드.md`, `deploy_vm.sh`, `static/flux2.json`, `__pycache__/`)

빌드/실행 명령 (VM, `~/comfyui`):

```bash
cd ~/comfyui
sudo docker build -t comfy-web .
sudo docker rm -f comfy-web 2>/dev/null
sudo docker run -d --name comfy-web --restart unless-stopped \
  -p 5000:5000 \
  -e COMFY_URL=http://192.168.24.115:8188 \
  -e OLLAMA_URL=http://192.168.24.115:11434 \
  -e OLLAMA_MODEL=gemma4:e2b \
  comfy-web
```

## 참고 / 교훈

- Ollama 같은 느린 콜드 로딩 모델은 **짧은 타임아웃 + 재시도**보다 **긴 타임아웃 1회**가 낫다 (클라이언트가 연결을 끊으면 서버 쪽 로딩도 취소됨).
- `docker exec <container> nvidia-smi`는 컨테이너 관점이라 프로세스 목록이 안 보일 수 있음(WDDM/WSL2 GPU passthrough 한계) — 실제 점유 프로세스 확인은 호스트(Windows cmd)에서 직접 `nvidia-smi` 실행해야 함.
- GPU 메모리가 부족한 간헐적/상시적 모델 로딩 실패는 소프트웨어 버그가 아니라 **호스트에서 열려 있는 다른 GPU 가속 앱들과의 VRAM 경쟁**일 수 있음 — 데모/수업 전 불필요한 앱 정리 권장.
