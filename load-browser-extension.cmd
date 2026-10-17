@echo off
chcp 65001 >nul
echo.
echo   AI Career OS ^| BOSS 岗位导入扩展 - 安装引导
echo   ============================================================
echo.
echo   下面会同时打开两个窗口：Edge 扩展管理页 + 扩展文件夹。
echo.
echo   请按这三步操作：
echo     1. 在「扩展」页面左下角打开【开发人员模式】
echo     2. 点【加载解压缩的扩展】，选择已打开的文件夹 apps\extension
echo     3. 打开 AI Career OS 设置页 ^-^> 生成配对码 ^-^> 粘贴到扩展弹窗完成配对
echo.
echo   配对完成后：在 BOSS 职位详情页点扩展图标 ^-^> 读取当前岗位 ^-^> 发送到 AI Career OS
echo   （扩展只读取页面可见内容，不读 Cookie / 密码 / 聊天记录）
echo.
echo ------------------------------------------------------------
start "" msedge.exe "edge://extensions"
start "" explorer.exe "%~dp0apps\extension"
echo.
echo   已打开上述两个窗口。完成安装后关掉本窗口即可。
echo.
pause
