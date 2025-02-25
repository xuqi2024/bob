#!/usr/bin/env python3

import os
import sys
from pathlib import Path

def create_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)

def create_example_project():
    # 项目根目录
    project_root = Path("bob-example")
    
    # 创建基础目录结构
    for d in ["recipes", "classes", "layers", "src"]:
        (project_root / d).mkdir(parents=True, exist_ok=True)

    # 1. 创建配置类
    create_file(project_root / "classes/toolchain.yaml", """
classes:
    gcc-toolchain:
        environment:
            CC: "gcc"
            CXX: "g++"
            CFLAGS: "-Wall -Wextra"
    
    debug-build:
        environment:
            CFLAGS: "-g -O0"
            
    release-build:
        environment:
            CFLAGS: "-O2"
""")

    # 2. 创建基础库菜谱
    create_file(project_root / "recipes/base-lib.yaml", """
root: True

# 包的基本信息
name: base-lib
version: "1.0.0"

# 构建策略
checkoutScript: |
    cp -r ${BOB_INPUT_DIR}/src/* .

buildScript: |
    mkdir -p build
    ${CC} ${CFLAGS} -c lib.c -o build/lib.o
    ar rcs build/libbase.a build/lib.o

packageScript: |
    mkdir -p ${PACKAGE_DIR}/lib
    mkdir -p ${PACKAGE_DIR}/include
    cp build/libbase.a ${PACKAGE_DIR}/lib/
    cp lib.h ${PACKAGE_DIR}/include/
""")

    # 3. 创建应用菜谱
    create_file(project_root / "recipes/app.yaml", """
name: app
version: "1.0.0"

depends:
    - name: base-lib
      use: [result]

inherit: [gcc-toolchain]

checkoutScript: |
    cp -r ${BOB_INPUT_DIR}/src/* .

multiPackage:
    debug:
        inherit: [debug-build]
        
    release:
        inherit: [release-build]

buildScript: |
    mkdir -p build
    ${CC} ${CFLAGS} -I${base_lib_root}/include main.c \
        -L${base_lib_root}/lib -lbase -o build/app

packageScript: |
    mkdir -p ${PACKAGE_DIR}/bin
    cp build/app ${PACKAGE_DIR}/bin/
""")

    # 4. 创建源代码
    create_file(project_root / "src/lib.h", """
#ifndef LIB_H
#define LIB_H

int add(int a, int b);

#endif
""")

    create_file(project_root / "src/lib.c", """
#include "lib.h"

int add(int a, int b) {
    return a + b;
}
""")

    create_file(project_root / "src/main.c", """
#include <stdio.h>
#include <lib.h>

int main() {
    printf("Result: %d\\n", add(40, 2));
    return 0;
}
""")

    # 5. 创建配置文件
    create_file(project_root / "config.yaml", """
# Bob项目配置
bobMinimumVersion: "0.16"

# 策略配置
policies:
    managedLayers: False  # 不使用托管层
    cleanCheckout: False  # 允许增量检出
    buildPolicy: "always" # 总是构建
    packagePolicy: "always" # 总是打包
    defaultPolicy: "dev"  # 默认开发策略

# 插件配置
plugins:
    - plugins.build_time.BuildTimePlugin

# 全局环境变量
environment:
    PYTHONPATH: "${BOB_ROOT}/lib"
""")

    # 6. 创建插件
    create_file(project_root / "plugins/build_time.py", """
import time

class BuildTimePlugin:
    def __init__(self, **settings):
        self.start_times = {}
    
    def defineHooks(self, hooks):
        hooks.buildStepStart.append(self.onStart)
        hooks.buildStepFinished.append(self.onFinish)
    
    def onStart(self, step):
        name = step.getPackage().getName()
        self.start_times[name] = time.time()
    
    def onFinish(self, step, rc):
        name = step.getPackage().getName()
        duration = time.time() - self.start_times.get(name, 0)
        print(f"构建 {name} 耗时: {duration:.2f}秒")
""")

    # 创建插件的__init__.py文件
    create_file(project_root / "plugins/__init__.py", "")

    # 7. 创建使用说明
    create_file(project_root / "README.md", """
# Bob示例项目

## 项目结构
- classes/: 构建配置类
- recipes/: 构建菜谱
- src/: 源代码
- plugins/: 插件

## 验证命令

1. 构建调试版本:
```bash
bob build app-debug
```

2. 构建发布版本:
```bash
bob build app-release
```

3. 开发模式:
```bash
bob dev app-debug
```

4. 查看依赖图:
```bash
bob graph app-debug
```

5. 清理构建:
```bash
bob clean
```
""")

    print(f"""
示例项目已创建在 {project_root} 目录下！

使用方法:
1. cd {project_root}
2. bob build app-debug   # 构建调试版本
3. bob build app-release # 构建发布版本
4. bob dev app-debug     # 开发模式

项目结构:
{project_root}
├── classes/          # 构建配置类
├── recipes/          # 构建菜谱
├── src/             # 源代码
└── plugins/         # 插件

更多信息请查看 README.md
""")

if __name__ == "__main__":
    create_example_project()