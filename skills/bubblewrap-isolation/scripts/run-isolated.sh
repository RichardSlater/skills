#!/usr/bin/env bash
# Fail-closed Bubblewrap launcher for short-lived agent commands.
# Extra programs, per-command network, and host execution come only from the
# invoking user's real ~/.config/bubblewrap-isolation/. Repository files,
# mount flags, and network flags do not grant authority.
set -euo pipefail

usage() {
  printf 'Usage: %s -- command [argument ...]\n' "${0##*/}" >&2
  printf 'Operator config: ~/.config/bubblewrap-isolation/{extra-commands,network-commands,host-commands,package-managers}\n' >&2
  exit 64
}

die() {
  printf 'error: %s\n' "$1" >&2
  exit "${2:-65}"
}

canonical_dir() {
  local path="$1"
  (cd "$path" && pwd -P)
}

reject_caller_config() {
  if [[ -n "${BUBBLEWRAP_ISOLATION_CONFIG:-}${BUBBLEWRAP_ISOLATION_CONFIG_DIR:-}${BWRAP_CONFIG:-}" ]]; then
    die "caller-supplied config path is not accepted"
  fi
  case "${1:-}" in
    --config|--config-dir|--config=*|--config-dir=*|--policy|--policy=*)
      die "caller-supplied config path is not accepted"
      ;;
    --share-net|--mount)
      die "command-line network or mount flags are not grants"
      ;;
  esac
}

resolve_real_home() {
  local uid line home
  uid="$(/usr/bin/id -u)"
  line="$(/usr/bin/getent passwd "$uid")" || die "cannot resolve invoking user from the user database"
  home="$(printf '%s\n' "$line" | /usr/bin/awk -F: 'NR==1 { print $6 }')"
  [[ -n "$home" && "$home" == /* ]] || die "cannot resolve invoking user home from the user database"
  [[ ! -L "$home" && -d "$home" ]] || die "invoking user home must be a real directory"
  REAL_HOME="$(canonical_dir "$home")"
  REAL_USER="$(printf '%s\n' "$line" | /usr/bin/awk -F: 'NR==1 { print $1 }')"
  [[ -n "$REAL_USER" && "$REAL_USER" != *$'\n'* ]] || die "cannot resolve invoking user name from the user database"
  CONFIG_DIR="$REAL_HOME/.config/bubblewrap-isolation"
}

refuse_project_contains_home() {
  case "$REAL_HOME" in
    "$PROJECT"|"$PROJECT"/*)
      die "refusing Git project that contains the invoking user's home: $PROJECT"
      ;;
  esac
}

resolve_project() {
  command -v git >/dev/null 2>&1 || die "git is required" 69
  local toplevel
  toplevel="$(git rev-parse --show-toplevel 2>/dev/null)" || die "run this command from inside a Git working tree" 69
  [[ -d "$toplevel" && ! -L "$toplevel" ]] || die "Git project root must be a real directory: $toplevel"
  PROJECT="$(canonical_dir "$toplevel")"
  WORKDIR="$(pwd -P)"
  case "$WORKDIR" in
    "$PROJECT"|"$PROJECT"/*) ;;
    *) die "physical working directory is outside the Git project root" ;;
  esac
}

path_has_symlink_component() {
  local path="$1" cursor="" part
  [[ "$path" == /* ]] || return 0
  local rest="${path#/}"
  local -a parts=()
  IFS=/ read -r -a parts <<<"$rest"
  for part in "${parts[@]}"; do
    [[ -n "$part" ]] || return 0
    cursor+="/$part"
    if [[ -L "$cursor" ]]; then
      return 0
    fi
  done
  return 1
}

reject_newline() {
  local value="$1" label="$2"
  [[ "$value" != *$'\n'* ]] || die "$label contains a newline"
}

validate_relative() {
  local relative="$1" part
  reject_newline "$relative" "relative path"
  [[ -n "$relative" && "$relative" != "." && "$relative" != ".git" ]] || die "refusing overly broad protected path: $relative"
  [[ "$relative" != /* ]] || die "protected path must be project-relative: $relative"
  [[ "$relative" != *'*'* && "$relative" != *'?'* && "$relative" != *'['* ]] || die "protected path must be literal: $relative"
  local -a parts=()
  IFS=/ read -r -a parts <<<"$relative"
  for part in "${parts[@]}"; do
    [[ -n "$part" && "$part" != "." && "$part" != ".." ]] || die "unsafe protected path: $relative"
  done
}

assert_no_symlink_chain() {
  local root="$1" relative="$2" cursor part
  cursor="$root"
  local -a parts=()
  IFS=/ read -r -a parts <<<"$relative"
  for part in "${parts[@]}"; do
    cursor+="/$part"
    if [[ -L "$cursor" ]]; then
      die "refusing symlink in protected path: $cursor"
    fi
  done
}

is_secret_name() {
  local name="${1##*/}"
  [[ "$name" == ".env" || "$name" == ".envrc" || "$name" == .env.* ]]
}

is_credential_relative() {
  local rel="$1"
  case "$rel" in
    .ssh|.ssh/*|*/.ssh|*/.ssh/*|\
    .gnupg|.gnupg/*|*/.gnupg|*/.gnupg/*|\
    .aws|.aws/*|*/.aws|*/.aws/*|\
    .kube|.kube/*|*/.kube|*/.kube/*|\
    .docker|.docker/*|*/.docker|*/.docker/*|\
    .config/git|.config/git/*|*/.config/git|*/.config/git/*|\
    .config/gh|.config/gh/*|*/.config/gh|*/.config/gh/*|\
    .cache/pre-commit|.cache/pre-commit/*|*/.cache/pre-commit|*/.cache/pre-commit/*|\
    .config/bubblewrap-isolation|.config/bubblewrap-isolation/*|*/.config/bubblewrap-isolation|*/.config/bubblewrap-isolation/*)
      return 0
      ;;
  esac
  return 1
}

scan_inodes() {
  local entry id listing rel credential=""
  listing="$(mktemp)"
  if ! find -P "$PROJECT" -xdev \( -type f -o -type d -o -type l \) -print0 >"$listing"; then
    rm -f "$listing"
    die "hardlink scan failed"
  fi
  declare -gA INODE_PATHS=()
  while IFS= read -r -d '' entry; do
    reject_newline "$entry" "project path"
    if [[ "$entry" == "$PROJECT" ]]; then
      continue
    fi
    rel="${entry#"$PROJECT"/}"
    if [[ -z "$credential" ]] && is_credential_relative "$rel" && { [[ -d "$entry" || -L "$entry" ]]; }; then
      credential="$rel"
    fi
    if is_secret_name "$rel"; then
      append_unique "$rel"
    fi
    if [[ -L "$entry" ]]; then
      continue
    fi
    id="$(stat -c '%d:%i' -- "$entry")"
    if [[ -n "${INODE_PATHS[$id]+x}" ]]; then
      INODE_PATHS["$id"]+=$'\n'"$entry"
    else
      INODE_PATHS["$id"]="$entry"
    fi
  done <"$listing"
  rm -f "$listing"
  [[ -z "$credential" ]] || die "refusing credential directory in project: $credential"
}

assert_unique_inode() {
  local path="$1" id others other
  id="$(stat -c '%d:%i' -- "$path")"
  others="${INODE_PATHS[$id]-}"
  while IFS= read -r other; do
    [[ -n "$other" && "$other" != "$path" ]] || continue
    die "refusing aliased path $path (also $other)"
  done <<<"$others"
  if [[ -f "$path" ]]; then
    [[ "$(stat -c '%h' -- "$path")" == 1 ]] || die "refusing hard-linked file: $path"
  fi
}

append_unique() {
  local value="$1" existing
  for existing in "${PROTECTED_RELS[@]+"${PROTECTED_RELS[@]}"}"; do
    [[ "$existing" == "$value" ]] && return 0
  done
  PROTECTED_RELS+=("$value")
}

add_default_protected() {
  local name path
  PROTECTED_RELS=()
  append_unique ".env"
  append_unique ".envrc"
  append_unique ".git/hooks"
  append_unique ".git/config"
  append_unique ".pi"
  append_unique ".bwrap"
  shopt -s nullglob dotglob
  for path in "$PROJECT"/.env.*; do
    name="${path##*/}"
    append_unique "$name"
  done
  shopt -u nullglob dotglob
  local git_dir hooks config
  git_dir="$(git -C "$PROJECT" rev-parse --absolute-git-dir)"
  hooks="$git_dir/hooks"
  config="$git_dir/config"
  case "$hooks" in
    "$PROJECT"/*) append_unique "${hooks#"$PROJECT"/}" ;;
  esac
  case "$config" in
    "$PROJECT"/*) append_unique "${config#"$PROJECT"/}" ;;
  esac
}

classify_protected() {
  local relative="$1" path="$PROJECT/$relative"
  validate_relative "$relative"
  assert_no_symlink_chain "$PROJECT" "$relative"
  if [[ ! -e "$path" ]]; then
    return 0
  fi
  assert_unique_inode "$path"
  case "$relative" in
    .git/config|*/config)
      if [[ "$path" == "$(git -C "$PROJECT" rev-parse --absolute-git-dir)/config" || "$relative" == ".git/config" ]]; then
        [[ -f "$path" ]] || die "git config must be a regular file: $path"
        MASKS+=(--ro-bind "$path" "$path")
        PROTECTED_ABS+=("$path")
        return 0
      fi
      ;;
  esac
  if [[ -d "$path" ]]; then
    MASKS+=(--tmpfs "$path" --remount-ro "$path")
    PROTECTED_ABS+=("$path")
  elif [[ -f "$path" ]]; then
    MASKS+=(--ro-bind /dev/null "$path")
    PROTECTED_ABS+=("$path")
  else
    die "unsupported protected path: $path"
  fi
}

