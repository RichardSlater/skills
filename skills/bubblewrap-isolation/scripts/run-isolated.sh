#!/usr/bin/env bash
# Fail-closed Bubblewrap launcher for short-lived agent commands.
# Shared approvals live in the committed .bwrap/approvals tree. Working-tree
# edits and repository .bwrap.yaml do not grant authority.
set -euo pipefail

usage() {
  printf 'Usage: %s -- command [argument ...]\n' "${0##*/}" >&2
  printf '       %s record-approval --id ID --execution sandbox|host --note TEXT -- command [argument ...]\n' "${0##*/}" >&2
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
  REL_CWD="."
  if [[ "$WORKDIR" != "$PROJECT" ]]; then
    REL_CWD="${WORKDIR#"$PROJECT"/}"
  fi
}

materialize_committed_approvals() {
  POLICY_DIR=""
  git -C "$PROJECT" rev-parse --verify HEAD >/dev/null 2>&1 || return 0
  git -C "$PROJECT" cat-file -e HEAD:.bwrap/approvals 2>/dev/null || return 0
  if git -C "$PROJECT" ls-tree -r HEAD .bwrap/approvals | awk '$1 == "120000" { found = 1 } END { exit !found }'; then
    die "refusing symlink in committed .bwrap/approvals"
  fi
  POLICY_DIR="$(mktemp -d)"
  git -C "$PROJECT" archive --format=tar HEAD:.bwrap/approvals | tar -x -C "$POLICY_DIR"
  if [[ -n "$(git -C "$PROJECT" status --porcelain -- .bwrap/approvals)" ]]; then
    printf 'warning: uncommitted .bwrap/approvals changes are ignored until committed\n' >&2
  fi
}

cleanup_policy() {
  if [[ -n "${POLICY_DIR:-}" ]]; then
    rm -rf -- "$POLICY_DIR"
    POLICY_DIR=""
  fi
}

