"""
FastAPI Main Application Module (fixed for pytest)

Changes made:
- Removed top-level `uvicorn` import (only import when running as __main__).
  This prevents pytest hangs on Windows when uvicorn/uvloop are imported.
- Switched absolute "from app.*" imports to relative imports so the module
  behaves correctly when imported as a package.
- Added a PYTEST_RUNNING env switch to disable the lifespan handler during tests.
  This prevents the tests from triggering DB table creation / startup events.
- Kept static/templates mounting unchanged (they expect "static" and "templates"
  directories at project root).
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import List

from fastapi import Body, FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

# Use relative imports to avoid import path issues when running tests or as a package
from .auth.dependencies import get_current_active_user
from .models.calculation import Calculation
from .models.user import User
from .schemas.calculation import CalculationBase, CalculationResponse, CalculationUpdate
from .schemas.token import TokenResponse
from .schemas.user import UserCreate, UserResponse, UserLogin
from .database import Base, get_db, engine

# -------------------------------------------------------------------------
# Test-mode detection: disable lifespan/startup side-effects when running pytest
# -------------------------------------------------------------------------
# In pytest.ini you can set env var PYTEST_RUNNING=1 (or set it in the test runner).
PYTEST_RUNNING = os.getenv("PYTEST_RUNNING", "0") == "1"

# -------------------------------------------------------------------------
# Lifespan: create tables on startup (disabled during pytest)
# -------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager that creates DB tables at startup.
    Disabled while running tests (PYTEST_RUNNING=1).
    """
    # Only create tables when not running under pytest to avoid side-effects
    if not PYTEST_RUNNING:
        # It's useful to keep minimal logging for local runs
        print("Creating tables...")
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully!")
    yield
    # (Optional) Add shutdown/cleanup logic here if needed


# Initialize FastAPI app; disable lifespan when running tests
app = FastAPI(
    title="Calculations API",
    description="API for managing calculations",
    version="1.0.0",
    lifespan=None if PYTEST_RUNNING else lifespan,
)

# -------------------------------------------------------------------------
# Static files and templates (DISABLED during pytest to prevent hangs)
# -------------------------------------------------------------------------
if not PYTEST_RUNNING:
    app.mount("/static", StaticFiles(directory="static"), name="static")
    templates = Jinja2Templates(directory="templates")
else:
    templates = None


# -------------------------------------------------------------------------
# Web routes (HTML)
# -------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, tags=["web"])
def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse, tags=["web"])
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse, tags=["web"])
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse, tags=["web"])
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/dashboard/view/{calc_id}", response_class=HTMLResponse, tags=["web"])
def view_calculation_page(request: Request, calc_id: str):
    return templates.TemplateResponse("view_calculation.html", {"request": request, "calc_id": calc_id})


@app.get("/dashboard/edit/{calc_id}", response_class=HTMLResponse, tags=["web"])
def edit_calculation_page(request: Request, calc_id: str):
    return templates.TemplateResponse("edit_calculation.html", {"request": request, "calc_id": calc_id})


# -------------------------------------------------------------------------
# Health endpoint
# -------------------------------------------------------------------------
@app.get("/health", tags=["health"])
def read_health():
    return {"status": "ok"}


# -------------------------------------------------------------------------
# Auth: register / login
# -------------------------------------------------------------------------
@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
)
def register(user_create: UserCreate, db: Session = Depends(get_db)):
    user_data = user_create.dict(exclude={"confirm_password"})
    try:
        user = User.register(db, user_data)
        db.commit()
        db.refresh(user)
        return user
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login_json(user_login: UserLogin, db: Session = Depends(get_db)):
    auth_result = User.authenticate(db, user_login.username, user_login.password)
    if auth_result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = auth_result["user"]
    db.commit()

    expires_at = auth_result.get("expires_at")
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    return TokenResponse(
        access_token=auth_result["access_token"],
        refresh_token=auth_result["refresh_token"],
        token_type="bearer",
        expires_at=expires_at,
        user_id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
    )


@app.post("/auth/token", tags=["auth"])
def login_form(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    auth_result = User.authenticate(db, form_data.username, form_data.password)
    if auth_result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"access_token": auth_result["access_token"], "token_type": "bearer"}


# -------------------------------------------------------------------------
# Calculations endpoints (BREAD)
# -------------------------------------------------------------------------
@app.post(
    "/calculations",
    response_model=CalculationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["calculations"],
)
def create_calculation(
    calculation_data: CalculationBase,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        new_calculation = Calculation.create(
            calculation_type=calculation_data.type,
            user_id=current_user.id,
            inputs=calculation_data.inputs,
        )
        new_calculation.result = new_calculation.get_result()

        db.add(new_calculation)
        db.commit()
        db.refresh(new_calculation)
        return new_calculation

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/calculations", response_model=List[CalculationResponse], tags=["calculations"])
def list_calculations(current_user=Depends(get_current_active_user), db: Session = Depends(get_db)):
    calculations = db.query(Calculation).filter(Calculation.user_id == current_user.id).all()
    return calculations


@app.get("/calculations/{calc_id}", response_model=CalculationResponse, tags=["calculations"])
def get_calculation(calc_id: str, current_user=Depends(get_current_active_user), db: Session = Depends(get_db)):
    try:
        calc_uuid = UUID(calc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid calculation id format.")

    calculation = (
        db.query(Calculation).filter(Calculation.id == calc_uuid, Calculation.user_id == current_user.id).first()
    )
    if not calculation:
        raise HTTPException(status_code=404, detail="Calculation not found.")
    return calculation


@app.put("/calculations/{calc_id}", response_model=CalculationResponse, tags=["calculations"])
def update_calculation(
    calc_id: str,
    calculation_update: CalculationUpdate,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        calc_uuid = UUID(calc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid calculation id format.")

    calculation = (
        db.query(Calculation).filter(Calculation.id == calc_uuid, Calculation.user_id == current_user.id).first()
    )
    if not calculation:
        raise HTTPException(status_code=404, detail="Calculation not found.")

    if calculation_update.inputs is not None:
        calculation.inputs = calculation_update.inputs
        calculation.result = calculation.get_result()

    calculation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(calculation)
    return calculation


@app.delete("/calculations/{calc_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["calculations"])
def delete_calculation(calc_id: str, current_user=Depends(get_current_active_user), db: Session = Depends(get_db)):
    try:
        calc_uuid = UUID(calc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid calculation id format.")

    calculation = (
        db.query(Calculation).filter(Calculation.id == calc_uuid, Calculation.user_id == current_user.id).first()
    )
    if not calculation:
        raise HTTPException(status_code=404, detail="Calculation not found.")

    db.delete(calculation)
    db.commit()
    return None


# -------------------------------------------------------------------------
# Server entrypoint (only when running the module directly)
# -------------------------------------------------------------------------
if __name__ == "__main__":
    # Import uvicorn here to avoid importing it during pytest runs / module import.
    import uvicorn

    # When run as a module: python -m app.main
    # Use "app.main:app" so uvicorn can locate the ASGI app inside the package.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, log_level="info")
