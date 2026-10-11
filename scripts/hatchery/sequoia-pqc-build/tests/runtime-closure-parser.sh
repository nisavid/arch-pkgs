#!/usr/bin/bash
set -Eeuo pipefail

tests_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${tests_dir%/*}
helper="$source_root/procedure/runtime-closure.sh"
scratch=$(mktemp -d)
trap 'find "$scratch" -depth -delete' EXIT

candidate="$scratch/candidate/clean"
runtime_root="$scratch/runtime-root"
owner_log="$scratch/owner.log"
mkdir -p "${candidate%/*}" "$runtime_root"
printf '#!/usr/bin/bash\nexit 0\n' >"$candidate"
chmod 755 "$candidate"
printf 'library fixture\n' >"$runtime_root/libfixture.so"
printf 'loader fixture\n' >"$runtime_root/ld-fixture.so"

fake_ldd="$scratch/fake-ldd"
cat >"$fake_ldd" <<'EOF'
#!/usr/bin/bash
set -Eeuo pipefail
case "${HATCHERY_TEST_LDD_CASE-}" in
  complete)
    printf 'linux-vdso.so.1 (0x0000000000000000)\n'
    printf 'libfixture.so => %s/libfixture.so (0x0000000000000000)\n' "$HATCHERY_TEST_RUNTIME_ROOT"
    printf '  %s/ld-fixture.so (0x0000000000000000)\n' "$HATCHERY_TEST_RUNTIME_ROOT"
    printf 'libfixture-duplicate.so => %s/libfixture.so (0x0000000000000000)\n' "$HATCHERY_TEST_RUNTIME_ROOT"
    ;;
  missing)
    printf 'libfixture.so => %s/libfixture.so (0x0000000000000000)\n' "$HATCHERY_TEST_RUNTIME_ROOT"
    printf 'libmissing.so => not found\n'
    ;;
  *) exit 2 ;;
esac
EOF
chmod 755 "$fake_ldd"

fake_owner="$scratch/fake-owner"
cat >"$fake_owner" <<'EOF'
#!/usr/bin/bash
set -Eeuo pipefail
printf '%s\n' "$*" >>"$HATCHERY_TEST_OWNER_LOG"
printf 'fixture-owner %s\n' "${!#}"
EOF
chmod 755 "$fake_owner"

run_fixture() {
  local fixture_case=$1 ldd_receipt=$2 closure_receipt=$3
  env -i PATH=/usr/bin:/bin LC_ALL=C.UTF-8 LANG=C.UTF-8 \
    HATCHERY_RUNTIME_CLOSURE_TEST_MODE=1 \
    HATCHERY_TEST_LDD_COMMAND="$fake_ldd" \
    HATCHERY_TEST_LDD_CASE="$fixture_case" \
    HATCHERY_TEST_RUNTIME_ROOT="$runtime_root" \
    HATCHERY_TEST_OWNER_COMMAND="$fake_owner" \
    HATCHERY_TEST_OWNER_LOG="$owner_log" \
    /usr/bin/bash "$helper" "$candidate" \
    3>"$ldd_receipt" >"$closure_receipt" 2>&1
}

run_fixture complete "$scratch/complete.ldd" "$scratch/complete.closure"
for object in "$runtime_root/libfixture.so" "$runtime_root/ld-fixture.so"; do
  [[ $(grep -Fxc "reported_path=$object" "$scratch/complete.closure") == 1 ]]
  [[ $(grep -Fxc -- "-Qo -- $object" "$owner_log") == 1 ]]
  grep -Fq "sha256=$(sha256sum "$object" | cut -d' ' -f1)" "$scratch/complete.closure"
done
[[ $(grep -c '^reported_path=' "$scratch/complete.closure") == 2 ]]

set +e
run_fixture missing "$scratch/missing.ldd" "$scratch/missing.closure"
missing_exit=$?
set -e
(( missing_exit != 0 ))
grep -Fxq 'missing_runtime_object=libmissing.so' "$scratch/missing.closure"

printf 'runtime closure records each reported object once and rejects missing objects: PASS\n'
