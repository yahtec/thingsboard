@echo off
REM Accepts the SSH host fingerprint by piping "y" through cmd.exe (which does it
REM more reliably than PowerShell's native pipe). plink stores the fingerprint
REM in HKCU\Software\SimonTatham\PuTTY\SshHostKeys, after which all subsequent
REM batch-mode calls succeed without prompting.
echo y | "C:\Program Files\PuTTY\plink.exe" -agent %1@%2 "echo HOSTKEY_ACCEPTED"
exit /B %ERRORLEVEL%
