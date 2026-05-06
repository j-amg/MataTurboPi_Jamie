#!/usr/bin/env bash
set -euo pipefail

# FastDDS multicast reduction helper for Ubuntu 22.04 / ROS 2 Humble robots.
#
# Context:
# - TurboPi robots here use ROS 2 Humble with rmw_fastrtps_cpp.
# - FastDDS commonly emits multicast discovery traffic on UDP 7400.
# - FastDDS documentation indicates multicast can be avoided when peers are
#   known/configured and unicast metatraffic locators are used.
# - For a larger fleet later, a Discovery Server design may be a better fit
#   than per-robot static configuration.
#
# This script:
# - Detects the wlan0 IPv4 address
# - Writes /etc/fastdds/no_multicast.xml
# - Sets FASTRTPS_DEFAULT_PROFILES_FILE in common environments
# - Optionally restarts ROS-related processes if --restart-ros is passed
#
# Safe to run repeatedly.

XML_PATH="/etc/fastdds/no_multicast.xml"
XML_DIR="/etc/fastdds"
ENV_FILE="/etc/environment"
UBUNTU_HOME="/home/ubuntu"
ZSHRC="${UBUNTU_HOME}/.zshrc"
BASHRC="${UBUNTU_HOME}/.bashrc"
EXPORT_LINE='FASTRTPS_DEFAULT_PROFILES_FILE=/etc/fastdds/no_multicast.xml'
SCRIPT_NAME="$(basename "$0")"
RESTART_ROS=0

log() {
  printf '[fastdds-no-multicast] %s\n' "$*"
}

warn() {
  printf '[fastdds-no-multicast] WARN: %s\n' "$*" >&2
}

die() {
  printf '[fastdds-no-multicast] ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  sudo bash setup_fastdds_no_multicast.sh [--restart-ros] [--rollback]

Options:
  --restart-ros   Cautiously stop common ROS-related processes after config write
  --rollback      Restore the latest XML backup and remove env lines
  -h, --help      Show this help
EOF
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "Run as root, for example: sudo bash setup_fastdds_no_multicast.sh"
  fi
}

get_wifi_ip() {
  ip -4 addr show wlan0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 | head -n1
}

backup_file() {
  local path="$1"
  if [[ -f "${path}" ]]; then
    local ts
    ts="$(date +%Y%m%d_%H%M%S)"
    cp -a "${path}" "${path}.bak.${ts}"
  fi
}

backup_xml_if_present() {
  if [[ -f "${XML_PATH}" ]]; then
    local ts
    ts="$(date +%Y%m%d_%H%M%S)"
    local backup="${XML_PATH}.bak.${ts}"
    cp -a "${XML_PATH}" "${backup}"
    log "Backed up existing XML to ${backup}"
  fi
}

write_xml() {
  local wifi_ip="$1"
  mkdir -p "${XML_DIR}"
  cat > "${XML_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8" ?>
<profiles xmlns="http://www.eprosima.com">
  <participant profile_name="initial_peers_multicast_avoidance" is_default_profile="true">
    <rtps>
      <builtin>
        <metatrafficUnicastLocatorList>
          <locator>
            <udpv4>
              <address>${wifi_ip}</address>
              <port>7412</port>
            </udpv4>
          </locator>
        </metatrafficUnicastLocatorList>
      </builtin>
    </rtps>
  </participant>
</profiles>
EOF
  chmod 0644 "${XML_PATH}"
  log "Wrote ${XML_PATH}"
}

validate_xml() {
  if command -v xmllint >/dev/null 2>&1; then
    xmllint --noout "${XML_PATH}"
    log "XML validation passed with xmllint"
  else
    warn "xmllint not found; skipping XML validation"
  fi
}

ensure_line_in_file() {
  local file="$1"
  local line="$2"
  local pattern="$3"

  touch "${file}"

  if grep -Fxq "${line}" "${file}"; then
    log "Line already present in ${file}"
    return 0
  fi

  if grep -Eq "${pattern}" "${file}"; then
    backup_file "${file}"
    python3 - "$file" "$pattern" "$line" <<'PY'
import re
import sys

path, pattern, line = sys.argv[1:]
rx = re.compile(pattern)
with open(path, "r", encoding="utf-8") as f:
    lines = f.read().splitlines()

out = []
replaced = False
for existing in lines:
    if rx.match(existing) and not replaced:
        out.append(line)
        replaced = True
    elif rx.match(existing):
        continue
    else:
        out.append(existing)

with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(out).rstrip("\n") + "\n")
PY
    log "Updated existing FASTRTPS_DEFAULT_PROFILES_FILE in ${file}"
  else
    printf '\n%s\n' "${line}" >> "${file}"
    log "Added FASTRTPS_DEFAULT_PROFILES_FILE to ${file}"
  fi
}

