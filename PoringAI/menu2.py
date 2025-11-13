from flask import(
  Blueprint, flash, g, redirect, render_template, request, url_for
)
from werkzeug.exceptions import abort
from .db import get_db

bp = Blueprint('menu2', __name__, url_prefix='/menu2')

@bp.route('/')
def menu2():
  db = get_db()

  sql = '''
  SELECT
        h.hub_id,
        h.hub_name,
        h.latitude,
        h.longitude,
        COALESCE(SUM(s.parked_slot), 0) AS parked_sum,
        COALESCE(SUM(s.total_slots), 0)  AS total_sum
    FROM hubs h
    LEFT JOIN stations s ON s.hub_id = h.hub_id
    GROUP BY h.hub_id, h.hub_name, h.latitude, h.longitude
    ORDER BY h.hub_id;
  '''
  rows = db.execute(sql).fetchall()

  hubs = [dict(row) for row in rows]

  return render_template("menu2.html", hubs=hubs);