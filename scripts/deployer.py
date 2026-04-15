import os, zipfile
import config


def package_modified(modified_dir) -> str:
    """Zip the modified directory. Returns the path to the .zip file."""
    zip_path = os.path.join(config.WORKSPACE_DIR, "deploy_package.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(modified_dir):
            for fname in files:
                full = os.path.join(root, fname)
                zf.write(full, os.path.relpath(full, modified_dir))
    print(f"\nPackaged to {zip_path} ({os.path.getsize(zip_path):,} bytes)")
    return zip_path


def inspect_before_deploy(client, zip_path: str) -> dict:
    print("\nRunning pre-deployment inspection ...")
    result   = client.inspect_package(zip_path)
    status   = result.get("status", "UNKNOWN")
    errors   = result.get("errors",   [])
    warnings = result.get("warnings", [])
    print(f"  Inspection status : {status}")
    print(f"  Errors: {len(errors)}   Warnings: {len(warnings)}")
    for err in errors:
        print(f"    [ERROR] {err.get('objectName', '—')}: {err.get('message', '')}")
    for w in warnings:
        print(f"    [WARN]  {w.get('objectName', '—')}: {w.get('message', '')}")
    if not errors and not warnings:
        print("  No issues found.")
    return result


def deploy(client, zip_path: str, name="Automated Deployment", description="Deployed via appian_workflow.py") -> dict:
    print(f"\nDeploying: {name} ...")
    result  = client.deploy_package(zip_path, name=name, description=description)
    status  = result.get("status", "UNKNOWN")
    uuid    = result.get("uuid",   "N/A")
    errors  = result.get("errors",   [])
    warnings = result.get("warnings", [])

    print(f"\n  Deployment UUID   : {uuid}")
    print(f"  Deployment status : {status}")

    if errors:
        print(f"\n  Errors:")
        for err in errors:
            print(f"    {err.get('objectName', '—')}: {err.get('message', '')}")
    if warnings:
        print(f"\n  Warnings:")
        for w in warnings:
            print(f"    {w.get('objectName', '—')}: {w.get('message', '')}")

    if status == "COMPLETED":
        print("\n  Deployment completed successfully.")
    elif status in ("FAILED", "COMPLETED_WITH_ERRORS"):
        print(f"\n  Deployment ended with status: {status}")

    return result
