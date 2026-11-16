from decouple import config

#kết nối đên VM4
KAFKA_BOOTSTRAP_SERVICES = config('KAFKA_BOOTSTRAP_SERVERS')
KAFKA_BOOTSTRAP_GROUP = config('KAFKA_CONSUMER_GROUP')

#kết nối đến VM3
REDIS_URL = config('REDIS_URL')

#kết nối database
DB_NAME = config('DB_NAME')
DB_USER = config('DB_USER')
DB_PASSWORD = config('DB_PASSWORD')
DB_HOST = config('DB_HOST')
DB_PORT = config('DB_PORT')

#SECRET_KEY
SECRET_KEY = config('SECRET_KEY')