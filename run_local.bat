@echo off
setlocal

cd /d "%~dp0"

REM Установите зависимости один раз:
REM pip install -r requirements.txt

REM Настройте пароль админа:
REM set PORTFOLIO_ADMIN_USERNAME=admin
REM set PORTFOLIO_ADMIN_PASSWORD=ВАШ_ПАРОЛЬ

REM Если хотите задать сразу watermark (текст водяного знака):
REM set PORTFOLIO_WATERMARK_TEXT=JaneM

uvicorn src.main:auth_app --reload --host 127.0.0.1 --port 8000
