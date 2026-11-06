# AI Podcast 設計書

> **実装状況（2026-11 時点）**: P0〜P2 相当を実装済み。台本の自動生成（P1, P3 の queue → PR）は未実装で、台本は手動で `episodes/` に置く。
> 設計からの変更点:
> - TTS は **VOICEVOX ENGINE**（Actions のサービスコンテナで実行、API キー不要）を採用。話者はキャラクター名＋スタイル名で `podcast.yaml` に指定。
> - 音声メタデータ（bytes / 長さ / sha256 / 台本の fingerprint）は `episode.yaml` に書き戻さず、Release に `NNNN.json` として MP3 と並べて置く。fingerprint が変わった回だけ再合成する（リポジトリへの自動コミットが不要）。
> - Pages は Actions から `gh-pages` ブランチへ push する方式（Settings → Pages の Source は `gh-pages` ブランチ）。

調べた論文を AI に要約させ、音声合成で読み上げ、RSS フィードとして GitHub Pages で配信する個人ポッドキャストの設計。

## 1. 目的と前提

| 項目 | 内容 |
| --- | --- |
| 目的 | 読んだ／読みたい論文を、通勤中などに耳で復習・予習できるようにする |
| 公開範囲 | パブリックリポジトリ + GitHub Pages（誰でも購読可能） |
| 許容するもの | 「どんな分野・論文に興味があるか」が外部から分かること |
| 許容しないもの | 個人のメモ・感想・未公開研究・氏名/メール等の個人情報・API キー・論文 PDF 本体の再配布 |
| 運用者 | 1 人。手間は「論文 URL を 1 行追加する」程度に抑える |

## 2. 全体アーキテクチャ

```
 ┌───────────────┐   (1) URL を追加して push / workflow_dispatch
 │ queue/*.yaml  │────────────────────────────┐
 └───────────────┘                            ▼
                                   ┌─────────────────────────┐
                                   │ GitHub Actions: script  │
                                   │  - arXiv 等からメタ取得 │
                                   │  - PDF を一時取得(非commit)
                                   │  - LLM で台本生成       │
                                   └───────────┬─────────────┘
                                               │ (2) 台本を PR として提出
                                               ▼
                                   ┌─────────────────────────┐
                                   │  人間レビュー (PR)      │  ← 誤り・プライバシー確認
                                   └───────────┬─────────────┘
                                               │ (3) merge
                                               ▼
                                   ┌─────────────────────────┐
                                   │ GitHub Actions: publish │
                                   │  - TTS で音声合成       │
                                   │  - ffmpeg で MP3 化     │
                                   │  - Release に MP3 添付  │
                                   │  - feed.xml / HTML 生成 │
                                   │  - GitHub Pages へ deploy
                                   └───────────┬─────────────┘
                                               ▼
                          https://pn11.github.io/ai-podcast/feed.xml
                                               ▼
                               Podcast アプリ (Apple / Pocket Casts / AntennaPod …)
```

ポイント:

- **台本生成と音声公開を 2 段階に分け、間に PR レビューを挟む。** LLM の誤要約（ハルシネーション）と意図しない情報混入を公開前に止めるため。慣れたら自動マージ設定も可能にする。
- **リポジトリにコミットするのは「公開してよいもの」だけ。** 入力 URL、生成台本、エピソードメタデータ、サイトのソース。PDF・音声中間ファイル・API キーはコミットしない。
- **MP3 はリポジトリに入れず GitHub Releases のアセットに置く。** リポジトリ肥大化（Pages サイトは 1GB 推奨上限、1 ファイル 100MB 上限）を避けるため。

## 3. リポジトリ構成

