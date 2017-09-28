# -*- coding: utf-8 -*-

from __future__ import absolute_import

import json
import demjson
from os import urandom
from config import SECRET
from config import PRIORITY
from config import INTERFACES
from config import SLAVE_CHANNEL
from config import WORKERS_KEY_PREFIX
from utils import get_slave
from utils import publish_message
from utils import process_request
from utils import send_wx_msg
from utils import validate_task_id
from utils import get_current_timestamp
from utils import dict_values_to_utf8
from flask import Flask, jsonify, request, abort


app = Flask(__name__)
app.secret = urandom(32)


@app.errorhandler(404)  # handle 404 error
def not_found(error):
    msg = error.description
    return jsonify({
        'code': '90404',
        'msg': 'not found' if not msg else msg,
        'timestamp': get_current_timestamp(),
    }), 200


@app.errorhandler(403)  # handle 403 error
def not_allowed(error):
    msg = error.description
    return jsonify({
        'code': '90403',
        'msg': 'unauthorized' if not msg else msg,
        'timestamp': get_current_timestamp(),
    }), 200


@app.errorhandler(500)  # handle 500 error
def internal_error(error):
    msg = error.description
    return jsonify({
        'code': '90500',
        'msg': 'internal error' if not msg else msg,
        'timestamp': get_current_timestamp(),
    }), 200


@app.route('/', methods=['GET'])  # master service index
def index():
    return jsonify({
        'code': '00000',
        'msg': 'success',
        'timestamp': get_current_timestamp(),
    }), 200


@app.route('/send', methods=['GET', 'POST'])  # send wx msg interface
def send():
    if request.method == 'GET':
        title = request.args.get('text', '')
        body = request.args.get('desp', '')
    elif request.method == 'POST':
        title = request.form.get('text', '')
        body = request.form.get('desp', '')
    if not title and not body:
        abort(404, 'require at least one param: msg title or msg body')
    _status, _data = send_wx_msg(text=title, desp=body)
    if _status:
        code = '00000'
        msg = 'send wechat msg success'
        return jsonify({
            'code': code,
            'msg': msg,
            'data': _data,
            'timestamp': get_current_timestamp(),
        }), 200
    else:
        code = '90500'
        msg = 'send wechat msg failure'
        return jsonify({
            'code': code,
            'msg': msg,
            'timestamp': get_current_timestamp(),
        }), 500


@app.route('/wplus', methods=['GET'])  # for slaves to register workers
def wplus():
    secret = request.headers.get('secret', '')
    if not secret or secret != SECRET:
        abort(403, 'bad secret')
    _args = request.args.to_dict()
    service = _args.get('service', '')
    ip = _args.get('ip', '')
    num = int(_args.get('num', '0'))
    _data = {
        'service': service,
        'ip': ip,
        'num': num,
    }
    return jsonify({
        'code': 200,
        'msg': 'success',
        'timestamp': get_current_timestamp(),
    }), 200


@app.route('/queue/<string:interface>', methods=['GET', 'POST'])
def queue(interface):
    """master queue generator, secret, task_id, request args required"""
    # make sure interface in INTERFACES
    if interface not in INTERFACES:
        abort(404, 'bad interface')
    secret = request.headers.get('secret', '')
    if secret != SECRET:
        abort(403, 'bad secret')
    task_id = request.headers.get('task_id', '')
    # if not secret or secret not match, abort 403
    if not task_id:
        abort(403, 'no task_id')
    if  not validate_task_id(task_id):
        abort(403, 'invalid task_id')
    if get_slave().keys(task_id) or get_slave().keys('-'.join([task_id,'result'])):
        abort(403, 'duplicate task_id')
    priority = request.headers.get('priority', 'avg')
    rtype = request.headers.get('rtype', 'common')
    # if priority is not acceptable, abort 403
    if not priority or priority not in PRIORITY.keys():
        abort(403, 'invalid priority')
    priority = PRIORITY[priority]  # replace priority string with integer code

    # parsing params from request object depending on the request method
    if request.method == 'GET':  # parse request GET args to dict object
        _args = request.args.to_dict()
    elif request.method == 'POST':  # parse request POST args to dict object
        _args = request.form.to_dict()
    # reformat the whole request url, except for domain name
    if _args:
        task = '?'.join([
            interface,
            '&'.join(map(lambda k: '='.join([k, _args[k]]), _args.keys()))
        ])
    else:
        task = interface

    timestamp = get_current_timestamp()
    data = {
        'code': '90202',
        'rtype': rtype,
        'interface': interface,
        'task': task,
        'priority': priority,
        'status': 'TODO',
        'message': 'queue',
        'counter': 0,
        'timestamp': timestamp,
    }

    # if successfully published the task message return 00000
    if process_request(task_id, data):
        return jsonify({
            # 'task_id': task_id,
            'code': '00000',
            'msg': 'success',
            'timestamp': timestamp,
        }), 200
    else:  # or else abort 500
        abort(500)


@app.route('/result', methods=['GET', 'POST'])
def result():
    """task result fetcher interface, secret and task_id required"""
    # if secret not match, abort 403
    if request.headers.get('secret', '') != SECRET:
        abort(403, 'bad secret')
    # parse task_id value from request depending on request method
    if request.method == 'GET':
        args = request.args.to_dict()
    elif request.method == 'POST':
        args = request.form.to_dict()
    task_id = args.get('task_id', '')
    # if task_id 
    if not task_id:
        abort(403, 'no task_id')
    # if task_id not exists then abort 404
    if not get_slave().keys(task_id):
        abort(404, 'invalid task_id')
    else:
        # get corresponding status,code,msg with task_id from redis
        code, msg, status, result = get_slave().hmget(task_id, ['code', 'message', 'status', 'result'])
        result = demjson.decode(result, encoding='utf8') if result else []
        # return initial response content
        return jsonify({
            'task_id': task_id,
            'code': code,
            'msg': msg,
            'status': status,
            'data': result,
            'timestamp': get_current_timestamp(),
        }), 200


@app.route('/results', methods=['GET', 'POST'])
def results(task_ids):
    """return batch results according to task_ids"""
    # if secret not match, abort 403
    if request.headers.get('secret', '') != SECRET:
        abort(403, 'bad secret')
    # parse task_ids  from request depending on request method
    if request.method == 'GET':
        args = request.args.to_dict()
    elif request.method == 'POST':
        args = request.form.to_dict()
    _task_ids = args.get('task_ids', '')
    # split task_ids into list
    task_ids = _task_ids.split('|')
    results = []
    # get result with task_id and append to results list
    for task_id in task_ids:
        # if task_id not exists then code is  90404
        if not get_slave().keys(task_id):
            code = '90404'
            msg = 'not found'
            status = 'VOID'
            result = []
        else:
            code, msg, status, result = get_slave().hmget(task_id, ['code', 'msg', 'status', 'result'])
        result = {
            'task_id': task_id,
            'code': code,
            'msg': msg,
            'status': status,
            'data': dict_values_to_utf8(result),
            'timestamp': get_current_timestamp(),
        }
        results.append(result)
    return jsonify(results), 200  # return all results of task_ids


if __name__ == '__main__':
    from config import MASTER_PORT
    app.run(host='0.0.0.0', port=MASTER_PORT, debug=True)
