from flask import request, jsonify, url_for
import os, json, requests
from ..db import get_db
from . import bp


def _find_nearest_hub(user_lat, user_lon, db):
    """
    사용자의 위도/경도를 기반으로 DB에서 가장 가까운 허브 이름을 찾습니다.
    """
    if user_lat is None or user_lon is None:
        return None
        
    try:
        user_lat = float(user_lat)
        user_lon = float(user_lon)
    except ValueError:
        return None

    # menu2.py의 쿼리를 참고하여 모든 허브의 위치를 가져옵니다.
    rows = db.execute("SELECT hub_name, latitude, longitude FROM hubs").fetchall()
    
    min_dist_sq = float('inf')
    nearest_hub = None
    
    for hub in rows:
        if not hub['latitude'] or not hub['longitude']:
            continue
        
        # 간단한 유클리드 거리 제곱 계산 (근사치)
        dist_sq = (user_lat - hub['latitude'])**2 + (user_lon - hub['longitude'])**2
        
        if dist_sq < min_dist_sq:
            min_dist_sq = dist_sq
            nearest_hub = hub['hub_name']
            
    return nearest_hub

@bp.route("/available-nearby-bikes", methods=["GET"])
def available_nearby_bikes():
  """
  사용자의 현재 위치(lat, lon)를 받아, 내부 /api/available-nearby-bikes를 호출하고
  가장 가까운 허브의 이용가능 자전거 대수만 요약해서 반환한다.

  예:
    GET /api/closest-available-bikes?lat=36.0123&lon=129.3210&r_km=1.0&limit=10
  응답 형태:
  {
    "query": {...},
    "closest": {
      "hub_id": ...,
      "hub_name": "...",
      "distance_km": 0.123,
      "available_bikes": 7
    },
    "count_examined": 5
  }
  """
  # 필수 파라미터
  lat_raw = request.args.get("lat")
  lon_raw = request.args.get("lon")
  if lat_raw is None or lon_raw is None:
      return jsonify({
            "hub_name": None,              
            "found": False,
            "available_bikes": 0,
            "error": "lat, lon 쿼리 파라미터가 필요합니다 (float)"
        }), 400

        
  db = get_db()
  nearest_hub = _find_nearest_hub(lat_raw, lon_raw, db)
  print(f'nearest_hub : {nearest_hub}')
  if nearest_hub == None:
    return jsonify({
            "hub_name": None,             
            "found": False,
            "available_bikes": 0,
            "error": "근처 허브를 찾을 수 없습니다."
        }), 400

  hub = db.execute("SELECT hub_id FROM hubs WHERE hub_name = ?", (nearest_hub,)).fetchone()
  if not hub:
    return jsonify({"hub_name" : nearest_hub, "found" : False, "available_bikes": 0, "error" : f"{nearest_hub} 허브를 찾을 수 없습니다."}), 200

  row = db.execute(
    '''
    SELECT COUNT(*) AS cnt
    FROM bikes
    WHERE assigned_hub_id = ?
      AND is_active = 1
      AND is_under_repair = 0
      AND is_retired = 0
      AND status = 'Returned'
    ''',
    (hub["hub_id"], ),
  ).fetchone()

  data = {
    "hub_name" : nearest_hub,
    "found" : True,
    "available_bikes" : int(row["cnt"])
  }
  print(data)
  
  """내부 API(/available-bikes) 호출"""
  api_url = url_for("api.generate_sentence", _external=True)
  try:
    res = requests.post(api_url, 
                        json={"messages_for_model": [
                            {"role": "system", "content":"You are Poring-AI, a chatbot for a bike rental service. You will engage in natural conversation with the user to tell them the number of available bikes at a specified location. If there are no bikes at that location, recommend the nearest alternative station. Rules: 1) Always maintain a friendly and warm tone. 2) Keep answers concise, limited to 1-2 sentences. 3) Do not provide unnecessary explanations, background information, or verbose descriptions. 4) Avoid an overly humorous or casual tone. 5) Always respond in short, clear Korean sentences."},
                            {"role":"user", "content": f"다음 값을 자연스럽게 한문장으로 바꿔줘 허브이름 : {data['hub_name']}, 자전거 개수 : {data['available_bikes']}"}
                            ],
                            "data" : data},
                        timeout=5)
    return res.json()
  except Exception as e:
    data["error"] = str(e)
    return jsonify(data)