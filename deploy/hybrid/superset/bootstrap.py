import os
from sqlalchemy.engine import URL
from superset.app import create_app
from superset import db

app = create_app()
with app.app_context():
    from superset.models.core import Database
    security = app.appbuilder.sm
    if not security.find_user(username="admin"):
        user = security.add_user("admin", "Hybrid", "Administrator", os.environ["BI_ADMIN_EMAIL"], security.find_role("Admin"), os.environ["BI_ADMIN_PASSWORD"])
        if not user:
            raise RuntimeError("Could not create Superset administrator")
    source = db.session.query(Database).filter_by(database_name="Attendance mart (read only)").first()
    uri = URL.create("postgresql+psycopg2", username="hybrid_superset_reader", password=os.environ["SUPERSET_MART_PASSWORD"], host="epresensi-mart-postgres", port=5432, database=os.environ.get("MART_DATABASE", "mart_bkd")).render_as_string(hide_password=False)
    if source is None:
        source = Database(database_name="Attendance mart (read only)")
        db.session.add(source)
    source.sqlalchemy_uri = uri
    source.expose_in_sqllab = True
    source.allow_dml = source.allow_ctas = source.allow_cvas = False
    db.session.commit()
