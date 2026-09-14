def get_pipeline_state(conn, pipeline_name):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                pipeline_name,
                source_table,
                watermark_type,
                last_watermark_timestamp,
                last_watermark_id,
                last_success_at
            FROM etl_control.pipeline_state
            WHERE pipeline_name = %s
            """,
            (pipeline_name,),
        )
        return cur.fetchone()


def upsert_pipeline_state(
    conn,
    pipeline_name,
    source_table,
    watermark_type,
    last_watermark_timestamp=None,
    last_watermark_id=None,
):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO etl_control.pipeline_state (
                pipeline_name,
                source_table,
                watermark_type,
                last_watermark_timestamp,
                last_watermark_id,
                last_success_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (pipeline_name)
            DO UPDATE SET
                source_table = EXCLUDED.source_table,
                watermark_type = EXCLUDED.watermark_type,
                last_watermark_timestamp = EXCLUDED.last_watermark_timestamp,
                last_watermark_id = EXCLUDED.last_watermark_id,
                last_success_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                pipeline_name,
                source_table,
                watermark_type,
                last_watermark_timestamp,
                last_watermark_id,
            ),
        )
