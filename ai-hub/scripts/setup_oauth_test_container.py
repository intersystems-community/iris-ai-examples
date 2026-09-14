#!/usr/bin/env python3
"""
Start or reuse the aihub-oauth-test IRIS container, compile Sample.AI.OAuth.*,
and return the container name so the caller can run irispython tests inside it.

Usage:
    python scripts/setup_oauth_test_container.py [--no-reuse] [--stop]

Exit codes:
    0  — container ready, name printed to stdout
    1  — fatal error
"""

import argparse
import os
import subprocess
import sys
import time

CONTAINER_NAME = "aihub-oauth-test"

# No default image: %AI.* classes ship only in AI Hub builds, and the registry that
# carries them is not public. Set IRIS_IMAGE to whatever tag your `docker load`
# printed, e.g. `<registry>/intersystems/iris-community:2026.3.0AI.141.0`.
IRIS_IMAGE = os.environ.get("IRIS_IMAGE", "")
CLS_DIR = os.path.join(os.path.dirname(__file__), "..", "objectscript", "cls")
NAMESPACE = "USER"

CLASSES = [
    "Sample/AI/OAuth/RBACPolicy.cls",
    "Sample/AI/OAuth/RoleDiscovery.cls",
    "Sample/AI/OAuth/ScopeAuthenticator.cls",
    "Sample/AI/OAuth/OAuthMCPService.cls",
    "Sample/AI/OAuth/DemoToolSet.cls",
    "Sample/AI/OAuth/Setup.cls",
]


def container_running() -> bool:
    r = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", CONTAINER_NAME],
        capture_output=True, text=True,
    )
    return r.returncode == 0 and r.stdout.strip() == "true"


def stop_container():
    if container_running():
        subprocess.run(["docker", "stop", CONTAINER_NAME], check=False)
        subprocess.run(["docker", "rm", CONTAINER_NAME], check=False)
        print(f"Stopped and removed {CONTAINER_NAME}", file=sys.stderr)


def start_container():
    subprocess.run(
        [
            "docker", "run", "-d",
            "--name", CONTAINER_NAME,
            IRIS_IMAGE,
        ],
        check=True,
    )
    _wait_iris_ready()


def _wait_iris_ready(timeout: int = 180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "iris", "qlist"],
            capture_output=True,
        )
        out = r.stdout.decode().lower() + r.stderr.decode().lower()
        if r.returncode == 0 and "running" in out:
            time.sleep(3)
            return
        time.sleep(5)
    # Print last status for debugging
    d = subprocess.run(["docker", "logs", "--tail", "20", CONTAINER_NAME], capture_output=True)
    raise RuntimeError(
        f"{CONTAINER_NAME}: IRIS not ready after {timeout}s\n{d.stdout.decode()}\n{d.stderr.decode()}"
    )


def _load_cls(container_path: str, class_name: str, flags: str = "c") -> tuple[bool, str]:
    """Load and compile a .cls file. Returns (ok, output)."""
    result = subprocess.run(
        [
            "docker", "exec", "-u", "irisowner", "-i", CONTAINER_NAME,
            "iris", "session", "IRIS", "-U", NAMESPACE,
        ],
        input=f'Do $System.OBJ.Load("{container_path}", "{flags}")\nHalt\n'.encode(),
        capture_output=True,
        timeout=60,
    )
    output = result.stdout.decode()
    ok = result.returncode == 0 and "Detected" not in output and "failed" not in output.lower()
    return ok, output


def compile_classes():
    """Load each .cls file into IRIS and compile it."""
    abs_cls_dir = os.path.abspath(CLS_DIR)
    for rel_path in CLASSES:
        host_path = os.path.join(abs_cls_dir, rel_path)
        container_path = f"/tmp/{os.path.basename(rel_path)}"
        subprocess.run(
            ["docker", "cp", host_path, f"{CONTAINER_NAME}:{container_path}"],
            check=True,
        )
        class_name = os.path.basename(rel_path).replace(".cls", "")
        print(f"  Compiling {class_name}...", file=sys.stderr)

        ok, output = _load_cls(container_path, class_name, "c")
        if not ok:
            # %AI.ToolSet subclasses with self-referencing XData need two passes:
            # first pass imports the definition, second pass compiles successfully.
            print(f"    Retrying {class_name} (two-pass compile)...", file=sys.stderr)
            ok2, output2 = _load_cls(container_path, class_name, "ck")
            if not ok2:
                raise RuntimeError(f"Compile errors for {class_name}:\n{output2}")

    # Verify a key class compiled
    verify = subprocess.run(
        [
            "docker", "exec", "-u", "irisowner", "-i", CONTAINER_NAME,
            "iris", "session", "IRIS", "-U", NAMESPACE,
        ],
        input=(
            'Write ##class(%Dictionary.CompiledClass).%ExistsId("Sample.AI.OAuth.RBACPolicy")\n'
            "Halt\n"
        ).encode(),
        capture_output=True,
        timeout=30,
    )
    out = verify.stdout.decode()
    if "1" not in out:
        raise RuntimeError(f"Sample.AI.OAuth.RBACPolicy not compiled: {out}")
    print("  All Sample.AI.OAuth classes compiled OK.", file=sys.stderr)


def unexpire_passwords():
    subprocess.run(
        [
            "docker", "exec", "-u", "irisowner", "-i", CONTAINER_NAME,
            "iris", "session", "IRIS", "-U", "%SYS",
        ],
        input='Do ##class(Security.Users).UnExpireUserPasswords("*")\nHalt\n'.encode(),
        capture_output=True,
        timeout=30,
    )


def enable_callin():
    """Enable %Service_CallIn so irispython embedded mode works."""
    subprocess.run(
        [
            "docker", "exec", "-u", "irisowner", "-i", CONTAINER_NAME,
            "iris", "session", "IRIS", "-U", "%SYS",
        ],
        input=(
            'Kill tProp\n'
            'Set tSC = ##class(Security.Services).Get("%Service_CallIn", .tProp)\n'
            'Set tProp("Enabled") = 1\n'
            'Set tSC = ##class(Security.Services).Modify("%Service_CallIn", .tProp)\n'
            'Halt\n'
        ).encode(),
        capture_output=True,
        timeout=30,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-reuse", action="store_true", help="Force container restart")
    parser.add_argument("--stop", action="store_true", help="Stop and remove container")
    args = parser.parse_args()

    if args.stop:
        stop_container()
        return

    if args.no_reuse and container_running():
        stop_container()

    if not container_running():
        if not IRIS_IMAGE:
            print(
                "IRIS_IMAGE is not set. This script needs an AI Hub IRIS image "
                "(one that ships the %AI.* classes); there is no public default. Load "
                "your EAP tarball and export the tag docker load printed:\n"
                "    export IRIS_IMAGE=<registry>/intersystems/iris-community:<ai-tag>",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Starting {CONTAINER_NAME} ({IRIS_IMAGE})...", file=sys.stderr)
        # Remove any stopped container with same name
        subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)
        start_container()
        unexpire_passwords()
        enable_callin()
        compile_classes()
    else:
        print(f"Reusing existing {CONTAINER_NAME}", file=sys.stderr)
        compile_classes()

    print(CONTAINER_NAME)


if __name__ == "__main__":
    main()
