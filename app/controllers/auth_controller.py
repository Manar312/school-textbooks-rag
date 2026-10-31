from app.schemas import LoginIn, TokenOut
from app.services.auth_service import AuthService


class AuthController:
    def __init__(self, auth: AuthService):
        self.auth = auth

    async def login(self, body: LoginIn, ip: str) -> TokenOut:
        return TokenOut(access_token=await self.auth.login(body.email, body.password, ip))
