from pymongo import MongoClient
from config import Config

_client = MongoClient(Config.MONGO_URI, connect=True)
db = _client.EmployeeManagement
