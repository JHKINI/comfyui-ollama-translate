from flask import Flask, request, render_template, jsonify
from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from summarize_chain import summarize_text

app = Flask(__name__)

_json_llm = ChatOllama(model="gemma4:e2b", temperature=0.2,
                       base_url="http://host.docker.internal:11434")
_json_parser = JsonOutputParser()
_json_format = _json_parser.get_format_instructions()
_json_prompt = ChatPromptTemplate.from_template(
    """다음 텍스트를 JSON으로 요약해.
- "summary": 한국어 핵심 요약(3~5문장)
- "keywords": 핵심 키워드 5~8개 리스트
- "oneline": 한 줄 요약(20자 내외)
반드시 JSON만 출력.
{format_instructions}
텍스트:
{content}
"""
)
_json_chain = _json_prompt | _json_llm | _json_parser


@app.route("/", methods=["GET"])
def index():
    return render_template("summarize.html")


@app.route("/summarize", methods=["POST"])
def summarize():
    text = (request.get_json(silent=True) or {}).get("text", "").strip()
    if not text:
        return jsonify({"error": "텍스트를 입력하세요."}), 400
    try:
        return jsonify({"summary": summarize_text(text)})
    except Exception as e:
        return jsonify({"error": f"요약 실패: {e}"}), 500


@app.route("/summarize/structured", methods=["POST"])
def summarize_structured():
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return {"error": "text 필드가 필요합니다."}, 400
    try:
        result = _json_chain.invoke({
            "content": text,
            "format_instructions": _json_format
        })
    except OutputParserException as e:
        # 모델이 JSON 외 텍스트를 섞어내면 파서가 예외를 던짐
        return {"error": f"모델 응답을 JSON으로 파싱하지 못했습니다: {e}"}, 502
    return result


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