update_environment_files() {
  ensure_line_in_file "${ENV_FILE}" "${EXPORT_LINE}" '^FASTRTPS_DEFAULT_PROFILES_FILE='

  if [[ -f "${ZSHRC}" ]]; then
    ensure_line_in_file "${ZSHRC}" "export ${EXPORT_LINE}" '^export FASTRTPS_DEFAULT_PROFILES_FILE='
  else
    log "${ZSHRC} not present; skipping"
  fi

  if [[ -f "${BASHRC}" ]]; then
    ensure_line_in_file "${BASHRC}" "export ${EXPORT_LINE}" '^export FASTRTPS_DEFAULT_PROFILES_FILE='
  else
    log "${BASHRC} not present; skipping"
  fi
}

restart_ros_processes() {
  log "--restart-ros passed; cautiously stopping common ROS-related processes"
  local patterns=(
    "ros2"
    "launch"
    "component_container"
    "controller"
    "camera"
    "image"
    "rplidar"
    "depthai"
    "realsense"
  )

  for pat in "${patterns[@]}"; do
    log "Trying pkill -f ${pat}"
    pkill -f "${pat}" 2>/dev/null || true
  done

  log "ROS-related process stop attempts complete"
  log "If you use supervisor, docker, or a custom launcher, start the stack again manually"
}

remove_line_if_present() {
  local file="$1"
  local line="$2"
  [[ -f "${file}" ]] || return 0

  python3 - "$file" "$line" <<'PY'
import sys

path, line = sys.argv[1:]
with open(path, "r", encoding="utf-8") as f:
    lines = [s.rstrip("\n") for s in f]

out = [s for s in lines if s != line]
with open(path, "w", encoding="utf-8") as f:
    if out:
        f.write("\n".join(out).rstrip("\n") + "\n")
    else:
        f.write("")
PY
}

rollback() {
  require_root

  local latest_backup
  latest_backup="$(ls -1t "${XML_PATH}".bak.* 2>/dev/null | head -n1 || true)"

  if [[ -n "${latest_backup}" && -f "${latest_backup}" ]]; then
    cp -a "${latest_backup}" "${XML_PATH}"
    log "Restored XML from ${latest_backup}"
  else
    warn "No XML backup found for ${XML_PATH}"
  fi

  remove_line_if_present "${ENV_FILE}" "${EXPORT_LINE}"
  log "Removed variable from ${ENV_FILE}"

  if [[ -f "${ZSHRC}" ]]; then
    remove_line_if_present "${ZSHRC}" "export ${EXPORT_LINE}"
    log "Removed variable from ${ZSHRC}"
  fi

  if [[ -f "${BASHRC}" ]]; then
    remove_line_if_present "${BASHRC}" "export ${EXPORT_LINE}"
    log "Removed variable from ${BASHRC}"
  fi

  cat <<'EOF'

Rollback complete.

You should now:
  1. restart ROS manually, or reboot
  2. retest:
     ros2 doctor --report | grep -i middleware
     sudo tcpdump -i wlan0 udp port 7400
     sudo tcpdump -i wlan0 multicast
EOF
}

print_status() {
  local wifi_ip="$1"
  cat <<EOF

Configuration applied.

Detected wlan0 IP:
  ${wifi_ip}

FastDDS profile:
  ${XML_PATH}

Environment variable:
  ${EXPORT_LINE}

Before/after test commands:
  ros2 doctor --report | grep -i middleware
  sudo tcpdump -i wlan0 udp port 7400
  sudo tcpdump -i wlan0 multicast

Expected result:
  - ROS should still report rmw_fastrtps_cpp
  - UDP 7400 multicast should be reduced or absent after restart/reboot

Rollback:
  sudo bash ${SCRIPT_NAME} --rollback

Recommendation:
  Reboot the robot to ensure every shell, service, and ROS process picks up the new profile.
EOF
}

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --restart-ros)
        RESTART_ROS=1
        shift
        ;;
      --rollback)
        rollback
        exit 0
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "Unknown argument: $1"
        ;;
    esac
  done

  require_root

  local wifi_ip
  wifi_ip="$(get_wifi_ip)"
  if [[ -z "${wifi_ip}" ]]; then
    die "Could not detect an IPv4 address on wlan0"
  fi

  log "Detected wlan0 IP: ${wifi_ip}"

  backup_xml_if_present
  write_xml "${wifi_ip}"
  validate_xml
  update_environment_files

  if [[ "${RESTART_ROS}" -eq 1 ]]; then
    restart_ros_processes
  else
    log "ROS processes were not touched. Pass --restart-ros if you want cautious pkill-based restarts."
  fi

  print_status "${wifi_ip}"
}

main "$@"
