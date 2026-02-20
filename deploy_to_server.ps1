# A股投研平台 - Windows部署脚本

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "A股投研平台 - Windows部署" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查管理员权限
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "❌ 请使用管理员权限运行此脚本" -ForegroundColor Red
    exit 1
}

# 配置变量
$DOMAIN = "localhost"  # 修改为你的域名或IP
$PROJECT_DIR = "C:\a-share-research"
$GIT_REPO = "https://github.com/你的用户名/a-share-research-platform.git"

Write-Host "1. 安装系统依赖..." -ForegroundColor Yellow
winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
winget install OpenJS.NodeJS --accept-package-agreements --accept-source-agreements

Write-Host ""
Write-Host "2. 创建项目目录..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path $PROJECT_DIR -Force | Out-Null
Set-Location $PROJECT_DIR

Write-Host ""
Write-Host "3. 克隆代码..." -ForegroundColor Yellow
git clone $GIT_REPO .

Write-Host ""
Write-Host "4. 创建虚拟环境..." -ForegroundColor Yellow
python -m venv venv
.\venv\Scripts\activate

Write-Host ""
Write-Host "5. 安装Python依赖..." -ForegroundColor Yellow
python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Host ""
Write-Host "6. 配置环境变量..." -ForegroundColor Yellow
@"
TUSHARE_TOKEN=你的Tushare_Token
ZHIPU_API_KEY=你的智谱AI_API_Key
PLATFORM_NAME=A股投研平台
DEFAULT_STOCK=000001.SZ
ANALYSIS_DAYS=90
"@ | Out-File -FilePath .env -Encoding UTF8

Write-Host ""
Write-Host "7. 配置Streamlit..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path .streamlit -Force | Out-Null
@"
[server]
headless = true
port = 8501
address = "0.0.0.0"

[browser]
gatherUsageStats = false

[theme]
primaryColor = "#1f77b4"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
font = "sans serif"
"@ | Out-File -FilePath .streamlit/config.toml -Encoding UTF8

Write-Host ""
Write-Host "8. 启动平台..." -ForegroundColor Yellow
Write-Host "访问地址: http://localhost:8501" -ForegroundColor Green
Write-Host ""
Write-Host "按 Ctrl+C 停止平台" -ForegroundColor Yellow

.\venv\Scripts\streamlit run app.py

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ 部署完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
