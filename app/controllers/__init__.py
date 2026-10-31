"""Controllers: translate validated HTTP input into service calls and shape the output.
No SQL here, no framework routing here (that's routers/), no vendor SDKs (that's providers/)."""
from app.controllers.auth_controller import AuthController
from app.controllers.book_controller import BookController
from app.controllers.chat_controller import ChatController
from app.controllers.health_controller import HealthController
from app.controllers.student_controller import StudentController

__all__ = ["AuthController", "BookController", "ChatController", "HealthController", "StudentController"]
