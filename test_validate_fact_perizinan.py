from etl.connectors.oltp import get_oltp_connection
from etl.extract.fact_perizinan.extract_perizinan import extract_perizinan
from etl.transform.fact_perizinan.normalize import normalize_perizinan_rows
from etl.transform.fact_perizinan.validation import validate_perizinan_reference


def get_valid_pegawai_ids(conn):
    query = """
        SELECT id
        FROM m_pegawai
    """

    with conn.cursor() as cur:
        cur.execute(query)

        return {
            row[0]
            for row in cur.fetchall()
        }


def get_valid_jenis_izin_ids(conn):
    query = """
        SELECT id
        FROM m_jenis_ijin
    """

    with conn.cursor() as cur:
        cur.execute(query)

        return {
            row[0]
            for row in cur.fetchall()
        }


def main():
    conn = get_oltp_connection()

    try:
        source_rows = extract_perizinan(conn)
        rows = normalize_perizinan_rows(source_rows)

        pegawai_ids = get_valid_pegawai_ids(conn)
        jenis_izin_ids = get_valid_jenis_izin_ids(conn)

        validated_rows = validate_perizinan_reference(
            rows,
            pegawai_ids,
            jenis_izin_ids,
        )

        total = len(validated_rows)

        invalid_pegawai = sum(
            not row["is_pegawai_valid"]
            for row in validated_rows
        )

        invalid_jenis_izin = sum(
            not row["is_jenis_izin_valid"]
            for row in validated_rows
        )

        print(f"Total perizinan    : {total}")
        print(f"Pegawai invalid    : {invalid_pegawai}")
        print(f"Jenis izin invalid : {invalid_jenis_izin}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()