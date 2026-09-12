# PAMA API - Start and Stop Guide

## Starting the API Server

### Method 1: Using run.py (Recommended)
```powershell
cd E:\pama_api
python run.py
```

### Method 2: Using uvicorn directly
```powershell
cd E:\pama_api
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Method 3: Background process (Windows PowerShell)
```powershell
cd E:\pama_api
Start-Process python -ArgumentList "run.py" -WindowStyle Hidden
```

## Stopping the API Server

### Method 1: If running in foreground (Ctrl+C)
- Press `Ctrl + C` in the terminal where the API is running

### Method 2: Find and kill process by port
```powershell
# Find process using port 8000
netstat -ano | findstr :8000

# Kill the process (replace PID with the actual Process ID from above)
taskkill /PID <PID> /F
```

### Method 3: Kill all Python processes (Use with caution!)
```powershell
# This will kill ALL Python processes
taskkill /IM python.exe /F
```

### Method 4: Kill by process name (More specific)
```powershell
# Kill uvicorn processes
Get-Process | Where-Object {$_.ProcessName -eq "python"} | Where-Object {$_.CommandLine -like "*uvicorn*"} | Stop-Process -Force
```

## Quick Start/Stop Scripts

### Start API (start_api.ps1)
```powershell
cd E:\pama_api
python run.py
```

### Stop API (stop_api.ps1)
```powershell
$port = 8000
$processes = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
if ($processes) {
    $processes | ForEach-Object { Stop-Process -Id $_ -Force }
    Write-Host "API stopped successfully"
} else {
    Write-Host "No process found on port $port"
}
```

## Check if API is Running

```powershell
# Check if port 8000 is in use
netstat -ano | findstr :8000

# Test API health endpoint
Invoke-WebRequest -Uri http://localhost:8000/health -UseBasicParsing
```

## Common Issues

### Port Already in Use
If port 8000 is already in use:
1. Find the process: `netstat -ano | findstr :8000`
2. Kill it: `taskkill /PID <PID> /F`
3. Or change port in `.env` file: `PORT=8001`

### API Won't Start
- Check if Python is installed: `python --version`
- Check if dependencies are installed: `pip install -r requirements.txt`
- Check `.env` file exists and has correct database credentials

