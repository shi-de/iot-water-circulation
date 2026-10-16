@echo off
chcp 65001
cd backend
echo =====水循环技能赛后端启动=====
python -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