mask_git_pointer() {
  local pointer="$PROJECT/.git"
  if [[ -L "$pointer" ]]; then
    die "refusing symlinked .git"
  fi
  if [[ -f "$pointer" ]]; then
    assert_unique_inode "$pointer"
    [[ "$(stat -c '%h' -- "$pointer")" == 1 ]] || die "refusing hard-linked .git file"
    MASKS+=(--ro-bind "$pointer" "$pointer")
    PROTECTED_ABS+=("$pointer")
  fi
}

is_blank_line() {
  local value="$1"
  [[ -z "${value//[[:space:]]/}" ]]
}

valid_program_name() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*$ ]]
}

valid_arg_token() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._+@=-]*$ || "$1" =~ ^--?[A-Za-z0-9][A-Za-z0-9._+@=-]*$ ]]
}

validate_network_line() {
  local line="$1" token
  [[ "$line" != *$'\t'* && "$line" != ' '* && "$line" != *' ' ]] || return 1
  [[ "$line" != *'  '* ]] || return 1
  local -a tokens=()
  read -r -a tokens <<<"$line"
  [[ "${#tokens[@]}" -ge 1 ]] || return 1
  for token in "${tokens[@]}"; do
    valid_arg_token "$token" || return 1
  done
}

assert_private_config() {
  local path="$1" owner mode
  owner="$(stat -c '%u' -- "$path")"
  [[ "$owner" == "$(/usr/bin/id -u)" ]] || die "refusing operator config not owned by the invoking user: $path"
  mode="$(stat -c '%a' -- "$path")"
  if (( (8#$mode & 022) != 0 )); then
    die "refusing group- or other-writable operator config: $path"
  fi
}

load_operator_config() {
  EXTRA_NAMES=()
  NETWORK_LINES=()
  HOST_LINES=()
  PACKAGE_MANAGERS=()
  local cursor="$REAL_HOME" part
  for part in .config bubblewrap-isolation; do
    cursor+="/$part"
    if [[ -L "$cursor" ]]; then
      die "refusing symlink in config path: $cursor"
    fi
    if [[ ! -e "$cursor" ]]; then
      return 0
    fi
  done
  [[ -d "$CONFIG_DIR" ]] || die "config path must be a directory: $CONFIG_DIR"
  assert_private_config "$CONFIG_DIR"
  shopt -s nullglob dotglob
  local entry name
  for entry in "$CONFIG_DIR"/*; do
    name="${entry##*/}"
    reject_newline "$name" "config entry"
    case "$name" in
      extra-commands|network-commands|host-commands|package-managers) ;;
      *) die "unknown config entry: $name" ;;
    esac
    [[ ! -L "$entry" ]] || die "refusing symlink in config: $name"
    [[ -f "$entry" ]] || die "config entry must be a regular file: $name"
    assert_private_config "$entry"
  done
  shopt -u nullglob dotglob
  local file line
  for file in extra-commands network-commands host-commands package-managers; do
    [[ -f "$CONFIG_DIR/$file" && ! -L "$CONFIG_DIR/$file" ]] || continue
    while IFS= read -r line || [[ -n "$line" ]]; do
      [[ "$line" != *$'\r'* ]] || die "unknown line in $file: $line"
      if is_blank_line "$line"; then
        continue
      fi
      case "$file" in
        package-managers)
          case "$line" in
            uv|npm|pnpm|cargo|bun|deno|pip) PACKAGE_MANAGERS+=("$line") ;;
            *) die "unknown line in package-managers: $line" ;;
          esac
          ;;
        extra-commands)
          valid_program_name "$line" || die "unknown line in extra-commands: $line"
          EXTRA_NAMES+=("$line")
          ;;
        network-commands)
          validate_network_line "$line" || die "unknown line in network-commands: $line"
          NETWORK_LINES+=("$line")
          ;;
        host-commands)
          validate_network_line "$line" || die "unknown line in host-commands: $line"
          # Refused as host grants, not as sandbox commands. pre-commit stays
          # here so the quality gate cannot escape onto the host cache.
          if refused_host_command "${line%% *}"; then
            die "unknown line in host-commands: $line"
          fi
          HOST_LINES+=("$line")
          ;;
      esac
    done <"$CONFIG_DIR/$file"
  done
}