path_has_symlink_component() {
  local path="$1" cursor="/" part
  [[ "$path" == /* ]] || return 0
  local rest="${path#/}"
  IFS=/ read -r -a parts <<<"$rest"
  cursor=""
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
  IFS=/ read -r -a parts <<<"$relative"
  for part in "${parts[@]}"; do
    [[ -n "$part" && "$part" != "." && "$part" != ".." ]] || die "unsafe protected path: $relative"
  done
}

assert_no_symlink_chain() {
  local root="$1"
  local relative="$2"
  local cursor="$root"
  local part
  IFS=/ read -r -a parts <<<"$relative"
  for part in "${parts[@]}"; do
    cursor+="/$part"
    if [[ -L "$cursor" ]]; then
      die "refusing symlink in protected path: $cursor"
    fi
  done
}

scan_inodes() {
  local entry id
  declare -gA INODE_PATHS=()
  while IFS= read -r -d '' entry; do
    reject_newline "$entry" "project path"
    id="$(stat -c '%d:%i' -- "$entry")"
    if [[ -n "${INODE_PATHS[$id]+x}" ]]; then
      INODE_PATHS["$id"]+=$'\n'"$entry"
    else
      INODE_PATHS["$id"]="$entry"
    fi
  done < <(find -P "$PROJECT" -xdev \( -type f -o -type d \) -print0)
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
  if [[ "$relative" == ".git/config" || "$relative" == ".git/config" ]]; then
    :
  fi
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

host_command_allowed() {
  [[ "$#" -ge 1 ]] || return 1
  case "$1" in
    git)
      [[ "$#" -ge 2 ]] || return 1
      case "$2" in
        commit|push) return 0 ;;
        *) return 1 ;;
      esac
      ;;
    pre-commit) return 0 ;;
    *) return 1 ;;
  esac
}

validate_host_metadata() {
  local git_dir hooks config name
  if git -C "$PROJECT" config --get core.hooksPath >/dev/null 2>&1; then
    die "core.hooksPath is set; refusing host execution until it is removed and hooks are reviewed"
  fi
  git_dir="$(git -C "$PROJECT" rev-parse --absolute-git-dir)"
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
  git_dir="$(git -C "$PROJECT" rev-parse --absolute-git-dir)"
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

forbidden_mount_source() {
  local src="$1" home
  case "$src" in
    /|/etc|/etc/*|/dev|/dev/*|/proc|/proc/*|/sys|/sys/*|/run|/run/*|/boot|/boot/*|/var|/var/*|/tmp|/tmp/*|/usr|/usr/*|/bin|/bin/*|/lib|/lib/*|/lib64|/lib64/*|/sbin|/sbin/*)
      return 0
      ;;
  esac
  case "$PROJECT" in
    "$src"|"$src"/*) return 0 ;;
  esac
  if [[ -n "${HOME:-}" ]]; then
    home="$(canonical_dir "$HOME")"
    [[ "$src" != "$home" ]] || return 0
    case "$home" in
      "$src"|"$src"/*) return 0 ;;
    esac
    case "$src" in
      "$home/.ssh"|"$home/.ssh"/*|"$home/.gnupg"|"$home/.gnupg"/*|"$home/.aws"|"$home/.aws"/*|"$home/.kube"|"$home/.kube"/*|"$home/.docker"|"$home/.docker"/*|"$home/.config/git"|"$home/.config/git"/*|"$home/.config/gh"|"$home/.config/gh"/*|"$home/.cache/pre-commit"|"$home/.cache/pre-commit"/*|"$home/.config/bubblewrap-isolation"|"$home/.config/bubblewrap-isolation"/*)
        return 0
        ;;
    esac
  fi
  return 1
}

allowed_network_file() {
  local src="$1"
  case "$src" in
    /etc/resolv.conf|/etc/hosts) [[ -f "$src" && ! -L "$src" ]] ;;
    /etc/ssl/certs|/etc/pki/tls/certs) [[ -d "$src" && ! -L "$src" ]] ;;
    *) return 1 ;;
  esac
}

validate_mount() {
  local mode="$1" src="$2"
  [[ "$mode" == ro || "$mode" == rw ]] || die "mount mode must be ro or rw"
  [[ "$src" == /* ]] || die "mount source must be absolute: $src"
  reject_newline "$src" "mount source"
  path_has_symlink_component "$src" && die "refusing symlink in mount source: $src"
  [[ -e "$src" ]] || die "mount source does not exist: $src"
  if [[ -f "$src" ]]; then
    [[ "$(stat -c '%h' -- "$src")" == 1 ]] || die "refusing hard-linked mount source: $src"
  elif [[ ! -d "$src" ]]; then
    die "mount source must be a file or directory: $src"
  fi
  local protected dest_parent
  for protected in "${PROTECTED_ABS[@]+"${PROTECTED_ABS[@]}"}"; do
    if [[ "$src" == "$protected" ]]; then
      [[ "$mode" == ro ]] || die "refusing writable mount over protected path: $src"
      return 0
    fi
    case "$protected" in
      "$src"/*) die "mount would uncover protected path $protected" ;;
    esac
  done
  if allowed_network_file "$src"; then
    [[ "$mode" == ro ]] || die "network prerequisite mounts must be read-only"
    return 0
  fi
  forbidden_mount_source "$src" && die "refusing mount source: $src"
  dest_parent="$(dirname "$src")"
  [[ "$dest_parent" != "$src" ]] || die "refusing mount source: $src"
}

read_tokens() {
  local file="$1"
  TOKEN_BUF=()
  local token
  while IFS= read -r -d '' token || [[ -n "$token" ]]; do
    TOKEN_BUF+=("$token")
  done <"$file"
}

command_matches_array() {
  local match_type="$1" dir="$2"
  shift 2
  local -a want=("$@")
  local i
  [[ "$(<"$dir/cwd")" == "$REL_CWD" ]] || return 1
  read_tokens "$dir/command"
  if [[ "$match_type" == exact ]]; then
    [[ "${#TOKEN_BUF[@]}" -eq "${#want[@]}" ]] || return 1
  elif [[ "$match_type" == prefix ]]; then
    [[ "${#want[@]}" -ge "${#TOKEN_BUF[@]}" && "${#TOKEN_BUF[@]}" -ge 1 ]] || return 1
  else
    return 1
  fi
  for i in "${!TOKEN_BUF[@]}"; do
    [[ "${TOKEN_BUF[$i]}" == "${want[$i]}" ]] || return 1
  done
}

load_matching_approval() {
  MATCHED_DIR=""
  local store id_dir match_type count=0
  store="${POLICY_DIR:-}"
  [[ -n "$store" && -d "$store" ]] || return 0
  [[ ! -L "$store" ]] || die "refusing symlinked approval checkout"
  for id_dir in "$store"/*; do
    [[ -d "$id_dir" && ! -L "$id_dir" ]] || continue
    [[ -f "$id_dir/format" && ! -L "$id_dir/format" ]] || continue
    [[ "$(<"$id_dir/format")" == "1" ]] || die "unknown approval format: $id_dir"
    match_type="$(<"$id_dir/match")"
    local execution
    execution="$(<"$id_dir/execution")"
    if command_matches_array "$match_type" "$id_dir" "$@"; then
      if [[ "$execution" == host ]]; then
        host_command_allowed "$@" || die "host approval is outside the launcher allowlist"
        [[ "$match_type" == prefix ]] || die "host approval must be a prefix match"
      elif [[ "$execution" == sandbox ]]; then
        [[ "$match_type" == exact ]] || die "sandbox approval must be an exact match"
      else
        die "invalid execution record: $execution"
      fi
      count=$((count + 1))
      MATCHED_DIR="$id_dir"
    fi
  done
  [[ "$count" -le 1 ]] || die "multiple approval records match; refusing to combine permissions"
}

resolve_host_executable() {
  local name="$1" entry physical resolved
  local IFS=':'
  local -a entries
  read -r -a entries <<<"${HOST_PATH:-$PATH}"
  for entry in "${entries[@]}"; do
    [[ -n "$entry" && -d "$entry" ]] || continue
    physical="$(canonical_dir "$entry")" || continue
    case "$physical" in
      "$PROJECT"|"$PROJECT"/*) continue ;;
    esac
    [[ -x "$entry/$name" ]] || continue
    resolved="$(readlink -f -- "$entry/$name")"
    case "$resolved" in
      "$PROJECT"|"$PROJECT"/*) continue ;;
    esac
    printf '%s\n' "$resolved"
    return 0
  done
  return 1
}

confirm_or_die() {
  local answer
  [[ -r /dev/tty && -w /dev/tty ]] || die "record-approval requires a controlling terminal"
  printf 'Type "approve" to confirm: ' >/dev/tty
  IFS= read -r answer </dev/tty || die "approval confirmation failed"
  [[ "$answer" == "approve" ]] || die "approval not confirmed"
}

record_approval() {
  local id="" execution="" note="" match="exact" share_net="false" replace=0
  local -a mounts=() protected_extra=()
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --id)
        id="${2:-}"
        shift 2
        ;;
      --execution)
        execution="${2:-}"
        shift 2
        ;;
      --note)
        note="${2:-}"
        shift 2
        ;;
      --match)
        match="${2:-}"
        shift 2
        ;;
      --share-net)
        share_net="true"
        shift
        ;;
      --mount)
        mounts+=("${2:-}" "${3:-}")
        shift 3
        ;;
      --protect)
        protected_extra+=("${2:-}")
        shift 2
        ;;
      --replace)
        replace=1
        shift
        ;;
      --)
        shift
        break
        ;;
      *) usage ;;
    esac
  done
  [[ "$#" -ge 1 ]] || usage
  [[ "$id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || die "invalid approval id"
  [[ "$execution" == sandbox || "$execution" == host ]] || die "execution must be sandbox or host"
  [[ "$match" == exact || "$match" == prefix ]] || die "match must be exact or prefix"
  [[ -n "$note" ]] || die "approval note is required"
  reject_newline "$note" "approval note"
  if [[ "$execution" == host ]]; then
    host_command_allowed "$@" || die "host execution is limited to git commit, git push, and pre-commit"
    [[ "$match" == prefix ]] || die "host approvals must use --match prefix"
    [[ "$share_net" == false && "${#mounts[@]}" -eq 0 ]] || die "host approvals cannot grant sandbox mounts or network"
  else
    [[ "$match" == exact ]] || die "sandbox exceptions must use an exact command match"
  fi
  resolve_project
  local store dest tmp mode src fingerprint="-"
  [[ ! -L "$PROJECT/.bwrap" ]] || die "refusing symlinked .bwrap"
  store="$PROJECT/.bwrap/approvals"
  [[ ! -L "$store" ]] || die "refusing symlinked approval directory"
  mkdir -p -- "$store"
  dest="$store/$id"
  [[ "$replace" -eq 1 || ! -e "$dest" ]] || die "approval id already exists: $id"
  add_default_protected
  scan_inodes
  MASKS=()
  PROTECTED_ABS=()
  local relative
  for relative in "${PROTECTED_RELS[@]}"; do
    classify_protected "$relative"
  done
  mask_git_pointer
  local i
  for ((i = 0; i < ${#mounts[@]}; i += 2)); do
    mode="${mounts[$i]}"
    src="${mounts[$((i + 1))]}"
    validate_mount "$mode" "$src"
  done
  for relative in "${protected_extra[@]+"${protected_extra[@]}"}"; do
    validate_relative "$relative"
  done
  if [[ "$execution" == host ]]; then
    fingerprint="$(hooks_fingerprint)"
  fi
  [[ -r /dev/tty && -w /dev/tty ]] || die "record-approval requires a controlling terminal"
  printf 'Project: %s\nExecution: %s\nMatch: %s\nCWD: %s\nNetwork: %s\nCommand:' "$PROJECT" "$execution" "$match" "$REL_CWD" "$share_net" >/dev/tty
  printf ' %q' "$@" >/dev/tty
  printf '\n' >/dev/tty
  if [[ "${#mounts[@]}" -gt 0 ]]; then
    printf 'Mounts:\n' >/dev/tty
    for ((i = 0; i < ${#mounts[@]}; i += 2)); do
      printf '  %s %s\n' "${mounts[$i]}" "${mounts[$((i + 1))]}" >/dev/tty
    done
  fi
  confirm_or_die
  tmp="$(mktemp -d)"
  printf '1\n' >"$tmp/format"
  printf '%s\n' "$execution" >"$tmp/execution"
  printf '%s\n' "$share_net" >"$tmp/share-net"
  printf '%s\n' "$match" >"$tmp/match"
  printf '%s\n' "$REL_CWD" >"$tmp/cwd"
  printf '%s\n' "$note" >"$tmp/note"
  printf '%s\n' "$fingerprint" >"$tmp/hooks-fingerprint"
  printf '%s\0' "$@" >"$tmp/command"
  : >"$tmp/mounts"
  for ((i = 0; i < ${#mounts[@]}; i += 2)); do
    printf '%s\t%s\n' "${mounts[$i]}" "${mounts[$((i + 1))]}" >>"$tmp/mounts"
  done
  : >"$tmp/protected"
  for relative in "${protected_extra[@]+"${protected_extra[@]}"}"; do
    printf '%s\n' "$relative" >>"$tmp/protected"
  done
  chmod 755 "$tmp"
  chmod 644 "$tmp"/*
  if [[ -L "$dest" ]]; then
    die "refusing symlinked approval id"
  fi
  if [[ -e "$dest" ]]; then
    rm -rf -- "$dest"
  fi
  mv -- "$tmp" "$dest"
  printf 'recorded approval %s in .bwrap/approvals/%s\n' "$id" "$id" >&2
  printf 'inactive until committed; commit it so every clone and machine shares this policy\n' >&2
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
  local -a parts
  IFS=/ read -r -a parts <<<"${PROJECT#/}"
  for part in "${parts[@]:0:${#parts[@]}-1}"; do
    mount_parent+="/$part"
    PARENTS+=(--dir "$mount_parent")
  done
}

copy_network_files() {
  local path fd
  [[ "$SHARE_NET" == true ]] || return 0
  for path in /etc/resolv.conf /etc/hosts; do
    [[ -e "$path" ]] || continue
    exec {fd}<"$path"
    NETWORK_FDS+=("$fd")
    NETWORK+=(--ro-bind-data "$fd" "$path")
  done
  for path in /etc/ssl/certs /etc/pki/tls/certs; do
    if [[ -d "$path" && ! -L "$path" ]]; then
      NETWORK+=(--ro-bind "$path" "$path")
    fi
  done
}

apply_recorded_mounts() {
  local line mode src
  [[ -n "${MATCHED_MOUNTS:-}" && -f "$MATCHED_MOUNTS" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -n "$line" ]] || continue
    mode="${line%%$'\t'*}"
    src="${line#*$'\t'}"
    validate_mount "$mode" "$src"
    if [[ "$mode" == ro ]]; then
      MOUNTS+=(--ro-bind "$src" "$src")
    else
      MOUNTS+=(--bind "$src" "$src")
    fi
  done <"$MATCHED_MOUNTS"
}

run_sandboxed() {
  local bwrap
  bwrap="$(resolve_bwrap)"
  RUNTIME=()
  PARENTS=()
  NETWORK=()
  NETWORK_FDS=()
  MOUNTS=()
  add_runtime
  add_project_parents
  copy_network_files
  apply_recorded_mounts
  local -a args=(
    --unshare-all
    --unshare-user
    --disable-userns
    --new-session
    --die-with-parent
    --cap-drop ALL
    --clearenv
    --setenv PATH /usr/bin:/bin:/usr/sbin:/sbin
    --setenv HOME /tmp/bwrap-home
    --setenv TMPDIR /tmp
    --setenv PWD "$WORKDIR"
  )
  if [[ "$SHARE_NET" == true ]]; then
    args+=(--share-net)
  fi
  args+=("${RUNTIME[@]}")
  args+=(--proc /proc --dev /dev --size 1073741824 --tmpfs /tmp --dir /tmp/bwrap-home)
  args+=("${PARENTS[@]+"${PARENTS[@]}"}")
  args+=(--bind "$PROJECT" "$PROJECT")
  args+=("${MASKS[@]+"${MASKS[@]}"}")
  args+=("${MOUNTS[@]+"${MOUNTS[@]}"}")
  args+=(--chdir "$WORKDIR" -- "$@")
  local network="isolated"
  [[ "$SHARE_NET" == true ]] && network="shared"
  printf 'bubblewrap-isolation: execution=sandbox network=%s project=%s\n' "$network" "$PROJECT" >&2
  exec "$bwrap" "${args[@]}" < /dev/null
}

run_host() {
  local resolved
  host_command_allowed "$@" || die "host execution is limited to git commit, git push, and pre-commit"
  [[ "$MATCHED_FINGERPRINT" == "$(hooks_fingerprint)" ]] || die "hook or Git config fingerprint changed; record a new approval after review"
  resolved="$(resolve_host_executable "$1")" || die "refusing host executable resolved inside the project or missing from PATH: $1"
  shift
  printf 'bubblewrap-isolation: execution=host network=host project=%s\n' "$PROJECT" >&2
  cd -- "$WORKDIR"
  exec "$resolved" "$@" < /dev/null
}

snapshot_match() {
  MATCHED_EXECUTION=""
  MATCHED_SHARE_NET="false"
  MATCHED_FINGERPRINT="-"
  MATCHED_MOUNTS=""
  MATCHED_PROTECTED=""
  [[ -n "$MATCHED_DIR" ]] || return 0
  MATCHED_EXECUTION="$(<"$MATCHED_DIR/execution")"
  MATCHED_SHARE_NET="$(<"$MATCHED_DIR/share-net")"
  MATCHED_FINGERPRINT="$(<"$MATCHED_DIR/hooks-fingerprint")"
  MATCHED_MOUNTS="$(mktemp)"
  MATCHED_PROTECTED="$(mktemp)"
  cp -- "$MATCHED_DIR/mounts" "$MATCHED_MOUNTS"
  cp -- "$MATCHED_DIR/protected" "$MATCHED_PROTECTED"
}

run_command() {
  [[ "$#" -ge 1 ]] || usage
  resolve_project
  materialize_committed_approvals
  add_default_protected
  load_matching_approval "$@"
  if [[ -n "$MATCHED_DIR" ]]; then
    local extra
    while IFS= read -r extra || [[ -n "$extra" ]]; do
      [[ -n "$extra" ]] || continue
      append_unique "$extra"
    done <"$MATCHED_DIR/protected"
  fi
  snapshot_match
  cleanup_policy
  scan_inodes
  MASKS=()
  PROTECTED_ABS=()
  local relative
  for relative in "${PROTECTED_RELS[@]}"; do
    classify_protected "$relative"
  done
  mask_git_pointer
  SHARE_NET="false"
  if [[ "$MATCHED_EXECUTION" == host ]]; then
    run_host "$@"
  fi
  if [[ -n "$MATCHED_EXECUTION" ]]; then
    SHARE_NET="$MATCHED_SHARE_NET"
    [[ "$SHARE_NET" == true || "$SHARE_NET" == false ]] || die "invalid share-net record"
  fi
  run_sandboxed "$@"
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

main() {
  umask 077
  HOST_PATH="${PATH}"
  case "${1:-}" in
    record-approval)
      shift
      record_approval "$@"
      ;;
    --)
      shift
      run_command "$@"
      ;;
    *) usage ;;
  esac
}

main "$@"
