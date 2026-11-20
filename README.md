# ComfyUI + Ollama 번역 연동 이미지 생성 웹

한국어 프롬프트를 입력하면 Ollama(`gemma4:e2b`)가 영어로 번역하고, 그 영어 프롬프트로 ComfyUI가 이미지를 생성해서 웹 화면에 보여주는 Flask 앱.

## 동작 흐름

```
브라우저(한국어 프롬프트 입력)
  → Flask: 프롬프트 + "영어로 번역해줘" → Ollama /api/generate
  → Flask: 영어 번역 결과 → ComfyUI /prompt (워크플로 test.json)
  → Flask: 완성 이미지를 /view 프록시로 전달 → 화면 표시
```

## 아키텍처

```
[VM: 192.168.26.188]              [로컬 PC: 192.168.24.115, RTX 3080]
  comfy-web (Flask, Docker)  ──►    comfyui (Docker, :8188)
                                    ollama  (Docker, :11434, gemma4:e2b)
```

브라우저는 VM의 Flask에만 접속하고, Flask가 로컬 PC의 ComfyUI / Ollama를 대신 호출한다.

## 폴더 구조

```
.
├── app.py                  # Flask 서버 (번역 + ComfyUI 연동)
├── requirements.txt        # flask, requests
├── Dockerfile
├── templates/image.html    # 프론트
├── static/test.json        # ComfyUI 워크플로
└── docs/WORK_LOG.md        # 작업 로그 / 디버깅 기록
```

## 환경변수

| 이름 | 기본값 | 설명 |
|---|---|---|
| `COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI 서버 주소 |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama 서버 주소 |
| `OLLAMA_MODEL` | `gemma4:e2b` | 번역에 쓸 모델 |
| `WORKFLOW_PATH` | `static/test.json` | 워크플로 JSON 경로 |
| `PORT` | `5000` | Flask 포트 |

## 실행

로컬 실행 (Python 3.10 이상):

```bash
pip install -r requirements.txt
python app.py
```

Docker (VM에서):

```bash
sudo docker build -t comfy-web .
sudo docker rm -f comfy-web 2>/dev/null
sudo docker run -d --name comfy-web --restart unless-stopped \
  -p 5000:5000 \
  -e COMFY_URL=http://192.168.24.115:8188 \
  -e OLLAMA_URL=http://192.168.24.115:11434 \
  -e OLLAMA_MODEL=gemma4:e2b \
  comfy-web
```

## 핵심 포인트

- **번역**: 프롬프트 뒤에 `영어로 번역해줘. 번역된 문장만 출력해.`를 붙여 호출. `keep_alive: 30m`으로 모델을 메모리에 유지.
- **타임아웃은 길게 1회 (300초)**: 짧게 끊고 재시도하면 서버 쪽 모델 로딩이 취소돼서 계속 처음부터 로딩됨.
- **VRAM 확보**: 번역 전에 ComfyUI `/free`로 모델을 내려서 Ollama가 올라갈 공간을 만듦.
- **이미지 프록시**: 브라우저가 GPU 서버에 직접 붙지 않도록 Flask `/view`가 이미지를 중계.

## 트러블슈팅 요약

Ollama가 계속 타임아웃 → 원인은 코드가 아니라 **Windows 호스트의 GUI 앱들이 VRAM 94%를 점유**하고 있던 것.
호스트 cmd에서 `nvidia-smi`로 확인하고(컨테이너 안에서는 안 보임), 작업 관리자로 불필요한 앱을 완전히 종료하니 4초대로 응답.
자세한 과정은 [docs/WORK_LOG.md](docs/WORK_LOG.md) 참고.
