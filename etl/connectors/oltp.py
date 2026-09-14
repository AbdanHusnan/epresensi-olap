import os

import psycopg
from dotenv import load_dotenv


load_dotenv()


def get_oltp_connection():
    return psycopg.connect(
        host=os.getenv("OLTP_HOST"),
        port=os.getenv("OLTP_PORT"),
        dbname=os.getenv("OLTP_DB"),
        user=os.getenv("OLTP_USER"),
        password=os.getenv("OLTP_PASSWORD"),
    )
