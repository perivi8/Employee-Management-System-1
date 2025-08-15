from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from datetime import datetime
from models.task import Task
from utils.email_utils import send_email
from utils.db import db

task_bp = Blueprint('task', __name__)

def send_assignment_notification(emails, title, deadline, body_extra=''):
    for email in emails:
        send_email(
            subject="New Task Assigned",
            recipient=email,
            body=f"You have been assigned a new task: {title}\nDeadline: {deadline}\n{body_extra}",
            meta={"status": "Assigned", "title": title}
        )

@task_bp.route('/create', methods=['POST', 'OPTIONS'])
@jwt_required()
def create_task():
    if request.method == "OPTIONS":
        return '', 200
    user_id = get_jwt_identity()
    current_user = db.users.find_one({"_id": ObjectId(user_id)})
    if not current_user or current_user.get("role") not in ["Admin", "Manager"]:
        return jsonify({"msg": "You do not have permission to create tasks."}), 403

    data = request.get_json(force=True)
    assigned_to = data.get('assigned_to', [])
    deadline = data.get('deadline')
    tasks_created = []

    if data.get('assign_to_all'):
        employees_cursor = db.users.find({"role": "Employee"})
        assigned_to = [emp['employee_id'] for emp in employees_cursor]

    employees = list(db.users.find({"employee_id": {"$in": assigned_to}, "role": "Employee"}))
    if not employees:
        return jsonify({"msg": "Assigned user(s) must be valid employees."}), 400

    for emp in employees:
        task = Task(
            data['title'], data['description'], emp['employee_id'],
            data['priority'], data['status'], deadline
        )
        t_id = db.tasks.insert_one({
            **task.__dict__,
            "created_by": current_user['username'],
            "created_at": datetime.utcnow().isoformat()
        }).inserted_id
        tasks_created.append(str(t_id))

    send_assignment_notification(
        [emp['email'] for emp in employees],
        data['title'], deadline
    )
    return jsonify({"msg": "Tasks created for assigned employees.", "task_ids": tasks_created}), 201

@task_bp.route('/update/<task_id>', methods=['PUT', 'OPTIONS'])
@jwt_required()
def update_task(task_id):
    if request.method == "OPTIONS":
        return '', 200
    user_id = get_jwt_identity()
    current_user = db.users.find_one({"_id": ObjectId(user_id)})
    data = request.get_json(force=True)

    try:
        task = db.tasks.find_one({'_id': ObjectId(task_id)})
    except Exception:
        return jsonify({"msg": "Task not found"}), 404
    if not task:
        return jsonify({"msg": "Task not found"}), 404

    if task.get('status') == 'Overdue' and current_user.get('role') == 'Employee':
        return jsonify({"msg": "Task is overdue and cannot be updated by employee."}), 403

    if current_user.get('role') == 'Employee':
        if task['assigned_to'] != current_user.get('employee_id'):
            return jsonify({"msg": "Can only update your own tasks."}), 403
        new_status = data.get('status')
        if not new_status:
            return jsonify({"msg": "Nothing to update"}), 400
        db.tasks.update_one({'_id': ObjectId(task_id)}, {'$set': {'status': new_status}})
        if new_status in ['In Progress', 'Done']:
            managers = db.users.find({"role": {"$in": ["Manager", "Admin"]}})
            meta = {
                "status": new_status,
                "task_id": str(task['_id']),
                "title": task.get('title'),
                "employee_id": current_user.get('employee_id'),
                "username": current_user.get('username')
            }
            subject = f"Task {new_status} Notification"
            notify_body = (
                f"Employee ID: {current_user.get('employee_id')}\n"
                f"Name: {current_user.get('username')}\n"
                f"Task: {task.get('title')}\n"
                f"Status: {new_status}"
            )
            for mgr in managers:
                send_email(subject=subject, recipient=mgr['email'], body=notify_body, meta=meta)
        return jsonify({"msg": "Task status updated"}), 200
    else:
        db.tasks.update_one({'_id': ObjectId(task_id)}, {'$set': data})
        return jsonify({"msg": "Task updated"}), 200

