# OpenBB + Tushare A股分析系统
# PowerShell 版本

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "OpenBB + Tushare A股分析系统" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[1/3] 检查 Python..." -ForegroundColor Yellow
    Write-Host "Python 版本: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[错误] 未找到 Python，请先安装 Python 3.9-3.12" -ForegroundColor Red
    exit 1
}

# 检查依赖
Write-Host "[2/3] 检查依赖..." -ForegroundColor Yellow
try {
    python -c "import openbb; import tushare"
    Write-Host "依赖已安装" -ForegroundColor Green
} catch {
    Write-Host "[警告] 依赖未安装，正在安装..." -ForegroundColor Yellow
    pip install "openbb[all]" tushare
}

# 检查 Token
Write-Host "[3/3] 检查 Tushare Token..." -ForegroundColor Yellow
try {
    $token = $env:TUSHARE_TOKEN
    if ($token -and $token -ne 'YOUR_TUSHARE_TOKEN_HERE') {
        Write-Host "Token: 已设置" -ForegroundColor Green
    } else {
        Write-Host "[错误] 未设置 TUSHARE_TOKEN 环境变量" -ForegroundColor Red
        Write-Host "请访问 https://tushare.pro/ 注册并获取 Token" -ForegroundColor Yellow
        Write-Host "设置方法:" -ForegroundColor Yellow
        Write-Host "  $env:TUSHARE_TOKEN='你的token'" -ForegroundColor Gray
        exit 1
    }
} catch {
    Write-Host "[错误] 无法读取环境变量" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "运行分析..." -ForegroundColor Yellow
Write-Host ""

# 运行
python example.py

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "分析完成！" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
