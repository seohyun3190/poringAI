from flask import Blueprint, render_template, request, url_for, session
import os, json, requests

bp = Blueprint("api", __name__)

from . import available_bikes
from . import generate_sentence
from . import available_nearby_bikes



def fetch_available_bikes(hub_name: str):
  """내부 API(/available-bikes) 호출"""
  api_url = url_for("api.available_bikes", _external=True)
  try:
    res = requests.get(api_url, params={"hub_name": hub_name}, timeout=5)
    return res.json(), res.status_code
  except Exception as e:
    return {"hub_name": hub_name, "found": False, "available_bikes": 0, "error": str(e)}, 500

    
def fetch_available_nearby_bikes(lat: float, lon: float):
  """
  내부 API /api/available-nearby-bikes를 호출해 가까운 허브 목록을 그대로 받아온다.
  서버 내부에서 거리 계산은 하지 않는다(요청만 전달).
  """
  api_url = url_for("api.available_nearby_bikes", _external=True)
  params = {"lat": lat, "lon": lon}

  try:
    res = requests.get(api_url, params=params, timeout=5)
    return res.json(), res.status_code
  except Exception as e:
    return {
        "hub_name" : None,
        "query": {"lat": lat, "lon": lon},
        "found": False,
        "available_bikes": 0,
        "error": str(e)
    }, 500