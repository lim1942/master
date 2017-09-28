# -*- coding: utf-8 -*-

from __future__ import absolute_import
import json
import time
import random
import requests
from config import SECRET
from config import PROJECT
from config import _ENVIRONMENT
from config import TASK_TODO
from config import SLAVE_IPS
from config import SLAVE_URLS
from config import IPBL_URLS
from config import REDIS_DB
from config import REDIS_AUTH
from config import WX_MSG_KEY
from config import WX_MSG_URL
from config import TASK_CHANNEL
from config import PROJECT_SERVICES
from config import REDIS_RESULT_EXPIRE
from config import REDIS_SENTINEL_NAME
from config import REDIS_SENTINEL_CONFIG
from config import WORKERS_KEY_PREFIX
from config import UPDATE_MODE_ALL
from config import UPDATE_MODE_REPLACE
from config import UPDATE_MODE_UPDATE
from config import UPDATE_MODE_DELETE
from redis.sentinel import Sentinel


MASTER = None
SLAVE = None
SENTINEL = None
_DEFAULT_TEXT = ':'.join([_ENVIRONMENT, PROJECT])


_START, _END, _DRURATION = 0, 0, 0


def validate_task_id(task_id):
    if len(task_id) != 36:
        return False
    _parts = task_id.split('-')
    if len(_parts) != 5:
        return False
    if '|'.join(map(lambda x: str(len(x)), _parts)) != '8|4|4|4|12':
        return False
    return True



def get_current_timestamp():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))


def mark_start():
    global _START
    _START = time.time()


def mark_end():
    global _END
    _END = time.time()


def get_druration():
    global _START, _END, _DRURATION
    mark_end()
    _DRURATION = _END - _START
    return _DRURATION


def send_wx_msg(text=_DEFAULT_TEXT, desp='', retry=10):
    """publish a send wx message to redis"""
    desp = str(desp)
    # print desp
    if retry > len(SLAVE_URLS):
        retry = len(SLAVE_URLS)
    for url in SLAVE_URLS:
        data = {
            'url': WX_MSG_URL.format(key=WX_MSG_KEY, title=text, body=desp)
        }
        try:
            html = requests.post(url, data=data).content
            jdata = json.loads(html)
            return True, jdata
        except Exception:
            return False, None


def get_sentinel():
    """get a sentinel connection object"""
    global SENTINEL
    if not SENTINEL:
        try:
            SENTINEL = Sentinel(
                REDIS_SENTINEL_CONFIG,
                # password=REDIS_AUTH,
                db=REDIS_DB,
                decode_responses=True,
                socket_timeout=0.1)
            assert SENTINEL.discover_master(REDIS_SENTINEL_NAME)
            assert SENTINEL.discover_slaves(REDIS_SENTINEL_NAME)
        except Exception as e:
            send_wx_msg(desp=e)
    return SENTINEL


def get_master(refresh=False):
    """get a master instance, if refresh is True then force refresh master"""
    global SENTINEL, MASTER
    if refresh is True:
        MASTER = None
    if MASTER is None or refresh is True:
        sentinel = get_sentinel()
        if sentinel:
            try:
                MASTER = sentinel.master_for(REDIS_SENTINEL_NAME)
            except Exception as e:
                send_wx_msg(desp=e)
    return MASTER

def get_slave(refresh=False):
    """get a slave instance, if refresh is True then force refresh slave"""
    global SENTINEL, SLAVE
    if refresh is True:
        SLAVE = None
    if SLAVE is None or refresh is True:
        sentinel = get_sentinel()
        if sentinel:
            try:
                SLAVE = sentinel.slave_for(REDIS_SENTINEL_NAME)
            except Exception as e:
                send_wx_msg(desp=e)
    return SLAVE


def get_master_and_slave(refresh=False):
    """get redis master and redis slave instance at the same time"""
    return get_master(refresh), get_slave(refresh)


def publish_message(msg, channel):
    """publish a message to redis channel"""
    try:
        if isinstance(msg, dict):  # dump to string if msg is dict
            # print msg
            msg.update({'timestamp': get_current_timestamp()})
            msg = json.dumps(msg, ensure_ascii=False)
        get_master().publish(channel=channel, message=msg)
    except Exception as e:
        print 'error in publish message'
        print str(e)
        return False
    else:
        return True


def batch_publish_messages_same_channel(msges, channel):
    """batch publish messages to the same redis channel"""
    for msg in msges:
        publish_message(msg, channel=channel)


def batch_publish_messages_diff_channel(msg_channel_tuple_list):
    """batch publish messages to different redis channel"""
    for msg_channel in msg_channel_tuple_list:
        if isinstance(msg_channel, dict):
            msg, channel = msg_channel.get('msg'), msg_channel.get('channel')
        elif isinstance(msg_channel, (tuple, list)):
            msg, channel = msg_channel[0], msg_channel[1]
        elif isinstance(msg_channel, str):
            msg, channel = msg_channel.split('|')
        publish_message(msg, channel=channel)


def process_request(task_id, data):
    """process request with data from redis messages"""
    try:
        # first rpush task_id to spider_tasks_todo list
        get_master().rpush(TASK_TODO, task_id)
        # then hmset task_id with data, and set expire time
        get_master().hmset(task_id, data)
        # set task result expire time
        get_master().expire(task_id, REDIS_RESULT_EXPIRE)
        # finally pubulish a message to redis
        publish_message(task_id, channel=TASK_CHANNEL)
    except Exception as e:
        send_wx_msg(desp=e)
        return False
    return True


def get_idle_server(service):
    """get a slave with max idle workers"""
    try:
        values = map(lambda ip: int(get_master().hget(
            '_'.join([WORKERS_KEY_PREFIX, service]), ip)), SLAVE_IPS)
        if service == 'ipbl':
            _slaves = IPBL_URLS
        else:
            _slaves = SLAVE_URLS

        def _get_index(values):
            _min = min(values)
            _duplicate = values.count(_min)
            assert _duplicate > 0
            if _duplicate > 1:
                _values = values[:]
                _count = random.choice(range(0, _duplicate)) + 1
                _index = values.index(_min)
                for x in xrange(1, _count):
                    _values = _values[_values.index(_min) + 1:]
                    _index += _values.index(_min) + 1
                return _index
            return values.index(_min)

        _index = _get_index(values)
        server = _slaves[_index]
        ip = server.split('//')[1].split(':')[0]
        return server, ip, min(values)
    except Exception as e:
        print(str(e))


def init_workers():
    """reset workers counter to 0, both all and idle"""
    for key in ['spider_workers_slave', 'spider_workers_ipbl']:
        for ip in SLAVE_IPS:
            get_master().hset(key, ip, 0)


def update_workers(service, ip, num=1, init=False):
    # basic params assertions
    assert service in PROJECT_SERVICES
    assert ip in SLAVE_IPS
    assert isinstance(num, int)
    # init workers counter if init is True
    if init is True:
        init_workers()
    # generate the worker counters key, eg: spider_workers_slave 192.168.20.201
    _key = '_'.join([WORKERS_KEY_PREFIX, service])
    # increase ip field by num
    if not get_master().hget(_key, ip):
        get_master().hset(_key, ip, 0)
    get_master().hincrby(_key, ip, num)


def dict_values_to_utf8(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                try:
                    value = value.decode()
                    data.update({key: value})
                except Exception as e:
                    print e
        return data
    return {}
