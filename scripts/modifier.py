import os, shutil
import xml.etree.ElementTree as ET
import yaml
import config

def load_patches(patch_file):
    with open(patch_file) as f: data = yaml.safe_load(f)
    patches = data.get("patches", [])
    print(f"\nLoaded {len(patches)} patch(es) from {patch_file}")
    return patches

def apply_patches(extract_dir, patches):
    modified_dir = config.MODIFIED_DIR
    if os.path.isdir(modified_dir): shutil.rmtree(modified_dir)
    shutil.copytree(extract_dir, modified_dir)
    applied = skipped = 0
    for patch in patches:
        target = os.path.join(modified_dir, patch["file"])
        if not os.path.isfile(target):
            print(f"  SKIP: {patch['file']}"); skipped += 1; continue
        if "xpath" in patch:
            _apply_xpath_patch(target, patch); applied += 1
        elif patch.get("changes"):
            _apply_text_patches(target, patch["changes"]); applied += 1
    print(f"\nPatch summary: {applied} applied, {skipped} skipped")
    return modified_dir

def _apply_text_patches(file_path, changes):
    with open(file_path, "r", encoding="utf-8") as f: content = f.read()
    original = content
    for c in changes:
        if c["find"] in content:
            content = content.replace(c["find"], c["replace"])
            print(f"  REPLACED in {os.path.basename(file_path)}: '{c['find'][:50]}'")
        else:
            print(f"  NOT FOUND in {os.path.basename(file_path)}: '{c['find'][:50]}'")
    if content != original:
        with open(file_path, "w", encoding="utf-8") as f: f.write(content)

def _apply_xpath_patch(file_path, patch):
    tree = ET.parse(file_path); root = tree.getroot()
    xpath, new_value = patch["xpath"], patch.get("new_value","")
    elements = root.findall(xpath)
    if elements:
        for el in elements:
            if new_value: el.text = new_value
            el.attrib.update(patch.get("new_attrib",{}))
        tree.write(file_path, xml_declaration=True, encoding="utf-8")
        print(f"  XPATH PATCH {os.path.basename(file_path)}: {len(elements)} element(s)")
    else:
        print(f"  XPATH NOT FOUND in {os.path.basename(file_path)}: {xpath}")
