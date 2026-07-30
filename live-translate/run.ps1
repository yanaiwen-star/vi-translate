# 启动 vi-translate 商用后端（本地模式：SQLite + fakeredis，无需 Docker/Postgres/Redis）
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venv = Join-Path $root ".venv"
if (-not (Test-Path $venv)) {
    Write-Host "未找到 .venv，请先用 Python 3.13 创建虚拟环境并安装依赖" -ForegroundColor Red
    exit 1
}

$activate = Join-Path $venv "Scripts/Activate.ps1"
. $activate

# 端口可在环境变量或此处修改
$port = if ($env:PORT) { $env:PORT } else { "8000" }
Write-Host "启动后端于 http://127.0.0.1:$port ..." -ForegroundColor Green
uvicorn app.main:app --host 0.0.0.0 --port $port
