@echo off
chcp 65001 > nul
echo ========================================
echo A股投研平台 - 启动
echo ========================================
echo.

REM 检查配置文件
if not exist ".env" (
    echo [错误] 未找到 .env 配置文件
    echo 请先运行 install.bat 安装并配置
    pause
    exit /b 1
)

REM 检查虚拟环境（可选）
if not exist "venv" (
    echo [提示] 未检测到虚拟环境
    echo 建议: 使用虚拟环境以避免依赖冲突
    echo 运行: python -m venv venv
    echo 激活: venv\Scripts\activate
    echo 重新安装: pip install -r requirements.txt
)

echo 启动平台中...
echo.
streamlit run app.py

pause
