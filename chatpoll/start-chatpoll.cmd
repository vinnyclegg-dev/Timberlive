@echo off
rem Starts the TimberLive viewer poll counter in the background (reads YouTube chat, writes vote counts only).
start "" "%~dp0..\runtime\pythonw.exe" "%~dp0poll_service.py"
