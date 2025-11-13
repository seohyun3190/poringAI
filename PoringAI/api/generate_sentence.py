from flask import request, jsonify, url_for
import os, json, requests
from ..db import get_db
from . import bp

@bp.route("/generate-sentence", methods=["POST"])
def generate_sentence():
  try:    
    payload = request.get_json()
    messages_for_model = payload.get("messages_for_model")
    data = payload.get("data")
    
    if not isinstance(messages_for_model, list):
      return jsonify({"error": "messages_for_model must be a list of messages"}), 400
    
    ## TODO : MOCK 넣기 
    from openai import OpenAI   
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    # GPT에게 질문 보내기
    resp = client.chat.completions.create(
      model="gpt-4o-mini",
      messages=messages_for_model,
      temperature=0.1
    )

    # output 추출
    output = resp.choices[0].message.content

    data["content"] = output
    
    return jsonify(data), 200
              
  except Exception as e:
    data["error"] = str(e)
    return jsonify(data), 400