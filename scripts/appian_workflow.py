#!/usr/bin/env python3
import argparse, sys
import config
from appian_client import AppianClient
from exporter import list_applications, export_application, list_extracted_objects
from modifier import load_patches, apply_patches
from deployer import package_modified, inspect_before_deploy, deploy

def main():
    args = parse_args()
    skip_inspect = args.skip_inspect or config.SKIP_INSPECT
    auto_approve = args.auto_approve or config.AUTO_APPROVE
    app_uuid     = args.app_uuid or config.APPIAN_APP_UUID
    deploy_name  = args.deploy_name or config.APPIAN_DEPLOY_NAME
    deploy_desc  = args.deploy_desc or config.APPIAN_DEPLOY_DESCRIPTION

    config.validate()
    config.print_summary()

    client = AppianClient(config.APPIAN_URL, config.APPIAN_API_KEY)

    if args.list_apps:
        list_applications(client); return

    if args.deploy_zip:
        with open(args.deploy_zip, "rb") as f: pkg = f.read()
        print(f"Loaded {args.deploy_zip} ({len(pkg):,} bytes)")
        if not skip_inspect:
            if inspect_before_deploy(client, pkg).get("status") == "FAILED":
                print("Inspection failed — aborting."); sys.exit(1)
        sys.exit(0 if deploy(client, pkg, deploy_name, deploy_desc).get("status") == "COMPLETED" else 1)

    if not app_uuid:
        print("ERROR: --app-uuid required (or set APPIAN_APP_UUID via setup_credentials.py).")
        print("Use --list-apps to find UUIDs."); sys.exit(1)

    print("="*60+"\nSTEP 1: EXPORT\n"+"="*60)
    extract_dir = export_application(client, app_uuid)
    list_extracted_objects(extract_dir)
    if args.export_only:
        print(f"\nExport complete: {extract_dir}"); return

    print("\n"+"="*60+"\nSTEP 2: MODIFY\n"+"="*60)
    if args.patches:
        modified_dir = apply_patches(extract_dir, load_patches(args.patches))
    else:
        print("No patch file — packaging unmodified export.")
        modified_dir = extract_dir

    print("\n"+"="*60+"\nSTEP 3: PACKAGE\n"+"="*60)
    pkg = package_modified(modified_dir)

    if not skip_inspect:
        print("\n"+"="*60+"\nSTEP 4: INSPECT\n"+"="*60)
        if inspect_before_deploy(client, pkg).get("status") == "FAILED":
            print("Inspection failed — aborting."); sys.exit(1)

    print("\n"+"="*60+f"\nSTEP 5: DEPLOY → {config.APPIAN_URL}\n"+"="*60)
    if not auto_approve:
        if input("\nProceed with deployment? [y/N] ").lower() != "y":
            print("Cancelled."); return

    result = deploy(client, pkg, deploy_name, deploy_desc)
    ok = result.get("status") == "COMPLETED"
    print("\n"+"="*60)
    print("WORKFLOW COMPLETE — successful." if ok else "WORKFLOW FAILED.")
    print("="*60)
    sys.exit(0 if ok else 1)

def parse_args():
    p = argparse.ArgumentParser(description="Appian Export → Modify → Deploy (same environment)")
    p.add_argument("--app-uuid",      help="Application UUID to export")
    p.add_argument("--patches",       help="Path to patches YAML file")
    p.add_argument("--list-apps",     action="store_true", help="List all applications")
    p.add_argument("--export-only",   action="store_true", help="Export without deploying")
    p.add_argument("--deploy-zip",    help="Deploy a pre-built zip directly")
    p.add_argument("--skip-inspect",  action="store_true", help="Skip pre-deploy inspection")
    p.add_argument("--auto-approve",  action="store_true", help="Deploy without confirmation prompt")
    p.add_argument("--deploy-name",   default="", help="Deployment name")
    p.add_argument("--deploy-desc",   default="", help="Deployment description")
    return p.parse_args()

if __name__ == "__main__":
    main()