name_listed() {
  local name="$1" existing
  for existing in "${EXTRA_NAMES[@]+"${EXTRA_NAMES[@]}"}"; do
    [[ "$existing" == "$name" ]] && return 0
  done
  return 1
}

argv_matches_line() {
  local line="$1"
  shift
  local -a prefix=()
  read -r -a prefix <<<"$line"
  [[ "${#prefix[@]}" -ge 1 && "$#" -ge "${#prefix[@]}" ]] || return 1
  local i arg
  for i in "${!prefix[@]}"; do
    arg="${@:$((i + 1)):1}"
    [[ "${prefix[$i]}" == "$arg" ]] || return 1
  done
}

host_line_matches() {
  local line
  for line in "${HOST_LINES[@]+"${HOST_LINES[@]}"}"; do
    if argv_matches_line "$line" "$@"; then
      return 0
    fi
  done
  return 1
}

network_line_matches() {
  local line
  for line in "${NETWORK_LINES[@]+"${NETWORK_LINES[@]}"}"; do
    if argv_matches_line "$line" "$@"; then
      return 0
    fi
  done
  return 1
}

is_git_host_command() {
  [[ "$#" -ge 2 && "$1" == git && ( "$2" == commit || "$2" == push ) ]]
}

# Host grants run with the real home. Refuse names that would make that grant
# an interpreter, a privilege or namespace transition, or the sandboxed
# pre-commit gate. These names still use the normal sandbox path.
refused_host_command() {
  case "$1" in
    bwrap|sudo|su|sudoedit|pkexec|doas|unshare|chroot|nsenter|systemd-run|\
    machinectl|lxc-attach|docker|podman|crun|runc|proot|setpriv|capsh|\
    newuidmap|newgidmap|fakeroot|nix|nix-shell|\
    bash|sh|dash|zsh|fish|python|python3|perl|ruby|node|env|busybox|\
    timeout|nohup|stdbuf|nice|ionice|setsid|script|ssh|scp|sftp|gpg|\
    pre-commit)
      return 0
      ;;
  esac
  return 1
}

host_commands_summary() {
  local out="" line
  local -A seen=()
  for line in "${HOST_LINES[@]+"${HOST_LINES[@]}"}"; do
    [[ -z "${seen[$line]+x}" ]] || continue
    seen["$line"]=1
    out+="${out:+,}$line"
  done
  printf '%s' "${out:-none}"
}

print_status() {
  local execution="$1" network="$2"
  shift 2
  {
    printf 'bubblewrap-isolation: execution=%s network=%s project=%s host-commands=%s command=' \
      "$execution" "$network" "$PROJECT" "$(host_commands_summary)"
    printf '%q' "$1"
    shift
    local arg
    for arg in "$@"; do
      printf ' %q' "$arg"
    done
    printf '\n'
  } >&2
}

