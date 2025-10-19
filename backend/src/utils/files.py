from pathlib import Path
import json, shutil, asyncio, re


from src.utils.common import group_dir_process, group_dir_final
# вспомогалки (совместимы с вашим кодом отчётов)
_norm_result_suffix = re.compile(r"(?:_result)?$", re.IGNORECASE)
_norm_idx_suffix    = re.compile(r"_(\d{3,})$")


def _stem_norm(name: str) -> str:
    stem = Path(name).stem
    stem = _norm_result_suffix.sub("", stem)
    stem = _norm_idx_suffix.sub("", stem)
    return stem

async def _write_text_atomic(path: Path, text: str) -> None:
    """Безопасная запись файла в выделенном треде."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    def _sync():
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    await asyncio.to_thread(_sync)

async def _copy2(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    def _sync():
        shutil.copy2(src, dst)
    await asyncio.to_thread(_sync)

def _guess_group_root_by_stage_dir(group_uuid: str, stage: str) -> Path:
    """Возвращает корень группы (.../groups/<uuid>/), чтобы затем найти raw_data/."""
    stage_dir = group_dir_final(group_uuid) if stage == "done" else group_dir_process(group_uuid)
    # /.../groups/<uuid>/<stage>/ -> корень /.../groups/<uuid>
    return stage_dir.parent

async def _find_source_image(meta: dict, base_stem: str, group_uuid: str | None) -> Path | None:
    """
    Пытаемся найти исходное изображение, опираясь на:
    - meta["filename"] / meta["original_name"]
    - stem, совпадающий с base_stem
    - расположение в raw_data/
    """
    name_in_meta = (meta.get("filename") or meta.get("original_name") or "").strip()
    candidates: list[Path] = []

    # 1) если в метадате есть абсолютный/относительный путь — пробуем его первым
    for k in ("path", "disk_path", "abs_path"):
        if meta.get(k):
            p = Path(meta[k])
            if p.exists() and p.is_file():
                candidates.append(p)

    # 2) если известно group_uuid — смотрим raw_data/
    if not group_uuid:
        group_uuid = meta.get("group_uuid")

    if group_uuid:
        group_root = _guess_group_root_by_stage_dir(group_uuid, "progress")  # корень группы
        raw_dir = group_root / "raw_data"
        if raw_dir.exists():
            # 2.1) точное имя из меты
            if name_in_meta:
                p = raw_dir / name_in_meta
                if p.exists():
                    candidates.append(p)
            # 2.2) по стему
            for p in raw_dir.glob("*"):
                if p.is_file() and _stem_norm(p.name).casefold() == base_stem.casefold():
                    candidates.append(p)

    # 3) берём первый существующий
    for p in candidates:
        if p.exists() and p.is_file():
            return p

    return None

