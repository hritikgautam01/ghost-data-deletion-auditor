"""
Packages the submission zip archive 'code.zip' adhering strictly to Section 6.8 & 6.9 of AGENTS.md.
Includes: code/, tests/, scripts/validate_output.py, and requirements.txt.
Excludes datasets, virtual environments, pycache, temporary files, and secrets.
"""
import os
import zipfile
from pathlib import Path

def package_submission(repo_root: Path, zip_output_path: Path) -> None:
    code_dir = repo_root / "code"
    tests_dir = repo_root / "tests"
    validate_script = repo_root / "scripts" / "validate_output.py"
    reqs_file = repo_root / "requirements.txt"

    if not code_dir.exists():
        raise FileNotFoundError(f"Code directory not found at {code_dir}")

    print(f"Creating submission archive: {zip_output_path}...")
    with zipfile.ZipFile(zip_output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        # 1. Include all files in code/
        for root, dirs, files in os.walk(code_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
            for f in files:
                if f.endswith(".pyc") or f.startswith(".") or f == ".env":
                    continue
                file_path = Path(root) / f
                arcname = file_path.relative_to(repo_root).as_posix()
                print(f"  Adding: {arcname}")
                zipf.write(file_path, arcname)

        # 2. Include all files in tests/
        if tests_dir.exists():
            for root, dirs, files in os.walk(tests_dir):
                dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
                for f in files:
                    if f.endswith(".pyc") or f.startswith(".") or f == ".env":
                        continue
                    file_path = Path(root) / f
                    arcname = file_path.relative_to(repo_root).as_posix()
                    print(f"  Adding: {arcname}")
                    zipf.write(file_path, arcname)

        # 3. Include scripts/validate_output.py
        if validate_script.exists():
            arcname = validate_script.relative_to(repo_root).as_posix()
            print(f"  Adding: {arcname}")
            zipf.write(validate_script, arcname)

        # 4. Include requirements.txt
        if reqs_file.exists():
            arcname = reqs_file.relative_to(repo_root).as_posix()
            print(f"  Adding: {arcname}")
            zipf.write(reqs_file, arcname)

    print(f"Successfully created {zip_output_path} ({zip_output_path.stat().st_size} bytes)")

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    target_zip = root / "code.zip"
    package_submission(root, target_zip)