under_base_prefix() {
  case "$1" in
    /usr|/usr/*|/bin|/bin/*|/sbin|/sbin/*|/lib|/lib/*|/lib64|/lib64/*) return 0 ;;
    *) return 1 ;;
  esac
}

in_base_mounts() {
  local path="$1" resolved
  under_base_prefix "$path" || return 1
  [[ -e "$path" ]] || return 1
  resolved="$(readlink -f -- "$path")" || return 1
  under_base_prefix "$resolved"
}

sandbox_path_dirs() {
  local dir
  SANDBOX_PATH=""
  for dir in /usr/local/bin /usr/local/sbin /usr/bin /bin /usr/sbin /sbin; do
    if [[ -d "$dir" ]]; then
      SANDBOX_PATH+="${SANDBOX_PATH:+:}$dir"
    fi
  done
  for dir in "${PACKAGE_PATH_DIRS[@]+"${PACKAGE_PATH_DIRS[@]}"}"; do
    SANDBOX_PATH="$dir${SANDBOX_PATH:+:$SANDBOX_PATH}"
  done
  for dir in "${EXTRA_PATH_DIRS[@]+"${EXTRA_PATH_DIRS[@]}"}"; do
    SANDBOX_PATH+=":$dir"
  done
}

sandbox_visible() {
  local name="$1" dir
  sandbox_path_dirs
  local IFS=':'
  local -a dirs=()
  read -r -a dirs <<<"$SANDBOX_PATH"
  for dir in "${dirs[@]}"; do
    [[ -n "$dir" && -e "$dir/$name" && ! -d "$dir/$name" ]] || continue
    if in_base_mounts "$dir/$name"; then
      return 0
    fi
  done
  return 1
}

in_forbidden_bind_dir() {
  local physical dir
  physical="$(readlink -f -- "$1")" || return 0
  for dir in \
    "$REAL_HOME/.ssh" \
    "$REAL_HOME/.gnupg" \
    "$REAL_HOME/.aws" \
    "$REAL_HOME/.kube" \
    "$REAL_HOME/.docker" \
    "$REAL_HOME/.config/git" \
    "$REAL_HOME/.config/gh" \
    "$REAL_HOME/.cache/pre-commit"
  do
    case "$physical" in
      "$dir"|"$dir"/*) return 0 ;;
    esac
  done
  return 1
}

lookup_host_command() {
  local name="$1" entry physical candidate
  local IFS=':'
  local -a entries=()
  read -r -a entries <<<"${HOST_PATH:-}"
  for entry in "${entries[@]}"; do
    [[ -n "$entry" && -d "$entry" ]] || continue
    physical="$(canonical_dir "$entry" 2>/dev/null)" || continue
    case "$physical" in
      "$PROJECT"|"$PROJECT"/*) continue ;;
    esac
    candidate="$entry/$name"
    [[ -e "$candidate" || -L "$candidate" ]] || continue
    if [[ -L "$candidate" || -d "$candidate" ]] || path_has_symlink_component "$candidate"; then
      return 2
    fi
    case "$physical" in
      "$PROJECT"|"$PROJECT"/*) continue ;;
    esac
    printf '%s\n' "$candidate"
    return 0
  done
  return 1
}

script_closure_ok() {
  local file="$1" line interp prog base
  IFS= read -r line <"$file" || return 1
  [[ "$line" == '#!'* ]] || return 1
  line="${line#\#!}"
  line="${line#"${line%%[![:space:]]*}"}"
  [[ -n "$line" ]] || return 1
  local -a parts=()
  read -r -a parts <<<"$line"
  interp="${parts[0]}"
  [[ "$interp" == /* ]] || return 1
  in_base_mounts "$interp" || return 1
  base="${interp##*/}"
  if [[ "$base" == env ]]; then
    [[ "${#parts[@]}" -ge 2 ]] || return 1
    prog="${parts[1]}"
    [[ "$prog" != */* ]] || return 1
    sandbox_visible "$prog" || return 1
  fi
  return 0
}

rpath_tokens_ok() {
  local raw="$1" token saved
  raw="${raw#\[}"
  raw="${raw%\]}"
  saved="$IFS"
  IFS=':'
  local -a tokens=()
  read -r -a tokens <<<"$raw"
  IFS="$saved"
  [[ "${#tokens[@]}" -ge 1 ]] || return 1
  for token in "${tokens[@]}"; do
    [[ "$token" == /* ]] || return 1
    under_base_prefix "$token" || return 1
  done
}

elf_closure_ok() {
  local file="$1" report interp_out interp soname resolved raw ldconfig="" candidate
  [[ -x /usr/bin/readelf ]] || return 1
  report="$(/usr/bin/readelf -d -- "$file" 2>&1)" || return 1
  [[ -n "${report//[[:space:]]/}" ]] || return 1
  if printf '%s\n' "$report" | /usr/bin/grep -q "no dynamic section"; then
    return 0
  fi
  printf '%s\n' "$report" | /usr/bin/grep -q "Dynamic section" || return 1
  interp_out="$(/usr/bin/readelf -l -- "$file" 2>&1)" || return 1
  interp="$(printf '%s\n' "$interp_out" | /usr/bin/sed -n 's/.*Requesting program interpreter: \([^]]*\).*/\1/p')"
  if [[ -n "$interp" ]]; then
    in_base_mounts "$interp" || return 1
  fi
  while IFS= read -r raw; do
    [[ -n "$raw" ]] || continue
    rpath_tokens_ok "$raw" || return 1
  done < <(printf '%s\n' "$report" | /usr/bin/awk '/\(RPATH\)|\(RUNPATH\)/ { print $NF }')
  for candidate in /sbin/ldconfig /usr/sbin/ldconfig; do
    if [[ -x "$candidate" ]] && under_base_prefix "$(readlink -f -- "$candidate")"; then
      ldconfig="$candidate"
      break
    fi
  done
  while IFS= read -r soname; do
    [[ -n "$soname" ]] || continue
    [[ -n "$ldconfig" ]] || return 1
    resolved="$("$ldconfig" -p 2>/dev/null | /usr/bin/awk -v soname="$soname" '$1 == soname { print $NF; exit }')"
    [[ -n "$resolved" ]] || return 1
    in_base_mounts "$resolved" || return 1
  done < <(printf '%s\n' "$report" | /usr/bin/awk '/\(NEEDED\)/ { gsub(/[\[\]]/, "", $NF); print $NF }')
  return 0
}

is_elf() {
  local magic
  magic="$(/usr/bin/od -An -t x1 -N 4 -- "$1" 2>/dev/null | tr -d ' \n')"
  [[ "$magic" == "7f454c46" ]]
}

closure_ok() {
  local file="$1"
  [[ -f "$file" && ! -L "$file" && ! -d "$file" ]] || return 1
  [[ -x "$file" ]] || return 1
  path_has_symlink_component "$file" && return 1
  [[ "$(stat -c '%h' -- "$file")" == 1 ]] || return 1
  in_forbidden_bind_dir "$file" && return 1
  case "$(readlink -f -- "$file")" in
    "$PROJECT"|"$PROJECT"/*) return 1 ;;
  esac
  if is_elf "$file"; then
    elf_closure_ok "$file"
    return
  fi
  local mark
  mark="$(/usr/bin/od -An -t c -N 2 -- "$file" 2>/dev/null | tr -d ' \n')"
  if [[ "$mark" == "#!" ]]; then
    script_closure_ok "$file"
    return
  fi
  return 1
}

# Package-manager grants expose prepared installations, not the host home or
# package-manager configuration. Keep discovery static: never execute a manager
# on the host to ask where it stores packages.
package_path_too_broad() {
  local path="$1" dir
  [[ -n "$path" && "$path" == /* && "$path" != / ]] || return 0
  case "$path" in
    /bin|/sbin|/lib|/lib64|/usr|/usr/bin|/usr/lib|/usr/local|/etc|/var|/tmp|/opt|/root|/home) return 0 ;;
  esac
  case "$REAL_HOME" in
    "$path"|"$path"/*) return 0 ;;
  esac
  case "$PROJECT" in
    "$path"|"$path"/*) return 0 ;;
  esac
  case "$path" in
    "$PROJECT"|"$PROJECT"/*) return 0 ;;
  esac
  if in_forbidden_bind_dir "$path"; then
    return 0
  fi
  for dir in \
    "$REAL_HOME/.ssh" \
    "$REAL_HOME/.gnupg" \
    "$REAL_HOME/.aws" \
    "$REAL_HOME/.kube" \
    "$REAL_HOME/.docker" \
    "$REAL_HOME/.config/git" \
    "$REAL_HOME/.config/gh" \
    "$REAL_HOME/.cache/pre-commit"
  do
    case "$dir" in
      "$path"|"$path"/*) return 0 ;;
    esac
  done
  return 1
}

package_remember_root() {
  local path="$1" existing
  for existing in "${PACKAGE_ROOTS[@]+"${PACKAGE_ROOTS[@]}"}"; do
    [[ "$existing" == "$path" ]] && return 0
  done
  PACKAGE_ROOTS+=("$path")
  return 1
}

package_root() {
  local path="$1" source remembered
  [[ -e "$path" || -L "$path" ]] || return 0
  [[ -d "$path" ]] || die "package-manager path must be a directory: $path"
  package_path_too_broad "$path" && die "refusing overly broad package-manager path: $path"
  source="$(readlink -f -- "$path")" || die "refusing package-manager path: $path"
  [[ -d "$source" ]] || die "package-manager path must be a directory: $path"
  package_path_too_broad "$source" && die "refusing overly broad package-manager path: $source"
  case "$source" in
    "$PROJECT"|"$PROJECT"/*) die "refusing package-manager path inside project: $source" ;;
  esac
  # Mount the physical tree at the path tools expect. Symlinked roots and
  # relative links inside them then resolve inside the sandbox.
  if package_remember_root "$path"; then
    return 0
  fi
  PACKAGE_BINDS+=(--ro-bind "$source" "$path")
  if [[ "$source" != "$path" ]]; then
    remembered=0
    package_remember_root "$source" || remembered=1
    if [[ "$remembered" -eq 1 ]]; then
      PACKAGE_BINDS+=(--ro-bind "$source" "$source")
    fi
  fi
}

package_host_program() {
  local name="$1" entry physical resolved
  local -a entries=()
  IFS=: read -r -a entries <<<"$HOST_PATH"
  for entry in "${entries[@]}"; do
    [[ "$entry" == /* && -d "$entry" ]] || continue
    physical="$(canonical_dir "$entry")"
    case "$physical" in "$PROJECT"|"$PROJECT"/*) continue ;; esac
    [[ -x "$entry/$name" && ! -d "$entry/$name" ]] || continue
    resolved="$(readlink -f -- "$entry/$name")" || continue
    case "$resolved" in "$PROJECT"|"$PROJECT"/*) continue ;; esac
    printf '%s\n' "$entry/$name"
    return 0
  done
  return 1
}

package_executable() {
  local path="$1" resolved root link
  resolved="$(readlink -f -- "$path")" || die "not available: ${path##*/}"
  [[ -f "$resolved" && -x "$resolved" ]] || die "not available: ${path##*/}"
  in_forbidden_bind_dir "$resolved" && die "refusing credential path for package manager: $resolved"
  package_path_too_broad "$resolved" && die "refusing overly broad package-manager path: $resolved"
  PACKAGE_FILES+=("$path")
  PACKAGE_PATH_DIRS+=("${path%/*}")
  in_base_mounts "$path" && return 0
  for root in "${PACKAGE_ROOTS[@]+"${PACKAGE_ROOTS[@]}"}"; do
    case "$path:$resolved" in "$root"/*:"$root"/*) return 0 ;; esac
  done
  # Keep a package-manager symlink intact and expose the file it points at.
  # Flattening the link breaks relative targets such as npm's CLI and rustup.
  if [[ -L "$path" ]]; then
    link="$(readlink -- "$path")" || die "not available: ${path##*/}"
    if ! in_base_mounts "$resolved"; then
      PACKAGE_BINDS+=(--ro-bind "$resolved" "$resolved")
    fi
    PACKAGE_BINDS+=(--symlink "$link" "$path")
    return 0
  fi
  PACKAGE_BINDS+=(--ro-bind "$resolved" "$path")
}

