# PoringAI/api/lock_api.py

from flask import request, jsonify
from ..db import get_db
from . import bp  # api/__init__.py 의 Blueprint("api", __name__) 재사용


def _as_int(value, name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name}는 정수여야 합니다.")


@bp.route("/lock-temporary", methods=["POST"])
def lock_temporary():
    """
    일시잠금:
    - lock_status 에 새 row 추가 (transferable=0, is_active=1)
    - bike.lock_state='locked', is_available=0 으로 변경
    """
    payload = request.get_json(silent=True) or {}
    bike_id = payload.get("bike_id")
    user_id = payload.get("user_id")
    lat = payload.get("lat")    # 잠근 위치 (있으면 기록)
    lng = payload.get("lng")

    try:
        bike_id = _as_int(bike_id, "bike_id")
        user_id = _as_int(user_id, "user_id")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    db = get_db()

    # 자전거 존재 여부 확인
    bike = db.execute(
        "SELECT bike_id FROM bike WHERE bike_id = ?",
        (bike_id,),
    ).fetchone()
    if bike is None:
        return jsonify({"error": "존재하지 않는 자전거입니다."}), 400

    # 이미 활성 잠금이 있다면 is_active=0 로 정리(여러 개 꼬이지 않게)
    db.execute(
        """
        UPDATE lock_status
        SET is_active = 0
        WHERE bike_id = ? AND user_id = ? AND is_active = 1
        """,
        (bike_id, user_id),
    )

    # 새 일시 잠금 row 추가 (transferable=0 → 내가 다시 탈 생각)
    db.execute(
        """
        INSERT INTO lock_status (bike_id, user_id, locked_at, lat, lng, transferable, is_active)
        VALUES (?, ?, datetime('now'), ?, ?, 0, 1)
        """,
        (bike_id, user_id, lat, lng),
    )

    # 자전거 상태: 잠김 + 다른 사람은 대여 불가
    db.execute(
        """
        UPDATE bike
        SET lock_state = 'locked',
            is_available = 0
        WHERE bike_id = ?
        """,
        (bike_id,),
    )

    db.commit()

    return jsonify({
        "bike_id": bike_id,
        "user_id": user_id,
        "status": "locked",
        "transferable": 0,
        "message": "자전거를 일시 잠금 상태로 전환했습니다."
    }), 200


@bp.route("/lock-transferable", methods=["POST"])
def lock_transferable():
    """
    대여가능(하이파이브) 상태:
    - 이미 일시잠금된 자전거(lock_status.is_active=1) 를 찾아 transferable=1 로 변경
    - bike.is_available=1 (다른 사용자에게 대여 가능)
    """
    payload = request.get_json(silent=True) or {}
    bike_id = payload.get("bike_id")
    user_id = payload.get("user_id")

    try:
        bike_id = _as_int(bike_id, "bike_id")
        user_id = _as_int(user_id, "user_id")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    db = get_db()

    # 활성 잠금 row 찾기 (내가 잠가둔 자전거인지 확인)
    active = db.execute(
        """
        SELECT lock_id
        FROM lock_status
        WHERE bike_id = ?
          AND user_id = ?
          AND is_active = 1
        ORDER BY locked_at DESC
        LIMIT 1
        """,
        (bike_id, user_id),
    ).fetchone()

    if not active:
        return jsonify({
            "error": "현재 이 사용자가 일시잠금한 자전거가 없습니다."
        }), 400

    # 이 잠금을 양도 가능 상태(transferable=1)로
    db.execute(
        "UPDATE lock_status SET transferable = 1 WHERE lock_id = ?",
        (active["lock_id"],),
    )

    # 자전거는 여전히 lock_state='locked' 이지만,
    # is_available=1 로 두어서 "하이파이브 후보"가 되게 함.
    db.execute(
        """
        UPDATE bike
        SET is_available = 1
        WHERE bike_id = ?
        """,
        (bike_id,),
    )

    db.commit()

    return jsonify({
        "bike_id": bike_id,
        "user_id": user_id,
        "status": "locked",
        "transferable": 1,
        "message": "자전거를 다른 사용자가 가져갈 수 있는 대여가능(하이파이브) 상태로 전환했습니다."
    }), 200
