@echo off
setlocal
rem Start ExamJudge with the offline keyword baseline (no Gemini API calls).
set GEMINI_API_KEY=
set APP_PASSWORD=
set GEMINI_MODEL=
if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment...
  py -m venv .venv
  if errorlevel 1 goto error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto error
echo Starting ExamJudge in offline baseline mode. Select Offline baseline in the sidebar.
python -m streamlit run app.py
goto end
:error
echo Setup failed. Confirm Python 3.10+ is installed and internet access is available for dependency installation.
pause
:end
endlocal
