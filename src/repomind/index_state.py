import sqlite3
from pathlib import Path


class IndexState:

    def __init__(self, database_path: str = ".repomind/index.db"):
        self.database_path = Path(database_path)

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.connection = sqlite3.connect(
            self.database_path
        )

        self._create_table()

    def _create_table(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS indexed_files (
                repository_path TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                PRIMARY KEY (repository_path, file_path)
            )
            """
        )

        self.connection.commit()

    def get_file_hash(
        self,
        repository_path: str,
        file_path: str,
    ) -> str | None:

        cursor = self.connection.execute(
            """
            SELECT file_hash
            FROM indexed_files
            WHERE repository_path = ?
              AND file_path = ?
            """,
            (repository_path, file_path),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return row[0]

    def save_file_hash(
        self,
        repository_path: str,
        file_path: str,
        file_hash: str,
    ) -> None:

        self.connection.execute(
            """
            INSERT INTO indexed_files (
                repository_path,
                file_path,
                file_hash
            )
            VALUES (?, ?, ?)
            ON CONFLICT(repository_path, file_path)
            DO UPDATE SET file_hash = excluded.file_hash
            """,
            (
                repository_path,
                file_path,
                file_hash,
            ),
        )

        self.connection.commit()

    def get_indexed_files(
        self,
        repository_path: str,
    ) -> list[str]:

        cursor = self.connection.execute(
            """
            SELECT file_path
            FROM indexed_files
            WHERE repository_path = ?
            """,
            (repository_path,),
        )

        return [
            row[0]
            for row in cursor.fetchall()
        ]

    def delete_file_record(
        self,
        repository_path: str,
        file_path: str,
    ) -> None:

        self.connection.execute(
            """
            DELETE FROM indexed_files
            WHERE repository_path = ?
              AND file_path = ?
            """,
            (
                repository_path,
                file_path,
            ),
        )

        self.connection.commit()

    def close(self) -> None:
        self.connection.close()