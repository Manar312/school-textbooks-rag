import uuid

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from app.controllers import BookController
from app.routers.deps import book_controller, require_admin
from app.schemas import BookOut

router = APIRouter(prefix="/admin/books", tags=["admin: books"], dependencies=[Depends(require_admin)])


@router.post("", response_model=BookOut, status_code=202)
async def upload_book(file: UploadFile = File(...), title: str = Form(..., max_length=300),
                      subject: str = Form(..., max_length=100), grade: str = Form(...), language: str = Form("ar"),
                      term: str | None = Form(None), ctrl: BookController = Depends(book_controller)):
    return await ctrl.upload(file, title, subject, grade, language, term)


@router.get("", response_model=list[BookOut])
async def list_books(grade: str | None = None, subject: str | None = None,
                     ctrl: BookController = Depends(book_controller)):
    return await ctrl.list_books(grade, subject)


@router.get("/{book_id}")
async def book_details(book_id: uuid.UUID, ctrl: BookController = Depends(book_controller)):
    return await ctrl.details(book_id)


@router.post("/{book_id}/retry", status_code=202)
async def retry_failed(book_id: uuid.UUID, ctrl: BookController = Depends(book_controller)):
    """Re-extract pending/failed pages only, then re-index."""
    return await ctrl.retry(book_id)


@router.post("/{book_id}/reindex", status_code=202)
async def reindex(book_id: uuid.UUID, ctrl: BookController = Depends(book_controller)):
    """Re-chunk + re-embed from stored page text (no VLM calls). Use after changing chunking or the embedding model."""
    return await ctrl.reindex(book_id)


@router.delete("/{book_id}", status_code=204)
async def delete_book(book_id: uuid.UUID, ctrl: BookController = Depends(book_controller)):
    await ctrl.delete(book_id)
    return Response(status_code=204)
