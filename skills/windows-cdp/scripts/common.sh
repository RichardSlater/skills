# shellcheck shell=bash
# Shared by the WSL launchers; source only from the resolved skill directory.
windows_cdp_validate_port() {
  port="${WINDOWS_CDP_PORT:-9222}"
  # Bound the digit count before arithmetic to prevent integer overflow.
  if [[ ! "$port" =~ ^[0-9]{1,5}$ ]] || (( 10#$port < 1 || 10#$port > 65535 )); then
    printf '%s: invalid WINDOWS_CDP_PORT: %s\n' "${0##*/}" "$port" >&2
    exit 2
  fi
  port=$((10#$port))
}

windows_cdp_find_powershell() {
  ps="$(command -v powershell.exe || true)"
  if [[ -z "$ps" && -x /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe ]]; then
    ps=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
  fi
}
