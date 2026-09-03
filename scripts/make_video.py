#!/usr/bin/env python3
"""scenes.json をもとに縦型ショート動画(mp4)を生成するスクリプト。

各シーンは「画像 + テロップ + 秒数」の組み合わせで、ズーム(Ken Burns)と
フェードイン/アウトを付けて 1 本の動画に結合する。テキスト描画は Pillow で
行うため、ffmpeg に drawtext フィルタが無くても動作する。

使い方:
    python scripts/make_video.py                # scenes.json -> output/short.mp4
    python scripts/make_video.py -c my.json -o output/my.mp4
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent


def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg が見つかりません。`pip install imageio-ffmpeg` を実行してください。")


def load_font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
    candidates = [path] if path else []
    candidates += [
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return ImageFont.truetype(c, size)
    print("警告: 日本語フォントが見つからないため既定フォントを使います", file=sys.stderr)
    return ImageFont.load_default()


def fit_image(img: Image.Image, w: int, h: int, mode: str) -> Image.Image:
    """画像をキャンバスに収める。cover は全面、contain は余白付き。"""
    if mode == "cover":
        return ImageOps.fit(img, (w, h), Image.LANCZOS)
    img = img.copy()
    img.thumbnail((w, h), Image.LANCZOS)
    return img


def render_scene_base(scene: dict, cfg: dict) -> Image.Image:
    w, h = cfg["width"], cfg["height"]
    canvas = Image.new("RGBA", (w, h), cfg["background"])
    img_path = ROOT / scene["image"]
    if img_path.exists():
        img = Image.open(img_path).convert("RGBA")
        fitted = fit_image(img, w, int(h * scene.get("image_height", 0.62)), scene.get("fit", "contain"))
        x = (w - fitted.width) // 2
        y = int(h * scene.get("image_top", 0.12))
        canvas.alpha_composite(fitted, (x, y))
    else:
        print(f"警告: 画像が見つかりません: {img_path}", file=sys.stderr)
    return canvas


def draw_caption(canvas: Image.Image, text: str, cfg: dict, scene: dict) -> None:
    if not text:
        return
    w, h = canvas.size
    font = load_font(cfg.get("font"), scene.get("font_size", cfg.get("font_size", 72)))
    draw = ImageDraw.Draw(canvas)
    stroke = max(2, font.size // 12)
    bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center", stroke_width=stroke, spacing=16)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (w - tw) // 2 - bbox[0]
    y = int(h * scene.get("text_top", 0.78)) - th // 2 - bbox[1]
    draw.multiline_text(
        (x, y),
        text,
        font=font,
        fill=cfg.get("text_color", "#ffffff"),
        stroke_width=stroke,
        stroke_fill=cfg.get("text_stroke", "#000000"),
        align="center",
        spacing=16,
    )


def zoom_frame(base: Image.Image, t: float, kind: str, strength: float = 0.08) -> Image.Image:
    """t: 0..1 の進行度。kind に応じて中心ズームする。"""
    if kind == "in":
        scale = 1.0 + strength * t
    elif kind == "out":
        scale = 1.0 + strength * (1.0 - t)
    else:
        return base
    w, h = base.size
    cw, ch = int(w / scale), int(h / scale)
    left, top = (w - cw) // 2, (h - ch) // 2
    return base.crop((left, top, left + cw, top + ch)).resize((w, h), Image.BILINEAR)


def fade_alpha(t_sec: float, duration: float, fade: float) -> float:
    if fade <= 0:
        return 1.0
    a = min(1.0, t_sec / fade, (duration - t_sec) / fade)
    return max(0.0, a)


def build(cfg_path: Path, out_path: Path) -> None:
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    w, h, fps = cfg["width"], cfg["height"], cfg["fps"]
    fade = cfg.get("fade", 0.5)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_video = out_path.with_suffix(".noaudio.mp4")
    cmd = [
        ffmpeg_exe(), "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
        "-movflags", "+faststart", str(tmp_video),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None

    bg = np.array(Image.new("RGB", (w, h), cfg["background"]), dtype=np.float32)
    total_frames = 0
    for i, scene in enumerate(cfg["scenes"], 1):
        base = render_scene_base(scene, cfg)
        draw_caption(base, scene.get("text", ""), cfg, scene)
        base = base.convert("RGB")
        n = int(round(scene["duration"] * fps))
        print(f"[{i}/{len(cfg['scenes'])}] {scene.get('text', '').replace(chr(10), ' ')} ({n} frames)")
        for f in range(n):
            t = f / max(1, n - 1)
            frame = zoom_frame(base, t, scene.get("zoom", "none"))
            a = fade_alpha(f / fps, scene["duration"], fade)
            arr = np.asarray(frame, dtype=np.float32)
            if a < 1.0:
                arr = arr * a + bg * (1.0 - a)
            proc.stdin.write(arr.astype(np.uint8).tobytes())
            total_frames += 1
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg のエンコードに失敗しました")

    bgm = cfg.get("bgm")
    if bgm and (ROOT / bgm).exists():
        dur = total_frames / fps
        vol = cfg.get("bgm_volume", 0.6)
        cmd = [
            ffmpeg_exe(), "-y", "-loglevel", "error",
            "-i", str(tmp_video), "-stream_loop", "-1", "-i", str(ROOT / bgm),
            "-filter_complex", f"[1:a]volume={vol},afade=t=out:st={max(0, dur - 1):.2f}:d=1[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{dur:.3f}", "-shortest", str(out_path),
        ]
        subprocess.run(cmd, check=True)
        tmp_video.unlink()
    else:
        tmp_video.replace(out_path)
    print(f"完成: {out_path} ({total_frames / fps:.1f} 秒, {w}x{h}, {fps}fps)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-c", "--config", default=str(ROOT / "scenes.json"))
    ap.add_argument("-o", "--output", default=str(ROOT / "output" / "short.mp4"))
    args = ap.parse_args()
    build(Path(args.config), Path(args.output))


if __name__ == "__main__":
    main()
