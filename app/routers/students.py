import uuid

from fastapi import APIRouter, Depends

from app.controllers import StudentController
from app.routers.deps import require_admin, student_controller
from app.schemas import StudentCreate, StudentPatch, UserOut

router = APIRouter(prefix="/admin/students", tags=["admin: students"], dependencies=[Depends(require_admin)])


@router.post("", response_model=UserOut, status_code=201)
async def create_student(body: StudentCreate, ctrl: StudentController = Depends(student_controller)):
    return await ctrl.create(body)


@router.get("", response_model=list[UserOut])
async def list_students(grade: str | None = None, ctrl: StudentController = Depends(student_controller)):
    return await ctrl.list_students(grade)


@router.patch("/{uid}", response_model=UserOut)
async def patch_student(uid: uuid.UUID, body: StudentPatch, ctrl: StudentController = Depends(student_controller)):
    return await ctrl.patch(uid, body)


@router.get("/{uid}/usage")
async def student_usage(uid: uuid.UUID, ctrl: StudentController = Depends(student_controller)):
    return await ctrl.usage(uid)
