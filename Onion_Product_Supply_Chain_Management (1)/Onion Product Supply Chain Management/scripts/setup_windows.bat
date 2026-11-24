@echo off
cd /d "%~dp0.."
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts\prepare_market_data.py
python scripts\initialize_database.py
echo.
echo Onion Product Supply Chain Management setup complete.
echo Run: streamlit run app.py
pause
