# -*- coding: utf-8 -*-

from __future__ import absolute_import
from config import WORKERS
from config import MASTER_PORT
from config import PYTHON_SHELL
from os import system


MASTER_JOBS = [
    # """cat config.py | grep _ENVIRONMENT | grep -v "==" | grep -v "#" | cut -d " " -f 3 | cut -d "'" -f 2 > RedisMonitor/environment.txt""",
    # """cd RedisMonitor && python redis_monitor_daemon.py""",
    # """cd RedisMonitor && python redis_live_daemon.py""",
    """nohup gunicorn -w {} -k gevent -b 0.0.0.0:{} master:app >>logs/gunicorn.log 2>>logs/gunicorn.err.log &""".format(
        WORKERS, MASTER_PORT),
    """nohup {} dispatcher.py >>logs/dispatcher.log 2>>logs/dispatcher.err.log &""".format(
        PYTHON_SHELL)
]

print "booting master services..."
for JOB in MASTER_JOBS:
    try:
        print "boot command: {}".format(JOB)
        system(JOB)
    except Exception as e:
        print("{}:\n\tboot failed: {}".format(JOB, str(e)))
