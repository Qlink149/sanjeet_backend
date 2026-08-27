from pymongo import MongoClient

from qlink_chatbot.utils.env_load import mongo_uri

# tz_aware so every datetime read back from Mongo carries explicit UTC
# tzinfo — without it, pymongo hands back naive datetimes, whose
# .isoformat() omits the offset, which browsers then misinterpret as
# already being in the viewer's local timezone instead of UTC.
client = MongoClient(
    mongo_uri,
    tz_aware=True,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=10000,
)
db = client["sanjeet"]
