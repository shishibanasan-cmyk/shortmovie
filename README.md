# shortmovie

LINEスタンプの紹介用ショート動画(縦型 1080x1920)を、画像とテロップから自動生成するリポジトリです。

## 仕組み

`scenes.json` に「画像・テロップ・秒数」をシーンごとに書くと、
`scripts/make_video.py` がズーム演出とフェードを付けて 1 本の mp4 にまとめます。
テロップは Pillow で描画するので、日本語フォントがあれば ffmpeg 側の設定は不要です。

## 使い方

```bash
pip install -r requirements.txt
python scripts/make_video.py            # -> output/short.mp4
python scripts/make_video.py -c scenes.json -o output/short.mp4
```

## フォルダ構成

| パス | 内容 |
| --- | --- |
| `assets/images/` | スタンプ画像など、シーンに使う素材 |
| `assets/audio/` | BGM(mp3 / wav)。`scenes.json` の `bgm` で指定 |
| `scenes.json` | 動画の構成(シーンの並び、テロップ、秒数) |
| `scripts/make_video.py` | 動画生成スクリプト |
| `output/` | 生成された動画(git 管理外) |

## scenes.json の項目

全体設定:

- `width` / `height` / `fps`: 解像度とフレームレート(既定は 1080x1920, 30fps)
- `background`: 背景色
- `font` / `font_size` / `text_color` / `text_stroke`: テロップのフォントと色
- `fade`: 各シーンのフェードイン・アウト秒数
- `bgm` / `bgm_volume`: BGM のパスと音量(0〜1)

シーンごとの設定:

- `image`: 画像のパス
- `text`: テロップ(`\n` で改行)
- `duration`: 表示秒数
- `zoom`: `in` / `out` / `none`
- `fit`: `contain`(余白付き、既定)または `cover`(全面)
- `image_top` / `image_height` / `text_top`: 画像とテロップの縦位置(画面高さに対する割合)

`assets/images/sample_*.png` は動作確認用のダミー画像です。実際のスタンプ画像に差し替えてください。
