# -*- coding: utf-8 -*-

from __future__ import absolute_import
import os
from base64 import b64encode
from hashlib import md5, sha512
from multiprocessing import cpu_count


# ---------------------- VITAL CONFIGURATION ---------------------------#

_ENVIRONMENT = 'local'
# _ENVIRONMENT = 'testing'
# _ENVIRONMENT = 'production'

# ---------------------- VITAL CONFIGURATION ---------------------------#
# ---------------------- common configuration --------------------------#

if _ENVIRONMENT == 'local':
    SERVER_IPS = ['127.0.0.1']
    SLAVE_IPS = ['127.0.0.1']
    REDIS_PORTS = [6379, 6479, 6579, 6679]
    REDIS_AUTH = 'mujin'
    REDIS_SENTINEL_NAME = 'mymaster'
    # number of workers per slave
    MAX_SLAVE_WORKERS = 4
    MAX_IPBL_WORKERS = 1
    # workers num settings
    WORKERS = 2 * max(cpu_count(), 2) - 1
elif _ENVIRONMENT == 'testing':
    SERVER_IPS = [
        '172.18.231.117',
        '172.18.231.118',
        '172.18.231.115',
    ]
    SLAVE_IPS = [
        '172.18.231.118',
        '172.18.231.115',
    ]
    REDIS_PORTS = [6379]
    REDIS_AUTH = '123456'
    REDIS_SENTINEL_NAME = 'master'
    # number of workers per slave
    MAX_SLAVE_WORKERS = 8
    MAX_IPBL_WORKERS = 1
    # workers num settings
    WORKERS = 3 * max(cpu_count(), 2) - 1
elif _ENVIRONMENT == 'production':
    SERVER_IPS = [
        '192.168.20.88',
        '192.168.20.201',
        '192.168.20.202',
        '192.168.20.203',
    ]
    SLAVE_IPS = [
        '192.168.20.201',
        '192.168.20.202',
        '192.168.20.203',
    ]
    REDIS_PORTS = [6379]
    REDIS_AUTH = 'ajclua&$01x'
    REDIS_SENTINEL_NAME = 'mymaster'
    # number of workers per slave
    MAX_SLAVE_WORKERS = 12
    MAX_IPBL_WORKERS = 1
    # workers num settings
    WORKERS = 4 * max(cpu_count(), 2) - 1

else:
    raise RuntimeError('Unknown running environment.')

# ---------------------- common configuration --------------------------#
# ---------------------- functions definition --------------------------#


def ensure_dir(dir_name):
    if not os.path.isdir(dir_name):
        try:
            os.mkdir(dir_name)
        except Exception as e:
            print(str(e))


def encrypt(s):
    m, n = sha512(), md5()
    m.update(b64encode(s))
    _ = m.hexdigest()
    seed = ''.join([_[k] for k in range(0, len(_), 2)])
    n.update(seed)
    return n.hexdigest()


def gen_redis_args(ips, ports, password, db):
    _sentinel = []
    for ip in ips:
        for port in ports:
            _sentinel.append({
                'host': ip,
                'port': port,
                'password': password,
                'db': db,
            })
    return _sentinel


def gen_slave_urls(ips, port):
    _slave_urls = []
    for ip in ips:
        _slave_urls.append('http://' + ip + ':' + str(port))
    return _slave_urls


# ---------------------- functions definition --------------------------#
# ------------------------ project parameters --------------------------#

# python shell config, default: python
PYTHON_SHELL = 'python'

# config a project name
PROJECT = 'mujin_spider_server'

# config service types
PROJECT_SERVICES = ['slave', 'ipbl']

# ftqq send wx msg settings
WX_MSG_KEY = '616-6d5498559c513bd42f2f0b4176f3e480'
WX_MSG_URL = 'https://pushbear.ftqq.com/sub?sendkey={key}&text={title}&desp={body}'

# service logs directory
LOG_DIR = 'logs'
ensure_dir(LOG_DIR)

# task timeout
TASK_TIMEOUT = 120

# task execution interval
TASK_MAX_SPAN = 1
# max task retry times on slave
TASK_MAX_RETRY = 3
# max jobs in queue to trigger service start
QUEUE_MAX_JOBS = 10

# service ports
MASTER_PORT = 5000
SLAVE_PORT = 8000
IPBL_PORT = 8001

# etag keyword in headers, needed every request
SECRET_KEY = 'mujinkeji'
SECRET = encrypt(SECRET_KEY)
with open('SECRET.KEY', 'w') as f:
    f.write(SECRET)

# ------------------------ project parameters --------------------------#
# ---------------------- redis sentinel config -------------------------#

# redis task expire config
REDIS_RESULT_HOURS = 24
REDIS_RESULT_EXPIRE = 60 * 60 * REDIS_RESULT_HOURS

# redis connection pool max size
REDIS_POOL_SIZE = 100


# generate related urls
SLAVE_URLS = gen_slave_urls(SLAVE_IPS, SLAVE_PORT)
IPBL_URLS = gen_slave_urls(SLAVE_IPS, IPBL_PORT)

# message channels
SLAVE_CHANNEL = 'spider_slave'
TASK_CHANNEL = 'spider_task'
RESULT_CHANNEL = 'spider_result'
DATA_CHANNEL = 'spider_data'

CHANNELS_ALL = [
    SLAVE_CHANNEL,
    TASK_CHANNEL,
    RESULT_CHANNEL,
    DATA_CHANNEL,
]

# redis hashtable update modes
UPDATE_MODE_REPLACE = 'replace'
UPDATE_MODE_UPDATE = 'update'
UPDATE_MODE_DELETE = 'delete'
UPDATE_MODE_ALL = [
    UPDATE_MODE_REPLACE,
    UPDATE_MODE_UPDATE,
    UPDATE_MODE_DELETE,
]

# tasks list
TASK_TODO = 'spider_tasks_todo'

# tasks failed list
TASK_FAIL = 'spider_tasks_fail'

# workers config
WORKERS_KEY_PREFIX = 'spider_workers'

# fetch message interval
MESSAGE_FETCH_INTERVAL = 0.001

# task priority config
PRIORITY = {
    'high': 9,
    'avg': 5,
    'low': 0,
}

# generate sentinels
REDIS_DB = 0
SENTINEL_PORT = 26379
SENTINEL_RECONNECT_INTERVAL = 1
REDIS_SENTINEL_CONFIG = [(SERVER_IPS[0], SENTINEL_PORT)]
REDIS_KWARGS = gen_redis_args(SERVER_IPS, REDIS_PORTS, REDIS_AUTH, REDIS_DB)

# ---------------------- redis sentinel config -------------------------#

# accepted incoming query interfaces
INTERFACES = [
    'getMobileInfoBasic',
    'getExecutionInfo',
    'getDishonestExecutionInfo',
    'getP2pRegisterValidate',
    'getAliveIpProxy',
    'getMobileTags',
    'getIpBlacklist',
    'getFraudPhoneInfo',
    'getIpIsp',]
