# -*- coding: utf-8 -*-
# Copyright ©2016 SoftInTouch.

from flask.views import MethodView
from flask.ext.babel import gettext
from flask import request, jsonify, flash, redirect, make_response, render_template
import re
import collections
from functools import wraps
import app
from app.utils.error import *
from app.model import *
from datetime import datetime
import dateutil.relativedelta
from time import time
from operator import attrgetter
from app.controller.login import loginRequired
from app.controller.restorePassword import genCode
from google.appengine.api.mail import EmailMessage
import csv
from google.appengine.ext import ndb
from math import *
from app.utils.utils import *


class AdminMtReport(MethodView):
    @loginRequired
    def post(self, domenAlias):
        response = getUserDomenMember(domenAlias)
        if type(response) != type(tuple()):
            return response
        elif response.__len__() == 4:
            user, domen, member, notification = response
        else:
            return response
        response = checkForBanned(user, member, domen)
        if response: return response
        admin = False
        if member.admin == 1 or domen.ownerId == user.key.id():
            admin = True
            form = dict(request.form)
            date = form.get('date')[0].strip()
            if len(date) != 25:
                return ErrorResponse.makeInvalidDateFormat()
            splitDate = re.split(r'-', date)
            fromDate = datetime.strptime(splitDate[0].strip(), "%d %b %Y")
            toDate = datetime.strptime(splitDate[1].strip(), "%d %b %Y")
            files = dict(request.files)
            response = self.checkEmpty(form, files)
            if response: return response
            count, error = self.checkFileForTimeTracking(files, form)
            if error: return error
            setMember = request.form['member']
            cache, error = self.createCache(files, form, fromDate, toDate, count)
            if error: return error
            report = self.createReport(domen, fromDate, toDate, setMember, cache)
            return jsonify({'status': 1, 'data': {'reportId': str(report.key.id())}}), 200
        else:
            return ErrorResponse.makeNotAdmin()

    def checkEmpty(self, form, files):
        checkForm = form
        checkForm.pop('date')
        checkForm.pop('member')
        if checkForm == {}:
            return ErrorResponse.makeSelectReportProject()
        for key in files.keys():
            if files[key][0].filename == "":
                return ErrorResponse.makeEmptyFile(files[key][0].filename)
        pass

    def checkFileForTimeTracking(self, files, form):
        count = {}
        error = {}
        for key in files.keys():
            project = Project.get_by_id(int(key))
            if project.active == 1:
                if form.get(str(project.key.id())):
                    if form.get(str(project.key.id()))[0] == "on":
                        file = files.get(str(project.key.id()))[0]
                        if file:
                            if file.filename[-4:] != ".csv":
                                error = ErrorResponse.makeInvalidFileFormat(file.filename)
                            elif count.get(str(project.key.id())) == None:
                                csvOpen = csv.reader(file)
                                array = [row for row in csvOpen]
                                array[0][0]=array[0][0].decode("utf-8-sig").encode("utf-8")
                                if array != []:
                                    if array[0][0] == "Date" and array[0][1] == "Client" and array[0][
                                        2] == "Project" and \
                                                    array[0][3] == "Notes" and array[0][4] == "Hours" and array[0][
                                        5] == "First name" and array[0][6] == "Last name":
                                        count[str(project.key.id())] = array
                                    else:
                                        error = ErrorResponse.makeInvalidFile(file.filename)
                                else:
                                    error = ErrorResponse.makeFileIsEmpty(files[key][0].filename)
        return count, error

    def createCache(self, files, form, fromDate, toDate, count):
        cache = {}
        error = None
        for key in count.keys():
            project = Project.get_by_id(int(key))
            try:
                if count[str(project.key.id())][1][2] != project.mtName:
                    flash(
                        gettext("WARNING!!! You have downloaded the") + " %s " %
                        count[str(project.key.id())][1][2] + gettext(
                            "CSV report for the project") + " %s" % project.mtName
                    )
            except:
                error = ErrorResponse.makeInvalidFile(files.get(str(project.key.id()))[0].filename)
            for member in project.member:
                if member.active == 1:
                    domenMember = DomenMember.get_by_id(int(member.memberId))
                    for row in count[str(project.key.id())]:
                        if row[0] != 'Date':
                            if datetime.strptime(row[0],
                                                 "%m/%d/%Y") >= fromDate and datetime.strptime(
                                row[0], "%m/%d/%Y") <= toDate:
                                if domenMember.mtFirstName == row[5].decode(
                                        'utf8') and domenMember.mtLastName == \
                                        row[6].decode('utf8'):
                                    if cache.get(str(domenMember.key.id())) == None:
                                        cache[str(domenMember.key.id())] = {}
                                    if cache.get(str(domenMember.key.id())).get(key) == None:
                                        cache[str(domenMember.key.id())].update({key: []})
                                    cache.get(str(domenMember.key.id())).get(key).append(row)
        return cache, error

    def createReport(self, domen, fromDate, toDate, setMember, cache):
        report = Report(domenId=domen.key.id(), fromDate=fromDate, toDate=toDate,
                        reportExpired=int(time() + 172800), forUser=setMember)
        report.put()
        for key in cache.keys():
            domenMember = DomenMember.get_by_id(int(key))
            if setMember == "All" or setMember == domenMember.nickname:
                reportUser = ReportUser(userId=domenMember.key.id(), reportId=report.key.id())
                reportUser.put()
                for projectId in cache.get(key).keys():
                    project = Project.get_by_id(int(projectId))
                    reportProject = ReportProject(projectId=project.key.id(),
                                                  userReportId=reportUser.key.id())
                    rate = self.getRate(domenMember.key.id(), project)
                    hours = 0.0
                    for task in cache.get(key).get(projectId):
                        hoursTask = float(task[4])
                        reportTask = ReportTask(task=task[3],
                                                hours=round(hoursTask, 1),
                                                score=rate * round(
                                                    hoursTask, 1),
                                                date=datetime.strptime(
                                                    task[0],
                                                    "%m/%d/%Y"))
                        hours += hoursTask
                        reportProject.task.append(reportTask)
                    reportProject.hours = int(ceil(hours))
                    reportProject.score = int(ceil(hours) * rate)
                    reportProject.put()
                    reportUser.hours += int(reportProject.hours)
                    reportUser.score += int(reportProject.score)
                reportUser.put()
        return report

    def getRate(self, memberId, project):
        for member in project.member:
            if member.memberId == memberId:
                return member.rate
        return 0
