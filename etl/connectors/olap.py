import os

import psycopg
from dotenv import load_dotenv


load_dotenv()


def get_olap_connection():
    return psycopg.connect(
        host=os.getenv("OLAP_HOST"),
        port=os.getenv("OLAP_PORT"),
        dbname=os.getenv("OLAP_DB"),
        user=os.getenv("OLAP_USER"),
        password=os.getenv("OLAP_PASSWORD"),
    )
