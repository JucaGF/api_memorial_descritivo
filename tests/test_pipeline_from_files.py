from __future__ import annotations

import io
from pathlib import Path
from tempfile import mkdtemp
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import UploadFile

from app.services.file_ingestion import FileIngestionResult, IngestedFileMetadata
from app.services.memorial_validator import MemorialValidationError, ValidationIssue
from app.services.pipeline import PipelineResult
from app.services.pipeline_from_files import (
    generate_memorial_eletrico_v1_from_ingested_files,
    generate_memorial_eletrico_v1_from_uploaded_files,
)
from app.services.project_extractor import ProjectExtractionResult


ROOT = Path(__file__).resolve().parent.parent


def build_ingested_file() -> IngestedFileMetadata:
    return IngestedFileMetadata(
        original_filename="projeto.docx",
        stored_filename="01_projeto.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        extension=".docx",
        size_bytes=1024,
        saved_path="/tmp/01_projeto.docx",
    )


def build_extraction_result() -> ProjectExtractionResult:
    return ProjectExtractionResult(
        raw_text="CONSTRUTORA: Exemplo Engenharia",
        source_files=[],
        signals={"total_files": 1},
    )


class PipelineFromFilesTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.pipeline_from_files.render_memorial_eletrico_v1")
    @patch("app.services.pipeline_from_files.validate_memorial_eletrico_v1_context")
    @patch("app.services.pipeline_from_files.build_memorial_eletrico_v1_context")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_context")
    @patch("app.services.pipeline_from_files.extract_project_files")
    async def test_generate_memorial_eletrico_v1_from_ingested_files_runs_full_flow(
        self,
        extract_mock,
        map_mock,
        build_mock,
        validate_mock,
        render_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        partial_context = {"obra": {"construtora": "Exemplo Engenharia"}}
        final_context = {"obra": {"construtora": "Exemplo Engenharia"}, "energia": {}}
        output_path = ROOT / "tests" / "output" / "pipeline_from_files.docx"

        extract_mock.return_value = extraction_result
        map_mock.return_value = partial_context
        build_mock.return_value = final_context
        validate_mock.return_value = []
        render_mock.return_value = output_path

        result = generate_memorial_eletrico_v1_from_ingested_files(
            ingested_files,
            output_path,
        )

        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.output_path, output_path)
        self.assertEqual(result.context, final_context)
        extract_mock.assert_called_once_with(ingested_files)
        map_mock.assert_called_once_with(extraction_result)
        build_mock.assert_called_once_with(partial_context)
        validate_mock.assert_called_once_with(final_context)
        render_mock.assert_called_once_with(final_context, output_path)

    @patch("app.services.pipeline_from_files.render_memorial_eletrico_v1")
    @patch("app.services.pipeline_from_files.validate_memorial_eletrico_v1_context")
    @patch("app.services.pipeline_from_files.build_memorial_eletrico_v1_context")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_context")
    @patch("app.services.pipeline_from_files.extract_project_files")
    async def test_generate_memorial_eletrico_v1_from_ingested_files_does_not_render_on_validation_error(
        self,
        extract_mock,
        map_mock,
        build_mock,
        validate_mock,
        render_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        partial_context = {"obra": {"construtora": "Exemplo Engenharia"}}
        incomplete_context = {"obra": {"construtora": "Exemplo Engenharia"}}
        output_path = ROOT / "tests" / "output" / "pipeline_from_files_invalid.docx"

        extract_mock.return_value = extraction_result
        map_mock.return_value = partial_context
        build_mock.return_value = incomplete_context
        validate_mock.side_effect = MemorialValidationError(
            [
                ValidationIssue(
                    path="$",
                    message="'documento' is a required property",
                    validator="required",
                )
            ]
        )

        with self.assertRaises(MemorialValidationError):
            generate_memorial_eletrico_v1_from_ingested_files(
                ingested_files,
                output_path,
            )

        render_mock.assert_not_called()

    @patch("app.services.pipeline_from_files.generate_memorial_eletrico_v1_from_ingested_files")
    @patch("app.services.pipeline_from_files.ingest_uploaded_files", new_callable=AsyncMock)
    async def test_generate_memorial_eletrico_v1_from_uploaded_files_reuses_ingestion_and_pipeline(
        self,
        ingest_mock,
        pipeline_mock,
    ) -> None:
        upload_files = [
            UploadFile(
                filename="projeto.docx",
                file=io.BytesIO(b"PK\x03\x04docx"),
                headers={
                    "content-type": (
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                },
            )
        ]
        ingested_files = [build_ingested_file()]
        ingestion_result = FileIngestionResult(
            request_dir="/tmp/eletrico_v1_upload_123",
            files=ingested_files,
        )
        output_path = ROOT / "tests" / "output" / "pipeline_from_uploaded_files.docx"
        expected_result = PipelineResult(context={"obra": {}}, output_path=output_path)

        ingest_mock.return_value = ingestion_result
        pipeline_mock.return_value = expected_result

        result = await generate_memorial_eletrico_v1_from_uploaded_files(
            upload_files,
            output_path,
        )

        self.assertEqual(result, expected_result)
        ingest_mock.assert_awaited_once_with(upload_files)
        pipeline_mock.assert_called_once_with(ingested_files, output_path)

    @patch("app.services.pipeline_from_files.cleanup_ingestion_result")
    @patch("app.services.pipeline_from_files.generate_memorial_eletrico_v1_from_ingested_files")
    @patch("app.services.pipeline_from_files.ingest_uploaded_files", new_callable=AsyncMock)
    async def test_generate_memorial_eletrico_v1_from_uploaded_files_cleans_temp_dir_even_on_error(
        self,
        ingest_mock,
        pipeline_mock,
        cleanup_mock,
    ) -> None:
        upload_files = [
            UploadFile(
                filename="projeto.docx",
                file=io.BytesIO(b"PK\x03\x04docx"),
                headers={
                    "content-type": (
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                },
            )
        ]
        ingestion_result = FileIngestionResult(
            request_dir=mkdtemp(prefix="eletrico_v1_upload_test_"),
            files=[build_ingested_file()],
        )
        output_path = ROOT / "tests" / "output" / "pipeline_from_uploaded_files_invalid.docx"
        ingest_mock.return_value = ingestion_result
        pipeline_mock.side_effect = MemorialValidationError(
            [
                ValidationIssue(
                    path="$",
                    message="'documento' is a required property",
                    validator="required",
                )
            ]
        )

        with self.assertRaises(MemorialValidationError):
            await generate_memorial_eletrico_v1_from_uploaded_files(upload_files, output_path)

        cleanup_mock.assert_called_once_with(ingestion_result)


if __name__ == "__main__":
    unittest.main()