```
ai-podcast/
├── podcast.yaml              # 番組メタデータ（タイトル、説明、言語、カテゴリ、アートワーク等）
├── queue/                    # これから作るエピソードの入力（1 ファイル = 1 エピソード）
│   └── 2026-11-05-attention.yaml
├── episodes/                 # 生成済みエピソード（公開状態の正）
│   └── 0001-attention-is-all-you-need/
│       ├── episode.yaml      # メタデータ（タイトル、論文情報、音声 URL、長さ、GUID…）
│       └── script.md         # 読み上げ台本（レビュー対象）
├── prompts/
│   ├── script_system.md      # 台本生成のシステムプロンプト
│   └── script_user.md        # 論文ごとのユーザープロンプトテンプレート
├── src/aipodcast/            # Python パッケージ
│   ├── cli.py                # `aipodcast script|audio|feed|build` サブコマンド
│   ├── sources/              # arXiv / DOI / 任意 URL からのメタデータ・本文取得
│   ├── llm.py                # 台本生成（Claude API）
│   ├── tts/                  # TTS プロバイダ抽象 + 実装
│   │   ├── base.py
│   │   ├── google.py
│   │   └── openai.py
│   ├── audio.py              # 分割合成した音声の結合・正規化・MP3 化
│   ├── feed.py               # RSS 2.0 + iTunes 名前空間の生成
│   ├── site.py               # エピソード一覧 HTML の生成
│   └── privacy.py            # 公開前チェック（後述）
├── site/                     # 静的アセット（artwork.png, style.css）
├── tests/
├── .github/workflows/
│   ├── script.yml            # queue → 台本 PR
│   ├── publish.yml           # main への merge → 音声 + feed + Pages
│   └── ci.yml                # lint / test / privacy チェック
├── .gitignore                # *.pdf, build/, .env, *.wav など
└── pyproject.toml
```

ビルド成果物（`build/` 以下の `feed.xml`, `index.html`, エピソードページ）はコミットせず、Actions の `actions/upload-pages-artifact` + `actions/deploy-pages` で直接 Pages に配信する。

## 4. データモデル

### 4.1 入力: `queue/*.yaml`

```yaml
# 必須は source だけ。他は任意。
source: https://arxiv.org/abs/1706.03762
style: dialogue        # dialogue（2 人の掛け合い） | monologue（1 人解説）
length: medium         # short(~5分) | medium(~12分) | long(~20分)
focus: |               # 任意。台本で強調してほしい観点（公開される前提で書く）
  手法の直感的な説明と、既存手法との差分を中心に
```

`focus` は公開される。ここに個人的な文脈（「自分の研究の○○に使えそう」等）を書かないことを README と PR テンプレートに明記する。

### 4.2 エピソード: `episodes/NNNN-slug/episode.yaml`

```yaml
id: 1                                   # 連番（エピソード番号）
slug: attention-is-all-you-need
guid: 3f1c2a9e-...                      # UUIDv4。一度発行したら絶対に変えない
title: "Attention Is All You Need を聴く"
description: "Transformer を提案した論文の要点を解説します。"
published_at: 2026-11-05T21:00:00+09:00
paper:
  title: Attention Is All You Need
  authors: [Ashish Vaswani, ...]
  url: https://arxiv.org/abs/1706.03762
  published: 2017-06-12
  license: http://arxiv.org/licenses/nonexclusive-distrib/1.0/
generation:
  llm_model: claude-sonnet-5-5
  prompt_version: 3
  tts_provider: google
  voices: [ja-JP-Chirp3-HD-Aoede, ja-JP-Chirp3-HD-Charon]
audio:                                   # publish 時に自動で埋まる
  url: https://github.com/pn11/ai-podcast/releases/download/ep-0001/0001.mp3
  bytes: 9876543
  duration_sec: 734
  sha256: ...
```

GUID は RSS の重複判定に使われるため、タイトルや URL を後から変えても GUID は変えない。

### 4.3 台本: `script.md`

話者タグ付きの Markdown。TTS 側でパースして話者ごとに声を切り替える。

```markdown
---
speakers:
  A: { name: ホスト, voice: ja-JP-Chirp3-HD-Aoede }
  B: { name: 解説役, voice: ja-JP-Chirp3-HD-Charon }
---

A: こんにちは。今日は 2017 年の論文「Attention Is All You Need」を取り上げます。
B: いわゆる Transformer を提案した論文ですね。
...
<!-- pause: 800ms -->
A: 最後にまとめです。
```

