from functools import wraps
import traceback
import json
import os
import time
import logging
import logging.handlers
import sys
import uuid

import requests
from flask import Flask, redirect, request, Response
import yaml

# consts
REQUEST_TIMEOUT = 120
LOG_NAME = 'Launcher-Service'
LOG_FORMAT = '%(asctime)s - %(filename)s:%(lineno)s - %(name)s:%(funcName)s - [%(levelname)s] %(message)s'

CONFIG_PATH = './config.yaml'

with open(CONFIG_PATH) as config_file:
    config_str = config_file.read()
    configs = yaml.load(config_str)

    LOG_LEVEL = configs['log_level']

    LAUNCH_STATUS_INTERVAL = configs['status_check_interval']
    LAUNCH_STATUS_CHECK_COUNT = configs['status_check_count']

    service_prefix = configs['jupyterhub_service_prefix']
    hub_url = configs['jupyterhub_url']
    hub_api_prefix = configs['jupyterhub_api_prefix']
    hub_api_token = configs['jupyterhub_api_token']

    user_token_lifetime = configs['user_token_lifetime']

    HOST = configs['host']
    PORT = configs['port']
    DEBUG = configs['debug']

# configs from envs
'''
LAUNCH_STATUS_INTERVAL = int(os.getenv('STATUS_CHECK_INTERVAL', ''))
LAUNCH_STATUS_CHECK_COUNT = int(os.getenv('STATUS_CHECK_COUNT', ''))
LOG_LEVEL = int(os.getenv('LOG_LEVEL', ''))

service_prefix = os.environ.get('JUPYTERHUB_SERVICE_PREFIX', '/').strip()
hub_url = os.getenv('JUPYTERHUB_URL', '').strip()
hub_api_prefix = os.getenv('JUPYTERHUB_API_PREFIX', '').strip()
hub_api_token = os.getenv('JUPYTERHUB_API_TOKEN', '').strip()

user_token_lifetime = int(os.getenv('USER_TOKEN_LIFETIME').strip())
'''

hub_api_url = '{}{}'.format(hub_url, hub_api_prefix)

def setup_logger(level):
    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter(LOG_FORMAT)
    handler.setFormatter(formatter)

    logger = logging.getLogger(LOG_NAME)
    logger.addHandler(handler)
    logger.setLevel(level)

    return logger

logger = setup_logger(int(LOG_LEVEL))

logger.info('\n*** Launcher-Service ***\n\nGot envs:\nSTATUS_CHECK_INTERVAL: {}\nSTATUS_CHECK_COUNT: {}\nLOG_LEVEL: {}\nJUPYTERHUB_SERVICE_PREFIX: {}\nJUPYTERHUB_URL: {}\nJUPYTERHUB_API_PREFIX: {}\nJUPYTERHUB_API_TOKEN: {}\n'.format(
    LAUNCH_STATUS_INTERVAL,
    LAUNCH_STATUS_CHECK_COUNT,
    LOG_LEVEL,
    service_prefix,
    hub_url,
    hub_api_prefix,
    hub_api_token
))

app = Flask(__name__)

def request_api(session, url, *args, method='get', **kwargs):
    headers = {
        'Authorization': 'token {}'.format(hub_api_token)
    }

    if method == 'get':
        resp = session.get(
            '{}/{}'.format(hub_api_url, url),
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            *args, **kwargs
        )
    elif method == 'post':
        resp = session.post(
            '{}/{}'.format(hub_api_url, url),
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            **kwargs
        )
    elif method == 'delete':
        resp = session.delete(
            '{}/{}'.format(hub_api_url, url),
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            **kwargs
        )

    if (method == 'get') and (resp.status_code != 404): # allow GET 404
        resp.raise_for_status()

    logger.debug('req - {} {}\nresp - code: {}, text: {}'.format(method, url, resp.status_code, resp.text))

    return resp

