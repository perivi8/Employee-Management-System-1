import random
import string
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from bson import ObjectId
import smtplib
from email.mime.text import MIMEText
import os

from models.user import User
from utils.db import db
from config import Config

user_bp = Blueprint('user', __name__)

def send_verification_email(email, code):
    try:
        msg = MIMEText(f"Your verification code is: {code}")
        msg['Subject'] = "Email Verification"
        msg['From'] = Config.SMTP_USER
        msg['To'] = email
        with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
            server.send_message(msg)
    except Exception:
        # do not fail registration if email sending fails
        pass

@user_bp.route('/', methods=['GET', 'OPTIONS'])
@jwt_required(optional=True)
def get_users():
    if request.method == "OPTIONS":
        return '', 200
    users = list(db.users.find({}, {"password_hash": 0}))
    for user in users:
        user["_id"] = str(user["_id"])
    return jsonify(users), 200

@user_bp.route('/<user_id>', methods=['GET', 'PUT', 'DELETE', 'OPTIONS'])
@jwt_required(optional=True)
def user_detail(user_id):
    if request.method == "OPTIONS":
        return '', 200
    try:
        user = db.users.find_one({"_id": ObjectId(user_id)}, {"password_hash": 0})
    except Exception:
        return jsonify({"msg": "User not found"}), 404
    if not user:
        return jsonify({"msg": "User not found"}), 404

    if request.method == "GET":
        user["_id"] = str(user["_id"])
        return jsonify(user), 200
    if request.method == "PUT":
        data = request.get_json(force=True)
        db.users.update_one({"_id": ObjectId(user_id)}, {"$set": data})
        return jsonify({"msg": "User updated"}), 200
    if request.method == "DELETE":
        db.users.delete_one({"_id": ObjectId(user_id)})
        return jsonify({"msg": "User deleted"}), 200

@user_bp.route('/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == "OPTIONS":
        return '', 200
    data = request.get_json(force=True)
    if db.users.find_one({"email": data['email']}):
        return jsonify({"msg": "User already exists!"}), 400

    role = 'Employee'
    if data['password'].startswith('Manager123'):
        role = 'Manager'
    elif data['password'].startswith('Admin123'):
        role = 'Admin'

    employee_id = None
    if role == 'Employee':
        num_employees = db.users.count_documents({"role": "Employee"})
        employee_id = f"EMP{num_employees + 1:03d}"

    user = User(data['username'], data['email'], data['password'], role)
    verification_code = ''.join(random.choices(string.digits, k=6))
    verification_expiry = datetime.utcnow() + timedelta(minutes=10)

    db.users.insert_one({
        "username": user.username,
        "email": user.email,
        "password_hash": user.password_hash,
        "role": role,
        "employee_id": employee_id,
        "is_verified": False,
        "verification_code": verification_code,
        "verification_expiry": verification_expiry
    })

    send_verification_email(user.email, verification_code)
    return jsonify({"msg": "Verification code sent to email"}), 201

@user_bp.route('/verify-email', methods=['POST', 'OPTIONS'])
def verify_email():
    if request.method == "OPTIONS":
        return '', 200
    data = request.get_json(force=True)
    user = db.users.find_one({"email": data['email']})
    if not user:
        return jsonify({"msg": "User not found"}), 404
    if user.get("verification_code") != data['code']:
        return jsonify({"msg": "Invalid code"}), 400
    if datetime.utcnow() > user.get("verification_expiry"):
        return jsonify({"msg": "Code expired"}), 400

    db.users.update_one(
        {"email": data['email']},
        {"$set": {"is_verified": True}, "$unset": {"verification_code": "", "verification_expiry": ""}}
    )
    return jsonify({"msg": "Email verified successfully"}), 200

@user_bp.route('/resend-code', methods=['POST', 'OPTIONS'])
def resend_code():
    if request.method == "OPTIONS":
        return '', 200
    data = request.get_json(force=True)
    user = db.users.find_one({"email": data['email']})
    if not user:
        return jsonify({"msg": "User not found"}), 404
    if user.get("is_verified"):
        return jsonify({"msg": "Email already verified"}), 400

    verification_code = ''.join(random.choices(string.digits, k=6))
    verification_expiry = datetime.utcnow() + timedelta(minutes=10)
    db.users.update_one(
        {"email": data['email']},
        {"$set": {"verification_code": verification_code, "verification_expiry": verification_expiry}}
    )
    send_verification_email(user['email'], verification_code)
    return jsonify({"msg": "New verification code sent"}), 200

@user_bp.route('/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == "OPTIONS":
        return '', 200
    data = request.get_json(force=True)
    user = db.users.find_one({"email": data['email']})
    if not user:
        return jsonify({"msg": "Invalid credentials"}), 401
    if not user.get("is_verified"):
        return jsonify({"msg": "Please verify your email before logging in"}), 403

    temp_user = User(user['username'], user['email'], "", user['role'])
    temp_user.password_hash = user['password_hash']
    if temp_user.verify_password(data['password']):
        access = create_access_token(identity=str(user['_id']))
        refresh = create_refresh_token(identity=str(user['_id']))
        return jsonify({
            "token": access,
            "refresh_token": refresh,
            "role": user['role'],
            "username": user['username'],
            "employee_id": user.get('employee_id', None)
        }), 200
    return jsonify({"msg": "Invalid credentials"}), 401

@user_bp.route('/refresh', methods=['POST', 'OPTIONS'])
@jwt_required(refresh=True)
def refresh():
    if request.method == "OPTIONS":
        return '', 200
    user_id = get_jwt_identity()
    new_access = create_access_token(identity=user_id)
    return jsonify({"token": new_access}), 200