- 冒頭で「この番組は AI が論文を要約し、合成音声で読み上げています。内容の正確性は原論文で確認してください」と定型の断り文を自動挿入する。
- 数式・記号・英語略語は読み上げ用に変換する（`O(n^2)` →「オーダー n の二乗」など）。LLM へのプロンプトで指示し、加えて `pronunciation.yaml`（読み辞書）で後処理する。

## 5. 処理パイプライン詳細

### 5.1 台本生成 (`aipodcast script`)

1. `queue/*.yaml` を読み、`source` から種類を判別（arXiv / DOI / 一般 URL / ローカル PDF）。
2. メタデータ取得: arXiv API（タイトル・著者・概要・ライセンス）。DOI は Crossref API。
3. 本文取得: arXiv の PDF を一時ディレクトリにダウンロード。**コミットしない。**
4. LLM 呼び出し: Claude API に PDF をドキュメントとして渡し、`prompts/` のテンプレートで台本を生成。
   - モデルは設定で切替（デフォルト `claude-sonnet-5-5`、品質重視なら `claude-opus-5-5`）。
   - 出力は構造化（JSON: タイトル案、説明文、台本行の配列）で受け、Markdown に整形。
   - プロンプトに含める指示: 論文に書かれていないことを断定しない／数値は論文から引用／限界・批判点にも触れる／読み上げやすい口語／指定の長さ（文字数目安: 日本語で 1 分 ≒ 300 字）。
5. 2 段目の LLM 呼び出し（任意・推奨）: 生成台本と論文を突き合わせる「ファクトチェック」パスで、根拠のない主張にフラグを立て PR 本文に列挙する。
6. `episodes/NNNN-slug/` を作成し、`queue/` の該当ファイルを削除。
7. `privacy.py` チェック（後述）を実行。
8. ブランチを切って PR を作成（PR 本文にファクトチェック結果、推定再生時間、推定コスト）。

### 5.2 音声生成 (`aipodcast audio`)

1. `audio.url` が未設定のエピソードを対象にする（冪等）。
2. 台本を話者・段落単位のチャンクに分割（TTS API の 1 リクエスト上限に合わせる）。
3. TTS 合成 → チャンクごとの WAV。同一テキストのキャッシュは Actions cache を使い、再実行時のコストを抑える。
4. ffmpeg で結合、無音挿入、ラウドネス正規化（`loudnorm` I=-16 LUFS）、MP3 化（モノラル 64kbps / 44.1kHz、音声のみなら十分。15 分で約 7MB）。
5. ID3 タグはタイトル・番組名・エピソード番号だけを明示的に設定し、それ以外のメタデータ（エンコーダ情報やパス等）は除去する。
6. `gh release create ep-NNNN NNNN.mp3` で Release に添付し、URL・バイト数・長さ・SHA256 を `episode.yaml` に書き戻してコミット。

### 5.3 フィード・サイト生成 (`aipodcast feed`)

`episodes/*/episode.yaml` と `podcast.yaml` から以下を生成し、Pages にデプロイ。

- `feed.xml`: RSS 2.0 + `itunes:` / `podcast:` 名前空間
  - チャンネル: `title`, `link`, `description`, `language` (`ja`), `itunes:image`（3000×3000 px PNG）, `itunes:category`（Science / Technology）, `itunes:explicit` (`false`), `itunes:author`
  - アイテム: `title`, `guid isPermaLink="false"`, `pubDate`, `enclosure url length type="audio/mpeg"`, `itunes:duration`, `itunes:episode`, `description`（論文リンク・著者・ライセンス・AI 生成である旨を含む）
  - `atom:link rel="self"` を付与
- `index.html`: 番組説明、購読ボタン（RSS URL コピー）、エピソード一覧
- `episodes/NNNN/index.html`: 台本全文（＝文字起こし）と原論文リンク。`podcast:transcript` でフィードからも参照
- 生成後に XML スキーマ的な自己検証（必須タグ、enclosure の length が実ファイルと一致）を実行

## 6. GitHub Actions ワークフロー

