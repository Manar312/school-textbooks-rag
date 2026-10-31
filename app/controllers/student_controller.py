import uuid

from app.schemas import StudentCreate, StudentPatch, UserOut
from app.services.student_service import StudentService


class StudentController:
    def __init__(self, students: StudentService):
        self.students = students

    async def create(self, body: StudentCreate) -> UserOut:
        return UserOut.model_validate(await self.students.create(body))

    async def list_students(self, grade: str | None) -> list[UserOut]:
        return [UserOut.model_validate(u) for u in await self.students.list_students(grade)]

    async def patch(self, uid: uuid.UUID, body: StudentPatch) -> UserOut:
        return UserOut.model_validate(await self.students.patch(uid, body))

    async def usage(self, uid: uuid.UUID) -> dict:
        return await self.students.usage(uid)
