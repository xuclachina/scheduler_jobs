#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   app_jobs.py
@Time    :   2020/03/23 17:34:36
@Author  :   xuchenliang 
@Desc    :   None
'''
import uvicorn
from pytz import utc
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from fastapi import FastAPI, HTTPException, status

from ansible_utils import AnsibleHost, AnsibleTask


jobstores = {
    'default': SQLAlchemyJobStore(url='mysql://xucl:xuclxucl123@127.0.0.1/jobs')
}

executors = {
    'default': ThreadPoolExecutor(20),
    'processpool': ProcessPoolExecutor(5)
}

job_defaults = {
    'coalesce': False,
    'max_instances': 3,
    'misfire_grace_time': 60
}


def cronjob():
    hosts = [['ip', port, 'ssh', 'root', 'password'], ]
    hosts_arry = []
    for i in hosts:
        hosts_arry.append(AnsibleHost(i[0], i[1], i[2], i[3], i[4]))
    task = AnsibleTask(hosts_arry, {"demaxiya": "a"})
    result = task.exec_playbook(['test.yml'])
    if result['ok']:
        print("play success")

def task1():
    print(1)

def task2():
    print(2)

scheduler = BackgroundScheduler(jobstores=jobstores, executors=executors,
                                    job_defaults=job_defaults, timezone=utc)


app = FastAPI()


@app.get("/jobs/")
async def get_jobs():
    jobs = scheduler.get_jobs()
    job_list = list()
    for job in jobs:
        job_dict = dict()
        job_dict['id'] = job.id
        job_dict['name'] = job.name
        job_list.append(job_dict)
    return {"jobs": job_list}


@app.post("/jobs/add/")
async def add_job(funcname: str, id: str):
    func = globals().get(funcname)
    print(func)
    if not func:
        HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="fun not exists")
    try:
        scheduler.add_job(func, 'interval', seconds=10, id=id)
    except:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="add job faild")
    return {"msg": "add job success"}


@app.post("/jobs/remove/")
async def remove_job(id: str):
    job_list = [job.id for job in scheduler.get_jobs()]
    if id not in job_list:
        return {"msg": "job not exists"}
    scheduler.remove_job(id)
    return {"msg": "remove job success"}


@app.post("/jobs/pause/")
async def pause_job(id: str):
    job_list = [job.id for job in scheduler.get_jobs()]
    if id not in job_list:
        return {"msg": "job not exists"}
    scheduler.pause_job(id)
    return {"msg": "pause job success"}


@app.post("/jobs/resume/")
async def resume_job(id: str):
    job_list = [job.id for job in scheduler.get_jobs()]
    if id not in job_list:
        return {"msg": "job not exists"}
    scheduler.resume_job(id)
    return {"msg": "resume job success"}


@app.on_event("startup")
@app.post("/scheduler/start/")
async def start_scheduler():
    scheduler.start()


@app.post("/scheduler/stop/")
async def stop_scheduler():
    scheduler.shutdown()

if __name__ == "__main__":
    uvicorn.run(app='main:app', host="0.0.0.0", port=9123)
