## Prompt Studio.  한국어 입력 → LangChain 구조화 번역 → ComfyUI 이미지 생성

한국어로 positive / negative 프롬프트를 입력하면, 로컬 LLM(Ollama `gemma4:e2b`)이 **한 번의 호출**로 영어 프롬프트를 JSON으로 만들어 주고, 그 결과를 ComfyUI에 보내 이미지를 생성해 웹 화면에 보여주는 Flask 앱입니다.

```
브라우저 ─▶ Flask(app.py) ─▶ LangChain + Ollama  : 한국어 → 영어, JSON 구조화 (1회 호출)
                          └▶ ComfyUI            : 영어 프롬프트로 이미지 생성
                          └▶ /view 프록시        : 생성된 이미지를 브라우저로 전달
```
## 결과화면 
<img src="image/스크린샷 2026-11-25 090903.png" width="600"> 
## 구조화 출력 (접이식 JSON)

화면의 이미지 아래에 입력 원문과 번역 결과가 JSON으로 표시됩니다 (클릭해서 접고 펼 수 있음).

```json
{
  "kor_positive": "눈 덮인 숲속의 작은 오두막",
  "kor_negative": "사람, 흐릿함",
  "eng_positive": "A small cabin in a snowy forest",
  "eng_negative": "people, blurry"
}
```

- `kor_*` 는 사용자가 입력한 **원문 그대로**입니다. 모델이 다시 쓰지 않으므로 원문이 바뀔 위험이 없습니다.
- `eng_*` 만 모델이 번역해서 JSON으로 돌려줍니다. 이 값이 ComfyUI 워크플로의 positive / negative 노드에 들어갑니다.

## 핵심 코드 (`app.py`)

```python
_llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_URL, temperature=0.2,
                  format="json", keep_alive="30m", client_kwargs={"timeout": 300})
_parser = JsonOutputParser()
_prompt = ChatPromptTemplate.from_template(
    """다음 한국어 이미지 생성 프롬프트를 영어로 번역해서 JSON으로만 출력해.
- "eng_positive": ...
- "eng_negative": ...
{format_instructions}

positive: {kor_positive}
negative: {kor_negative}
""")
_chain = _prompt | _llm | _parser        # 프롬프트 → LLM → JSON 파싱
```

- `format="json"` 으로 Ollama가 JSON만 출력하도록 강제하고, `JsonOutputParser` 가 dict 로 바꿉니다.
- 모델이 JSON이 아닌 글을 섞어 내면 `OutputParserException` 을 잡아 화면에 오류 메시지를 보여줍니다.
- 모델 콜드 로딩이 오래 걸릴 수 있어 타임아웃을 300초로 두고, **재시도하지 않습니다**. 클라이언트가 연결을 끊으면 서버의 모델 로딩 자체가 취소되기 때문입니다.
- 번역 전에 ComfyUI의 `/free` 를 호출해 VRAM을 비워 Ollama가 모델을 올릴 공간을 확보합니다.

## 파일 구성

```
.
├── app.py                 # Flask 앱 (LangChain 체인 + ComfyUI 연동)
├── templates/image.html   # 입력 폼, 이미지, 접이식 JSON
├── static/test.json       # ComfyUI 워크플로 (SDXL Turbo)
├── requirements.txt       # flask, requests, langchain-core, langchain-ollama
├── Dockerfile
└── langchain_practice/    # LangChain + Ollama 요약 Chain 실습 (아래 참고)
```

워크플로(`static/test.json`)의 노드 번호가 `app.py` 의 `update_prompts()` 와 일치해야 합니다: `6` = positive, `7` = negative, `13` = 시드(`noise_seed`, 요청마다 랜덤).

## 실행

### 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI 서버 주소 |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama 서버 주소 |
| `OLLAMA_MODEL` | `gemma4:e2b` | 번역에 쓸 모델 (서버에 실제로 있는 태그여야 함) |
| `WORKFLOW_PATH` | `static/test.json` | ComfyUI 워크플로 JSON |
| `PORT` | `5000` | Flask 포트 |

