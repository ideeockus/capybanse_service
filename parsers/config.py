from os import environ

RABBITMQ_HOST = environ.get('RABBITMQ_HOST', 'localhost')

