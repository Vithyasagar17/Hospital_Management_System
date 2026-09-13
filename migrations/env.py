from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from flask import current_app

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _db():
    return current_app.extensions['migrate'].db


def _metadata():
    return _db().metadata


def run_migrations_offline():
    context.configure(
        url=current_app.config['SQLALCHEMY_DATABASE_URI'],
        target_metadata=_metadata(),
        literal_binds=True,
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = _db().engine
    with connectable.connect() as connection:
        configure_args = dict(current_app.extensions['migrate'].configure_args)
        configure_args.setdefault('compare_type', True)
        configure_args.setdefault('render_as_batch', True)
        context.configure(
            connection=connection,
            target_metadata=_metadata(),
            **configure_args,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
