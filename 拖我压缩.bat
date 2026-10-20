@echo off
chcp 65001 >nul
REM 一键压缩: 把图片/文件夹直接拖到本文件上即可
REM 也可双击本 bat 压缩脚本所在目录的全部图片

cd /d "%~dp0"

if "%~1"=="" (
    echo [用法] 把图片或文件夹拖到本文件上, 或双击压缩当前目录全部图
    echo.
    python compress_images.py .
    pause
) else (
    python compress_images.py %*
    pause
)
