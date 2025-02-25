#!/usr/bin/env python3

import os
import sys
import subprocess
import venv
from pathlib import Path

def run_command(cmd, cwd=None):
    """运行命令并打印输出"""
    print(f"执行: {' '.join(cmd)}")
    process = subprocess.run(cmd, cwd=cwd, check=True)
    return process.returncode == 0

def setup_bob_env():
    # 创建工作目录
    work_dir = Path("bob-workspace")
    venv_dir = work_dir / "venv"
    
    print("=== 创建Bob开发环境 ===")
    
    # 1. 创建目录
    print("\n1. 创建工作目录...")
    work_dir.mkdir(exist_ok=True)
    
    # 2. 创建虚拟环境
    print("\n2. 创建Python虚拟环境...")
    venv.create(venv_dir, with_pip=True)
    
    # 获取Python解释器路径
    if sys.platform == "win32":
        python = venv_dir / "Scripts" / "python.exe"
        pip = venv_dir / "Scripts" / "pip.exe"
        bob_cmd = venv_dir / "Scripts" / "bob.exe"
    else:
        python = venv_dir / "bin" / "python"
        pip = venv_dir / "bin" / "pip"
        bob_cmd = venv_dir / "bin" / "bob"
    
    # 3. 升级pip
    print("\n3. 升级pip...")
    run_command([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    
    # 4. 安装依赖
    print("\n4. 安装必要的依赖...")
    dependencies = [
        "sphinx",
        "sphinx-rtd-theme",
        "docutils",
        "wheel",
        "setuptools>=65.0.0"
    ]
    run_command([str(pip), "install"] + dependencies)
    
    # 5. 安装Bob
    print("\n5. 安装Bob构建工具...")
    run_command([str(pip), "install", "BobBuildTool"])
    
    # 6. 验证安装
    print("\n6. 验证Bob安装...")
    if bob_cmd.exists():
        run_command([str(bob_cmd), "--version"])
    else:
        print("警告: Bob命令未找到。请尝试重新激活虚拟环境后使用 'bob --version' 验证安装。")
    
    # 7. 创建激活脚本
    if sys.platform == "win32":
        activate_script = """@echo off
call "{venv_dir}\\Scripts\\activate.bat"
""".format(venv_dir=venv_dir)
        activate_file = work_dir / "activate.bat"
    else:
        activate_script = """#!/bin/bash
source "{venv_dir}/bin/activate"
""".format(venv_dir=venv_dir)
        activate_file = work_dir / "activate.sh"
    
    with open(activate_file, "w") as f:
        f.write(activate_script)
    
    if sys.platform != "win32":
        os.chmod(activate_file, 0o755)
    
    # 8. 创建示例配置
    config_dir = work_dir / "config"
    config_dir.mkdir(exist_ok=True)
    
    with open(config_dir / "default.yaml", "w") as f:
        f.write("""
# Bob默认配置
policies:
    - dev
    - release

environment:
    PYTHONPATH: "${BOB_ROOT}/lib"
""")
    
    print(f"""
=== Bob环境设置完成! ===

工作目录: {work_dir.absolute()}

使用方法:
1. 激活虚拟环境:
   {'call activate.bat' if sys.platform == "win32" else 'source activate.sh'}

2. 验证Bob:
   bob --version

3. 创建新项目:
   bob init my-project

4. 构建项目:
   cd my-project
   bob build

配置文件位置:
{config_dir.absolute()}

注意:
- 每次使用Bob前需要先激活虚拟环境
- 可以修改 config/default.yaml 来自定义默认配置
""")

if __name__ == "__main__":
    try:
        setup_bob_env()
    except subprocess.CalledProcessError as e:
        print(f"\n错误: 命令执行失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)