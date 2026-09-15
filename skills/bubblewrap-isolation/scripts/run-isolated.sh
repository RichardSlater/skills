#!/usr/bin/env bash
# Run a command in a Bubblewrap sandbox with only the current Git project writable.
set -euo pipefail

usage() {
  printf 'Usage: %s -- command [argument ...]\n' "${0##*/}" >&2
  exit 64
}

[[ $# -ge 2 && $1 == "--" ]] || usage
shift

command -v bwrap >/dev/null 2>&1 || {
  printf 'error: Bubblewrap (bwrap) is required\n' >&2
  exit 69
}
command -v git >/dev/null 2>&1 || {
  printf 'error: git is required to locate the project root\n' >&2
  exit 69
}

project_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  printf 'error: run this command from inside a Git working tree\n' >&2
  exit 69
}
project_root="$(cd "$project_root" && pwd -P)"
working_dir="$(pwd -P)"

case "$working_dir" in
  "$project_root"|"$project_root"/*) ;;
  *)
    printf 'error: physical working directory is outside the Git project root\n' >&2
    exit 65
    ;;
esac

# Keep the project at its host path: this preserves project-local interpreter
# shebangs without revealing any parent directory contents. Bubblewrap starts
# with an empty filesystem, so create only the mountpoint parents needed.
bwrap_args=(
  --unshare-user
  --unshare-all
  --die-with-parent
  --new-session
  --cap-drop ALL
  --clearenv
  --setenv HOME /tmp/home/sandbox
  --setenv TMPDIR /tmp
  --setenv PATH /usr/sbin:/usr/bin:/sbin:/bin
  --setenv LANG C.UTF-8
  --setenv PWD "$working_dir"
  --ro-bind /usr /usr
  --ro-bind-try /bin /bin
  --ro-bind-try /sbin /sbin
  --ro-bind-try /lib /lib
  --ro-bind-try /lib64 /lib64
  --proc /proc
  --dev /dev
  --size 1073741824
  --tmpfs /tmp
  --dir /tmp/home
  --dir /tmp/home/sandbox
  --dir /run
)

mount_parent=""
IFS=/ read -r -a path_parts <<<"${project_root#/}"
for path_part in "${path_parts[@]:0:${#path_parts[@]} - 1}"; do
  mount_parent+="/${path_part}"
  bwrap_args+=(--dir "$mount_parent")
done

bwrap_args+=(
  --bind "$project_root" "$project_root"
  --chdir "$working_dir"
)

exec bwrap "${bwrap_args[@]}" -- "$@"
