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

### NotebookLM などで作った音声を使う場合

`script.md` の代わりに音声ファイルを `episodes/NNNN-slug/audio.m4a`（または `audio.mp3`）として置く。
`episode.yaml` に `audio_credit: NotebookLM の音声解説で生成` のように書くと概要欄に表示される。
音声は 64kbps モノラルに再エンコードされ、元ファイルのメタデータ（タグ・チャプター等）は除去される。
`script.md` を一緒に置いた場合は「参考：台本メモ」としてページに載る（読み上げはされない）。

> 音声ファイルは Git の履歴に残り続けるので、差し替えるたびにリポジトリが大きくなる点に注意。

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

## ライセンス・クレジット

- コード: MIT
- 台本（`episodes/*/script.md`）: CC BY 4.0
- 音声: CC BY の対象外。各音声合成サービス・音声ライブラリの利用規約に従う
  - VOICEVOX 使用回: VOICEVOX:春日部つむぎ、VOICEVOX:玄野武宏（[VOICEVOX 利用規約](https://voicevox.hiroshiba.jp/term/) と各キャラクターの規約）
- 紹介している論文の著作権は各著者に帰属
