import ast
import base64
import os
import re
import shlex
import sys
from collections import OrderedDict
from hashlib import sha1
from heapq import heappush
from types import SimpleNamespace
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

import requests

HTTP_TIMEOUT = (10, 120)


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def validate_source_tree_path(path):
    normalized_path = os.path.normpath(path)
    if (
        "\0" in path
        or os.path.isabs(path)
        or normalized_path in ("", ".", "..")
        or any(part == ".." for part in normalized_path.split(os.sep))
    ):
        raise ValueError(f"unsafe source tree path: {path}")
    return normalized_path


def is_https_host(url, hostname):
    parsed = urlparse(url)
    if parsed.hostname is None:
        return False
    return parsed.scheme == "https" and (
        parsed.hostname == hostname or parsed.hostname.endswith(f".{hostname}")
    )


def is_googlesource_url(url):
    return is_https_host(url, "googlesource.com")


def fetch_text(url, *, decode_base64=False):
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as err:
        raise RuntimeError(f"failed to fetch {url}: {err}") from err
    if decode_base64:
        return base64.b64decode(response.text).decode("utf-8")
    return response.text


def fetch_deps(url, rev):
    # Get the DEPS file from the given URL and revision
    parsed = urlparse(url)
    if is_googlesource_url(url):
        deps_url = f"{url}/+/{rev}/DEPS?format=text"
        eprint(f"  Fetching {deps_url}")
        return fetch_text(deps_url, decode_base64=True)
    elif parsed.scheme == "https" and parsed.hostname == "github.com":
        if url.endswith(".git"):
            url = url[: -len(".git")]
        deps_url = f"{url}/raw/{rev}/DEPS"
        eprint(f"  Fetching {deps_url}")
        return fetch_text(deps_url)
    else:
        raise Exception(f"Unimplemented for URL {url}")


class Str:
    def __init__(self, s):
        self.inner = s

    def __str__(self):
        return self.inner


