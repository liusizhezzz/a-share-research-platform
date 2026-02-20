# A股投研平台 - PowerShell一键部署脚本
# 自动连接阿里云服务器并部署

$ServerIP = "39.97.33.153"
$ServerUser = "root"
$ServerPass = "@20080415Ab"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "A股投研平台 - 一键部署" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 步骤1: 连接到服务器检查状态
Write-Host "[1/5] 连接到服务器检查状态..." -ForegroundColor Yellow
$sshCommand = @"
ssh -o StrictHostKeyChecking=no $ServerUser@$ServerIP `
    'uptime && echo "---" && netstat -tuln | grep -E ":(3000|8501|80|443)"'
"@

try {
    Invoke-Expression $sshCommand
    Write-Host "✅ 服务器连接成功" -ForegroundColor Green
} catch {
    Write-Host "❌ 服务器连接失败: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""

# 步骤2: 停止旧服务
Write-Host "[2/5] 检查并停止旧服务..." -ForegroundColor Yellow
$stopCommand = @"
ssh -o StrictHostKeyChecking=no $ServerUser@$ServerIP `
    'pkill -f "node.*3000" 2>/dev/null; pkill -f "streamlit" 2>/dev/null; systemctl stop nginx 2>/dev/null; echo "旧服务已停止"'
"@

try {
    Invoke-Expression $stopCommand
    Write-Host "✅ 旧服务已停止" -ForegroundColor Green
} catch {
    Write-Host "⚠️  停止旧服务时出现警告: $_" -ForegroundColor Yellow
}

Write-Host ""

# 步骤3: 安装依赖
Write-Host "[3/5] 安装系统依赖..." -ForegroundColor Yellow
$installCommand = @"
ssh -o StrictHostKeyChecking=no $ServerUser@$ServerIP `
    'apt update && apt install -y python3.9 python3.9-venv python3-pip nginx git curl 2>&1 | tail -20'
"@

try {
    Invoke-Expression $installCommand
    Write-Host "✅ 依赖安装完成" -ForegroundColor Green
} catch {
    Write-Host "❌ 依赖安装失败: $_" -ForegroundColor Red
}

Write-Host ""

# 步骤4: 创建项目目录并克隆代码
Write-Host "[4/5] 创建项目并克隆代码..." -ForegroundColor Yellow
$cloneCommand = @"
ssh -o StrictHostKeyChecking=no $ServerUser@$ServerIP `
    'mkdir -p $PROJECT_DIR && cd $PROJECT_DIR && git clone $GIT_REPO . 2>&1 | tail -10'
"@

try {
    Invoke-Expression $cloneCommand
    Write-Host "✅ 代码克隆完成" -ForegroundColor Green
} catch {
    Write-Host "❌ 代码克隆失败: $_" -ForegroundColor Red
}

Write-Host ""

# 步骤5: 配置并启动服务
Write-Host "[5/5] 配置并启动服务..." -ForegroundColor Yellow
$deployCommand = @"
ssh -o StrictHostKeyChecking=no $ServerUser@$ServerIP `
    'cd $PROJECT_DIR && python3.9 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && mkdir -p .streamlit && cat > .streamlit/config.toml << EOF
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
EOF
systemctl daemon-reload && systemctl enable a-share-platform && systemctl start a-share-platform && echo "✅ 服务启动成功"'
"@

try {
    Invoke-Expression $deployCommand
    Write-Host "✅ 服务启动成功" -ForegroundColor Green
} catch {
    Write-Host "❌ 服务启动失败: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ 部署完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "访问地址: http://$ServerIP:8501" -ForegroundColor Green
Write-Host "服务状态: systemctl status a-share-platform" -ForegroundColor Yellow
Write-Host "查看日志: journalctl -u a-share-platform -f" -ForegroundColor Yellow
Write-Host ""
