#!/usr/bin/env python3
"""Build a repository-level Feishu member package, with legacy workspace mode."""
from __future__ import annotations
import argparse, hashlib, json, re, shutil, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path
import yaml

EXCLUDED_ROOT_KEYS={"record_root","archive_root"}
EXCLUDED_PARTS={".git",".obsidian","__pycache__","cache","caches","tmp","temp","log","logs","test","tests","eval","evals","98_处理记录","99_归档","运行产物","缓存","测试"}
EXCLUDED_SUFFIXES={".pyc",".pyo",".log",".tmp",".bak"}
SECRET_NAME=re.compile(r"(^|[._-])(env|token|secret|password|passwd|credential|credentials|private)([._-]|$)",re.I)

def digest(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda:f.read(1024*1024),b""): h.update(c)
    return h.hexdigest()

def excluded(p:Path)->str|None:
    if any(x.casefold() in {part.casefold() for part in EXCLUDED_PARTS} for x in p.parts): return "cache/log/runtime/test/archive"
    if p.suffix.lower() in EXCLUDED_SUFFIXES: return "cache/log/runtime"
    if SECRET_NAME.search(p.name) or p.name.startswith("."): return "secret/local configuration"
    try:
        if p.is_file() and b"-----BEGIN " in p.read_bytes()[:4096]: return "private key"
    except OSError: pass
    return None

def add_file(stage:Path, src:Path, rel:Path, files:list[dict]):
    if excluded(rel): return
    if not src.is_file(): raise FileNotFoundError(f"required file missing: {src}")
    if SECRET_NAME.search(src.name): return
    try:
        if b"-----BEGIN " in src.read_bytes()[:4096]: return
    except OSError:
        pass
    dst=stage/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
    files.append({"path":rel.as_posix(),"size":dst.stat().st_size,"sha256":digest(dst)})

def add_tree(stage:Path, src:Path, rel:Path, files:list[dict], required=True):
    if not src.is_dir():
        if required: raise FileNotFoundError(f"required directory missing: {src}")
        return
    for p in sorted(src.rglob("*")):
        if p.is_file(): add_file(stage,p,rel/p.relative_to(src),files)

def workspace_config(ws:Path)->dict:
    p=ws/"workspace.yaml"
    if not p.is_file(): raise FileNotFoundError(f"workspace.yaml missing: {ws}")
    c=yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(c,dict): raise ValueError(f"invalid workspace config: {p}")
    return c

def add_workspace(stage:Path, ws:Path, dest:Path, files:list[dict])->dict:
    c=workspace_config(ws); add_file(stage,ws/"workspace.yaml",dest/"workspace.yaml",files)
    for n in ("README.md","说明.md"):
        if (ws/n).is_file(): add_file(stage,ws/n,dest/n,files)
    included=[]
    for k,v in c.items():
        if not k.endswith("_root") or k in EXCLUDED_ROOT_KEYS or not isinstance(v,str): continue
        p=Path(v)
        if p.is_absolute() or ".." in p.parts: raise ValueError(f"invalid workspace root: {ws/'workspace.yaml'}: {v}")
        add_tree(stage,ws/p,dest/p,files,required=True); included.append({"key":k,"path":(dest/p).as_posix()})
    return {"source":str(ws),"package_path":dest.as_posix(),"included":included}

def version_for(root:Path)->str:
    return (root/"VERSION").read_text(encoding="utf-8").strip() if (root/"VERSION").is_file() else "unknown"

def build_repository(root:Path,stage:Path,files:list[dict]):
    import sys; sys.path.insert(0,str(root/"tools"))
    from check_skill_registry import registry
    for n in ("README.md","LICENSE","NOTICE.md","DATA-POLICY.md","CONTRIBUTING.md","VERSION","CHANGELOG.md","requirements.txt"):
        if (root/n).is_file(): add_file(stage,root/n,Path(n),files)
    for d in ("docs","shared","tools",".github"): add_tree(stage,root/d,Path(d),files,required=False)
    entries=[e for e in registry(root).get("skills",[]) if e.get("distribution")=="public" and e.get("status")=="stable"]
    for e in entries:
        package=Path(e["package_path"]); add_tree(stage,root/package,package,files)
        if e.get("workspace_template"): add_workspace(stage,root/e["workspace_template"],Path(e["workspace_template"]),files)
    return [e["id"] for e in entries]

def write_package(output:Path,stage:Path,version:str,skills:list[str],workspaces:list,excluded_items:list[str]):
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file(): z.write(p,p.relative_to(stage).as_posix())
    files=[]
    with zipfile.ZipFile(output) as z:
        names=[i.filename for i in z.infolist() if not i.is_dir()]
        if any(Path(n).is_absolute() or ":" in n.split("/")[0] for n in names): raise ValueError("absolute path found in package")
    for p in sorted(stage.rglob("*")):
        if p.is_file(): files.append({"path":p.relative_to(stage).as_posix(),"size":p.stat().st_size,"sha256":digest(p)})
    manifest={"schema_version":2,"package_type":"feishu_member","version":version,"package":output.name,"built_at":datetime.now(timezone.utc).isoformat(),"skills":skills,"workspaces":workspaces,"file_count":len(files),"total_size":sum(x["size"] for x in files),"files":files,"excluded":excluded_items}
    manifest["archive_size"] = output.stat().st_size
    manifest["archive_sha256"] = digest(output)
    output.with_suffix(".json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def main()->int:
    ap=argparse.ArgumentParser(); g=ap.add_mutually_exclusive_group(required=True); g.add_argument("--root"); g.add_argument("--workspace"); ap.add_argument("--output",required=True); ap.add_argument("--version")
    a=ap.parse_args(); base=Path(a.root or a.workspace).resolve(); version=a.version or version_for(base)
    with tempfile.TemporaryDirectory(prefix="future2046-member-") as td:
        stage=Path(td)/"Future2046-Skills"; stage.mkdir(); files=[]
        if a.root: skills=build_repository(base,stage,files); workspaces=[e.get("workspace_template") for e in __import__("yaml").safe_load((base/"shared/skill-registry.yaml").read_text(encoding="utf-8")).get("skills",[]) if e.get("distribution")=="public" and e.get("status")=="stable" and e.get("workspace_template")]
        else: skills=[]; workspaces=[base.name]; add_workspace(stage,base,Path(),files)
        output=Path(a.output).resolve(); write_package(output,stage,version,skills,workspaces,sorted(EXCLUDED_PARTS))
    print(f"PASS: built {output}"); return 0
if __name__=="__main__": raise SystemExit(main())
