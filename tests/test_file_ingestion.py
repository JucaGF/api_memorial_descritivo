from __future__ import annotations

import io
from pathlib import Path
from tempfile import mkdtemp
import unittest

from fastapi import UploadFile

from app.services.file_ingestion import (
    FileIngestionError,
    FileIngestionResult,
    cleanup_ingestion_result,
    ingest_uploaded_files,
)


class FileIngestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_ingest_uploaded_files_saves_pdf_and_docx(self) -> None:
        files = [
            UploadFile(
                filename="Projeto Eletrico.pdf",
                file=io.BytesIO(b"%PDF-1.4 exemplo"),
                headers={"content-type": "application/pdf"},
            ),
            UploadFile(
                filename="Memorial Base.docx",
                file=io.BytesIO(b"PK\x03\x04docx"),
                headers={
                    "content-type": (
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                },
            ),
        ]

        result = await ingest_uploaded_files(files)

        self.assertEqual(len(result.files), 2)
        self.assertTrue(Path(result.request_dir).exists())
        self.assertEqual(result.files[0].extension, ".pdf")
        self.assertEqual(result.files[1].extension, ".docx")
        self.assertTrue(Path(result.files[0].saved_path).exists())
        self.assertTrue(Path(result.files[1].saved_path).exists())
        cleanup_ingestion_result(result)

    async def test_ingest_uploaded_files_rejects_invalid_extension(self) -> None:
        files = [
            UploadFile(
                filename="planilha.xlsx",
                file=io.BytesIO(b"dados"),
                headers={
                    "content-type": (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                },
            )
        ]

        with self.assertRaises(FileIngestionError) as error_info:
            await ingest_uploaded_files(files)

        self.assertIn("Extensao nao suportada", str(error_info.exception))

    async def test_ingest_uploaded_files_rejects_empty_list(self) -> None:
        with self.assertRaises(FileIngestionError) as error_info:
            await ingest_uploaded_files([])

        self.assertEqual(
            str(error_info.exception),
            "Envie ao menos um arquivo PDF ou DOCX.",
        )

    def test_cleanup_ingestion_result_removes_request_dir(self) -> None:
        request_dir = Path(mkdtemp(prefix="eletrico_v1_cleanup_test_"))
        saved_path = request_dir / "arquivo.pdf"
        saved_path.write_bytes(b"%PDF-1.4")
        result = FileIngestionResult(
            request_dir=str(request_dir),
            files=[],
        )

        cleanup_ingestion_result(result)

        self.assertFalse(request_dir.exists())


if __name__ == "__main__":
    unittest.main()
