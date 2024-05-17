from os import environ

RABBITMQ_HOST = environ.get('RABBITMQ_HOST', 'localhost')
RABBITMQ_USER = environ.get('RABBITMQ_USER')
RABBITMQ_PASSWORD = environ.get('RABBITMQ_PASSWORD')

POSTGRES_HOST = environ.get('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = environ.get('POSTGRES_PORT', '5432')

POSTGRES_USER = environ.get('POSTGRES_USER')
POSTGRES_PASSWORD = environ.get('POSTGRES_PASSWORD')
POSTGRES_DB = environ.get('POSTGRES_DB')

