@echo off
rem Double-click to install or update Strydr. Downloads the current installer and runs it.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072; iex (irm 'https://raw.githubusercontent.com/OuttaLineNomad/strydr/main/install/windows/install.ps1')"
if errorlevel 1 pause
