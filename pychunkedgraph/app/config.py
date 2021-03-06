import logging
import os
import json


class BaseConfig(object):
    DEBUG = False
    TESTING = False
    HOME = os.path.expanduser("~")
    # TODO get this secret out of source control
    SECRET_KEY = '1d94e52c-1c89-4515-b87a-f48cf3cb7f0b'

    LOGGING_FORMAT = '{"source":"%(name)s","time":"%(asctime)s","severity":"%(levelname)s","message":"%(message)s"}'
    LOGGING_DATEFORMAT = '%Y-%m-%dT%H:%M:%S.0Z'
    LOGGING_LEVEL = logging.DEBUG

    CHUNKGRAPH_INSTANCE_ID = "pychunkedgraph"
    PROJECT_ID = os.environ.get('PROJECT_ID', None)

    # TODO what is this suppose to be by default?
    CHUNKGRAPH_TABLE_ID = "pinky100_sv16"
    # CHUNKGRAPH_TABLE_ID = "pinky100_benchmark_v92"

    USE_REDIS_JOBS = False
    
    MESHING_ENDPOINT = os.environ.get("MESHING_ENDPOINT", "http://meshing-service/meshing")
    
    if os.environ.get("DAF_CREDENTIALS", None) is not None:
        with open(os.environ.get("DAF_CREDENTIALS"), "r") as f:
            AUTH_TOKEN = json.load(f)["token"]
    else:
        AUTH_TOKEN = ""

class DevelopmentConfig(BaseConfig):
    """Development configuration."""
    USE_REDIS_JOBS = False
    DEBUG = True


class DockerDevelopmentConfig(BaseConfig):
    """Development configuration."""
    USE_REDIS_JOBS = True
    REDIS_HOST = os.environ.get('REDIS_SERVICE_HOST', 'localhost')
    REDIS_PORT = os.environ.get('REDIS_SERVICE_PORT', '6379')
    REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', 'dev')
    REDIS_URL = f'redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0'    


class DeploymentWithRedisConfig(BaseConfig):
    """Deployment configuration with Redis."""
    USE_REDIS_JOBS = True
    REDIS_HOST = os.environ.get('REDIS_SERVICE_HOST')
    REDIS_PORT = os.environ.get('REDIS_SERVICE_PORT')
    REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD')
    REDIS_URL = f'redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0'


class TestingConfig(BaseConfig):
    """Testing configuration."""
    TESTING = True
    USE_REDIS_JOBS = False
    PRESERVE_CONTEXT_ON_EXCEPTION = False
