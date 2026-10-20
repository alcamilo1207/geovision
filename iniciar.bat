@echo off
cd /d "%~dp0"
echo Iniciando GeoVision U044...
python -m streamlit run web_app.py --server.port 8501
pause
