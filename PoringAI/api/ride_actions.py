import sqlite3
from flask import request, jsonify, g
from ..db import get_db
from . import bp
from datetime import datetime

@bp.route('/rent', methods=['POST'])
def rent_bike():
    """
    자전거 대여를 처리하는 API 엔드포인트. (ERD v_image_fbd067 기준)
    Request Body (JSON): { "bike_id": 123, "user_id": 1 }
    """
    
    # 1. 요청 본문(JSON)에서 user_id와 bike_id를 받습니다.
    # (ERD에서 bikes.bikes_id, users.user_id, rentals.bike_id, rentals.user_id가 혼용되나,
    #  요청의 편의를 위해 bike_id, user_id로 통일합니다.)
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "JSON 요청이 필요합니다."}), 400

    user_id = data.get('user_id')
    bike_id = data.get('bike_id') # 이 ID가 ERD의 bikes.bikes_id 라고 가정

    if not user_id:
        return jsonify({"success": False, "error": "user_id가 필요합니다."}), 400
    if not bike_id:
        return jsonify({"success": False, "error": "bike_id가 필요합니다."}), 400

    db = get_db()
    
    try:
        # 2. user_id가 DB(users 테이블)에 실재하는지 확인
        user = db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not user:
            return jsonify({"success": False, "error": "존재하지 않는 사용자입니다."}), 404

        # 3. 자전거의 현재 상태, 주차 위치, 할당 ID 확인 (bikes 테이블)
        bike = db.execute(
            """
            SELECT assigned_hub_id, where_parked, status 
            FROM bikes 
            WHERE bikes_id = ?
            """,
            (bike_id,)
        ).fetchone()

        if not bike:
            return jsonify({"success": False, "error": "존재하지 않는 자전거입니다."}), 404

        # ERD의 status ('Using', 'Returned', 'Returning') 기준
        if bike['status'] != 'Returned':
            return jsonify({"success": False, "error": "이미 대여 중이거나 이용 불가능한 자전거입니다."}), 409

        # 4. 대여 기록(rentals)에 사용할 변수 준비
        where_parked = bike['where_parked'] # 'Station' 또는 'Zone'
        parked_location_id = bike['assigned_hub_id'] # station_id 또는 zone_id로 간주
        start_at_iso = datetime.now().isoformat()
        start_hub_id = None # rentals에 기록할 실제 hub_id (stations/zones에서 조회)

        # 5. [핵심 로직] 주차된 위치(Station/Zone)의 parked_slots를 1 감소
        if where_parked == 'Station':
            if not parked_location_id:
                raise Exception("Station에서 대여하지만 assigned_hub_id(station_id)가 없습니다.")
            
            # 5-1. stations 테이블의 parked_slots 1 감소
            db.execute(
                "UPDATE stations SET parked_slots = parked_slots - 1 WHERE station_id = ? AND parked_slots > 0",
                (parked_location_id,)
            )
            # 5-2. rentals에 기록할 hub_id 조회
            hub_row = db.execute("SELECT hub_id FROM stations WHERE station_id = ?", (parked_location_id,)).fetchone()
            if hub_row:
                start_hub_id = hub_row['hub_id']

        elif where_parked == 'Zone':
            if not parked_location_id:
                raise Exception("Zone에서 대여하지만 assigned_hub_id(zone_id)가 없습니다.")
                
            # 5-1. zones 테이블의 parked_slots 1 감소
            db.execute(
                "UPDATE zones SET parked_slots = parked_slots - 1 WHERE zone_id = ? AND parked_slots > 0",
                (parked_location_id,)
            )
            # 5-2. rentals에 기록할 hub_id 조회
            hub_row = db.execute("SELECT hub_id FROM zones WHERE zone_id = ?", (parked_location_id,)).fetchone()
            if hub_row:
                start_hub_id = hub_row['hub_id']
                
        else:
            # 주차된 상태가 아니거나(예: 'Returning' 상태로 길에 있음) 알 수 없는 값
            return jsonify({"success": False, "error": "자전거가 허브나 존에 주차된 상태가 아닙니다."}), 409
        
        if start_hub_id is None:
            raise Exception(f"{where_parked} (ID: {parked_location_id})에 해당하는 hub_id를 찾을 수 없습니다.")

        # 6. bikes 테이블 상태 업데이트 (대여 중)
        # (status='Using', assigned_hub_id=NULL, where_parked=NULL로 변경)
        db.execute(
            """
            UPDATE bikes 
            SET status = 'Using', assigned_hub_id = NULL, where_parked = NULL, last_rental_datetime = ?
            WHERE bikes_id = ?
            """,
            (start_at_iso, bike_id)
        )

        # 7. rentals 테이블에 새 대여 기록 추가
        cursor = db.execute(
            """
            INSERT INTO rentals (bike_id, user_id, start_hub_id, rental_start_datetime, status) 
            VALUES (?, ?, ?, ?, ?)
            """,
            (bike_id, user_id, start_hub_id, start_at_iso, 'Using') # ERD의 rentals.status는 'Using', 'Paid' 등일 수 있음
        )
        
        new_rental_id = cursor.lastrowid

        # 8. DB에 모든 변경사항 확정 (Commit)
        db.commit()

        # 성공 응답
        return jsonify({
            "success": True, 
            "message": "대여가 시작되었습니다.",
            "rental_id": new_rental_id,
            "start_at": start_at_iso,
            "user_id": user_id 
        }), 201

    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"success": False, "error": f"데이터베이스 오류: {e}"}), 500
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "error": f"작업 중 오류 발생: {e}"}), 500