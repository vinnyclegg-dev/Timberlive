@echo off
rem Starts the TimberLive OBS overlay server (http://127.0.0.1:8096/) in the background.
start "" "%~dp0..\runtime\pythonw.exe" "%~dp0server.py"
