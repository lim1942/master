# -*- coding: utf-8 -*-

from __future__ import absolute_import


import time
import json
import demjson
import random
from config import SECRET
from config import TASK_TODO
from config import TASK_FAIL
from config import SLAVE_URLS
from config import TASK_CHANNEL
from config import SLAVE_CHANNEL
from config import RESULT_CHANNEL
from config import CHANNELS_ALL
from config import TASK_MAX_SPAN
from config import TASK_MAX_RETRY
from config import QUEUE_MAX_JOBS
from config import TASK_TIMEOUT
from config import SENTINEL_RECONNECT_INTERVAL
from config import MAX_IPBL_WORKERS
from config import MAX_SLAVE_WORKERS

from utils import mark_start
from utils import get_druration
from utils import get_master
from utils import init_workers
from utils import update_workers
from utils import publish_message
from utils import get_idle_server
from utils import send_wx_msg


import requests
from multiprocessing.dummy import Pool
from multiprocessing.dummy import cpu_count


JOBS = []


def dispatch_task(task_id, url, headers):
    response = None
    try:
        retry = get_master().hset(task_id, 'counter', 0)
        get_master().hincrby(task_id, 'counter', 1)
        if retry >= TASK_MAX_RETRY:
            # print 'in exceeds retry'
            get_master().rpush(TASK_FAIL, task_id)
            if get_master().hget(task_id, 'status') in ['TODO', 'PENDING', 'ERROR']:
                get_master().hmset(task_id, {'status': 'ABORT', 'code': '90500', 'message': 'exceeds max retry'})
            return True
        # print 'before response'
        response = requests.get(url, headers=headers, timeout=TASK_TIMEOUT)
        # print 'after response'
        if response and response.status_code == 200 and response.content:
            result = json.loads(response.content)
            # print 'as result:', result
            if headers['rtype'] == 'common':
                result.update({'task_id': task_id, 'url': url})
                publish_message(result, channel=RESULT_CHANNEL)
            return True
        return False
    except Exception as e:
        print str(e)
        get_master().hmset(task_id, {'status': 'ERROR', 'code': '90500', 'message': 'error'})
        return dispatch_task(task_id, url, headers)


def dispatch(task_id):
    global JOBS
    # print 'in dispatch',
    """dispatch task from redis message queue to a slave"""
    # change task status to PENDING if current status is TODO
    status = get_master().hget(task_id, 'status')
    if status in ['TODO', 'PENDING']:
        get_master().hmset(task_id, {'status': 'PENDING','code': '90202', 'message': 'working'})
    # get priority and task (request args string) of task_id
    priority, interface, task, rtype = get_master().hmget(task_id, 'priority', 'interface', 'task', 'rtype')
    # generate initial headers
    headers = {
        'rtype': rtype,
        'secret': SECRET,
        'priority': priority,
        'task_id': task_id,
    }
    # depending which the service is
    url = None
    if 'getIpBlacklist' == interface:
        service = 'ipbl'
        server, ip, ipbl_workers = get_idle_server('ipbl')
        if server and ipbl_workers <= MAX_IPBL_WORKERS:
            url = '/'.join([server, task])
        else:
            print 'IPBL too busy, workers: {}'.format(ipbl_workers)
    else:
        service = 'slave'
        server, ip, slave_workers = get_idle_server('slave')
        if server and slave_workers <= MAX_SLAVE_WORKERS:
            url = '/'.join([server, task])
        else:
            print 'SLAVE too busy, workers: {}'.format(slave_workers)
    try:
        if url:
            _occupy_data = {
                'service': service,
                'ip': ip,
                'num': 1,
            }
            _release_data = {
                'service': service,
                'ip': ip,
                'num': -1,
            }

            # occupy the instance
            publish_message(msg=_occupy_data, channel=SLAVE_CHANNEL)
            if dispatch_task(task_id, url, headers=headers):
                if task_id in JOBS:
                    JOBS.remove(task_id)
            # release the instance
            publish_message(msg=_release_data, channel=SLAVE_CHANNEL)
        else:
            print '----------------workers too busy--------------------'
            if task_id not in JOBS:
                # JOBS.insert(0, task_id)
                get_master().lpush(TASK_TODO, task_id)
                time.sleep(0.1)
                print '-----------------task %s back to queue--------------' % task_id
    except Exception as e:
        send_wx_msg(desp=e)


def update_result(data):
    timestamp = data.pop('timestamp')
    task_id = data.pop('task_id')
    url = data.pop('url')
    result = data.pop('data')
    result = demjson.encode(result, encoding='utf8')
    if task_id:
        code = data.pop('code')
        msg = data.pop('msg')
        _data = {
            'status': 'SUCCESS',
            'code': code,
            'message': msg,
            'result': result,
            'timestamp': timestamp,
        }
        get_master().hmset(task_id, _data)


def update_slave(data):
    service = data.get('service')
    ip = data.get('ip')
    num = data.get('num', 0)
    update_workers(service, ip, num)


def execute_map_async(jobs):
    POOL = Pool(MAX_SLAVE_WORKERS)
    POOL.map_async(dispatch, jobs)
    POOL.close()
    # POOL.join()


def process_message(retry=3):
    global JOBS
    _threads = max(MAX_SLAVE_WORKERS, cpu_count() * 2 - 1)
    while retry > 0:
        try:
            sub = get_master().pubsub(ignore_subscribe_messages=True)
            sub.subscribe(*CHANNELS_ALL)
            mark_start()
            while True:
                if get_master().llen(TASK_TODO) > 0:
                    # if len(JOBS) < _threads:
                    if len(JOBS) < _threads:
                        JOBS.append(get_master().lpop(TASK_TODO))
                message = sub.get_message()
                if message is not None and message['type'] == 'message':
                    print 'current message:', message
                    channel = message['channel']
                    # if channel == TASK_CHANNEL:
                    #     task_id = message['data']
                        # JOBS.append(task_id)
                    if channel == RESULT_CHANNEL:
                        data = message['data']
                        update_result(json.loads(data))
                    elif channel == SLAVE_CHANNEL:
                        data = message['data']
                        update_slave(json.loads(data))
                if len(JOBS) > QUEUE_MAX_JOBS:
                    _JOBS, JOBS = JOBS[:MAX_SLAVE_WORKERS], JOBS[MAX_SLAVE_WORKERS:]
                    execute_map_async(_JOBS)
                elif get_druration() > TASK_MAX_SPAN:
                    _JOBS, JOBS = JOBS[:MAX_SLAVE_WORKERS], JOBS[MAX_SLAVE_WORKERS:]
                    execute_map_async(_JOBS)
                    mark_start()
                time.sleep(0.01)
        except Exception as e:
            print('in main exception')
            print(str(e))
            time.sleep(SENTINEL_RECONNECT_INTERVAL)
            retry -= 1
        else:
            retry = 3
    else:
        print('main try again')
        send_wx_msg(desp=e)
        time.sleep(5)
        process_message()


if __name__ == '__main__':
    init_workers()
    process_message()
