# AI論文ラジオ

読んだ論文を AI が要約・解説し、合成音声で読み上げて配信する個人ポッドキャスト。
GitHub Actions で音声を作り、GitHub Pages で RSS フィードを公開します。

- 購読（RSS）: https://pn11.github.io/ai-podcast/feed.xml
- サイト: https://pn11.github.io/ai-podcast/
- 設計: [docs/DESIGN.md](docs/DESIGN.md)

> このリポジトリはパブリックです。台本やメタデータに個人的なメモ・個人情報を書かないでください。
> 配信内容は AI 生成であり、誤りを含む可能性があります。正確な内容は原論文を参照してください。

## エピソードの追加

1. `episodes/NNNN-slug/` を作り、2 ファイルを置く
   - `script.md`: 台本。`ミナ: せりふ` / `ケン: せりふ` の行だけが読み上げられる（見出しやメモ行は無視）
   - `episode.yaml`: 番号・GUID（`python -c "import uuid;print(uuid.uuid4())"`）・タイトル・概要・公開日時・論文リスト
2. `main` に push → `publish` ワークフローが新規・変更分だけ音声合成し、Releases に MP3 を添付、フィードを更新

台本を直して push すると、その回だけ作り直されます（全部作り直すなら Actions から `publish` を `force` 付きで手動実行）。

## ローカルでの確認

```sh
uv sync
uv run aipodcast check                    # プライバシー / 整合性チェック
uv run aipodcast audio --tts dummy        # 音声の代わりにビープ音で通しテスト
docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-0.26.0   # 本物の音声で試すなら
uv run aipodcast audio
uv run aipodcast site && python -m http.server -d build/site
uv run pytest
```

## クレジット

音声: VOICEVOX:春日部つむぎ、VOICEVOX:玄野武宏
