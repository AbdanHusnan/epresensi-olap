"""Idempotently provision the new instance; never modifies another Superset."""
import os
from urllib.parse import quote_plus
from superset.app import create_app

app = create_app()
with app.app_context():
    from superset import db, security_manager
    from superset.models.core import Database
    from superset.connectors.sqla.models import SqlaTable, SqlMetric

    username = os.environ['SUPERSET_ADMIN_USERNAME']
    if not security_manager.find_user(username=username):
        user = security_manager.add_user(
            username=username, first_name='Dashboard', last_name='Admin',
            email='dashboard-admin@localhost',
            role=security_manager.find_role('Admin'),
            password=os.environ['SUPERSET_ADMIN_PASSWORD'],
        )
        if not user:
            raise RuntimeError('Admin creation failed')
    security_manager.add_role('DashboardGuest')
    database = db.session.query(Database).filter_by(database_name='ePresensi OLAP').one_or_none()
    if database is None:
        database = Database(database_name='ePresensi OLAP')
        db.session.add(database)
    database.sqlalchemy_uri = (
        'postgresql+psycopg2://dashboard_reader:'
        + quote_plus(os.environ['DASHBOARD_READER_PASSWORD'])
        + '@postgres-olap:5432/' + quote_plus(os.environ['DASHBOARD_OLAP_DB'])
    )
    database.allow_dml = False
    database.allow_ctas = False
    database.allow_cvas = False
    database.expose_in_sqllab = False
    db.session.flush()
    metrics = {
        'attendance_rate': ('100.0 * SUM(present_days) / NULLIF(SUM(expected_days), 0)', 'Attendance Rate (%)'),
        'ontime_rate': ('100.0 * SUM(ontime_days) / NULLIF(SUM(evaluated_days), 0)', 'On-Time Rate (%)'),
        'absence_rate': ('100.0 * SUM(absent_days) / NULLIF(SUM(expected_days), 0)', 'Absence Rate (%)'),
        'average_lateness': ('1.0 * SUM(late_minutes) / NULLIF(SUM(late_days), 0)', 'Average Lateness (minutes)'),
    }
    for name in ('attendance_daily', 'attendance_department_daily'):
        dataset = db.session.query(SqlaTable).filter_by(database_id=database.id, schema='analytics', table_name=name).one_or_none()
        if dataset is None:
            dataset = SqlaTable(table_name=name, schema='analytics', database=database)
            db.session.add(dataset)
            db.session.flush()
        dataset.fetch_metadata()
        dataset.main_dttm_col = 'tanggal'
        dataset.description = ('Provisional KPI definitions; dummy August 2026. Targets unset. '
            'Attendance=present/expected; absence excludes leave; ontime uses evaluated attendance; '
            'average lateness uses late days only. Current day is provisional.')
        for key, (expression, label) in metrics.items():
            metric = next((m for m in dataset.metrics if m.metric_name == key), None)
            if metric is None:
                metric = SqlMetric(metric_name=key, table=dataset)
                db.session.add(metric)
            metric.expression = expression
            metric.verbose_name = label
            metric.d3format = '.2f'
        db.session.flush()
    db.session.commit()
    print('Dashboard admin, isolated OLAP connection and two datasets ready; targets remain NULL.')
