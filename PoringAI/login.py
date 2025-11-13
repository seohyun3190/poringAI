# login.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from .db import get_db

bp = Blueprint('login', __name__, url_prefix='/login')

@bp.route('/', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()

        if not user_id:
            flash("user_id를 입력해주세요.")
        else:
            db = get_db()

            # users_id인지 user_id인지 확인해서 맞춰줘
            row = db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()

            if row is None:
                flash("존재하지 않는 user_id입니다.")
            else:
                session.clear()
                session["user_id"] = row["user_id"]
                return redirect(url_for("index"))

    return render_template("login/login.html")

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))
