from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeSerializer, BadSignature
from dotenv import load_dotenv
import hashlib
import hmac
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import os


BASE_DIR = Path(__file__).resolve().parent.parent

# Загружаем .env ДО чтения любых переменных окружения ниже.
load_dotenv(BASE_DIR / ".env")

auth_app = FastAPI()

STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOADS_DIR = BASE_DIR / "uploads"
PROTECTED_DIR = BASE_DIR / "protected"
META_FILE = BASE_DIR / "works_meta.json"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
PROTECTED_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

auth_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# CORS (не обязателен для локального использования, но не мешает)
auth_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Простая схема проверки пароля для локального админ-доступа.
# Без bcrypt, чтобы не зависеть от backend passlib.

def verify_admin_password(password: str) -> bool:
    # Поддерживаем два режима:
    # 1) PORTFOLIO_ADMIN_PASSWORD (plaintext) — сравнение напрямую
    # 2) PORTFOLIO_ADMIN_PASSWORD_HASH — compare по sha256
    stored_plain = os.getenv("PORTFOLIO_ADMIN_PASSWORD")
    if stored_plain is not None and stored_plain != "":
        return hmac.compare_digest(password, stored_plain)

    stored_hash = os.getenv("PORTFOLIO_ADMIN_PASSWORD_HASH")
    if stored_hash:
        digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(digest, stored_hash)

    return False

SECRET_KEY = os.getenv("PORTFOLIO_SECRET_KEY", "change-me")
COOKIE_NAME = os.getenv("PORTFOLIO_COOKIE_NAME", "admin_session")

# Простой админ-аккаунт.
# При первом запуске создайте ADMIN_PASSWORD в .env или установите переменные окружения.
ADMIN_USERNAME = os.getenv("PORTFOLIO_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("PORTFOLIO_ADMIN_PASSWORD_HASH")

serializer = URLSafeSerializer(SECRET_KEY, salt="admin")


# Проверка пароля делается в verify_admin_password.
# Поэтому инициализация/хеширование при старте не требуется.


def create_admin_cookie(username: str) -> str:
    return serializer.dumps({"u": username})


def read_admin_cookie(cookie: str | None) -> str | None:
    if not cookie:
        return None
    try:
        data = serializer.loads(cookie)
        return data.get("u")
    except BadSignature:
        return None


async def require_admin(request: Request) -> str:
    cookie = request.cookies.get(COOKIE_NAME)
    u = read_admin_cookie(cookie)
    if u != ADMIN_USERNAME:
        raise PermissionError("unauthorized")
    return u


def _load_font(size: int):
    # Ищем шрифт по типичным путям Windows/Linux, иначе берём встроенный.
    for candidate in [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        try:
            if os.path.exists(candidate):
                return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def watermark_image(in_path: Path, out_path: Path, text: str) -> None:
    img = Image.open(in_path).convert("RGBA")
    w, h = img.size

    font_size = max(16, int(w * 0.042))
    font = _load_font(font_size)

    # Рисуем текст на отдельном прозрачном слое.
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    bbox = d.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    fill = (255, 255, 255, 54)
    stroke_fill = (0, 0, 0, 82)
    stroke_width = max(1, int(font_size * 0.025))

    # Сохраняем покрытие всей работы, но раздвигаем повторения.
    step_x = max(int(tw * 1.8), 360)
    step_y = max(int(th * 2.2), 280)
    for yy in range(-h, h * 2, step_y):
        for xx in range(-w, w * 2, step_x):
            d.text((xx, yy), text, font=font, fill=fill, stroke_fill=stroke_fill, stroke_width=stroke_width)

    rotated = layer.rotate(-25, resample=Image.Resampling.BICUBIC, center=(w / 2, h / 2))
    result = Image.alpha_composite(img, rotated)

    ext = out_path.suffix.lower()

    # Сохраняем корректно под формат исходного расширения.
    if ext in {".jpg", ".jpeg"}:
        result.convert("RGB").save(out_path, format="JPEG", quality=92, optimize=True)
    elif ext == ".png":
        result.save(out_path, format="PNG")
    else:
        result.convert("RGB").save(out_path, format="JPEG", quality=92, optimize=True)


@auth_app.get("/protected/{name}")
async def protected_image(name: str):
    # Защита от path traversal: только имя файла в текущей папке.
    safe_name = Path(name).name
    if safe_name != name:
        raise HTTPException(status_code=404)

    path = PROTECTED_DIR / safe_name
    if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=404)

    resp = FileResponse(path)
    # Запрещаем скачивание/кэширование и открытие картинки в новой вкладке как файла.
    resp.headers["Content-Disposition"] = "inline"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


def load_works_meta() -> dict:
    """Метаданные работ: {имя_файла: {title, tech, category}}."""
    if META_FILE.is_file():
        try:
            return json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_works_meta(meta: dict) -> None:
    META_FILE.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_protected_images() -> list[dict]:
    """Список работ: имя файла + метаданные (название, техника, категория)."""
    meta = load_works_meta()
    files = []
    for p in PROTECTED_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            m = meta.get(p.name, {})
            files.append({
                "name": p.name,
                "title": m.get("title", ""),
                "tech": m.get("tech", ""),
                "category": m.get("category", ""),
            })
    files.sort(key=lambda x: x["name"], reverse=True)
    return files


@auth_app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    works = list_protected_images()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "works": works,
            "site_title": os.getenv("PORTFOLIO_SITE_TITLE", "Artist Portfolio"),
            "site_desc": os.getenv(
                "PORTFOLIO_SITE_DESC",
                "Портфолио цифровых рисунков. Добавляйте новые работы через админку.",
            ),
        },
    )


