# Sequoia PQC source and build procedure

The `sequoia-sq-pqc` and `sequoia-sqv-pqc` lanes pair opt-in OpenSSL recipes with a controlled build procedure and its synthetic regression suite. Both release-4 lanes are deferred: source checks do not establish a new package archive, runtime qualification, or publication eligibility. The current work is tracked in [dotfiles #148](https://github.com/nisavid/dotfiles/issues/148).

The package READMEs record each baseline and deliberate divergence:

- [`sequoia-sq-pqc`](../../packages/sequoia-sq-pqc/README.md), version 1.4.0-4;
- [`sequoia-sqv-pqc`](../../packages/sequoia-sqv-pqc/README.md), version 1.5.0-4.

The maintained [procedure](../../scripts/hatchery/sequoia-pqc-build/procedure/PROCEDURE.md) owns setup, attempt execution, input verification, cleanup, and evidence assembly. Read it before preparing an actual build. The optional SOP variant remains outside this source increment.

## Stage a reviewed revision

The controller and tests expect sibling `procedure/`, `recipes/`, and `tests/` trees in a fresh directory. Their maintained repository paths separate package recipes from the procedure, so stage copies before invoking either. Use actual files and directories, preserving modes; symlink aliases do not satisfy the procedure's input contract. Keep test staging separate from an actual build run.

From a clean checkout of the reviewed revision:

```bash
source_revision=$(git rev-parse HEAD)
source_root=$PWD
run_root=$(mktemp -d)
mkdir "$run_root/recipes"
cp -a "$source_root/scripts/hatchery/sequoia-pqc-build/procedure" "$run_root/procedure"
cp -a "$source_root/scripts/hatchery/sequoia-pqc-build/tests" "$run_root/tests"
cp -a "$source_root/packages/sequoia-sq-pqc" "$run_root/recipes/sequoia-sq-pqc"
cp -a "$source_root/packages/sequoia-sqv-pqc" "$run_root/recipes/sequoia-sqv-pqc"
printf '%s\n' "$source_revision" > "$run_root/source-revision.txt"
diff -qr "$source_root/scripts/hatchery/sequoia-pqc-build/procedure" "$run_root/procedure"
diff -qr "$source_root/scripts/hatchery/sequoia-pqc-build/tests" "$run_root/tests"
diff -qr "$source_root/packages/sequoia-sq-pqc" "$run_root/recipes/sequoia-sq-pqc"
diff -qr "$source_root/packages/sequoia-sqv-pqc" "$run_root/recipes/sequoia-sqv-pqc"
```

Record the reviewed revision and compare staged bytes and modes against its source inventory. The `diff` commands above compare contents; they do not prove modes or authenticate a review. The procedure's freeze and replay steps bind their own complete inputs before accepting an attempt.

## Check the maintained source

Run the repository consistency checker from the repository root:

```bash
python3 tools/check_repo_consistency.py
git diff --check
```

It checks package metadata, `.SRCINFO` agreement, the catalog, README maintenance fields, and repository tests. It does not build either Sequoia package or decide qualification. `.SRCINFO` generation evaluates the recipes, so use the reviewed source.

After the separate test staging above, run the maintained synthetic suite:

```bash
/usr/bin/bash "$run_root/tests/run.sh"
```

The suite runs inert failure, namespace, input-binding, path, and cleanup controls, including a synthetic compiled fixture. It is separate from source retrieval and a real package build. Retain the source revision, exact commands, results, and environment limitations with the review evidence. Run Bash syntax and ShellCheck on changed procedure and test scripts as well.

## Continue build qualification

A successor must load the maintained procedure from the reviewed revision, verify the staged source identity, and confirm authority for its setup and build steps before execution. The procedure identifies required system dependencies and the separate toolchain installation, public-key import, and networked phases. Direct package-directory build commands do not substitute for its evidence path.

A new unsigned archive requires fresh controller evidence and its own package and executable identities. Cryptographic-operation checks, macOS interoperability, installation, authenticated rollback, independent acceptance, and deployment retain their separate gates. A source commit or passing synthetic suite closes none of them. Keep both catalog entries `deferred` and publication eligibility `no` until their owning acceptance workflow changes those states.
