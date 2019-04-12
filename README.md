
# jupyterhub-launcher-service

Extended launcher service for jupyterhub, to start container with run-time parameters.  
<a href="https://996.icu"><img src="https://img.shields.io/badge/link-996.icu-red.svg" alt="996.icu" /></a>

## Docker build
```sh
   git clone https://github.com/Orientsoft/moop-launcher-service.git
   cd moop-launcher-service
   docker build -t moop-launcher-service .
   docker run -p 5000:5000 moop-launcher-service
```

## jupyterhub config

add the following spawner wrapper code to your jupyterhub ```config.yaml```:  

```yaml
hub:
  auth:
    type: custom
    custom:
      # disable login (users created exclusively via API)
      className: nullauthenticator.NullAuthenticator
        
  services:
    launcher:
      url: http://[host]:[port] # launcher-service的地址
      api_token: 'ad6b8dc16f624b54a5b7d265f0744c98' # JupyterHub的API Token，要与launcher-service环境变量的配置对应

  extraConfig: |-
    from kubespawner import KubeSpawner

    class LauncherSpawner(KubeSpawner):
      def start(self):
        if 'start_count' not in dir(self):
          self.start_count = 0
          self.original_volumes = self.volumes.copy()
          self.original_volume_mounts = self.volume_mounts.copy()
        
        self.start_count += 1

        if 'image' in self.user_options:
          self.image = self.user_options['image']

        if ('volumes' in self.user_options) and (self.user_options['volumes'] is not None):
          self.volumes = self.original_volumes.copy()
          self.volumes.extend(self.user_options['volumes'])

        if ('volume_mounts' in self.user_options) and (self.user_options['volume_mounts'] is not None):
          self.volume_mounts = self.original_volume_mounts.copy()
          self.volume_mounts.extend(self.user_options['volume_mounts'])

        return super().start()
    
    c.JupyterHub.spawner_class = LauncherSpawner
```

## envs

default ```env.sh```:  

```sh
# do NOT change these, if you don't know why
export STATUS_CHECK_INTERVAL=1
export STATUS_CHECK_COUNT=300

# refer to: https://docs.python.org/3.6/library/logging.html#logging-levels
export LOG_LEVEL=10 # debug

# extended endpoint
export JUPYTERHUB_SERVICE_PREFIX="/services/launcher/"

# change these to match your jupyterhub deploy
export JUPYTERHUB_URL="http://192.168.0.31:30711"
export JUPYTERHUB_API_PREFIX="/hub/api"
export JUPYTERHUB_API_TOKEN="ad6b8dc16f624b54a5b7d265f0744c98"

# user token expires in 1800s by default
export USER_TOKEN_LIFETIME=1800
```

## dev start

```sh
source ./env.sh
FLASK_APP=./launcher-service.py flask run -h 0.0.0.0 -p 5000
```

## API

Launcher Service extends the following HTTP **POST** API to jupyterhub services path:  

```
POST http://192.168.0.31:30711/services/launcher/containers
```

Submit run-time parameters in request.body - **image, username, server_name and volume parameters are supported**:  

```js
{
    "image": "jupyter/base-notebook:latest",
    "username": "voyager",
    "vols": [
        {
            "pvc": String, // PVC name
            "mount": String, // mount point
        }
    ]
}
```

server_name could be omitted, if you don't need named server. By default, we only allow a user to start an unnamed server.  
  
The request should be finished in tens of seconds, so you might want to set a long timeout to your http client.  
If the container cannot start in 300 seconds, the service will fail with 500 status code.  
If container starts successfully, notebook endpoint url and other info will be returned:  

```js
{
    "image": "jupyter/base-notebook:latest",
    "server_name": "",
    "token": "be6ac9cb7581421da30d6a16339eaf91",
    "url": "http://192.168.0.31:30711/user/voyager/", // endpoint url
    "username": "voyager",
    "vols": [
        {
            "pvc": String, // PVC name
            "mount": String, // mount point
        }
    ]
}
```

To get server status of a user:  

```
GET http://192.168.0.31:30711/services/launcher/containers?username=voyager
```

Returns:  

```js
{
    "last_activity": "2019-03-15T03:01:17.012565Z",
    "name": "",
    "pending": null,
    "progress_url": "/hub/api/users/voyager/server/progress",
    "ready": true,
    "started": "2019-03-15T03:01:17.012565Z",
    "state": {
        "pod_name": "jupyter-voyager"
    },
    "url": "/user/voyager/"
}
```

If no server could be found for specified user, 400 status code will be returned.  

To shutdown server:  

```
DELETE http://192.168.0.31:30711/services/launcher/containers?username=voyager
```

Returns empty body if successed.  
400 status code will be returned if no server could be found.

## notebook endpoint

Just concat url and token returned from the API to create notebook endpoint for direct access:  

```py
# eg. http://192.168.0.31:30711/user/voyager/?token=be6ac9cb7581421da30d6a16339eaf91
endpoint = '{}/?token={}'.format(resp.url, resp.token)
```
