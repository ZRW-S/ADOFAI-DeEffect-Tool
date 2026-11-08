# -*- coding: utf-8 -*-
"""把当前仓库目录上传到 GitHub（使用 GitHub REST API，无需安装 git）。

用法：
  python upload_to_github.py --token <PAT> [--repo ADOFAI-DeEffect-Tool]
                             [--description "..."] [--private]
                             [--assets <发布文件目录>]

token 也可以通过环境变量 GITHUB_TOKEN 提供（推荐）。
需要 classic token 且勾选 repo 权限；若只上传到已有仓库，可用 contents 权限的 fine-grained token。
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
DEFAULT_REPO = "ADOFAI-DeEffect-Tool"
DEFAULT_DESC = "ADOFAI 去特效工具：一键清理《冰与火之舞》谱面视觉特效，保留玩法判定。"
VERSION = "v2.0.0"
RELEASE_BODY = """ADOFAI 去特效工具 v2.0.0

- 一键去除谱面装饰 / 滤镜 / 粒子等视觉特效，保留玩法判定
- 支持游戏 3.4 新增的 15 个事件
- 过滤器配置可视化编辑（图标化三栏拖拽）
- 轨道消失动画统一设置：无 / 收缩 / 暗淡
- 处理完成可直接打开输出目录
- 安装版 / 绿色版双版本

详见仓库 README 与 CHANGELOG。"""

IGNORE_DIRS = {".git", "__pycache__", "dist", "build", "release_assets", "release"}
IGNORE_FILES = {"ui_state.json"}


def api(method, url, token, data=None, raw=None, content_type=None):
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "adoifai-deeffect-uploader",
    }
    body = None
    if raw is not None:
        body = raw
        headers["Content-Type"] = content_type or "application/octet-stream"
    elif data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API {method} {url} -> {exc.code}: {detail[:800]}") from None


def collect_files(root):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            if name in IGNORE_FILES:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            files.append((full, rel))
    files.sort(key=lambda item: item[1])
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--description", default=DEFAULT_DESC)
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--assets", default="", help="发布文件目录（安装包/绿色版）")
    parser.add_argument("--no-release", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    token = args.token.strip()
    if not token:
        print("错误：需要 GitHub token（--token 或环境变量 GITHUB_TOKEN）")
        return 2

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = collect_files(root)
    print(f"待上传文件：{len(files)} 个")
    for full, rel in files[:5]:
        print("  ", rel)
    if args.dry_run:
        return 0

    status, body = api("GET", f"{API}/user", token)
    login = json.loads(body)["login"]
    print("GitHub 用户：", login)

    repo_url = f"{API}/repos/{login}/{args.repo}"
    try:
        api("GET", repo_url, token)
        print("仓库已存在，更新 main 分支")
        exists = True
    except RuntimeError as exc:
        if "404" not in str(exc):
            raise
        print("创建仓库：", args.repo)
        api("POST", f"{API}/user/repos", token, {
            "name": args.repo,
            "description": args.description,
            "private": args.private,
            "has_issues": True,
            "has_projects": False,
            "has_wiki": False,
            "auto_init": False,
        })
        exists = False

    # 1) 创建 blobs
    tree = []
    for index, (full, rel) in enumerate(files, 1):
        with open(full, "rb") as handle:
            content = base64.b64encode(handle.read()).decode("ascii")
        _, response = api("POST", f"{API}/repos/{login}/{args.repo}/git/blobs", token,
                         {"content": content, "encoding": "base64"})
        sha = json.loads(response)["sha"]
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": sha})
        if index % 20 == 0 or index == len(files):
            print(f"  已上传 {index}/{len(files)}")

    # 2) 生成 tree / commit
    base_tree = None
    parents = []
    ref_name = "refs/heads/main"
    try:
        _, ref_body = api("GET", f"{API}/repos/{login}/{args.repo}/git/ref/heads/main", token)
        commit_sha = json.loads(ref_body)["object"]["sha"]
        parents = [commit_sha]
        _, commit_body = api("GET", f"{API}/repos/{login}/{args.repo}/git/commits/{commit_sha}", token)
        base_tree = json.loads(commit_body)["tree"]["sha"]
    except RuntimeError as exc:
        if "404" not in str(exc) and "409" not in str(exc):
            raise
        print("仓库为空，创建首个提交")

    tree_payload = {"tree": tree}
    if base_tree:
        tree_payload["base_tree"] = base_tree
    try:
        _, tree_body = api("POST", f"{API}/repos/{login}/{args.repo}/git/trees", token, tree_payload)
    except RuntimeError as exc:
        # 空仓库需要至少一个 parent 时也允许；否则报错
        raise

    tree_sha = json.loads(tree_body)["sha"]
    commit_message = f"Upload {VERSION}"
    _, new_commit_body = api("POST", f"{API}/repos/{login}/{args.repo}/git/commits", token, {
        "message": commit_message,
        "tree": tree_sha,
        "parents": parents,
    })
    new_commit = json.loads(new_commit_body)["sha"]

    if parents:
        api("PATCH", f"{API}/repos/{login}/{args.repo}/git/refs/heads/main", token,
            {"sha": new_commit, "force": True})
    else:
        try:
            api("POST", f"{API}/repos/{login}/{args.repo}/git/refs", token,
                {"ref": ref_name, "sha": new_commit})
        except RuntimeError:
            api("PATCH", f"{API}/repos/{login}/{args.repo}/git/refs/heads/main", token,
                {"sha": new_commit, "force": True})

    repo_html = f"https://github.com/{login}/{args.repo}"
    print("仓库已更新：", repo_html)

    # 3) 发布 Release 并上传发布包
    if args.assets and not args.no_release:
        release = None
        try:
            _, rel_body = api("GET", f"{API}/repos/{login}/{args.repo}/releases/tags/{VERSION}", token)
            release = json.loads(rel_body)
            print("Release 已存在：", release.get("html_url"))
        except RuntimeError as exc:
            if "404" not in str(exc):
                raise
            _, rel_body = api("POST", f"{API}/repos/{login}/{args.repo}/releases", token, {
                "tag_name": VERSION,
                "target_commitish": "main",
                "name": f"ADOFAI 去特效工具 {VERSION}",
                "body": RELEASE_BODY,
                "draft": False,
                "prerelease": False,
            })
            release = json.loads(rel_body)
            print("Release 已创建：", release.get("html_url"))

        upload_url = release["upload_url"].split("{")[0]
        for name in sorted(os.listdir(args.assets)):
            path = os.path.join(args.assets, name)
            if not os.path.isfile(path):
                continue
            print("上传发布文件：", name)
            url = upload_url + "?" + urllib.parse.urlencode({"name": name})
            content_type = "application/octet-stream"
            if name.lower().endswith(".zip"):
                content_type = "application/zip"
            with open(path, "rb") as handle:
                status, _ = api("POST", url, token, raw=handle.read(), content_type=content_type)
            print("  完成", status)
        print("Release 页面：", release.get("html_url"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
