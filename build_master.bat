@echo off
echo Building Master Desktop App...
pyinstaller --noconfirm --onedir --windowed --name "Stargate_Master" run_master.py
echo Build complete.
exit
