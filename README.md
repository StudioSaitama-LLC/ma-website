# 間｜MA — ma-website

Indies Lifestyle Media 間｜MA のウェブサイト（株式会社まなか × Studio Saitama）。
静的 HTML/CSS/JS 構成。GitHub Pages で公開する。

- 公開URL: https://studiosaitama-llc.github.io/ma-website/
- 関連リポジトリ: [ma-jpn](https://github.com/StudioSaitama-LLC/ma-jpn)（旧サイト / GitHub Pages。本 repo とは別系統）
- 企画・戦略ドキュメント: `studiosaitama/clients/manaka/docs/`（ローカル）/ [manaka-docs](https://github.com/StudioSaitama-LLC/manaka-docs)

## 構成（2026-10 β版から）

ページは `src/` のデータから `tools/build.py` が生成する。**生成された HTML を直接直さない**（次の生成で消える）。

```
src/                           # 直すのはここ
  site.json                    # サイト名・Home の言葉・セクション名・NEWS・Device の事業一覧
  programs.json                # 番組（死を、教えてくれ。／間を、喰う。／異能の表現者たち）
  contents.json                # コンテンツ（#2-1-3 など。種類・番組・状態・YouTube・記事）
  manifesto.json               # MA Notion のマニフェスト（tools/import_manifesto.py で docx から作る）
  device.json                  # Device の商品（tools/import_device.py で荒井さんの Device 表から作る）
  articles/*.html              # Magazine 記事の本文（HTML の断片。画像の @/ はサイトの最上位）
tools/
  build.py                     # src/ → 公開用 HTML（標準ライブラリだけ・Python 3.9 以上）
  import_manifesto.py          # Notion の docx → src/manifesto.json
  import_device.py             # Device 表の xlsx → src/device.json
  generated.txt                # build.py が生成したファイルの一覧
css/ js/ assets/               # 見た目と画像（assets/device/ は Device の写真）

# 生成されるページ（URL）
index.html                     # Home
notion/                        # MA Notion / 間の一次情報（マニフェスト）
channel/                       # 2 MA Channel（番組の一覧と、TV・Magazine・Radio ごとの一覧）
channel/<番組>/                # 番組ごとのページ
channel/<番組>/<番号>/         # Magazine 記事
do/  do/device/  do/device/manaka-store/   # 3 MA Do / Device / 祈りの道具屋まなか
company/  contact/             # 準備中
about.html ほか 8 月版のページ   # 新しいページへ転送するだけのページ
```

### `src/contents.json` の項目

| 項目 | 中身 |
|---|---|
| `id` | 番号。`2-1-3` の形（2.1 TV・2.2 Magazine・2.3 Radio）。重複不可 |
| `kind` | `tv` / `mag` / `radio` |
| `program` | `programs.json` の `slug` |
| `status` | `published`（公開）/ `editing`（編集中）/ `planned`（掲載予定）。公開以外は枠だけ出す |
| `title` `caption` `badge` `place` `recorded` | 表示する題・ひとこと・記事の種類・場所・収録日（`YYYY-MM-DD`） |
| `youtube` | YouTube の動画 ID（11 文字）。公開のときだけ埋め込む |
| `article` `excerpt` | Magazine の本文（`src/articles/` の断片）と抜き出し。公開のときだけ記事ページを作る |
| `redirect_from` | この記事へ転送する 8 月版の URL |
| `related` | 番組ページで「関連コンテンツ」に回すとき `true` |
| `memo` | 作業用のメモ。ページには出ないが、この repo は公開なので人に見せられないことは書かない |

`build.py` は生成の前にこれらを検査し、綴り違い・未登録の番組・画像の置き忘れがあると止まる。

Device の写真は `assets/device/` にファイル名のまま置く（Device 表の「メイン画像」「特徴 N 画像」の名前と一致させる）。

## 更新のしかた

```bash
python3 tools/build.py            # src/ から生成し直す
python3 tools/build.py --check    # 生成結果と repo のファイルが一致するか確かめる
```

マニフェストや Device 表の新しい版が届いたとき:

```bash
python3 tools/import_manifesto.py <Notion_YYYYMMDD.docx>
python3 tools/import_device.py <Device_YYYYMMDD.xlsx> --ids 2
python3 tools/build.py
```

PR と main への push では、GitHub Actions（`.github/workflows/check.yml`）が `tools/build.py --check` を実行する。
src/ を直して生成し忘れた PR や、生成された HTML を直接直した PR はここで失敗する
（マージを止めるには、main の保護設定でこの確認を必須にする）。

ローカル確認は任意の静的サーバーで（`channel/` のような URL はファイルを直接開くと一覧表示になるため、サーバー経由で見る）:

```bash
python3 -m http.server 8000
```

main への直 push は禁止。ブランチ → PR でマージする（Pages は main から自動配信）。
β版の間（2026-10-26 の定例で一般公開を決めるまで）は `src/site.json` の `noindex` を `true` にしておく。

## Provenance（archived-from）

- 初期ファイル一式はデザイナー制作の静的書き出しを Google Drive 経由で受領したもの（2026-07-27 受領 / `drive-download-20260727T043816Z-1-001/ma-website`）
- git 管理化（2026-08-02）以前は Vercel に CLI 直デプロイで公開されていた:
  - https://ma-website-pied.vercel.app/ （受領ファイルと同一内容の先行デプロイ）
  - Vercel チーム `studiosaitama-llc` の `ma-website` プロジェクト（Git 連携なし・最終デプロイ 2026-07-29 は ERROR）
- 本 repo 化以降は GitHub Pages を正とする