### 직접 실행

```bash
pip install -r requirements.txt
COMFY_URL=http://<GPU-PC-IP>:8188 OLLAMA_URL=http://<GPU-PC-IP>:11434 python app.py
```

브라우저에서 `http://127.0.0.1:5000/` → 프롬프트 입력 후 **이미지 생성** (또는 Ctrl+Enter).

### Docker

```bash
docker build -t comfy-web .
docker run -d --name comfy-web -p 5000:5000 \
  -e COMFY_URL=http://<GPU-PC-IP>:8188 \
  -e OLLAMA_URL=http://<GPU-PC-IP>:11434 \
  -e OLLAMA_MODEL=gemma4:e2b \
  comfy-web
```

### ComfyUI 서버 (Docker 컨테이너에서 실행하는 경우)

컨테이너가 재시작되면 안에서 켜 둔 프로세스도 꺼지므로 다시 실행해야 합니다. 밖에서 접속하려면 `--listen 0.0.0.0` 이 필요합니다.

```bash
docker exec -it comfyui bash
cd /ComfyUI && python main.py --listen 0.0.0.0 --port 8188
```

## 문제 해결

| 증상 | 원인 / 해결 |
|---|---|
| `model '...' not found` | 모델 태그 오타. `GET <OLLAMA_URL>/api/tags` 로 실제 이름 확인 (예: `gemma4:e2b`, `gemma4:2b` 아님) |
| `GPU 서버(...)에 연결할 수 없습니다` — Connection refused | ComfyUI 프로세스가 안 떠 있음 |
| 같은 에러인데 `RemoteDisconnected` | 포트는 열렸지만 컨테이너 안에서 응답 없음 — 아직 로딩 중이거나 `--listen 0.0.0.0` 누락 |
| 번역 서버가 5분 넘게 응답하지 않습니다 | Ollama 모델 로딩 실패. GPU 메모리 부족이 흔한 원인 (아래 참고) |
| 코드 수정했는데 화면이 그대로 | `DEBUG=1` 이 아니면 자동 리로드되지 않음 → Flask 재시작 |

**GPU 메모리**: 같은 GPU를 ComfyUI와 Ollama가 함께 쓰므로, Windows에서 브라우저·런처·데스크톱 앱 등이 VRAM을 점유하면 모델 로딩이 계속 실패할 수 있습니다. 컨테이너 안이 아니라 **호스트에서** `nvidia-smi` 를 실행해야 실제 점유 프로세스가 보입니다.

## 측정 결과

- 첫 요청(모델 콜드 로딩 포함): 약 81초
- 모델이 올라간 뒤: 약 17초 (번역 + 이미지 생성)
- Ollama 호출은 요청당 1회

## LangChain 요약 Chain 실습 (`langchain_practice/`)

같은 구조화 방식을 요약에 적용해 본 실습입니다. 이미지 생성 앱의 번역 단계가 이 패턴을 그대로 사용합니다.

| 파일 | 내용 |
|---|---|
| `hello.py` | `ChatPromptTemplate \| ChatOllama \| StrOutputParser` 체인으로 한 줄 자기소개 (연결 확인용) |
| `summarize_chain.py` | 텍스트 파일을 한국어 bullet 5개로 요약. `chain.stream()` 으로 스트리밍 출력 |
| `app.py` | `POST /summarize` (bullet 요약), `POST /summarize/structured` (`summary` / `keywords` / `oneline` JSON) |
| `templates/summarize.html` | 위 두 API를 웹에서 쓰는 화면 (구조화 결과는 카드 형태로 표시) |

```bash
cd langchain_practice
python summarize_chain.py <요약할_텍스트파일>        # 터미널 요약
python app.py                                       # 웹: http://127.0.0.1:5000/
# Ollama 주소는 코드의 base_url 에 직접 지정되어 있음 (기본 http://host.docker.internal:11434)
```

> 요약 샘플 텍스트(기사 원문)는 저작권 때문에 저장소에 포함하지 않았습니다. 아무 한국어 텍스트 파일을 넣어 실행하세요.