| Workflow | トリガ | 主な処理 | 必要な権限 / Secret |
| --- | --- | --- | --- |
| `script.yml` | `queue/**` への push、`workflow_dispatch` | 5.1 → PR 作成 | `contents: write`, `pull-requests: write`, `ANTHROPIC_API_KEY` |
| `ci.yml` | PR | lint, test, privacy チェック, 台本の読み上げ時間見積もり | なし（Secret 不要） |
| `publish.yml` | `main` への push（`episodes/**`, `podcast.yaml`, `src/**`）、`workflow_dispatch` | 5.2 → 5.3 → Pages デプロイ | `contents: write`, `pages: write`, `id-token: write`, TTS の認証情報 |

セキュリティ上の注意:

- Secret は `ci.yml`（PR トリガ、フォークからも動く）には渡さない。API を叩くのは `main` / `queue` への push と手動実行だけにする。
- `pull_request_target` は使わない。
- Google Cloud TTS を使う場合は JSON キーではなく Workload Identity Federation（OIDC）で認証し、長期キーを置かない。
- `concurrency` で publish の同時実行を 1 本に制限（Release と feed の整合性維持）。
- Pages の Source は「GitHub Actions」に設定。

## 7. プライバシー設計

パブリックリポジトリなので「コミット = 全世界公開（履歴含め削除困難）」として扱う。

### 7.1 公開されるもの（許容）

- 取り上げた論文の URL・タイトル・著者、要約台本、音声
- エピソードの公開日時（＝いつ頃その論文を読んだか）
- 番組名・説明・アートワーク
- Git のコミット履歴（コミット時刻、コミッタ名）

### 7.2 公開しないもの と その担保

| 対象 | 対策 |
| --- | --- |
| API キー等 | GitHub Secrets のみ。`.env` は `.gitignore`。GitHub の Secret scanning / Push protection を有効化 |
| 個人メール | コミットは `ID+user@users.noreply.github.com` を使用（GitHub 設定の "Keep my email addresses private" + "Block command line pushes that expose my email"）。フィードの `itunes:owner/itunes:email` は省略、または公開用の別アドレスを使う（Apple Podcasts のディレクトリ登録時のみ必要） |
| 個人的なメモ・感想・研究との関連 | リポジトリに置かない設計にする。`focus` 欄は公開前提と明記。どうしても個人メモを使いたい場合は `private/`（`.gitignore` 済み）に置きローカル実行時のみ参照、生成物にのみ反映（ただし生成物に内容が漏れうる点に注意） |
| 論文 PDF 本体 | `*.pdf` を `.gitignore`。Actions 内の一時ディレクトリでのみ扱う |
| 未公開論文・査読中原稿 | 入力を「公開 URL（arXiv / DOI / 公開ページ）」に限定し、ローカル PDF 入力は CLI でのみ許可し CI では拒否 |
| 音声ファイルのメタデータ | ID3 を明示的に再設定し、エンコーダ由来の情報を除去 |
| 聴取者側のプライバシー | 計測タグ・トラッキングプレフィックスを使わない（Pages / Releases なのでアクセスログも取れない） |

### 7.3 自動チェック (`privacy.py`, CI で必須)