def get_launch_params(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        body = request.get_json()
        
        if 'image' not in body.keys():
            return Response(
                json.dumps({'error': 'no image parameter specified'}, indent=1, sort_keys=True),
                mimetype='application/json',
            )
        if 'username' not in body.keys():
            return Response(
                json.dumps({'error': 'no username parameter specified'}, indent=1, sort_keys=True),
                mimetype='application/json',
            )
        server_name = body['server_name'] if 'server_name' in body.keys() else ''

        if 'vols' in body.keys():
            vols = body['vols']

            vol_names = [str(uuid.uuid4()) for vol in vols]
            volumes = []
            volume_mounts = []

            for i, vol in enumerate(vols):
                volumes.append({
                    'name': vol_names[i],
                    'persistentVolumeClaim': {
                        'claimName': vol['pvc']
                    }
                })

                volume_mounts.append({
                    'name': vol_names[i],
                    'mountPath': vol['mount']
                })
        else:
            volumes = None
            volume_mounts = None

        return f(
            body['image'],
            body['username'],
            *args,
            server_name=server_name,
            volumes=volumes,
            volume_mounts=volume_mounts,
            **kwargs
        )

    return decorated

@app.route('{}{}'.format(service_prefix, 'containers'), methods=['POST'])
@get_launch_params
def launch(image, username, server_name='', volumes=None, volume_mounts=None):
    try:
        session = requests.Session()

        # named server not enabled
        # just check if the user has a running server ''
        if server_name == '':
            user_resp = request_api(session, 'users/{}'.format(username))

            if (user_resp.status_code == 404):
            # if 'status' in user_data and user_data['status'] == 404:
                new_user = request_api(session, 'users/{}'.format(username), method='post').json()
            else:
                user_data = user_resp.json()

                if 'servers' in user_data.keys() and server_name in user_data['servers'].keys():
                    return Response(
                        json.dumps(
                            {'error': '{} already has a running server'.format(username)},
                            indent=1,
                            sort_keys=True
                        ),
                        status=400,
                        mimetype='application/json'
                    )

        user_token_resp = request_api(
            session,
            'users/{}/tokens'.format(username),
            method='post',
            json={
                'note': 'launcher_token',
                'expires_in': user_token_lifetime
            }
        ).json()

        user_token = user_token_resp['token']
        
        data = {
            'image': image,
            'username': username,
            'server_name': server_name,
            'volumes': volumes,
            'volume_mounts': volume_mounts
        }

        logger.debug('data: {}'.format(data))

        # call jupyterhub api to launch server
        server_resp = request_api(
            session,
            'users/{}/servers/{}'.format(username, server_name),
            method='post',
            json=data
        )

        # wait for the server to start
        if server_resp.status_code == 202:
            for i in range(LAUNCH_STATUS_CHECK_COUNT):
                user_data = request_api(
                    session,
                    'users/{}'.format(username)
                ).json()

                logger.debug(user_data)

                if server_name in user_data['servers'].keys():
                    if user_data['servers'][server_name]['ready']:
                        # return container endpoint
                        data['url'] = '{}/user/{}/{}'.format(
                            hub_url,
                            username,
                            server_name
                        )
                        data['token'] = user_token

                        return Response(
                            json.dumps(
                                data,
                                indent=1,
                                sort_keys=True
                            ),
                            status=200,
                            mimetype='application/json'
                        )
                else:
                    raise ChildProcessError('launch failed')

                time.sleep(LAUNCH_STATUS_INTERVAL)
    except requests.exceptions.RequestException as e:
        # there might be something wrong with jupyterhub or network
        logger.error('Request Error: {}\nStack: {}\n'.format(e, traceback.format_exc()))
        return Response(
                json.dumps(
                    {'error': 'Request to jupyterhub API failed.'},
                    indent=1,
                    sort_keys=True
                ),
                status=500,
                mimetype='application/json'
            )
    except ChildProcessError as e:
        # cannot properly start a container
        logger.error('Container Error: {}\nStack: {}\n'.format(e, traceback.format_exc()))
        return Response(
            json.dumps(
                {'error': 'Jupyterhub container launch failed.'},
                indent=1,
                sort_keys=True
            ),
            status=500,
            mimetype='application/json'
        )
    except Exception as e:
        # this might be a bug
        logger.critical('Program Error: {}\nStack: {}\n'.format(e, traceback.format_exc()))
        return Response(
            json.dumps(
                {'error': 'Launcher service failed.'},
                indent=1,
                sort_keys=True
            ),
            status=500,
            mimetype='application/json'
        )

@app.route('{}{}'.format(service_prefix, 'containers'), methods=['GET'])
def read_container():
    try:
        session = requests.Session()
        body = request.args

        if 'username' not in body.keys():
            return Response(
                json.dumps({'error': 'no username parameter specified'}, indent=1, sort_keys=True),
                mimetype='application/json',
            )
        username = body['username']
        server_name = body['server_name'] if 'server_name' in body.keys() else ''

        user_data = request_api(session, 'users/{}'.format(username)).json()

        if server_name in user_data['servers'].keys():
            return Response(
                json.dumps(user_data['servers'][server_name], indent=1, sort_keys=True),
                mimetype='application/json',
            )
        else:
            return Response(
                json.dumps({'error': 'no server /user/{}/server/{} found'.format(username, server_name)}, indent=1, sort_keys=True),
                mimetype='application/json',
                status=400
            )
    except requests.exceptions.RequestException as e:
        # there might be something wrong with jupyterhub or network
        logger.error('Request Error: {}\nStack: {}\n'.format(e, traceback.format_exc()))
        return Response(
                json.dumps(
                    {'error': 'Request to jupyterhub API failed.'},
                    indent=1,
                    sort_keys=True
                ),
                status=500,
                mimetype='application/json'
            )
    except Exception as e:
        # this might be a bug
        logger.critical('Program Error: {}\nStack: {}\n'.format(e, traceback.format_exc()))
        return Response(
            json.dumps(
                {'error': 'Launcher service failed.'},
                indent=1,
                sort_keys=True
            ),
            status=500,
            mimetype='application/json'
        )

@app.route('{}{}'.format(service_prefix, 'containers'), methods=['DELETE'])
def remove_container():
    try:
        session = requests.Session()
        body = request.args

        if 'username' not in body.keys():
            return Response(
                json.dumps({'error': 'no username parameter specified'}, indent=1, sort_keys=True),
                mimetype='application/json',
            )
        username = body['username']
        server_name = body['server_name'] if 'server_name' in body.keys() else ''

        if server_name == '':
            server_resp = request_api(session, 'users/{}/server'.format(username), method='delete')
        else:
            server_resp = request_api(session, 'users/{}/server/{}'.format(username, server_name), method='delete')

        return Response(status=200)
    except requests.exceptions.RequestException as e:
        # there might be something wrong with jupyterhub or network
        logger.error('Request Error: {}\nStack: {}\n'.format(e, traceback.format_exc()))
        return Response(
            json.dumps(
                {'error': 'Request to jupyterhub API failed.'},
                indent=1,
                sort_keys=True
            ),
            status=500,
            mimetype='application/json'
        )
    except Exception as e:
        # this might be a bug
        logger.critical('Program Error: {}\nStack: {}\n'.format(e, traceback.format_exc()))
        return Response(
            json.dumps(
                {'error': 'Launcher service failed.'},
                indent=1,
                sort_keys=True
            ),
            status=500,
            mimetype='application/json'
        )
        
if __name__ == '__main__':
    logger.debug('configs: {}'.format(configs))
    app.run(
        debug=DEBUG,
        host=HOST,
        port=PORT,
        threaded=True
    )