package_pip_tools() {
  local site metadata name path
  shopt -s nullglob
  for site in "$REAL_HOME"/.local/lib/python*/site-packages; do
    package_root "$site"
    # Read entry-point names as data, without importing any installed package.
    for metadata in "$site"/*.dist-info/entry_points.txt; do
      while IFS= read -r name; do
        valid_program_name "$name" || continue
        path="$REAL_HOME/.local/bin/$name"
        [[ -f "$path" && -x "$path" ]] || continue
        package_executable "$path"
      done < <(awk -F= '
        /^\[/ { scripts = ($0 ~ /^\[(console_scripts|gui_scripts)\][[:space:]]*$/); next }
        scripts && NF >= 2 { gsub(/^[[:space:]]+|[[:space:]]+$/, "", $1); print $1 }
      ' "$metadata")
    done
  done
  shopt -u nullglob
}

package_settings_file() {
  local path="$1" source
  [[ -e "$path" || -L "$path" ]] || return 0
  source="$(readlink -f -- "$path")" || die "refusing package-manager path: $path"
  [[ -f "$source" ]] || die "package-manager settings must be a regular file: $path"
  package_path_too_broad "$path" && die "refusing overly broad package-manager path: $path"
  package_path_too_broad "$source" && die "refusing overly broad package-manager path: $source"
  in_forbidden_bind_dir "$source" && die "refusing credential path for package manager: $source"
  PACKAGE_BINDS+=(--ro-bind "$source" "$path")
}

prepare_package_managers() {
  PACKAGE_ROOTS=()
  PACKAGE_FILES=()
  PACKAGE_BINDS=()
  PACKAGE_PATH_DIRS=()
  PACKAGE_ENV=()
  MISSING_PACKAGE_MANAGERS=()
  MISSING_PACKAGE_RUNTIMES=()
  local manager executable resolved prefix path runtime
  for manager in "${PACKAGE_MANAGERS[@]+"${PACKAGE_MANAGERS[@]}"}"; do
    if ! executable="$(package_host_program "$manager")"; then
      MISSING_PACKAGE_MANAGERS+=("$manager")
      continue
    fi
    case "$manager" in
      cargo)
        for path in .cargo/bin .cargo/registry .cargo/git .rustup/toolchains; do
          package_root "$REAL_HOME/$path"
        done
        package_settings_file "$REAL_HOME/.rustup/settings.toml"
        PACKAGE_PATH_DIRS+=("$REAL_HOME/.cargo/bin")
        PACKAGE_ENV+=(--setenv CARGO_HOME "$REAL_HOME/.cargo" --setenv RUSTUP_HOME "$REAL_HOME/.rustup")
        ;;
      bun)
        for path in .bun/bin .bun/install/global .bun/install/cache; do
          package_root "$REAL_HOME/$path"
        done
        PACKAGE_PATH_DIRS+=("$REAL_HOME/.bun/bin")
        PACKAGE_ENV+=(--setenv BUN_INSTALL "$REAL_HOME/.bun"
          --setenv BUN_INSTALL_CACHE_DIR "$REAL_HOME/.bun/install/cache")
        ;;
      deno)
        package_root "$REAL_HOME/.deno/bin"
        package_root "$REAL_HOME/.cache/deno"
        PACKAGE_PATH_DIRS+=("$REAL_HOME/.deno/bin")
        PACKAGE_ENV+=(--setenv DENO_INSTALL_ROOT "$REAL_HOME/.deno"
          --setenv DENO_DIR "$REAL_HOME/.cache/deno")
        ;;
      pip)
        package_root "$REAL_HOME/.cache/pip"
        if ! runtime="$(package_host_program python3)"; then
          MISSING_PACKAGE_RUNTIMES+=("python3")
        else
          package_pip_tools
          PACKAGE_ENV+=(--setenv PYTHONUSERBASE "$REAL_HOME/.local"
            --setenv PIP_CACHE_DIR "$REAL_HOME/.cache/pip")
          package_executable "$runtime"
        fi
        ;;
      uv)
        package_root "$REAL_HOME/.local/share/uv/tools"
        package_root "$REAL_HOME/.local/share/uv/python"
        package_root "$REAL_HOME/.cache/uv"
        PACKAGE_ENV+=(--setenv UV_TOOL_DIR "$REAL_HOME/.local/share/uv/tools"
          --setenv UV_PYTHON_INSTALL_DIR "$REAL_HOME/.local/share/uv/python"
          --setenv UV_CACHE_DIR "$REAL_HOME/.cache/uv")
        shopt -s nullglob
        for path in "$REAL_HOME"/.local/share/uv/tools/*/bin; do
          PACKAGE_PATH_DIRS+=("$path")
        done
        shopt -u nullglob
        ;;
      pnpm)
        package_root "$REAL_HOME/.local/share/pnpm"
        package_root "$REAL_HOME/.cache/pnpm"
        PACKAGE_PATH_DIRS+=("$REAL_HOME/.local/share/pnpm")
        [[ ! -d "$REAL_HOME/.local/share/pnpm/bin" ]] || PACKAGE_PATH_DIRS+=("$REAL_HOME/.local/share/pnpm/bin")
        PACKAGE_ENV+=(--setenv PNPM_HOME "$REAL_HOME/.local/share/pnpm")
        ;;
      npm)
        # npm's resolved CLI identifies the active prefix, including NVM and a
        # home prefix. Mount only the module tree and bin shims.
        resolved="$(readlink -f -- "$executable")"
        case "$resolved" in
          */lib/node_modules/npm/bin/npm-cli.js)
            prefix="${resolved%/lib/node_modules/npm/bin/npm-cli.js}"
            [[ -n "$prefix" ]] || prefix=/
            if ! in_base_mounts "$prefix"; then
              package_root "$prefix/lib/node_modules"
              package_root "$prefix/bin"
              PACKAGE_PATH_DIRS+=("$prefix/bin")
            fi
            ;;
        esac
        package_root "$REAL_HOME/.npm-global"
        package_root "$REAL_HOME/.npm/_cacache"
        [[ ! -d "$REAL_HOME/.npm-global/bin" ]] || PACKAGE_PATH_DIRS+=("$REAL_HOME/.npm-global/bin")
        ;;
    esac
    package_executable "$executable"
    if [[ "$manager" == npm || "$manager" == pnpm ]]; then
      if ! runtime="$(package_host_program node)"; then
        MISSING_PACKAGE_RUNTIMES+=("node")
        continue
      fi
      package_executable "$runtime"
    fi
  done
}

