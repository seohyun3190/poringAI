from flask import request, jsonify
from ..db import get_db
from . import bp   # api/__init__.py 의 Blueprint("api", __name__) 재사용


def _is_hub_full_by_id(db, hub_id: int) -> bool:
    """
    hub_id 기준으로 허브가 꽉 찼는지 여부를 반환.
    schema.sql 의 hub(capacity, current_bikes)를 사용.
    """
    row = db.execute(
        "SELECT capacity, current_bikes FROM hub WHERE hub_id = ?",
        (hub_id,),
    ).fetchone()

    if row is None:
        # 허브를 못 찾으면 일단 False 처리 (Zone 반납 허용 안 함)
        return False

    return row["current_bikes"] >= row["capacity"]


@bp.route("/zone-return", methods=["POST"])
def zone_return():
    """
    Zone 반납 처리:
    - 허브가 꽉 찼을 때만 허용
    - ride(진행 중인 라이딩)를 종료
    - bike:
        current_hub_id = NULL (허브 밖, 존 위치)
        is_available   = 1   (다시 대여 가능)
        lock_state     = 'locked'
    - lock_status:
        is_active = 1 인 row 를 하나 남겨둔다
    """
    payload = request.get_json() or {}

    hub_id  = payload.get("hub_id")   # Zone 이 속한 허브 ID
    bike_id = payload.get("bike_id")
    user_id = payload.get("user_id")
    lat     = payload.get("lat")
    lng     = payload.get("lng")

    # 필수값 체크
    if not hub_id or not bike_id or not user_id:
        return jsonify({
            "ok": False,
            "reason": "missing_params",
            "message": "hub_id, bike_id, user_id 는 필수입니다."
        }), 400

    try:
        hub_id  = int(hub_id)
        bike_id = int(bike_id)
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "reason": "invalid_params",
            "message": "hub_id, bike_id, user_id 는 정수여야 합니다."
        }), 400

    db = get_db()

    # 1) 허브가 꽉 찼는지 확인
    if not _is_hub_full_by_id(db, hub_id):
        return jsonify({
            "ok": False,
            "reason": "hub_not_full",
            "message": "허브에 아직 빈 자리가 있어서 Zone 반납이 불가능합니다."
        }), 400

    # 2) 진행 중인 ride 찾기 (user_id + bike_id + end_at IS NULL)
    ride = db.execute(
        """
        SELECT ride_id, start_at
        FROM ride
        WHERE user_id = ?
          AND bike_id = ?
          AND end_at IS NULL
        ORDER BY start_at DESC
        LIMIT 1
        """,
        (user_id, bike_id),
    ).fetchone()

    if ride is None:
        return jsonify({
            "ok": False,
            "reason": "no_active_ride",
            "message": "현재 진행 중인 라이딩을 찾을 수 없습니다."
        }), 400

    ride_id = ride["ride_id"]

    # 3) ride 종료 (Zone 반납 → end_hub_id 는 NULL)
    db.execute(
        """
        UPDATE ride
        SET end_hub_id   = NULL,               -- 허브가 아닌 존에서 끝났다는 의미
            end_at       = datetime('now'),
            duration_min = CAST(
                (julianday(datetime('now')) - julianday(start_at)) * 24 * 60
                AS INTEGER
            )
        WHERE ride_id = ?
        """,
        (ride_id,),
    )

    # 4) 자전거 상태 업데이트
    #    - 허브 밖(존)에 있으므로 current_hub_id = NULL
    #    - is_available = 1 (누구나 새로 빌릴 수 있음)
    #    - lock_state   = 'locked' (물리적으로는 잠겨 있음)
    db.execute(
        """
        UPDATE bike
        SET current_hub_id = NULL,
            is_available   = 1,
            lock_state     = 'locked'
        WHERE bike_id = ?
        """,
        (bike_id,),
    )

    # 5) 이전에 활성화된 lock_status 가 있으면 정리(선택 사항)
    #    이미 잠금 로그가 있었다면 is_active=0 으로 꺼주고,
    #    이번 Zone 반납용으로 새 row 를 is_active=1 로 남겨둔다.
    db.execute(
        """
        UPDATE lock_status
        SET is_active = 0
        WHERE bike_id = ?
          AND user_id = ?
          AND is_active = 1
        """,
        (bike_id, user_id),
    )

    # 6) Zone 반납용 lock_status row 삽입
    #    - transferable 을 1로 두면 "누구나 가져가도 되는 상태"라는 의미.
    db.execute(
        """
        INSERT INTO lock_status (bike_id, user_id, locked_at, lat, lng, transferable, is_active)
        VALUES (?, ?, datetime('now'), ?, ?, 1, 1)
        """,
        (bike_id, user_id, lat, lng),
    )

    # 7) 위치 로그도 같이 남겨주기 (선택)
    if lat is not None and lng is not None:
        db.execute(
            """
            INSERT INTO bike_location_log (bike_id, lat, lng)
            VALUES (?, ?, ?)
            """,
            (bike_id, lat, lng),
        )

    db.commit()

    return jsonify({
        "ok": True,
        "zone_return": True,
        "ride_id": ride_id,
        "bike_id": bike_id,
        "user_id": user_id,
        "message": "허브가 꽉 차 있어 Zone 반납으로 라이딩을 종료했고, 자전거는 대여 가능 + 잠금 상태로 남겨두었습니다."
    }), 200