- 正規表現でメールアドレス、電話番号、`sk-` / `AIza` 等のキー形式、ローカルパス（`/Users/`, `/home/`, `C:\`）を検出したら失敗
- `denylist.txt`（ローカルのみ、`.gitignore`）に自分の氏名・所属などを書いておけば、ローカル実行時にそれも検出
- `queue/*.yaml` の `source` が許可ドメイン（arxiv.org, doi.org, openreview.net, aclanthology.org など）か確認

### 7.4 興味の露出をさらに抑えたい場合（任意）

- 番組名・リポジトリ名を自分の名前やハンドルと結びつかないものにする
- `itunes:block yes` でポッドキャストディレクトリへの掲載を避け、フィード URL を知る人だけが購読する運用にする（URL 自体は公開リポジトリから辿れるので「隠す」ではなく「目立たせない」程度）

## 8. 著作権・表示

- 配信するのは「AI による要約・解説」であり、論文本文の朗読や図表の転載はしない（プロンプトで長文引用を禁止）。
- 各エピソードの説明文とページに、原論文のタイトル・著者・URL・ライセンスを記載。
- 番組説明と各回冒頭で「AI 生成コンテンツであり誤りを含みうる」旨を表示・読み上げ。
- TTS の利用規約で、生成音声の公開配信が許可されていることを確認（クラウド TTS は概ね可。VOICEVOX 等はキャラクターごとのクレジット表記が必要）。
- リポジトリのライセンス: コードは MIT、台本は CC BY 4.0。音声は TTS／音声ライブラリの規約（VOICEVOX は他者への利用許諾時に規約遵守を義務付ける条項がある）と衝突しうるため CC BY の対象外とし、各規約に従う旨を明記する（原論文のライセンスとは別物である旨も明記）。

## 9. 技術選定

| 役割 | 第一候補 | 代替 | 理由 |
| --- | --- | --- | --- |
| 言語 | Python 3.12 + uv | — | arXiv / TTS / ffmpeg 周りのライブラリが揃っている |
| 台本生成 | Claude API（PDF 入力対応） | 他 LLM | PDF をそのまま渡せる。モデルは設定で切替 |
| TTS | Google Cloud TTS（日本語の高品質音声、複数話者） | OpenAI TTS, Azure Speech, VOICEVOX（無料・ローカル） | `tts/base.py` の抽象で差し替え可能にする |
| 音声処理 | ffmpeg | pydub | 結合・正規化・エンコードを 1 コマンドで |
| フィード | 自前テンプレート（Jinja2） | feedgen | iTunes / podcast 名前空間を細かく制御したい |
| 音声ホスティング | GitHub Releases | Cloudflare R2, Internet Archive | 無料・リポジトリ外・1 ファイル 2GB まで |
| サイト | GitHub Pages（Actions デプロイ） | — | 要件どおり |

GitHub Releases のダウンロード URL は別ドメインへのリダイレクトになる。主要アプリはリダイレクトを追従するが、将来問題が出た場合は R2 等に切り替えられるよう、`audio.url` のベース URL を `podcast.yaml` で設定可能にしておく。

## 10. コスト目安（1 エピソード 12 分想定）

- 台本生成: 論文 PDF（数万トークン）入力 + 台本 4,000 字程度の出力。ファクトチェックパスを入れると約 2 倍。
- TTS: 約 4,000 字。クラウド TTS は文字数課金で、高品質音声でも 1 回あたり数十円以内に収まる見込み。
- GitHub: パブリックリポジトリなら Actions・Pages・Releases は無料枠内。

正確な単価は各サービスの最新料金表で確認し、`aipodcast script` 実行時に推定コストを PR に表示する。

## 11. 運用フロー（日常）

1. 読んだ論文の URL で `queue/2026-11-05-foo.yaml` を作成して push（スマホからは GitHub の Web UI で 1 ファイル追加でも可）。
2. 数分後に台本 PR が届く → ファクトチェックの指摘と台本をざっと読み、必要なら直接編集。
3. merge すると音声が生成され、フィードが更新される。
4. ポッドキャストアプリで `https://pn11.github.io/ai-podcast/feed.xml` を購読しておけば自動で届く。

## 12. 実装フェーズ

| フェーズ | 内容 | 完了条件 |
| --- | --- | --- |
| P0 | 雛形、`podcast.yaml`、手書き台本 → TTS → MP3 → feed.xml をローカルで生成 | ローカルの feed.xml をアプリで再生できる |
| P1 | arXiv 取得 + LLM 台本生成（monologue） | URL 1 つから台本が出る |
| P2 | `publish.yml`: Releases へのアップロード + Pages デプロイ | 公開 URL のフィードを購読できる |
| P3 | `script.yml`: queue → PR の自動化、privacy チェック、CI | push だけでエピソードが作れる |
| P4 | dialogue 形式、ファクトチェックパス、読み辞書、文字起こしページ | 品質改善 |
| P5（任意） | 複数論文をまとめる週次ダイジェスト回、Apple Podcasts / Spotify 登録 | — |

## 13. 未決事項

- TTS プロバイダの最終決定（日本語の自然さを数社で聴き比べて決める）
- dialogue / monologue のどちらをデフォルトにするか
- 番組名・アートワーク
- Apple Podcasts 等のディレクトリに登録するか（登録するなら公開用メールアドレスが必要）
