"""文件树扫描（L1 硬排除）与前端表面定位（L2）的公共工具。"""
import json
from pathlib import Path

# 前端可见文件扩展名（L0-L2 的粗粒度白名单；L3 会进一步按 UI 标记评分）
FRONTEND_EXTENSIONS = {
    ".tsx", ".jsx", ".vue", ".svelte", ".html", ".css", ".scss", ".less",
    ".ts", ".js", ".mjs", ".cjs",
}

# 硬排除目录（L1）：构建产物、依赖、缓存、覆盖率等
HARD_EXCLUDED_DIRS = {
    "node_modules", ".next", ".turbo", "dist", "build", "out", "coverage",
    "storybook-static", "vendor", "tmp", "cache", "test-results",
}

TEST_PATTERNS = (".test.", ".spec.", "__tests__", ".stories.")
BACKEND_EXTENSIONS = {".rb", ".py", ".php", ".go", ".java", ".rs", ".ex", ".exs", ".prisma"}
GENERATED_PATTERNS = (".min.", ".map", ".d.ts", ".snap")


def load_json(path: Path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def iter_repo_files(root: Path):
    """DFS 遍历仓库文件，跳过硬排除目录、隐藏目录与符号链接。"""
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir(), key=lambda e: e.name)
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_symlink():
                    continue
                if e.is_dir():
                    if e.name in HARD_EXCLUDED_DIRS or e.name.startswith("."):
                        continue
                    stack.append(e)
                else:
                    yield e
            except OSError:
                continue


def find_package_jsons(root: Path, max_depth: int = 3) -> list:
    """在限定深度内发现所有 package.json（跳过依赖/构建目录）。"""
    results = []
    root = root.resolve()

    def walk(d: Path, depth: int):
        if depth > max_depth:
            return
        try:
            entries = list(d.iterdir())
        except OSError:
            return
        for e in entries:
            try:
                if e.is_symlink():
                    continue
                if e.is_dir():
                    if e.name in HARD_EXCLUDED_DIRS or e.name.startswith("."):
                        continue
                    walk(e, depth + 1)
                elif e.name == "package.json":
                    results.append(e)
            except OSError:
                continue

    walk(root, 0)
    return results


def surface_dirs(root: Path, framework: str, manifest_dir: Path | None) -> list:
    """返回已存在的、repo 相对的前端表面目录（L2）。

    manifest_dir 既可能是目录，也可能是 package.json 文件（此时取父目录）。
    """
    base = Path(".")
    if manifest_dir is not None:
        d = manifest_dir
        if not d.is_dir():
            d = d.parent  # package.json 文件 → 其所在应用目录
        try:
            base = d.relative_to(root)
        except ValueError:
            base = Path(".")

    if framework == "Next.js":
        subs = ("app", "pages", "src", "components")
    elif framework in ("Vue", "Nuxt"):
        # app/javascript 为 Rails+Vue 约定；其余为通用前端目录约定
        subs = ("app/javascript", "src", "frontend", "components", "pages")
    elif framework == "React":
        subs = ("src", "app", "components", "pages")
    elif framework == "Svelte":
        subs = ("src", "routes", "lib")
    else:
        subs = ("src", "app", "frontend", "web")

    # 统一以 manifest 所在应用目录为基准，适配 monorepo 嵌套（非根级）前端
    candidates = [(base / s) if base != Path(".") else Path(s) for s in subs]
    return [c for c in candidates if (root / c).is_dir()]
