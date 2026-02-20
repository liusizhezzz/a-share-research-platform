@echo off
chcp 65001 > nul
echo ========================================
echo A股投研平台 - 安装脚本
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.9-3.12
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] 检查依赖...
python -c "import streamlit" 2>nul
if %errorlevel% neq 0 (
    echo [2/4] 安装核心依赖...
    pip install -r requirements.txt
) else (
    echo [✓] 依赖已安装
)

echo.
echo [3/4] 验证配置文件...
if not exist ".env" (
    echo [错误] 未找到 .env 配置文件
    echo 请检查是否正确设置了 Tushare Token 和智谱AI API Key
    pause
    exit /b 1
)

echo [✓] 配置文件存在

echo.
echo [4/4] 安装完成！
echo.
echo ========================================
echo 启动平台
echo ========================================
echo.
echo 运行以下命令启动平台：
echo   streamlit run app.py
echo.
echo 或者直接双击: run.bat
echo.
pause