require_package_manager_for_command() {
  local name="${1##*/}" missing
  for missing in "${MISSING_PACKAGE_MANAGERS[@]+"${MISSING_PACKAGE_MANAGERS[@]}"}"; do
    [[ "$name" == "$missing" ]] && die "not available: $missing"
  done
  case "$name" in
    node|npm|pnpm)
      for missing in "${MISSING_PACKAGE_RUNTIMES[@]+"${MISSING_PACKAGE_RUNTIMES[@]}"}"; do
        [[ "$missing" == node ]] && die "not available: node"
      done
      ;;
    python3|pip)
      for missing in "${MISSING_PACKAGE_RUNTIMES[@]+"${MISSING_PACKAGE_RUNTIMES[@]}"}"; do
        [[ "$missing" == python3 ]] && die "not available: python3"
      done
      ;;
  esac
}

package_command_visible() {
  local command="$1" path resolved root
  local -a candidates=()
  if [[ "$command" == */* ]]; then
    if [[ "$command" == /* ]]; then candidates+=("$command"); else candidates+=("$WORKDIR/$command"); fi
  else
    for path in "${PACKAGE_PATH_DIRS[@]+"${PACKAGE_PATH_DIRS[@]}"}"; do
      candidates+=("$path/$command")
    done
  fi
  for path in "${candidates[@]+"${candidates[@]}"}"; do
    [[ -x "$path" && ! -d "$path" ]] || continue
    for root in "${PACKAGE_FILES[@]+"${PACKAGE_FILES[@]}"}"; do
      [[ "$path" == "$root" ]] && return 0
    done
    resolved="$(readlink -f -- "$path")" || continue
    for root in "${PACKAGE_ROOTS[@]+"${PACKAGE_ROOTS[@]}"}"; do
      case "$path" in
        "$root"/*)
          # A tool's symlink target must also be visible in the sandbox.
          in_base_mounts "$resolved" && return 0
          local target
          for target in "${PACKAGE_ROOTS[@]}"; do
            case "$resolved" in "$target"/*) return 0 ;; esac
          done
          ;;
      esac
    done
  done
  return 1
}

classify_invocation() {
  local cmd="$1" path physical
  INVOKE_NAME="${cmd##*/}"
  INVOKE_NEEDS_EXTRA=false
  INVOKE_BOUND=""
  INVOKE_PATH=""
  if package_command_visible "$cmd"; then
    return 0
  fi
  if [[ "$cmd" == */* ]]; then
    if [[ "$cmd" == /* ]]; then
      path="$cmd"
    else
      path="$WORKDIR/$cmd"
    fi
    if [[ -e "$path" || -L "$path" ]]; then
      physical="$(readlink -f -- "$path" 2>/dev/null || true)"
      if [[ -n "$physical" ]]; then
        case "$physical" in
          "$PROJECT"|"$PROJECT"/*) return 0 ;;
        esac
        if in_base_mounts "$path" || in_base_mounts "$physical"; then
          return 0
        fi
      fi
    fi
    if ! name_listed "$INVOKE_NAME"; then
      die "not in extra-commands: $INVOKE_NAME"
    fi
    INVOKE_NEEDS_EXTRA=true
    INVOKE_PATH="$path"
    return 0
  fi
  if sandbox_visible "$cmd"; then
    return 0
  fi
  if ! name_listed "$cmd"; then
    die "not in extra-commands: $cmd"
  fi
  INVOKE_NEEDS_EXTRA=true
}

bind_extra_commands() {
  EXTRA_BINDS=()
  EXTRA_PATH_DIRS=()
  local name resolved status parent seen=""
  for name in "${EXTRA_NAMES[@]+"${EXTRA_NAMES[@]}"}"; do
    case " $seen " in
      *" $name "*) continue ;;
    esac
    seen+=" $name"
    resolved=""
    status=0
    resolved="$(lookup_host_command "$name")" || status=$?
    if [[ "$status" -ne 0 ]]; then
      if [[ "$INVOKE_NEEDS_EXTRA" == true && "$name" == "$INVOKE_NAME" ]]; then
        die "not available: $name"
      fi
      continue
    fi
    if ! closure_ok "$resolved"; then
      if [[ "$INVOKE_NEEDS_EXTRA" == true && "$name" == "$INVOKE_NAME" ]]; then
        die "not available: $name"
      fi
      continue
    fi
    EXTRA_BINDS+=(--ro-bind "$resolved" "$resolved")
    parent="$(dirname "$resolved")"
    local existing_dir
    local seen_dir=0
    for existing_dir in "${EXTRA_PATH_DIRS[@]+"${EXTRA_PATH_DIRS[@]}"}"; do
      if [[ "$existing_dir" == "$parent" ]]; then
        seen_dir=1
      fi
    done
    if [[ "$seen_dir" -eq 0 ]]; then
      EXTRA_PATH_DIRS+=("$parent")
    fi
    if [[ "$name" == "$INVOKE_NAME" ]]; then
      INVOKE_BOUND="$resolved"
    fi
  done
  if [[ "$INVOKE_NEEDS_EXTRA" == true ]]; then
    [[ -n "$INVOKE_BOUND" ]] || die "not available: $INVOKE_NAME"
    if [[ -n "$INVOKE_PATH" ]]; then
      local wanted bound
      wanted="$(readlink -f -- "$INVOKE_PATH" 2>/dev/null || true)"
      bound="$(readlink -f -- "$INVOKE_BOUND")"
      [[ -n "$wanted" && "$wanted" == "$bound" ]] || die "not available: $INVOKE_NAME"
    fi
  fi
}

validate_host_metadata() {
  local git_dir hooks config name
  if git_clean config --get core.hooksPath >/dev/null 2>&1; then
    die "core.hooksPath is set; refusing host execution until it is removed and hooks are reviewed"
  fi
  if git_clean config --local --get core.sshCommand >/dev/null 2>&1; then
    die "core.sshCommand is set; refusing host execution"
  fi
  git_dir="$(git_clean rev-parse --absolute-git-dir)"
  hooks="$git_dir/hooks"
  config="$git_dir/config"
  [[ ! -L "$git_dir" && ! -L "$hooks" && ! -L "$config" ]] || die "refusing symlinked Git metadata"
  if [[ -d "$hooks" ]]; then
    while IFS= read -r -d '' name; do
      [[ ! -L "$name" ]] || die "refusing symlinked hook: $name"
    done < <(find -P "$hooks" -mindepth 1 -maxdepth 1 -print0)
  fi
  [[ ! -L "$PROJECT/.pre-commit-config.yaml" ]] || die "refusing symlinked .pre-commit-config.yaml"
}

hooks_fingerprint() {
  local git_dir hooks config name
  validate_host_metadata
  git_dir="$(git_clean rev-parse --absolute-git-dir)"
  hooks="$git_dir/hooks"
  config="$git_dir/config"
  {
    printf 'v1\n'
    if [[ -d "$hooks" ]]; then
      while IFS= read -r -d '' name; do
        printf 'hook %s ' "${name##*/}"
        sha256sum -- "$name"
      done < <(find -P "$hooks" -mindepth 1 -maxdepth 1 -print0 | sort -z)
    fi
    if [[ -f "$config" ]]; then
      printf 'config '
      sha256sum -- "$config"
    fi
    if [[ -f "$PROJECT/.pre-commit-config.yaml" ]]; then
      printf 'precommit '
      sha256sum -- "$PROJECT/.pre-commit-config.yaml"
    fi
  } | sha256sum | awk '{print $1}'
}

resolve_host_executable() {
  local name="$1" entry physical resolved
  local IFS=':'
  local -a entries=()
  read -r -a entries <<<"${HOST_PATH:-$PATH}"
  for entry in "${entries[@]}"; do
    [[ -n "$entry" && -d "$entry" ]] || continue
    physical="$(canonical_dir "$entry" 2>/dev/null)" || continue
    case "$physical" in
      "$PROJECT"|"$PROJECT"/*) continue ;;
    esac
    [[ -x "$entry/$name" && ! -d "$entry/$name" ]] || continue
    path_has_symlink_component "$entry/$name" && return 1
    resolved="$(readlink -f -- "$entry/$name")"
    case "$resolved" in
      "$PROJECT"|"$PROJECT"/*) continue ;;
    esac
    printf '%s\n' "$resolved"
    return 0
  done
  return 1
}

resolve_bwrap() {
  local candidate
  for candidate in /usr/bin/bwrap /bin/bwrap; do
    if [[ -x "$candidate" && ! -L "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  die "Bubblewrap (bwrap) is required at /usr/bin/bwrap or /bin/bwrap" 69
}

add_runtime() {
  local path target
  for path in /usr /bin /sbin /lib /lib64; do
    if [[ -L "$path" ]]; then
      target="$(readlink "$path")"
      RUNTIME+=(--symlink "$target" "$path")
    elif [[ -d "$path" ]]; then
      RUNTIME+=(--ro-bind "$path" "$path")
    fi
  done
  for path in /etc/ld.so.cache /etc/alternatives; do
    if [[ -e "$path" && ! -L "$path" ]]; then
      RUNTIME+=(--ro-bind "$path" "$path")
    fi
  done
}

add_project_parents() {
  local mount_parent="" part
  local -a parts=()
  IFS=/ read -r -a parts <<<"${PROJECT#/}"
  for part in "${parts[@]:0:${#parts[@]}-1}"; do
    mount_parent+="/$part"
    PARENTS+=(--dir "$mount_parent")
  done
}

resolver_target_allowed() {
  local canonical="$1"
  case "$canonical" in
    "$REAL_HOME"|"$REAL_HOME"/*)
      return 1
      ;;
  esac
  if in_forbidden_bind_dir "$canonical"; then
    return 1
  fi
  case "$canonical" in
    /etc|/etc/*|/run|/run/*) return 0 ;;
  esac
  return 1
}

copy_network_files() {
  local path canonical fd
  [[ "$SHARE_NET" == true ]] || return 0
  for path in /etc/resolv.conf /etc/hosts; do
    [[ -e "$path" || -L "$path" ]] || continue
    canonical="$(readlink -f -- "$path")" || die "refusing resolver path: $path"
    if ! resolver_target_allowed "$canonical"; then
      die "refusing resolver path: $canonical"
    fi
    [[ -f "$canonical" && ! -L "$canonical" && ! -d "$canonical" ]] || die "refusing resolver path: $canonical"
    exec {fd}<"$canonical"
    NETWORK_FDS+=("$fd")
    NETWORK+=(--ro-bind-data "$fd" "$path")
  done
  for path in /etc/ssl/certs /etc/pki/tls/certs; do
    [[ -e "$path" || -L "$path" ]] || continue
    canonical="$(readlink -f -- "$path" 2>/dev/null || true)"
    if [[ -n "$canonical" ]]; then
      case "$canonical" in
        "$REAL_HOME"|"$REAL_HOME"/*)
          die "refusing to mount host configuration for network: $canonical"
          ;;
      esac
      if in_forbidden_bind_dir "$canonical"; then
        die "refusing to mount host configuration for network: $canonical"
      fi
    fi
    [[ -d "$path" && ! -L "$path" ]] || continue
    [[ -n "$canonical" ]] || die "refusing to mount host configuration for network: $path"
    case "$canonical" in
      /etc|/etc/*) NETWORK+=(--ro-bind "$path" "$path") ;;
    esac
  done
}

run_sandboxed() {
  local bwrap network="off"
  bwrap="$(resolve_bwrap)"
  RUNTIME=()
  PARENTS=()
  NETWORK=()
  NETWORK_FDS=()
  add_runtime
  add_project_parents
  copy_network_files
  sandbox_path_dirs
  local -a args=(
    --unshare-all
    --unshare-user
    --disable-userns
    --new-session
    --die-with-parent
    --cap-drop ALL
    --clearenv
    --setenv PATH "$SANDBOX_PATH"
    --setenv HOME /tmp/bwrap-home
    --setenv TMPDIR /tmp
    --setenv PWD "$WORKDIR"
  )
  if [[ "$SHARE_NET" == true ]]; then
    args+=(--share-net)
    network="on"
  fi
  args+=("${RUNTIME[@]}")
  args+=(--proc /proc --dev /dev --size 1073741824 --tmpfs /tmp --dir /tmp/bwrap-home)
  args+=("${PARENTS[@]+"${PARENTS[@]}"}")
  args+=(--bind "$PROJECT" "$PROJECT")
  args+=("${MASKS[@]+"${MASKS[@]}"}")
  args+=("${NETWORK[@]+"${NETWORK[@]}"}")
  args+=("${EXTRA_BINDS[@]+"${EXTRA_BINDS[@]}"}")
  args+=("${PACKAGE_BINDS[@]+"${PACKAGE_BINDS[@]}"}")
  args+=("${PACKAGE_ENV[@]+"${PACKAGE_ENV[@]}"}")
  local -a cmd=("$@")
  if [[ -n "${INVOKE_BOUND:-}" && "$INVOKE_NEEDS_EXTRA" == true ]]; then
    cmd[0]="$INVOKE_BOUND"
  fi
  args+=(--chdir "$WORKDIR" -- "${cmd[@]}")
  print_status sandbox "$network" "$@"
  exec "$bwrap" "${args[@]}" < /dev/null
}

scrub_host_path() {
  local IFS=':' entry physical out=""
  local -a entries=()
  read -r -a entries <<<"${HOST_PATH:-}"
  for entry in "${entries[@]}"; do
    [[ -n "$entry" && "$entry" == /* && -d "$entry" ]] || continue
    physical="$(canonical_dir "$entry" 2>/dev/null)" || continue
    case "$physical" in
      "$PROJECT"|"$PROJECT"/*) continue ;;
    esac
    out+="${out:+:}$entry"
  done
  printf '%s\n' "$out"
}

ssh_auth_sock_ok() {
  local sock="$1"
  [[ -n "$sock" && "$sock" == /* && -S "$sock" && ! -L "$sock" ]] || return 1
  path_has_symlink_component "$sock" && return 1
  return 0
}

git_clean() {
  local -a cmd=(env -i PATH="$HOST_CLEAN_PATH" HOME="$REAL_HOME" USER="$REAL_USER")
  if [[ -n "${HOST_CLEAN_SSH:-}" ]]; then
    cmd+=(SSH_AUTH_SOCK="$HOST_CLEAN_SSH")
  fi
  cmd+=(git -C "$PROJECT")
  "${cmd[@]}" "$@"
}

prepare_host_environment() {
  HOST_CLEAN_PATH="$(scrub_host_path)"
  [[ -n "$HOST_CLEAN_PATH" ]] || die "refusing host execution with empty PATH"
  HOST_CLEAN_SSH=""
  if [[ "$1" == git && "${2:-}" == push ]] && ssh_auth_sock_ok "${SSH_AUTH_SOCK:-}"; then
    HOST_CLEAN_SSH="$SSH_AUTH_SOCK"
  fi
}

run_host() {
  local fingerprint resolved
  prepare_host_environment "$@"
  fingerprint="$(hooks_fingerprint)"
  resolved="$(resolve_host_executable "$1")" || die "refusing host executable resolved inside the project or missing from PATH: $1"
  [[ "$fingerprint" == "$(hooks_fingerprint)" ]] || die "hook or Git config fingerprint changed; refusing host execution"
  print_status host host "$@"
  shift
  cd -- "$WORKDIR"
  local -a cmd=(env -i PATH="$HOST_CLEAN_PATH" HOME="$REAL_HOME" USER="$REAL_USER")
  if [[ -n "$HOST_CLEAN_SSH" ]]; then
    cmd+=(SSH_AUTH_SOCK="$HOST_CLEAN_SSH")
  fi
  cmd+=("$resolved")
  exec "${cmd[@]}" "$@" < /dev/null
}

prepare_project_masks() {
  add_default_protected
  scan_inodes
  MASKS=()
  PROTECTED_ABS=()
  local relative
  for relative in "${PROTECTED_RELS[@]}"; do
    classify_protected "$relative"
  done
  mask_git_pointer
}

run_command() {
  [[ "$#" -ge 1 ]] || usage
  resolve_project
  resolve_real_home
  refuse_project_contains_home
  load_operator_config
  prepare_project_masks
  if host_line_matches "$@"; then
    run_host "$@"
  fi
  if is_git_host_command "$@"; then
    die "not in host-commands: git $2"
  fi
  prepare_package_managers
  require_package_manager_for_command "$1"
  classify_invocation "$1"
  SHARE_NET=false
  if network_line_matches "$@"; then
    SHARE_NET=true
  fi
  bind_extra_commands
  run_sandboxed "$@"
}

clear_git_environment() {
  local key
  while IFS= read -r key; do
    [[ -n "$key" ]] || continue
    unset "$key"
  done < <(compgen -v GIT_)
}

main() {
  umask 077
  HOST_PATH="${PATH-}"
  clear_git_environment
  reject_caller_config "${1:-}"
  case "${1:-}" in
    record-approval)
      resolve_real_home
      die "record-approval does not grant authority; edit $REAL_HOME/.config/bubblewrap-isolation (extra-commands, network-commands, host-commands, package-managers)"
      ;;
    --)
      shift
      run_command "$@"
      ;;
    *) usage ;;
  esac
}

main "$@"
