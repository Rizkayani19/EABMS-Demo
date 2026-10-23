import subprocess
import sys
import tempfile
from pathlib import Path

def main():
    wheelhouse = Path(r"D:\ABMS\wheelhouse").resolve()
    requirements = Path(r"D:\ABMS\02_Backend\requirements-runtime.txt").resolve()

    print(f"Testing air-gapped installation using wheelhouse: {wheelhouse}")
    print(f"Requirements file: {requirements}")

    if not wheelhouse.exists():
        print("ERROR: Wheelhouse does not exist!")
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="abms_airgap_") as tmpdir:
        tmp_path = Path(tmpdir)
        print(f"Creating clean isolated virtualenv in: {tmp_path}")
        
        # 1. Create venv
        res = subprocess.run([sys.executable, "-m", "venv", str(tmp_path)], capture_output=True, text=True)
        if res.returncode != 0:
            print("Failed to create venv:", res.stderr)
            sys.exit(1)

        pip_exe = str(tmp_path / "Scripts" / "pip.exe")
        python_exe = str(tmp_path / "Scripts" / "python.exe")

        # 2. Strict offline install: --no-index ensures 0 network traffic
        cmd = [
            pip_exe, "install",
            "--no-index",
            "--find-links", str(wheelhouse),
            "-r", str(requirements)
        ]
        print(f"Executing: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        print("--- PIP OUTPUT ---")
        print(res.stdout)
        if res.returncode != 0:
            print("--- PIP ERROR ---")
            print(res.stderr)
            print("FAILED: Offline installation could not find required wheels.")
            sys.exit(1)

        # 3. Test imports inside the newly installed air-gapped environment
        test_code = (
            "import django, openpyxl, reportlab, waitress, whitenoise, PIL, psycopg2, dotenv; "
            "print('DJANGO VERSION:', django.__version__); "
            "print('OPENPYXL VERSION:', openpyxl.__version__); "
            "print('REPORTLAB VERSION:', reportlab.__version__); "
            "print('WAITRESS IMPORT: SUCCESS'); "
            "print('PILLOW VERSION:', PIL.__version__); "
            "print('PSYCOPG2 VERSION:', psycopg2.__version__); "
            "print('ALL OFFLINE DEPENDENCIES VERIFIED 100% AIR-GAPPED READY!')"
        )
        res = subprocess.run([python_exe, "-c", test_code], capture_output=True, text=True)
        print("--- IMPORT VERIFICATION ---")
        print(res.stdout)
        if res.returncode != 0:
            print("Import error:", res.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
