"""PyInstaller 单文件 exe 入口。

保持与 `python -m spyglass` 完全一致的行为。
"""

from spyglass.cli import main

if __name__ == "__main__":
    main()
