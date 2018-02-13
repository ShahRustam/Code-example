# -*- coding: utf-8 -*-

from flask import render_template, request, jsonify, session
from flask.views import MethodView
from datetime import datetime
from flask import render_template

from ...utils import ErrorResponse, sendError, checkFields

from ...mongo import *

# class for login
class LoginEmployee(MethodView):
    def get(self):
        return render_template("login.html",title="Вход для сотрудников".decode("utf-8"), for_who="Для сотрудничества".decode("utf-8"))

    def post(self):
        errors = []
        try:
            email = request.form['email']
            password = request.form['password'].strip()
        except KeyError, error:
            errors.append(ErrorResponse.makeNeedDataError(error.args[0]))
            return sendError(errors)
        checkFields(errors, email=email, password=password)
        if errors:
            return sendError(errors)
        a = Employee()
        if a.loginuser(email, password):
            token = a.generate_auth_token(str(a.currentuser['_id']))
            session["token"] = token
            return jsonify({
                'status': 1,
                'name': a.currentuser["name"],
                'employeeId': str(a.currentuser['_id'])
            })
        errors.append(ErrorResponse.makeNotFoundError("email"))
        errors.append(ErrorResponse.makeNotFoundError("password"))
        return sendError(errors)

# class for add aplicant, login required, used decorator for check auth and write user entity to global "g" var
class AddApplicant(MethodView):
    @loginRequired
    def get(self):
        employee = g.employee
        institution = institutions.find_one({"_id": employee.get("instId")}, {"_id": 0})
        return render_template('employee/addApplicant.html', title="Добавить абитуриента".decode('utf-8'),
                               pageName="addApplicant", employee=employee, institution=institution)


# class for auth
class Employee():

    def gethash(self, passw):
        hashed = hashlib.sha256(salt + passw).hexdigest()
        return hashed

    def loginuser(self, email, passw):
        employee = employees.find_one({"status": 1, "email": email})
        if employee and (employee['password'] == self.gethash(passw)):
            self.currentuser = employee
            return True
        return False

    def generate_auth_token(self, id, expiration=3600):
        s = Serializer(secret_key, expires_in=expiration)
        token = s.dumps({'id': id, "timestamp": time() * 1000})
        log = {'userid': id, 'token': token, 'pth': request.path}
        actionlog.insert(log)
        return token

    @staticmethod
    def verify_auth_token(token, pth, errors):
        s = Serializer(secret_key)
        try:
            data = s.loads(token)
            actionlog.insert({'userid': str(data.get('id')), 'token': token, 'pth': pth})
            logsCount = actionlog.find({'token': token}).count()
            if logsCount == 2:
                employee = employees.find_one({"status": 1, "_id": ObjectId(str(data.get('id')))})
                if employee:
                    return True, employee
        except SignatureExpired:
            errors.append(ErrorResponse.makeTokenExpiredError())  # valid token, but expired
            return False, None
        except BadSignature:
            errors.append(ErrorResponse.makeTokenError())  # invalid token
            return False, None
        else:
            errors.append(ErrorResponse.makeTokenError())
            return False, None

# decorator
def loginRequired(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        errors = []
        token = session.get("token", "")
        status, employee = Employee.verify_auth_token(token, request.path, errors)
        if status == False:
            if request.method=="GET":
                return redirect("/employee/login")
            else:
                return sendError(errors)
        g.employee = employee
        a = Employee()
        token = a.generate_auth_token(str(employee["_id"]))
        session["token"] = token
        return f(*args, **kwargs)
    return wrap
