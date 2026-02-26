from itsdangerous import URLSafeTimedSerializer
from fastapi import Request, Response
from app.config import SECRET_KEY, APP_PIN

serializer = URLSafeTimedSerializer(SECRET_KEY)

SESSION_COOKIE = "dtdc_session"
SESSION_MAX_AGE = 60 * 60 * 8  # 8 hours


def verify_pin(input_pin: str):
    return input_pin == APP_PIN


def create_session(response: Response):
    token = serializer.dumps({"authenticated": True})
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True
    )


def is_authenticated(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE)
        return data.get("authenticated") is True
    except Exception:
        return False