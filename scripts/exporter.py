import os, zipfile, shutil
from appian_client import AppianClient
import config

def list_applications(client):
    apps = client.list_applications()
    print(f"\nFound {len(apps)} application(s):\n")
    for i, app in enumerate(apps, 1):
        print(f"  {i}. {app.get('name','Unnamed')}")
        print(f"     UUID: {app.get('uuid','N/A')}")
        if app.get("description"): print(f"     Desc: {app['description']}")
    return apps

def export_application(client, app_uuid):
    print(f"\nExporting application {app_uuid} ...")
    package_bytes = client.export_package(app_uuid)
    zip_path = os.path.join(config.EXPORT_DIR, "package.zip")
    with open(zip_path, "wb") as f: f.write(package_bytes)
    print(f"  Saved ZIP ({len(package_bytes):,} bytes)")
    extract_dir = os.path.join(config.EXPORT_DIR, "extracted")
    if os.path.isdir(extract_dir): shutil.rmtree(extract_dir)
    with zipfile.ZipFile(zip_path, "r") as zf: zf.extractall(extract_dir)
    file_count = sum(len(files) for _,_,files in os.walk(extract_dir))
    print(f"  Extracted {file_count} file(s) to {extract_dir}")
    return extract_dir

def list_extracted_objects(extract_dir):
    objects = {}
    for root, dirs, files in os.walk(extract_dir):
        for fname in files:
            rel = os.path.relpath(os.path.join(root,fname), extract_dir).replace("\\","/")
            parts = rel.split("/")
            obj_type = parts[1] if len(parts)>2 else parts[0]
            objects.setdefault(obj_type,[]).append(rel)
    print("\nExtracted object types:")
    for t,fl in sorted(objects.items()): print(f"  {t}: {len(fl)} file(s)")
    return objects
