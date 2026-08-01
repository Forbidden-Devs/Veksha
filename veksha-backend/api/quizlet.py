"""
api/quizlet.py — Quizlet export/import integration.

  POST /api/quizlet/export         — export un-exported words to CSV
  POST /api/quizlet/export-all     — export all words to CSV
  GET  /api/quizlet/export-status  — get export status
  POST /api/quizlet/import         — import words from CSV file
"""
from __future__ import annotations

import csv
import io
import logging
import time

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import db
from auth import CurrentUser
from learning_core_v2.acquisition import (
    LexicalItem,
    ReviewSchedule,
    VocabularyEncounter,
    lexical_item_id,
)
from storage import get_storage

log = logging.getLogger(__name__)

router = APIRouter()


class ExportStatusResponse(BaseModel):
    total_words: int
    exported_words: int
    unexported_words: int
    last_export_at: float | None = None


class ImportResultResponse(BaseModel):
    imported_count: int
    skipped_count: int
    errors: list[str]


@router.post("/api/quizlet/export")
async def api_quizlet_export(username: CurrentUser) -> StreamingResponse:
    """Export un-exported words to CSV."""
    storage = get_storage(username)

    # Get words not yet exported
    unexported_words = [
        item
        for item in storage.lexical_items
        if item.language == storage.settings.target_lang
        and item.status in {"learning", "known"}
        and not db.quizlet_is_exported(username, item.item_id)
    ]

    if not unexported_words:
        return StreamingResponse(
            iter([b"Word,Translation,Context\n"]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=quizlet_export_empty.csv"},
        )

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Word", "Translation", "Context"])

    for item in unexported_words:
        writer.writerow([
            item.term,
            item.translation,
            item.latest_context,
        ])

    # Mark as exported
    db.quizlet_export_mark(username, [item.item_id for item in unexported_words])
    log.info("[quizlet] user %r exported %d words", username, len(unexported_words))

    # Convert StringIO to bytes iterator
    csv_content = output.getvalue().encode("utf-8")

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=quizlet_export.csv"},
    )


@router.post("/api/quizlet/export-all")
async def api_quizlet_export_all(username: CurrentUser) -> StreamingResponse:
    """Export all words to CSV."""
    storage = get_storage(username)

    # Get all words of target language
    words = [
        item
        for item in storage.lexical_items
        if item.language == storage.settings.target_lang
        and item.status in {"learning", "known"}
    ]

    if not words:
        return StreamingResponse(
            iter([b"Word,Translation,Context\n"]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=quizlet_export_empty.csv"},
        )

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Word", "Translation", "Context"])

    for item in words:
        writer.writerow([
            item.term,
            item.translation,
            item.latest_context,
        ])

    # Mark all as exported
    db.quizlet_export_mark(username, [item.item_id for item in words])
    log.info("[quizlet] user %r exported all %d words", username, len(words))

    csv_content = output.getvalue().encode("utf-8")

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=quizlet_export_all.csv"},
    )


@router.get("/api/quizlet/export-status", response_model=ExportStatusResponse)
async def api_quizlet_export_status(username: CurrentUser) -> ExportStatusResponse:
    """Get export status (counts)."""
    storage = get_storage(username)

    # Count words by language
    target_words = [
        item
        for item in storage.lexical_items
        if item.language == storage.settings.target_lang
        and item.status in {"learning", "known"}
    ]
    total = len(target_words)

    # Count exported words
    exported = sum(
        1
        for item in target_words
        if db.quizlet_is_exported(username, item.item_id)
    )

    return ExportStatusResponse(
        total_words=total,
        exported_words=exported,
        unexported_words=max(0, total - exported),
    )


@router.post("/api/quizlet/import", response_model=ImportResultResponse)
async def api_quizlet_import(file: UploadFile = File(...), username: CurrentUser = None) -> ImportResultResponse:
    """Import words from CSV file (Word, Translation, Context columns)."""
    if not file.filename or not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    storage = get_storage(username)
    imported_count = 0
    skipped_count = 0
    errors: list[str] = []

    try:
        content = await file.read()
        text = content.decode('utf-8')

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise HTTPException(status_code=400, detail="Empty CSV file")

        # Detect column names (case-insensitive)
        fieldnames = {f.lower(): f for f in reader.fieldnames}
        word_col = fieldnames.get('word') or fieldnames.get('term') or fieldnames.get('front')
        trans_col = fieldnames.get('translation') or fieldnames.get('definition') or fieldnames.get('back')
        context_col = fieldnames.get('context')

        if not word_col or not trans_col:
            raise HTTPException(
                status_code=400,
                detail="CSV must have 'Word' and 'Translation' columns (or 'Term'/'Definition', 'Front'/'Back')"
            )

        imported: list[LexicalItem] = []
        existing_ids = {item.item_id for item in storage.lexical_items}

        for row_num, row in enumerate(reader, start=2):  # start=2 because header is row 1
            try:
                word = row.get(word_col, "").strip()
                translation = row.get(trans_col, "").strip()
                context = row.get(context_col, "").strip() if context_col else ""

                if not word or not translation:
                    errors.append(f"Row {row_num}: missing word or translation")
                    skipped_count += 1
                    continue

                item_id = lexical_item_id(
                    word, storage.settings.target_lang, translation
                )
                if item_id in existing_ids:
                    skipped_count += 1
                    continue

                added_at = time.time()
                imported.append(
                    LexicalItem(
                        item_id=item_id,
                        term=word,
                        language=storage.settings.target_lang,
                        translation=translation,
                        status="learning",
                        encounters=(
                            VocabularyEncounter(
                                context=context, observed_at=added_at
                            ),
                        )
                        if context
                        else (),
                        schedule=ReviewSchedule(added_at=added_at),
                    )
                )
                existing_ids.add(item_id)
                imported_count += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)[:100]}")
                skipped_count += 1

        # Apply all patches at once
        if imported:
            storage.lexical_items.extend(imported)
            storage.save()

        # Mark imported words as exported to prevent re-exporting
        if imported_count > 0:
            db.quizlet_export_mark(
                username, [item.item_id for item in imported]
            )

        log.info(
            "[quizlet] user %r imported %d words (skipped %d)",
            username, imported_count, skipped_count
        )

    except HTTPException:
        raise
    except Exception as e:
        log.exception("[quizlet] import error for user %r", username)
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)[:200]}")

    return ImportResultResponse(
        imported_count=imported_count,
        skipped_count=skipped_count,
        errors=errors[:10],  # Return first 10 errors
    )
