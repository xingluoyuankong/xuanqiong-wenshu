"""Preserve published long revision IDs on length-enforcing databases."""
from sqlalchemy import Column, MetaData, String, Table, inspect

VERSION_ID_LENGTH = 128


def ensure_mysql_version_table(connection):
    """Run only in Alembic's explicit migration transaction, never app startup."""
    if connection.dialect.name != 'mysql':
        return
    inspector = inspect(connection)
    if not inspector.has_table('alembic_version'):
        Table('alembic_version', MetaData(),
              Column('version_num', String(VERSION_ID_LENGTH), primary_key=True, nullable=False)
        ).create(connection)
        return
    columns = inspector.get_columns('alembic_version')
    version = next(column for column in columns if column['name'] == 'version_num')
    current_length = getattr(version['type'], 'length', None)
    if current_length is not None and current_length < VERSION_ID_LENGTH:
        connection.exec_driver_sql(
            'ALTER TABLE alembic_version MODIFY version_num VARCHAR(128) NOT NULL'
        )
