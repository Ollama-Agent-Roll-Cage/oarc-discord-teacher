@echo off
echo Starting UI with diagnostics...

rem Run the diagnostic tool first
python tools\ui_diagnostic.py

echo.
echo If there were any issues with the diagnostic, please review ui_diagnostic.log
echo.
echo Now starting the UI...
echo.

rem Run the UI
python start_ui.py

echo.
echo If the UI did not appear, check ui_startup.log for errors
