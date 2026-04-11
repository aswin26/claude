import os, zipfile
from appian_client import AppianClient
import config

def package_modified(modified_dir):
    zip_path = os.path.join(config.WORKSPACE_DIR, "deploy_package.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(modified_dir):
            for fname in files:
                full = os.path.join(root, fname)
                zf.write(full, os.path.relpath(full, modified_dir))
    with open(zip_path, "rb") as f: package_bytes = f.read()
    print(f"\nPackaged to {zip_path} ({len(package_bytes):,} bytes)")
    return package_bytes

def inspect_before_deploy(client, package_bytes):
    print("\nRunning pre-deployment inspection ...")
    result = client.inspect_package(package_bytes)
    print(f"  Inspection status: {result.get('status','UNKNOWN')}")
    for issue in result.get("issues",[]):
        print(f"    [{issue.get('severity','INFO')}] {issue.get('message','')}")
    if not result.get("issues"): print("  No issues found.")
    return result

def deploy(client, package_bytes, name="Automated Deployment", description="Deployed via appian_workflow.py"):
    print(f"\nDeploying: {name} ...")
    result = client.deploy_package(package_bytes, name=name, description=description)
    status = result.get("status","UNKNOWN")
    uuid   = result.get("uuid","N/A")
    print(f"\n  Deployment UUID:   {uuid}")
    print(f"  Deployment status: {status}")
    if uuid != "N/A":
        try:
            log = client.get_deployment_log(uuid)
            entries = log.get("entries",[])
            if entries:
                print(f"\n  Deployment log ({len(entries)} entries):")
                for e in entries: print(f"    [{e.get('timestamp','')}] {e.get('message','')}")
        except Exception as ex: print(f"  Could not fetch log: {ex}")
    if status == "COMPLETED": print("\n  Deployment completed successfully.")
    elif status == "FAILED":  print(f"\n  Deployment FAILED: {result.get('problemMessage','Unknown error')}")
    return result