@task_bp.route('/complete/<task_id>', methods=['POST', 'OPTIONS'])
@jwt_required()
def complete_task(task_id):
    if request.method == "OPTIONS":
        return '', 200
    user_id = get_jwt_identity()
    current_user = db.users.find_one({"_id": ObjectId(user_id)})
    if current_user.get('role') != 'Employee':
        return jsonify({"msg": "Only assigned employees may complete tasks."}), 403

    task = db.tasks.find_one({'_id': ObjectId(task_id)})
    if not task or task['assigned_to'] != current_user.get('employee_id'):
        return jsonify({"msg": "Not authorized for this task."}), 403

    db.tasks.update_one({'_id': ObjectId(task_id)}, {'$set': {'status': 'Done'}})

    managers = db.users.find({"role": {"$in": ["Manager", "Admin"]}})
    meta = {
        "status": "Done",
        "task_id": str(task['_id']),
        "title": task.get('title'),
        "employee_id": current_user.get('employee_id'),
        "username": current_user.get('username')
    }
    notify_body = (
        f"Employee ID: {current_user.get('employee_id')}\n"
        f"Name: {current_user.get('username')}\n"
        f"Task '{task['title']}' has been submitted (Done)."
    )
    for mgr in managers:
        send_email(subject="Task Submitted (Done)", recipient=mgr['email'], body=notify_body, meta=meta)
    send_email(subject="Task Completed", recipient=current_user.get('email'), body=f"You have completed: {task['title']}!", meta=meta)

    return jsonify({"msg": "Task completed notification sent!"}), 200

@task_bp.route('/delete/<task_id>', methods=['DELETE', 'OPTIONS'])
@jwt_required()
def delete_task(task_id):
    if request.method == "OPTIONS":
        return '', 200
    user_id = get_jwt_identity()
    current_user = db.users.find_one({"_id": ObjectId(user_id)})
    if current_user.get("role") not in ["Admin", "Manager"]:
        return jsonify({"msg": "Only admins and managers can delete tasks."}), 403
    db.tasks.delete_one({'_id': ObjectId(task_id)})
    return jsonify({"msg": "Task deleted successfully."}), 200

@task_bp.route('/', methods=['GET', 'OPTIONS'])
@jwt_required()
def get_tasks():
    if request.method == "OPTIONS":
        return '', 200
    user_id = get_jwt_identity()
    current_user = db.users.find_one({"_id": ObjectId(user_id)})

    if current_user.get('role') == 'Employee':
        tasks = list(db.tasks.find({"assigned_to": current_user.get('employee_id')}))
    else:
        tasks = list(db.tasks.find())
    for t in tasks:
        t["_id"] = str(t["_id"])
    return jsonify(tasks), 200

@task_bp.route('/<task_id>', methods=['GET', 'OPTIONS'])
@jwt_required()
def get_task(task_id):
    if request.method == "OPTIONS":
        return '', 200
    user_id = get_jwt_identity()
    current_user = db.users.find_one({"_id": ObjectId(user_id)})
    task = db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task:
        return jsonify({"msg": "Task not found"}), 404
    if current_user.get('role') == 'Employee' and task['assigned_to'] != current_user.get('employee_id'):
        return jsonify({"msg": "Not authorized"}), 403
    task["_id"] = str(task["_id"])
    return jsonify(task), 200

@task_bp.route('/mark-overdue/<task_id>', methods=['POST', 'OPTIONS'])
@jwt_required()
def mark_overdue(task_id):
    if request.method == "OPTIONS":
        return '', 200
    user_id = get_jwt_identity()
    current_user = db.users.find_one({"_id": ObjectId(user_id)})
    task = db.tasks.find_one({'_id': ObjectId(task_id)})
    if not task:
        return jsonify({"msg": "Task not found"}), 404
    if task.get('status') == 'Done':
        return jsonify({"msg": "Task already completed"}), 200

    already_overdue = (task.get('status') == 'Overdue')
    db.tasks.update_one({'_id': ObjectId(task_id)}, {'$set': {'status': 'Overdue'}})

    if not already_overdue:
        managers = db.users.find({"role": {"$in": ["Manager", "Admin"]}})
        meta = {
            "status": "Overdue",
            "task_id": str(task['_id']),
            "title": task.get('title'),
            "employee_id": task['assigned_to']
        }
        notify_body = (
            f"Task '{task.get('title')}' assigned to Employee ID: {task['assigned_to']} was not completed before the deadline."
        )
        for mgr in managers:
            send_email(subject="Task Overdue Alert", recipient=mgr['email'], body=notify_body, meta=meta)

    return jsonify({"msg": "Overdue processed"}), 200
