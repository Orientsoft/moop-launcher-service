
# jupyterhub-launcher-worker

Extended launcher service worker for jupyterhub, to start container with run-time parameters.  

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
        if 'transparent' not in self.user_options:
          if 'start_count' not in dir(self):
            self.start_count = 0
            self.original_volumes = self.volumes.copy()
            self.original_volume_mounts = self.volume_mounts.copy()
        
          self.start_count += 1
        
          self.image = self.user_options['image']

        if self.user_options.get('volumes'):
          self.volumes = self.original_volumes.copy()
          self.volumes.extend(self.user_options['volumes'])

        if self.user_options.get('volume_mounts'):
          self.volume_mounts = self.original_volume_mounts.copy()
          self.volume_mounts.extend(self.user_options['volume_mounts'])

        if self.user_options.get('cpu'):
          self.cpu_guarantee = self.user_options['cpu']['request']
          self.cpu_limit = self.user_options['cpu']['limit']

        if self.user_options.get('memory'):
          self.mem_guarantee = self.user_options['memory']['request']
          self.mem_limit = self.user_options['memory']['limit']

        if self.user_options.get('gpu'):
          self.extra_resource_guarantees = {"nvidia.com/gpu": "{}".format(self.user_options['gpu']['request'])}
          self.extra_resource_limits = {"nvidia.com/gpu": "{}".format(self.user_options['gpu']['limit'])}
          self.volumes.extend([{"name": "shm-volume", "emptyDir": {"medium": "Memory"}}])
          self.volume_mounts.extend([{"name": "shm-volume", "mountPath": "/dev/shm"}])
        else:
          self.user_options.pop('transparent', None)

          if 'start_count' not in dir(self):
            self.start_count = 0
            
            self.original_lists = {}

            for key, value in self.items():
              if isinstance(value, list):
                self.original_lists[key] = value.copy()

          for key, value in self.user_options.items():
            if not isinstance(value, list):
              setattr(self, key, value)
            else:
              new_list = self.original_lists[key].copy()
              new_list.extend(value)

              setattr(self, key, new_list)

        return super().start()
    
    c.JupyterHub.spawner_class = LauncherSpawner
```

## config.yaml

Please place config.yaml under the root of launcher service.  

config.yaml:  

```yaml
host: '0.0.0.0'
port: 5000
debug: true
# 10 - debug
log_level: 10
# do not alter the following 2 status parameters
status_check_interval: 2
status_check_count: 120
# launcher service prefix extended in JH
jupyterhub_service_prefix: '/services/launcher/'
jupyterhub_url: 'http://192.168.0.31:30264'
# prefix of jupyterhub api endpoint
jupyterhub_api_prefix: '/hub/api'
# service api token, must be the same as in JH config
jupyterhub_api_token: 'ad6b8dc16f624b54a5b7d265f0744c98'
# token lifetime requested from JH
user_token_lifetime: 1800
```

For log level, please check https://docs.python.org/3/library/logging.html#logging-levels.

celery-config.py:  

```py
broker_url = 'redis://:pass@a.b.c.d:6379/0'
result_backend = 'redis://:pass@a.b.c.d:6379/0'
```

## dev start

```sh
celery -A launcher-worker worker -l info
```

## API

celery tasks:

### 1. launch container

```py
def launch(image, username, server_name='', vols=None, cpu=None, memory=None, gpu=None, json=None, skip_check=True)
```

#### parameters:  
```js
"image": "jupyter/base-notebook:latest",
"username": "voyager",
"cpu": {
    "request": 0.5,
    "limit": 1
},
"memory": {
    "request": "512M",
    "limit": "1G"
},
"gpu":{
    "request": 1,
    "limit": 1
},
"vols": [
    {
        "pvc": String, // PVC name
        "mount": String, // mount point
        "subpath": String, // mount sub path
    }
]
```

server_name could be omitted, if you don't need named server. By default, we only allow a user to start an unnamed server.  
If you specify ```json``` with a ```transparent``` key, then launcher and spawner will use tranparent mode - the other keys in json will be directly assigned to spawner.  
To support gpu, use transparent mode and specify extra toleration:  
```yaml
  tolerations:
  - key: nvidia.com/gpu
    operator: Equal
    value: gpu
    effect: NoSchedule
```

If the container cannot start in 300 seconds, the service will fail and return ```None```.  

#### return:  
If container starts successfully, notebook endpoint url and other info will be returned:  

```js
{
    "image": "jupyter/base-notebook:latest",
    "server_name": "",
    "token": "be6ac9cb7581421da30d6a16339eaf91",
    "url": "http://192.168.0.31:30711/user/voyager/", // endpoint url
    "username": "voyager",
    "cpu": {
        "request": 0.5,
        "limit": 1
    },
    "memory": {
        "request": "512M",
        "limit": "1G"
    },
    "gpu":{
        "request": 1,
        "limit": 1
    },
    "vols": [
        {
            "pvc": String, // PVC name
            "mount": String, // mount point
            "subpath": String, // mount sub path
        }
    ]
}
```

### 2. read container

```py
def read(username, server_name='')
```

#### parameters:   
username and server_name

#### return:
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

### 3. remove container

```py
def remove(username, server_name='')
```

#### parameters:   
username and server_name

#### return:
Boolean, True for success, False for failure

## notebook endpoint

Just concat url and token returned from the API to create notebook endpoint for direct access:  

```py
# eg. http://192.168.0.31:30711/user/voyager/?token=be6ac9cb7581421da30d6a16339eaf91
endpoint = '{}/?token={}'.format(resp.url, resp.token)
```
