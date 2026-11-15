from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from trellis import auth
from trellis.api.deps import current_user, get_conn

router = APIRouter(prefix="/api")


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordIn(BaseModel):
    current: str
    new: str


def user_out(u) -> dict:
    return {"user_id": u["user_id"], "username": u["username"], "display_name": u["display_name"] or u["username"],
            "is_admin": bool(u["is_admin"])}


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.post("/login")
def login(body: LoginIn, request: Request, conn=Depends(get_conn)):
    ip = _ip(request)
    throttle = request.app.state.throttle
    if throttle.blocked(ip):
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    u = auth.check_login(conn, body.username, body.password)
    if u is None:
        throttle.fail(ip)
        raise HTTPException(401, "Wrong username or password.")
    throttle.clear(ip)
    request.session.clear()
    request.session["uid"] = u["user_id"]
    return user_out(u)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current_user)):
    return user_out(user)


@router.post("/me/password")
def change_password(body: PasswordIn, user=Depends(current_user), conn=Depends(get_conn)):
    if not auth.verify_password(body.current, user["pw_hash"]):
        raise HTTPException(400, "Current password is wrong.")
    try:
        auth.set_password(conn, user["user_id"], body.new)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
