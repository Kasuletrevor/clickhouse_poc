from __future__ import annotations

from contextlib import contextmanager

from app.config import Settings


class SourceUnavailableError(RuntimeError):
    pass


class SourceOperationError(RuntimeError):
    pass


class OracleDatabase:
    def __init__(self, settings: Settings):
        self.settings = settings

    @contextmanager
    def connection(self):
        if not self.settings.oracle_password:
            raise SourceUnavailableError("CDC_APP_PASSWORD is not configured.")

        try:
            import oracledb
        except ImportError as exc:
            raise SourceUnavailableError("python-oracledb is not installed.") from exc

        try:
            conn = oracledb.connect(
                user=self.settings.oracle_user,
                password=self.settings.oracle_password,
                dsn=self.settings.oracle_dsn,
            )
        except oracledb.Error as exc:
            raise SourceUnavailableError("Oracle source system is unavailable.") from exc

        try:
            yield conn
        except oracledb.Error as exc:
            try:
                conn.rollback()
            except oracledb.Error:
                pass
            raise SourceOperationError("Oracle source operation failed.") from exc
        finally:
            conn.close()
