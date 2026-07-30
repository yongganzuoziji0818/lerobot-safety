#!/usr/bin/env python3
"""Assert that E2 changes only the top-level exit-receipt control flow."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E1 = ROOT / "governance" / "launch_v4r1_e1_prestep_gate_001.sh"
E2 = ROOT / "governance" / "launch_v4r1_e2_prestep_gate_001.sh"


def normalize_attempt(text: str) -> str:
    return text.replace(
        "V4R1-E2-OPENPI-PRESTEP-GATE-001",
        "V4R1-E1-OPENPI-PRESTEP-GATE-001",
    ).replace(
        "LAUNCHED_V4R1_E2_OPENPI_PRESTEP_GATE_001",
        "LAUNCHED_V4R1_E1_OPENPI_PRESTEP_GATE_001",
    ).replace("V4R1_E2_GATE_PORT_IN_USE", "V4R1_E1_GATE_PORT_IN_USE")


def split_launcher(text: str) -> tuple[str, str, str]:
    start = "nohup bash -c '\n"
    end = "' _ \\\n"
    before, remainder = text.split(start, 1)
    body, after = remainder.split(end, 1)
    return before, body, after


def main() -> None:
    e1 = E1.read_text(encoding="utf-8")
    e2 = E2.read_text(encoding="utf-8")
    before1, body1, after1 = split_launcher(normalize_attempt(e1))
    before2, body2, after2 = split_launcher(normalize_attempt(e2))

    # E2 adds exactly one immutable-history verification block before launch.
    # Strip that block structurally so the audit is insensitive to the shell
    # continuation indentation while remaining fail-closed on any other delta.
    lines = before2.splitlines(keepends=True)
    stripped: list[str] = []
    index = 0
    terminal_hash = (
        "8486e77839c7303554a33b5cbd079a09032f66fe3f962da1a10f14762fa7618d"
    )
    terminal_manifest = (
        "V4R1_E1_GATE001_TERMINAL_CONTROL_FAILURE_GOVERNANCE_MANIFEST.sha256"
    )
    removed_hash_block = False
    removed_manifest_check = False
    while index < len(lines):
        if (
            lines[index].startswith("printf '%s  %s\\n'")
            and index + 3 < len(lines)
            and terminal_hash in lines[index + 1]
            and terminal_manifest in lines[index + 2]
            and "sha256sum -c -" in lines[index + 3]
        ):
            index += 4
            removed_hash_block = True
            continue
        if lines[index].strip() == f"sha256sum -c {terminal_manifest}":
            removed_manifest_check = True
            index += 1
            continue
        stripped.append(lines[index])
        index += 1
    assert removed_hash_block
    assert removed_manifest_check
    assert "".join(stripped) == before1
    assert after2 == after1

    for protected in (
        "run_engineering_prestep_gate_v4r1_e1.sh",
        'pi0 0 "${attempt}" 48301 "${gate}/pi0"',
        'pi05 0 "${attempt}" 48302 "${gate}/pi05"',
    ):
        assert protected in body1
        assert protected in body2

    assert 'exit $?' in body1
    assert 'printf "%s\\n" "${status}" >"${exit_path}"' in body2
    assert body2.index('printf "%s\\n" "${status}" >"${exit_path}"') < (
        body2.index('exit "${status}"')
    )
    assert 'exit $?' not in body2
    assert body2.count("status=$?") == 2
    assert 'if [[ "${status}" -eq 0 ]]; then' in body2

    print("PASS_V4R1_E2_LAUNCHER_ONLY_DELTA_AUDIT")


if __name__ == "__main__":
    main()
