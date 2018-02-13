# -*- coding: utf-8 -*-


from flask import render_template, request, jsonify
from flask.views import MethodView
from datetime import datetime
from hashlib import sha256
from validate_email import validate_email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import render_template
import smtplib
from kombu import Queue, Exchange
from email.utils import formataddr
from email.header import Header
from ..utils import ErrorResponse, sendError, checkFields
from ..mongo import *


class RegisterInstitution(MethodView):
    def get(self):
        return render_template("ed_register.html",title="Регистрация учебного заведения".decode("utf-8"))

    def post(self):
        errors = []
        try:
            name = request.form['name'].strip()
            position = request.form['position'].strip()
            email = request.form['email'].strip()
            phone = request.form["phone"].strip()
            password = request.form["password"].strip()
            password2 = request.form["password2"].strip()
            instName = request.form["instName"].strip()
        except KeyError, error:
            errors.append(ErrorResponse.makeNeedDataError(error.args[0]))
            return sendError(errors)
        checkFields(errors, name=name, email=email, phone=phone, position=position, instName=instName,
                    password=password, password2=password2)
        if errors:
            return sendError(errors)
        if institutions.find_one({"name": instName}):
            errors.append(ErrorResponse.makeAlreadyExist("instName"))
        if employees.find_one({"phone": phone}):
            errors.append(ErrorResponse.makeAlreadyExist("phone"))
        if employees.find_one({"email": email}):
            errors.append(ErrorResponse.makeAlreadyExist("email"))
        if errors:
            return sendError(errors)
        hash = sha256(salt + password).hexdigest()
        instId = institutions.insert_one({"name": instName, "status": 0}).inserted_id
        employees.insert(
            {"instId": instId, "status": 0, "name": name, "position": position, "email": email, "phone": phone,
             "password": hash})
        html = render_template("email/newInst.html", sender=email, position=position, instName=instName, name=name,
                               phone=phone)
        self.sendEmail("Register", "rustam@shakh.co", html)
        return jsonify({"status": 1, "data": {}})

    def sendEmail(self, subject, to_who, html, ):
        login = ""
        pas = ""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = formataddr((str(Header('ESAE', 'utf-8')), login))
        msg['To'] = to_who
        part = MIMEText(html.encode('utf-8'), 'html', 'utf-8')
        msg.attach(part)
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.ehlo()
        server.login(login, pas)
        server.sendmail(login, to_who, msg.as_string())
        server.quit()
