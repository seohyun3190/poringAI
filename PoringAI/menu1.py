from flask import Blueprint, render_template, request, url_for, session, redirect
from collections import deque
import time
import os, json, requests
from .api import fetch_available_bikes, fetch_available_nearby_bikes
from datetime import datetime

# 캐시 세팅
HIST_KEY = "menu1_hist" # Flask session에 저장할 키
MAX_MSGS = 16            # 최근 N개만 잡기
TTL_SEC = 60 * 30      # 30분 TTL, 0이면 비활성


bp = Blueprint('menu1', __name__, url_prefix='/menu1')

USE_MOCK = os.environ.get("OPENAI_MOCK", "0") == "1"

client = None
if not USE_MOCK:
  try:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
  except Exception:
    client = None

# OpenAI tools 정의
tools = [
  {
    "type": "function",
    "function": {
      "name": "get_available_bikes",
      "description": "허브 이름으로 이용가능 자전거 수를 조회한다.",
      "parameters": {
        "type": "object",
        "properties": {
          "hub_name": {
            "type": "string",
            "description": "허브의 정확한 이름을 추출해줘. 허브 이름에는 무은재기념관, 학생회관, 환경공학동, 생활관21동, 생활관3동, 생활관12동, 생활관15동, 박태준학술정보관, 친환경소재대학원, 제1실험동, 기계실험동, 가속기IBS가 있어. 지역에는 교사지역, 생활관지역, 인화지역, 가속기&연구실험동이 있어. 교사지역에 있는 허브로는 무은재기념관, 학생회관, 환경공학동이 있어. 생활관지역에는 생활관21동, 생활관3동, 생활관12동, 생활관15동이 있어. 인화지역에 있는 허브는 박태준학술정보관, 친환경소재대학원이 있어. 가속기&연구실험동에 있는 허브는 제1실험동, 기계실험동, 가속기IBS가 있어." # 자동으로 db에서 허브 이름 가져오는 시스템이 필요할듯
          }
        },
        "required": ["hub_name"]
      }
    }
  }, {
    "type": "function",
    "function": {
      "name": "get_available_nearby_bikes",
      "description": "자신 근처에 있는 허브의 이용가능 자전거 수를 조회한다. 질문에 자신의 근처를 묻는 것이 있어야한다."
    }
  }
]

@bp.app_template_filter('hm')
def hm(ts):
    try:
        return datetime.fromtimestamp(int(ts)).strftime('%H:%M')
    except Exception:
        return ''

@bp.route('/', methods=["GET", "POST"])
def menu1():
  answer = None
  question = None
  structured = None

  if request.method == "POST":
    question = (request.form.get("question") or "").strip()
    latitude = request.form.get("latitude")
    longitude = request.form.get("longitude")

    if question:
      if USE_MOCK or client is None:
        # MOCK 모드: 허브 이름 고정 예시
        structured = {"hub_name": "정문 앞", "found": True, "available_bikes": 5}
        answer = f"[MOCK] '{structured['hub_name']}' 허브 이용가능 대수: {structured['available_bikes']}대"
      else:
        try:
          hist = _get_history()
          messages_for_model = hist + [{"role" : "user", "content":question}]
          
          # GPT에게 질문 보내고 tool 호출 유도
          resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages_for_model,
            tools=tools,
            tool_choice="auto"
          )

          # tool call 추출
          tool_call = None
          tool_calls = resp.choices[0].message.tool_calls
          if tool_calls:
            tool_call = tool_calls[0]

          if tool_call:
            try:
              name = tool_call.function.name
              args = json.loads(tool_call.function.arguments)
            except Exception:
              name, args = None, {}

            if name == "get_available_bikes" and "hub_name" in args:
              # 0번째 : 실질적인 정보, 1번째 : status 코드
              structured = fetch_available_bikes(args["hub_name"])[0]
              
              # For Log
              print(structured)
              
              if not structured.get("error"):
                # answer = f"'{structured['hub_name']}' 허브 이용가능 대수: {structured['available_bikes']}대"
                answer = structured['content']
              else:
                msg = structured.get("error")
                answer = f"'{structured['hub_name']}' 허브를 찾을 수 없어요." + (f"\n[API ERROR] {msg}" if msg else "")

            elif name == "get_available_nearby_bikes":
                structured = fetch_available_nearby_bikes(latitude, longitude)[0]

                print(structured)

                if not structured.get("error"):
                  answer = structured['content']
                else:
                  msg = structured.get("error")
                  answer = f"'{structured['hub_name']}' 허브를 찾을 수 없어요." + (f"\n[API ERROR] {msg}" if msg else "")

            else:
              answer = "(허브 이름을 추출하지 못했습니다)"
          else:
              # 함수 호출이 없으면 일반 텍스트 응답 출력
              answer = resp.choices[0].message.content or "(응답이 없습니다)"
              
          
          
          # For Log
          _append("user", question)
          _append("system", answer)
          print(_get_history())
          
        except Exception as e:
          answer = f"[ERROR] {type(e).__name__}: {e}"

        return redirect(url_for('menu1.menu1'))

  # return render_template("menu1.html", question=question, answer=answer, structured=structured)
  history = _get_history()
  return render_template(
      "menu1.html",
      structured=structured,
      history=history,
  )


# 현재 시간 반환
def _now_ts():
  return int(time.time())

def _prune(hist_list):
  if not hist_list:
    return []
  if TTL_SEC > 0:
    cut_off = _now_ts() - TTL_SEC
    hist_list = [m for m in hist_list if (m.get("ts", 0) >= cut_off)]
  # 최근 MAX_MSGS만 유지
  if len(hist_list) > MAX_MSGS:
    hist_list = hist_list[-MAX_MSGS : ]
  return hist_list

def _get_history():
  hist = session.get(HIST_KEY, [])
  hist = _prune(hist)
  session[HIST_KEY] = hist
  session.modified = True
  return hist

def _append(role, content):
  content = (content or "").strip()
  hist = _get_history()
  hist.append({"role":role, "content":content, "ts" : _now_ts()})
  session[HIST_KEY] = _prune(hist)
  session.modified = True 
  
def _clear_history():
  session[HIST_KEY] = []
  session.modified = True

