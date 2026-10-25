@echo off
setlocal
rem Start ExamJudge using Gemini. Credentials are requested interactively and are not written to a file.
if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment...
  py -m venv .venv
  if errorlevel 1 goto error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto error
set /p GEMINI_API_KEY=Paste your Gemini API key (input may be visible; avoid shared computers): 
if "%GEMINI_API_KEY%"=="" (
  echo No API key supplied. Exiting.
  goto end
)
set /p APP_PASSWORD=Choose a local app password: 
if "%APP_PASSWORD%"=="" (
  echo An app password is required when Gemini is configured.
  goto end
)
set /p GEMINI_MODEL=Gemini model name [default gemini-2.5-flash]: 
if "%GEMINI_MODEL%"=="" set GEMINI_MODEL=gemini-2.5-flash
echo Starting ExamJudge. Choose Google Gemini in the sidebar.
python -m streamlit run app.py
goto end
:error
echo Setup failed. Confirm Python 3.10+ is installed and internet access is available for dependency installation.
pause
:end
set GEMINI_API_KEY=
set APP_PASSWORD=
set GEMINI_MODEL=
endlocal
