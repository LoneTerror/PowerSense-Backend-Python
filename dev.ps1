# dev.ps1
Write-Host "Booting PowerSense Dev Environment..." -ForegroundColor Cyan

# Execute the automation script
python automated_run.py

# Check the exit code returned by the Python script
if ($LASTEXITCODE -eq 42) {
    if (Test-Path ".\venv\Scripts\Activate.ps1") {
        Write-Host "Activating Virtual Environment..." -ForegroundColor Green
        & ".\venv\Scripts\Activate.ps1"
    } else {
        Write-Host "Venv not found. Please run the setup (Option 6) first." -ForegroundColor Yellow
    }
} elseif ($LASTEXITCODE -ne 0) {
    # Only pause the terminal if it crashed with a real error
    Write-Host "Script exited with an error code: $LASTEXITCODE" -ForegroundColor Red
    Read-Host -Prompt "Press Enter to exit"
}