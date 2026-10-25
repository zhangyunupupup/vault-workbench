"""Transactional ZIP export. Source bytes are only read and are hashed in flight."""
from datetime import datetime
from pathlib import Path
import csv
import hashlib
import io
import json
import os
import threading
import uuid
import zipfile

from .catalog import ValidationError
from .recipes import plan


def csv_bytes(headers, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


class ExportManager:
    def __init__(self, output):
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.jobs = {}
        self.lock = threading.Lock()

    def start(self, catalog, payload):
        snapshot = plan(catalog, payload)
        if not snapshot["parts"]:
            raise ValidationError("打印计划为空，请先加入配置或补打零件。")
        if snapshot["bytes"] > 8 * 1024 ** 3:
            raise ValidationError("单次导出超过 8 GiB，请拆分计划。")
        with self.lock:
            if any(j["status"] in ("queued", "running") for j in self.jobs.values()):
                raise ValidationError("已有打包任务进行中，请等待完成。")
            job_id = uuid.uuid4().hex[:12]
            job = {"id": job_id, "status": "queued", "progress": 0, "current": "准备导出",
                   "created": datetime.now().astimezone().isoformat(timespec="seconds"),
                   "file_count": snapshot["file_count"], "copies": snapshot["copies"],
                   "titles": snapshot["titles"], "name": "", "bytes": 0}
            self.jobs[job_id] = job
        threading.Thread(target=self._run, args=(catalog, snapshot, job), daemon=True).start()
        return dict(job)

    def _run(self, catalog, snapshot, job):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        folder = self.output / f"VAULT-{stamp}-{job['id']}"
        temp = folder / "打印包.zip.partial"
        target = folder / "VAULT打印包.zip"
        manifest = {"version": 1, "created": job["created"], "source_root": str(catalog.root),
                    "quantity_unit": "copies of entire STL file", **snapshot}
        try:
            folder.mkdir()
            job.update(status="running")
            total = max(snapshot["bytes"], 1)
            processed = 0
            with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
                for part in manifest["parts"]:
                    source = catalog.resolve(part["id"])
                    initial = source.stat()
                    color_folder = (part['color'].lstrip('#') + '/') if part.get('color') else ''
                    arcname = "STL/" + color_folder + part["group"] + "/" + part["relative"]
                    digest = hashlib.sha256()
                    copied = 0
                    job.update(current=part["name"])
                    with source.open("rb") as inp, archive.open(arcname, "w", force_zip64=True) as dest:
                        for block in iter(lambda: inp.read(1024 * 1024), b""):
                            dest.write(block)
                            digest.update(block)
                            copied += len(block)
                            processed += len(block)
                            job["progress"] = min(98, round(processed / total * 98))
                    final = source.stat()
                    if copied != part["size"] or initial.st_mtime_ns != final.st_mtime_ns or initial.st_size != final.st_size:
                        raise ValidationError("导出时源文件发生变化，请重新扫描后重试：" + part["name"])
                    part["sha256"] = digest.hexdigest()
                    part["archive_path"] = arcname
                print_csv = csv_bytes(
                    ["中文零件名称", "原始文件名", "整份STL打印次数", "文件内单位", "材料", "颜色HEX", "开启支撑", "用途", "来源", "原始相对路径", "包内路径", "SHA256"],
                    [[p["title"], p["name"], p["copies"], p["unit"], p["material"], p.get('color', '未指定'), "是" if p["supports"] else "未特别标注，仍需切片检查",
                      p["reason"], p["source"], p["relative"], p["archive_path"], p["sha256"]] for p in manifest["parts"]])
                hardware_csv = csv_bytes(["五金规格", "数量", "用途", "依据", "核对状态"],
                    [[h["name"], h["quantity"], h["reason"], h["source"], h["status"]] for h in snapshot["hardware"]])
                instructions = self.instructions(manifest)
                text_files = {"manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
                              "打印清单.csv": print_csv, "五金清单.csv": hardware_csv,
                              "打印说明.txt": instructions.encode("utf-8-sig")}
                if 'scene' in snapshot:
                    text_files['组合方案.json'] = json.dumps(snapshot['scene'], ensure_ascii=False, indent=2).encode('utf-8')
                for name, contents in text_files.items():
                    archive.writestr(name, contents)
            # No completed history entry appears until the full ZIP is closed.
            os.replace(temp, target)
            for name, contents in text_files.items():
                (folder / name).write_bytes(contents)
            job.update(status="done", progress=100, current="打包完成", name=folder.name,
                       bytes=target.stat().st_size, url=f"/api/download/{job['id']}")
            self._save_job(folder, job)
        except Exception as exc:
            temp.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            job.update(status="error", current=str(exc), error=str(exc))
            try:
                self._save_job(folder, job)
            except OSError:
                pass  # In-memory error remains visible if the output volume was lost.

    def _save_job(self, folder, job):
        (folder / "export.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def instructions(manifest):
        lines = ["VAULT 中文打印计划", "=" * 32, "生成时间：" + manifest["created"],
                 "模型库：" + manifest["source_root"], "", "所选配置："]
        lines += manifest["titles"] or ["独立零件补打"]
        lines += ["", "打印数量说明：", "每个 STL 文件在包内只保存一次。请按下列次数打印整份 STL。",
                  "一个 STL 可能包含左右一对或一整套零件，不要再次按物体个数相乘。", ""]
        for p in manifest["parts"]:
            lines.append(f"{p['copies']} 次  {p['title']}  |  {p['name']}  |  {p['unit']}")
            if p["supports"]:
                lines.append("  官方文件名明确要求开启支撑。")
            if p["material"] == "TPU":
                lines.append("  使用 TPU。")
        lines += ["", "核对与装配：", "本包为 STL 模型，不含切片参数或 G-code。导入切片器检查朝向、支撑和打印空间。",
                  "几何尺寸不等于所需打印空间；不提供未经切片的耗时和重量估算。",
                  "五金清单区分确定项和参考项；请按实际模型孔数、螺栓头型及装配图核对。"]
        lines += manifest["notes"]
        lines += ["", "官方手册：", "01_Instructions Manual.pdf：型号、命名、五金。",
                  "02_Drawer Assembly.pdf：抽屉装配。", "03_Sustainers Assembly.pdf：翻盖箱装配。",
                  "04_Modifications.pdf：移动底座与改装。", "05_Mounting Instructions.pdf：墙挂、桌下安装。",
                  "", "校验：manifest.json 记录源文件路径及 SHA-256，可核对导出文件。",
                  "原始模型库未被改名、移动或改写。"]
        return "\n".join(lines) + "\n"

    def history(self):
        entries = {}
        for path in self.output.glob("VAULT-*/export.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                entries[job["id"]] = job
            except (OSError, ValueError, KeyError):
                continue
        entries.update({k: dict(v) for k, v in self.jobs.items()})
        return sorted(entries.values(), key=lambda x: x["created"], reverse=True)

    def get(self, job_id):
        return next((j for j in self.history() if j["id"] == job_id), None)

    def download_path(self, job_id):
        job = self.get(job_id)
        if not job or job["status"] != "done":
            raise ValidationError("导出文件尚未完成或不存在。")
        path = (self.output / job["name"] / "VAULT打印包.zip").resolve()
        if not path.is_relative_to(self.output) or not path.is_file():
            raise ValidationError("导出 ZIP 已被移动或删除。")
        return path