class SafeDepsEvaluator:
    def __init__(self):
        self.vars = {}
        self.values = {
            "vars": self.vars,
            "deps": {},
            "gclient_gn_args": [],
            "recursedeps": [],
            "use_relative_paths": False,
        }

    def var_substitute(self, var_name):
        return self.vars[var_name]

    def eval_expr(self, node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Dict):
            return {
                self.eval_expr(key): self.eval_expr(value)
                for key, value in zip(node.keys, node.values)
            }
        if isinstance(node, ast.List):
            return [self.eval_expr(item) for item in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self.eval_expr(item) for item in node.elts)
        if isinstance(node, ast.Name):
            if node.id in self.values:
                return self.values[node.id]
            raise ValueError(f"unsupported name in DEPS: {node.id}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            args = [self.eval_expr(arg) for arg in node.args]
            if node.func.id == "Var":
                if len(args) != 1:
                    raise ValueError("Var() expects one argument")
                return self.var_substitute(args[0])
            if node.func.id == "Str":
                if len(args) != 1:
                    raise ValueError("Str() expects one argument")
                return Str(args[0])
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self.eval_expr(node.left) + self.eval_expr(node.right)
        raise ValueError(f"unsupported expression in DEPS: {ast.dump(node)}")

    def parse(self, path):
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        for statement in tree.body:
            if not isinstance(statement, ast.Assign):
                raise ValueError(
                    f"unsupported statement in DEPS: {ast.dump(statement)}"
                )
            value = self.eval_expr(statement.value)
            for target in statement.targets:
                if not isinstance(target, ast.Name):
                    raise ValueError(f"unsupported assignment target: {ast.dump(target)}")
                self.values[target.id] = value
                if target.id == "vars":
                    self.vars = value
                    self.values["vars"] = self.vars
        return SimpleNamespace(**self.values)


ignored_dep_prefix = [
    # MacOS specific
    "src/third_party/squirrel.mac",
    # Unnecessary parts
    "src/docs/website",
    # Test
    "src/third_party/accessibility_test_framework",
    "src/third_party/freetype-testing",
    "src/third_party/dawn/testing",
    "src/third_party/dawn/third_party/webgpu-cts",
    "src/third_party/webgpu-cts",
    # Repo become private, not sure why
    # last snapshot: https://web.archive.org/web/20250220152649/https://chromium.googlesource.com/chromium/wasm-tts-engine/
    "src/third_party/wasm_tts_engine",
]

ignored_dep_regex = [
    # Test
    ".*test\\/data.*",
    # Fuzz
    ".*[Ff]uzz.*",
    # Benchmark
    ".*bench.*",
    ".*speedometer.*",
]

ignored_gcs_dep_prefix = [
    # Host toolchains and node prebuilts are provided by package dependencies or
    # package-local setup instead of Chromium's GCS archives.
    "src/buildtools/",
    "src/third_party/llvm-build/",
    "src/third_party/node/",
    "src/third_party/rust-toolchain",
    "src/third_party/openscreen/src/buildtools/",
    "src/third_party/openscreen/src/third_party/llvm-build/",
    # Test, benchmark, coverage, and perf datasets are not needed for packaging
    # the Electron runtime.
    "src/base/tracing/test/",
    "src/content/test/",
    "src/third_party/blink/renderer/core/css/perftest_data",
    "src/third_party/instrumented_libs/",
    "src/third_party/js_code_coverage/",
    "src/third_party/opus/tests/",
    "src/third_party/subresource-filter-ruleset/data",
    "src/third_party/test_fonts/",
    "src/tools/perf/",
]


def parse_deps(path, prefix="", is_src=False, vars=None, reverse_map=None):
    """
    path: Path to the DEPS file
    prefix: Prefix to add when using recursedeps
    is_src: Whether the current DEPS file is the one from "src" repo
    vars: Override variables when generating gclient gn args file
    reverse_map: Map from url to path. Used for de-duplication
    """
    deps_module = SafeDepsEvaluator().parse(path)

    if not hasattr(deps_module, "vars"):
        deps_module.vars = {}

    for k in (
        "checkout_win",
        "checkout_mac",
        "checkout_ios",
        "checkout_chromeos",
        "checkout_fuchsia",
        "checkout_android",
        "checkout_cxx_debugging_extension_deps",
        # Skip architecture specific deps. They are prebuilt binaries and we should install them via pacman
        "checkout_x86",
        "checkout_x64",
        "checkout_arm64",
        "checkout_mips64",
        "checkout_mips",
        "checkout_ppc",
        "checkout_arm",
        "checkout_riscv64",
        "checkout_ai_evals",
    ):
        deps_module.vars[k] = False
    deps_module.vars["checkout_linux"] = True
    deps_module.vars["build_with_chromium"] = True
    deps_module.vars["non_git_source"] = True
    deps_module.vars["host_os"] = "linux"
    deps_module.vars["host_cpu"] = "x64"
    deps_module.vars["linux"] = "linux"
    deps_module.vars["mac"] = "mac"
    deps_module.vars["win"] = "win"
    use_relative_paths = (
        hasattr(deps_module, "use_relative_paths") and deps_module.use_relative_paths
    )

    def url_and_revision(raw_url):
        url = raw_url.format(**deps_module.vars)
        url, rev = url.rsplit("@", 1)
        if is_googlesource_url(url) and not url.endswith(".git"):
            # Unify url format by adding .git suffix (for de-duplication)
            url += ".git"
        return (url, rev)

    def format_path(dep_name):
        return dep_name if not use_relative_paths else f"{prefix}/{dep_name}"

    def safe_deps_path(dep_name):
        return validate_source_tree_path(format_path(dep_name))

    real_deps = OrderedDict()
    cipd_deps = {}
    gcs_deps = {}
    reverse_map = reverse_map or {}
    vars = vars or {}
    condition_vars = deps_module.vars | vars

    def eval_condition_node(node):
        if isinstance(node, ast.Expression):
            return eval_condition_node(node.body)
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for value in node.values:
                    if not eval_condition_node(value):
                        return False
                return True
            if isinstance(node.op, ast.Or):
                for value in node.values:
                    if eval_condition_node(value):
                        return True
                return False
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not eval_condition_node(node.operand)
        if isinstance(node, ast.Compare):
            left = eval_condition_node(node.left)
            for operator, comparator_node in zip(node.ops, node.comparators):
                right = eval_condition_node(comparator_node)
                if isinstance(operator, ast.Eq):
                    ok = left == right
                elif isinstance(operator, ast.NotEq):
                    ok = left != right
                elif isinstance(operator, ast.In):
                    ok = left in right
                elif isinstance(operator, ast.NotIn):
                    ok = left not in right
                else:
                    raise ValueError(
                        f"unsupported operator in DEPS condition: {ast.dump(operator)}"
                    )
                if not ok:
                    return False
                left = right
            return True
        if isinstance(node, ast.Name):
            if node.id not in condition_vars:
                raise ValueError(f"unknown symbol in DEPS condition: {node.id}")
            return condition_vars[node.id]
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return [eval_condition_node(item) for item in node.elts]
        raise ValueError(f"unsupported DEPS condition: {ast.dump(node)}")

    def condition_is_met(condition):
        return bool(eval_condition_node(ast.parse(condition, mode="eval")))

    def add_dep(dep_name, raw_url):
        path = safe_deps_path(dep_name)
        for ignored_prefix in ignored_dep_prefix:
            if path.startswith(ignored_prefix):
                eprint(f"Ignoring {path}")
                return
        for pat in ignored_dep_regex:
            if re.match(pat, path):
                eprint(f"Ignoring {path} (by regex)")
                return
        url, rev = url_and_revision(raw_url)
        real_deps[path] = (url, rev)
        # Add to reverse map for de-duplication, use a heap to make sure the shortest path is chosen
        heappush(reverse_map.setdefault(url, []), (len(path), path))

    if not hasattr(deps_module, "deps"):
        return real_deps, {}, cipd_deps, gcs_deps, reverse_map

    for dep_name, dep_value in deps_module.deps.items():
        if isinstance(dep_value, dict):
            if "dep_type" in dep_value:
                if dep_value["dep_type"] == "cipd":
                    if "condition" in dep_value and not condition_is_met(
                        dep_value["condition"]
                    ):
                        eprint(
                            f"Skipping {format_path(dep_name)} because of unmet condition {dep_value['condition']}"
                        )
                        continue
                    cipd_deps[safe_deps_path(dep_name)] = dep_value["packages"]
                elif dep_value["dep_type"] == "gcs":
                    if "condition" in dep_value and not condition_is_met(
                        dep_value["condition"]
                    ):
                        eprint(
                            f"Skipping {format_path(dep_name)} because of unmet condition {dep_value['condition']}"
                        )
                        continue
                    gcs_deps[safe_deps_path(dep_name)] = dep_value
                else:
                    raise Exception(f"Unknown DEP {dep_name} = {dep_value}")
            else:
                if "condition" in dep_value and not condition_is_met(
                    dep_value["condition"]
                ):
                    eprint(
                        f"Skipping {format_path(dep_name)} because of unmet condition {dep_value['condition']}"
                    )
                    continue
                add_dep(dep_name, dep_value["url"])
        elif isinstance(dep_value, str):
            eprint(f"Adding dep {dep_name} with {dep_value}")
            add_dep(dep_name, dep_value)
        else:
            raise Exception(f"Unknown DEP {dep_name} = {dep_value}")

    gclient_gn_args = {}
    if is_src and hasattr(deps_module, "gclient_gn_args"):
        for arg in deps_module.gclient_gn_args:
            # electron vars overwrites chromium vars
            gclient_gn_args[arg] = (deps_module.vars | vars).get(arg)

    if hasattr(deps_module, "recursedeps"):
        for dep in deps_module.recursedeps:
            dep_path = safe_deps_path(dep)
            if dep_path not in real_deps:
                eprint(f"Skipping recursive DEP {dep} as it's not found in deps dict")
                continue
            eprint(f"Fetching recursedep {dep}")
            deps_text = fetch_deps(*real_deps[dep_path])
            with NamedTemporaryFile(mode="w", delete=True) as f:
                f.write(deps_text)
                f.flush()
                dep_deps, dep_gclient_gn_args, dep_cipd_deps, dep_gcs_deps, _ = (
                    parse_deps(
                        f.name,
                        dep_path,
                        dep == "src",
                        deps_module.vars | vars,
                        reverse_map,
                    )
                )
                real_deps.update(dep_deps)
                gclient_gn_args.update(dep_gclient_gn_args)
                cipd_deps.update(dep_cipd_deps)
                gcs_deps.update(dep_gcs_deps)
    return real_deps, gclient_gn_args, cipd_deps, gcs_deps, reverse_map


repos_with_changed_url = {
    "https://chromium.googlesource.com/chromium/llvm-project/compiler-rt/lib/fuzzer.git",
    "https://chromium.googlesource.com/external/github.com/google/pthreadpool.git",
    "https://chromium.googlesource.com/external/github.com/google/perfetto.git",
}


def get_source_path(path, url, pkgname, reverse_map):
    """returns the source path and whether it's deduplicated or not"""
    deduplicated = False
    if len(reverse_map[url]) > 1:
        # Deduplicate, choose the shortest path
        shortest = reverse_map[url][0][1]
        if path != shortest:
            eprint(f"Deduplicate:  {path} -> {shortest}")
            deduplicated = True
        path = shortest
    flattened = path.replace("/", "_")
    result = re.sub("^src", "chromium-mirror", flattened)
    if url in repos_with_changed_url:
        # To make makepkg happy when using SRCDEST
        result += f"_{sha1(url.encode('utf-8')).hexdigest()[:8]}"
    return result, deduplicated


def generate_fragment(rev):
    if "." in rev:
        # Treat revisions that contain dot as tags
        return f"tag={rev}"
    else:
        return f"commit={rev}"


preferred_url_map = {
    # Replace with github mirror
    "https://chromium.googlesource.com/chromium/src.git": "https://github.com/chromium/chromium.git",
}


def get_preferred_url(url):
    preferred_url = preferred_url_map.get(url)
    return preferred_url or url


def generate_source_list(deps, indent, extra_sources, pkgname, reverse_map):
    for path, (url, rev) in deps.items():
        source_path, deduplicated = get_source_path(path, url, pkgname, reverse_map)
        if deduplicated:
            # Skip the duplicated source
            continue
        yield f"{indent}{source_path}::git+{get_preferred_url(url)}#{generate_fragment(rev)}"
    for s in extra_sources:
        yield f"{indent}{s}"


def generate_managed_scripts(deps, extra_cmds, pkgname, reverse_map):
    script = """#!/usr/bin/env bash
set -e
# Generated file. Do not modify by hand.
# Usage: script <CARCH>

fetch_git_source () {
    local name="$1"
    local url="$2"
    local rev="$3"
    local revspec="$rev"
    local remote_ref

    if [[ "$rev" == *.* ]]; then
        revspec="refs/tags/$rev"
    fi

    rm -rf "$name"
    git init --initial-branch=main "$name"
    git -C "$name" remote add origin "$url"

    if ! git -C "$name" fetch --depth 1 --no-tags origin "$revspec"; then
        remote_ref="$(git ls-remote "$url" | awk -v rev="$rev" '$1 == rev { print $2; exit }')"
        if [[ -z "$remote_ref" ]]; then
            return 1
        fi
        git -C "$name" fetch --depth 1 --no-tags origin "$remote_ref"
    fi

    git -C "$name" checkout --force --detach FETCH_HEAD
}

CARCH="$1"
case "$CARCH" in
    x86_64)
        _go_arch=amd64;;
    *)
        _go_arch="$CARCH";;
esac

"""
    for path, (url, rev) in deps.items():
        script += "fetch_git_source {} {} {}\n".format(
            shlex.quote(validate_source_tree_path(path)),
            shlex.quote(get_preferred_url(url)),
            shlex.quote(rev),
        )
    # Additional Commands
    script += """
export DEPOT_TOOLS_UPDATE=0

"""
    script += "\n".join(extra_cmds)
    filename = "prepare-electron-source-tree.sh"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(script)
    return filename


def pyobj_to_gn_arg(k, v):
    if isinstance(v, Str):
        return f'{k} = "{v.inner}"'
    elif isinstance(v, str):
        return f'{k} = "{v}"'
    elif isinstance(v, bool):
        return f"{k} = {'true' if v else 'false'}"
    else:
        raise TypeError(f"Cannot convert {k}={v} ({type(v)}) to gn arg")


def generate_gclient_args(args):
    """
    Writes gclient_args.gni
    Returns command to copy it
    """
    with open("gclient_args.gni", "w", encoding="utf-8") as f:
        f.writelines(pyobj_to_gn_arg(k, v) + "\n" for k, v in args.items())

    return "cp gclient_args.gni src/build/config/gclient_args.gni"


def cipd_path_substitute(cipd_path):
    # Assume PKGBUILD provides _go_arch variable
    return cipd_path.replace("${{platform}}", "linux-${_go_arch}").replace(
        "${{arch}}", "${_go_arch}"
    )


def generate_cipd_cmds(cipd_deps, enabled_deps):
    for dep, is_optional in enabled_deps:
        dep = validate_source_tree_path(dep)
        packages = cipd_deps.get(dep)
        if packages is None:
            if is_optional:
                continue
            else:
                raise RuntimeError(f"cipd dependency {dep} not found")
        for package in packages:
            yield "src/third_party/depot_tools/cipd install {} {} -root {}".format(
                shlex.quote(cipd_path_substitute(package["package"])),
                shlex.quote(package["version"]),
                shlex.quote(dep),
            )


def generate_gcs_cmds(gcs_deps):
    unsupported = []
    for path, package in gcs_deps.items():
        path = validate_source_tree_path(path)
        if any(path.startswith(prefix) for prefix in ignored_gcs_dep_prefix):
            eprint(f"Ignoring GCS dependency {path}")
            continue
        unsupported.append(f"{path}: {package}")

    if not unsupported:
        return []

    raise RuntimeError(
        "Unhandled gcs dependencies found; refusing to generate an incomplete "
        "managed script. Either ignore these dependencies explicitly or "
        "implement download/install handling for them:\n  - "
        + "\n  - ".join(unsupported)
    )


if __name__ == "__main__":
    if len(sys.argv) != 4:
        eprint(f"Usage: {sys.argv[0]} ACTION PATH_OR_ELECTRON_VERSION PKGNAME")
        sys.exit(1)
    action = sys.argv[1]
    deps_path = sys.argv[2]
    pkgname = sys.argv[3]
    if action not in ("print", "generate"):
        eprint(f"unsupported action: {action}")
        sys.exit(2)
    if not os.path.exists(deps_path):
        # Get it from web
        deps_text = fetch_text(f"https://github.com/electron/electron/raw/{deps_path}/DEPS")
        with NamedTemporaryFile(mode="w", encoding="utf-8", delete=True) as f:
            f.write(deps_text)
            f.flush()
            git_deps, gargs, cipd_deps, gcs_deps, reverse_map = parse_deps(f.name)
    else:
        git_deps, gargs, cipd_deps, gcs_deps, reverse_map = parse_deps(deps_path)
    if action == "print":
        for name, value in git_deps.items():
            print(f"git: {name} = {value}")
        for name, value in cipd_deps.items():
            print(f"cipd: {name} = {value}")
    if action == "generate":
        garg_cmd = generate_gclient_args(gargs)
        # cipd dependencies are usually binary blobs. Only add the necessary parts.
        cipd_cmds = generate_cipd_cmds(
            cipd_deps,
            [
                # (dependency path, is_optional)
                (
                    "src/third_party/screen-ai/linux",
                    True,
                ),  # only for new electron versions (probably >= 29)
                # The esbuild version 0.14.13 is not compatible with the system one
                ("src/third_party/devtools-frontend/src/third_party/esbuild", False),
                ("src/components/variations/test_data/cipd", False),
            ],
        )
        # gcs dependencies are usually binary blobs. They are not handled yet.
        gcs_cmds = generate_gcs_cmds(gcs_deps)
        managed_script = generate_managed_scripts(
            git_deps,
            [garg_cmd] + list(cipd_cmds) + list(gcs_cmds),
            pkgname,
            reverse_map,
        )
    print("Done")
