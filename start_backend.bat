@echo off
set PYTHONPATH=D:\????\xuanqiong-wenshu\backend
cd /d D:\????\xuanqiong-wenshu\backend
echo Starting xuanqiong-wenshu backend on port 8013...
python -m uvicorn app.main:app --host 127.0.0.1 --port 8013 --timeout-keep-alive 600 --log-level info > backend.log 2>&1
