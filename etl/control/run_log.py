def start_run(conn, pipeline_name):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO etl_control.pipeline_runs (
                pipeline_name,
                status,
                started_at
            )
            VALUES (%s, 'RUNNING', clock_timestamp())
            RETURNING run_id
            """,
            (pipeline_name,),
        )
        return cur.fetchone()[0]


def finish_run_success(
    conn,
    run_id,
    rows_extracted=0,
    rows_inserted=0,
    rows_updated=0,
):
    with conn.cursor() as cur:
        # Include deferred fact/mart validation in elapsed time, while keeping
        # data and SUCCESS atomic in the caller's transaction.
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cur.execute(
            """
            UPDATE etl_control.pipeline_runs
            SET
                finished_at = clock_timestamp(),
                status = 'SUCCESS',
                rows_extracted = %s,
                rows_inserted = %s,
                rows_updated = %s
            WHERE run_id = %s
            """,
            (
                rows_extracted,
                rows_inserted,
                rows_updated,
                run_id,
            ),
        )


def finish_run_failed(conn, run_id, error_message):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE etl_control.pipeline_runs
            SET
                finished_at = clock_timestamp(),
                status = 'FAILED',
                error_message = %s
            WHERE run_id = %s
            """,
            (
                str(error_message),
                run_id,
            ),
        )