@auth_app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@auth_app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    # Пароль админа проверяется функцией verify_admin_password.
    # Если ни PORTFOLIO_ADMIN_PASSWORD, ни PORTFOLIO_ADMIN_PASSWORD_HASH не заданы — вход невозможен.
    if not (os.getenv("PORTFOLIO_ADMIN_PASSWORD") or os.getenv("PORTFOLIO_ADMIN_PASSWORD_HASH")):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Сначала задайте PORTFOLIO_ADMIN_PASSWORD (или PORTFOLIO_ADMIN_PASSWORD_HASH)"},
            status_code=400,
        )

    if username != ADMIN_USERNAME:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин"},
            status_code=400,
        )

    if not verify_admin_password(password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный пароль"},
            status_code=400,
        )

    cookie = create_admin_cookie(username)
    resp = RedirectResponse(url="/admin", status_code=302)
    resp.set_cookie(COOKIE_NAME, cookie, httponly=True)
    return resp


@auth_app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    try:
        await require_admin(request)
    except Exception:
        return RedirectResponse(url="/login", status_code=302)

    works = list_protected_images()
    return templates.TemplateResponse("admin.html", {"request": request, "works": works})


@auth_app.post("/admin/upload")
async def upload_work(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    tech: str = Form(""),
    category: str = Form(""),
):
    try:
        await require_admin(request)
    except Exception:
        return RedirectResponse(url="/login", status_code=302)

    if not file.filename:
        return RedirectResponse(url="/admin", status_code=302)

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        return RedirectResponse(url="/admin", status_code=302)

    raw_path = UPLOADS_DIR / file.filename
    out_path = PROTECTED_DIR / file.filename

    # Сохраняем оригинал (можно потом запретить, но сейчас удобно)
    content = await file.read()
    raw_path.write_bytes(content)

    watermark_text = os.getenv("PORTFOLIO_WATERMARK_TEXT", "JaneM")
    watermark_image(raw_path, out_path, watermark_text)

    # Сохраняем подписи работы
    meta = load_works_meta()
    meta[file.filename] = {
        "title": title.strip(),
        "tech": tech.strip(),
        "category": category.strip(),
    }
    save_works_meta(meta)

    return RedirectResponse(url="/admin", status_code=302)


@auth_app.post("/admin/meta")
async def update_work_meta(
    request: Request,
    name: str = Form(...),
    title: str = Form(""),
    tech: str = Form(""),
    category: str = Form(""),
):
    try:
        await require_admin(request)
    except Exception:
        return RedirectResponse(url="/login", status_code=302)

    # Только имя файла, без путей.
    safe_name = Path(name).name
    meta = load_works_meta()
    meta[safe_name] = {
        "title": title.strip(),
        "tech": tech.strip(),
        "category": category.strip(),
    }
    save_works_meta(meta)

    return RedirectResponse(url="/admin", status_code=302)


@auth_app.post("/admin/delete")
async def delete_work(
    request: Request,
    name: str = Form(...),
):
    try:
        await require_admin(request)
    except Exception:
        return RedirectResponse(url="/login", status_code=302)

    safe_name = Path(name).name
    if safe_name != name or Path(safe_name).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=404)

    protected_path = PROTECTED_DIR / safe_name
    upload_path = UPLOADS_DIR / safe_name
    if not protected_path.is_file():
        raise HTTPException(status_code=404)

    protected_path.unlink()
    if upload_path.is_file():
        upload_path.unlink()

    meta = load_works_meta()
    meta.pop(safe_name, None)
    save_works_meta(meta)

    return RedirectResponse(url="/admin", status_code=303)
