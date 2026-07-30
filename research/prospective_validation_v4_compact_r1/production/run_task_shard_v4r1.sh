#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$#" -ne 6 ]]; then
  echo "usage: $0 MODE POLICY TASK_ORDINAL ATTEMPT_ID PORT OUTPUT" >&2
  exit 64
fi

mode="$1"
policy="$2"
task_ordinal="$3"
attempt_id="$4"
port="$5"
output="$6"

root="/workspace/lerobot-safety"
v3b="${root}/research/prospective_validation_v3b"
v3b1_remote="${root}/research/prospective_validation_v3b1/remote"
production="${root}/research/prospective_validation_v4_compact_r1/production"
robocasa_python="${root}/.venv-robocasa-v2-py311/bin/python"
lock="${root}/control/cdse_formal_single_executor.lock"
task_file="${v3b}/benchmark/task_set_target50.txt"

if [[ "${mode}" != "zero" && "${mode}" != "learned" ]]; then
  echo "INVALID_MODE:${mode}" >&2
  exit 64
fi
if [[ "${policy}" != "pi0" && "${policy}" != "pi05" && "${policy}" != "groot" ]]; then
  echo "INVALID_POLICY:${policy}" >&2
  exit 64
fi
if [[ ! "${task_ordinal}" =~ ^[0-9]+$ ]] || (( task_ordinal < 0 || task_ordinal >= 50 )); then
  echo "INVALID_TASK_ORDINAL:${task_ordinal}" >&2
  exit 64
fi
if [[ ! "${port}" =~ ^[0-9]+$ ]] || (( port < 1024 || port > 65535 )); then
  echo "INVALID_PORT:${port}" >&2
  exit 64
fi
if [[ -e "${output}" ]]; then
  echo "REFUSE_EXISTING_TASK_SHARD:${output}" >&2
  exit 2
fi
mkdir -p "$(dirname "${output}")"
mkdir "${output}"
mkdir "${output}/server"

task="$(
  awk -v target="$((task_ordinal + 1))" \
    'NF && $1 !~ /^#/ {count++; if (count == target) {print; exit}}' \
    "${task_file}"
)"
if [[ -z "${task}" ]]; then
  echo "EMPTY_TASK:${task_ordinal}" >&2
  exit 65
fi

if [[ "${policy}" == "groot" ]]; then
  server_python="${root}/.venv-groot-robocasa-v2-py311/bin/python"
else
  server_python="${root}/.venv-openpi-robocasa-v2-py311/bin/python"
fi

if [[ "${V4R1_PARENT_LOCK_HELD:-0}" != "1" ]]; then
  exec 9>"${lock}"
  if ! flock -n 9; then
    echo "SINGLE_EXECUTOR_LOCK_REFUSED" >&2
    exit 73
  fi
fi

export V4R1_IPC_TOKEN
V4R1_IPC_TOKEN="$(openssl rand -hex 32)"
export PYTHONPATH="${v3b1_remote}:${v3b}/scripts:${production}:${PYTHONPATH:-}"
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl

set +e
"${server_python}" "${production}/formal_policy_server_v4r1.py" \
  --policy "${policy}" \
  --mode "${mode}" \
  --attempt-id "${attempt_id}" \
  --task "${task}" \
  --task-ordinal "${task_ordinal}" \
  --port "${port}" \
  --output "${output}/server" \
  >"${output}/server.stdout.log" 2>"${output}/server.stderr.log" &
server_pid=$!
printf '%s\n' "${server_pid}" >"${output}/server.pid"

ready=0
for _ in $(seq 1 300); do
  if [[ -f "${output}/server/server_ready.json" ]]; then
    ready=1
    break
  fi
  if ! kill -0 "${server_pid}" 2>/dev/null; then
    break
  fi
  sleep 2
done
if [[ "${ready}" -ne 1 ]]; then
  if kill -0 "${server_pid}" 2>/dev/null; then
    kill "${server_pid}" 2>/dev/null
  fi
  wait "${server_pid}"
  server_status=$?
  printf '%s\n' "${server_status}" >"${output}/server.exit_code.txt"
  printf '%s\n' "74" >"${output}/client.exit_code.txt"
  printf '%s\n' "74" >"${output}/controller.exit_code.txt"
  echo "SERVER_NOT_READY" >&2
  exit 74
fi

"${robocasa_python}" "${production}/formal_rollout_client_v4r1.py" \
  --policy "${policy}" \
  --mode "${mode}" \
  --attempt-id "${attempt_id}" \
  --task-ordinal "${task_ordinal}" \
  --port "${port}" \
  --output "${output}" \
  >"${output}/client.stdout.log" 2>"${output}/client.stderr.log"
client_status=$?
printf '%s\n' "${client_status}" >"${output}/client.exit_code.txt"
if [[ "${client_status}" -ne 0 ]] && kill -0 "${server_pid}" 2>/dev/null; then
  kill "${server_pid}" 2>/dev/null
fi
wait "${server_pid}"
server_status=$?
printf '%s\n' "${server_status}" >"${output}/server.exit_code.txt"
set -e

if [[ "${client_status}" -ne 0 || "${server_status}" -ne 0 ]]; then
  printf '%s\n' "1" >"${output}/controller.exit_code.txt"
  echo "FAIL_V4R1_TASK_SHARD_RUNTIME client=${client_status} server=${server_status}" >&2
  exit 1
fi

set +e
"${robocasa_python}" "${production}/seal_task_shard_v4r1.py" \
  --policy "${policy}" \
  --mode "${mode}" \
  --attempt-id "${attempt_id}" \
  --task "${task}" \
  --task-ordinal "${task_ordinal}" \
  --output "${output}" \
  >"${output}/seal.stdout.log" 2>"${output}/seal.stderr.log"
seal_status=$?
set -e
printf '%s\n' "${seal_status}" >"${output}/seal.exit_code.txt"
if [[ "${seal_status}" -ne 0 ]]; then
  printf '%s\n' "1" >"${output}/controller.exit_code.txt"
  echo "FAIL_V4R1_TASK_SHARD_SEAL status=${seal_status}" >&2
  exit 1
fi
printf '%s\n' "0" >"${output}/controller.exit_code.txt"

echo "PASS_V4R1_TASK_SHARD policy=${policy} task=${task} mode=${mode}"
