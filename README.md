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
  site.json                    # サイト名・Gate と Door・Home の言葉・NEWS・Notion の図の言葉・お店の一覧・値段の表示
  programs.json                # 番組（間を、喰う／死を、教えてくれ。／異能の表現者たち）と回（ゲストごとのまとまり）
  contents.json                # コンテンツ（#2-1-3 など。種類・番組・回・状態・YouTube・記事）
  manifesto.json               # MA Notion のマニフェスト（tools/import_manifesto.py で docx から作る）
  device.json                  # Device の商品（tools/import_device.py で荒井さんの Device 表から作る）
  company.json                 # Company（まなかの軌道・会社概要・運営施設）と Contact us の窓口
  articles/*.html              # Magazine 記事の本文（HTML の断片。画像の @/ はサイトの最上位。article-head の中に日付の目印 <!-- build:meta --> を置く）
  lab.json                     # Gate 1: MA Lab の試作データ（用語・資料・検証のテーマ）
tools/
  build.py                     # src/ → 公開用 HTML（標準ライブラリだけ・Python 3.9 以上）
  import_manifesto.py          # Notion の docx → src/manifesto.json
  import_device.py             # Device 表の xlsx → src/device.json
  generated.txt                # build.py が生成したファイルの一覧
css/ js/ assets/               # 見た目と画像（assets/device/ は Device の写真、assets/illust/ は手描きの絵）

# 生成されるページ（URL）
index.html                     # Home
notion/                        # Gate 0: MA Notion（マニフェスト・密と間・三段の図）
lab/                           # Gate 1: MA Lab（試作。dictionary/ reference/ research/ の 3 部屋）
channel/                       # Gate 2: MA Channel（番組の一覧と、TV・Magazine・Radio ごとの新着）
channel/<番組>/                # 番組ごとのページ（回ごとに開閉。#ep-<回> で開いた状態で来られる）
channel/<番組>/<番号>/         # Magazine 記事
do/  do/device/                # Gate 3: MA Do / Device Room（検索・お店で絞り込み）
do/device/<お店>/<商品ID>/     # 商品のページ
company/  contact/             # Company / Contact us
about.html ほか 8 月版のページ   # 新しいページへ転送するだけのページ
```

### `src/contents.json` の項目

| 項目 | 中身 |
|---|---|
| `id` | 番号。`2-1-3` の形（2.1 TV・2.2 Magazine・2.3 Radio）。重複不可 |
| `kind` | `tv` / `mag` / `radio` |
| `program` | `programs.json` の `slug` |
| `episode` | `programs.json` の回の `key`（同じゲストの TV・Magazine・Radio をまとめる）。無ければ 1 件で 1 回 |
| `date` | 公開日（`YYYY-MM-DD`）。無ければ回（`programs.json` の episodes）の日付を引き継ぐ。Home の News には公開済みの回だけが新しい順に 3 件まで出る。`<NEW>` は日付の新しい 3 つのうち、いちばん新しい日付から 60 日以内のものに付く |
| `status` | 必須。`published`（公開）/ `editing`（編集中）/ `planned`（掲載予定）。公開以外は枠だけ出す |
| `title` `caption` `badge` `place` `recorded` | 表示する題・ひとこと・記事の種類・場所・収録日（`YYYY-MM-DD`） |
| `youtube` | YouTube の動画 ID（11 文字）。公開のときだけ埋め込む |
| `article` `excerpt` | Magazine の本文（`src/articles/` の断片）と抜き出し。公開のときだけ記事ページを作る |
| `redirect_from` | この記事へ転送する 8 月版の URL |
| `hero` `portrait` `portrait_focus` | 記事の冒頭で切り替わる写真（`assets/` の名前の並び）・記事の終わりに画面いっぱいに出す人物の写真・その切り抜きの中心（例 `"68% 50%"`） |
| `related` | 番組ページで「関連コンテンツ」に回すとき `true` |
| `memo` | 作業用のメモ。ページには出ないが、この repo は公開なので人に見せられないことは書かない |

`build.py` は生成の前にこれらを検査し、綴り違い・未登録の番組・画像の置き忘れがあると止まる。

Device の写真は `assets/device/` にファイル名のまま置く（Device 表の「メイン画像」「特徴 N 画像」の名前と一致させる）。

### 見た目について（2026-10-16 版デザイン）

- 荒井さんの PC / Phone の PDF（10/16）に合わせている。色は青地（`#1414dc`）に白、リンクと選ばれている所は水色。フッターの切り替えで灰地になる
- 寸法は スマホ 375px と PC 1920px のデザインの位置に合わせた。PC の寸法は画面の幅 1200px 以上で使う。481〜1199px（タブレットなど）はデザインが無いので、スマホの寸法のまま 480px の列にして中央に置く。360px 未満の小さい画面は、ページ全体を 0.8533 倍に縮めて組む（320px でちょうど 375px の組みになる。そのため 360px の前後で文字の大きさが少し変わる）
- 章（Notion・Company）は HTML の時点で閉じてあり、`js/main.js` が ↓ で開く。JavaScript が切ってある画面では全文を出すが、`js/main.js` だけが読み込めなかったときは閉じたままになる
- `assets/illust/` の手描きの絵（8 点）は SVG。デザインの高解像度の描画から線をなぞって作った。差し替えるときの取り決め:
  - 先頭の `<svg>` に `viewBox`、絵の本体は `<symbol id="art" viewBox="…">` の中に入れる（ページは `<use href="…#art">` で呼ぶ）
  - 色は `fill="currentColor"` にする（青地では白、灰地では黒になる）
  - 取り決めに合わないと `build.py` が止まる
- `assets/figures/` の「密」「間」の球（Notion）は、デザインの描画から球の中心と大きさを測って `tools/make_spheres.py` で作った SVG（光は右上から・下に影）
- 生成した HTML にある `data-m` / `data-mt` は、デザインの位置と比べる採寸用の目印（表示や動きには使っていない）
- **MA Lab は試作**。`src/lab.json` に用語（Dictionary）・資料（Reference）・検証のテーマ（Research）を書く。
  置き方の決まり: どの項目も、マニフェスト（`src/manifesto.json`）の章 `ch`（整数）と、その本文に一字一句そのまま含まれる
  8 字以上の一節 `quote` を持つ（無ければ `build.py` が止める）
  - 要素 `elements`: マニフェストの考えを分解したもの。`key`・`name`（6 字まで。地図の札に入れる）・`sub`（一言）・
    `mitsu`（密の側の姿）・`ma`（間の側の姿）・`ch` と `quote`・`acts`（マニフェストの羅列から、この要素に当たる行い）。
    用語・資料・検証は `elements` でこの `key` を引く。資料が 1 つも無い要素があると止める
  - 用語 `terms`: `key`（英小文字）・`word`・`reading`・`kind`・一般の意味 `gloss`・マニフェストでの使われ方 `sense`（本文に書いてあることだけ）・
    `onomatopoeia`（手がかりの語の並び）・`related`（他の用語の `key`）・`question`。`acts` は本文の羅列を写すとき
  - 資料 `references`: `id`（英小文字。年は入れない）・`form`（`forms` のどれか）・`field`・`title`・`creator`・`year`（文字列）・
    `terms`（用語の `key`）・`elements`（映っている要素。`相談中` 以外は 1 つ以上）・なぜ置くか `why`・`question`・`pole`（0 が密、100 が間）・`status`・`note`。
    `status` は **確認済み**（本は書誌を国会図書館・CiNii・版元で、作品・展覧会・標語は初演・初出・開催年を公開情報で確かめ、PR に確認先を残した）／**候補**（まだ確かめていない）／**相談中**（載せ方を決めていない）
  - 検証 `research`: `id`・`theme`・`lines`・`terms`・`status`。こちらの `status` は Channel と同じ `published / editing / planned`
  - `doors` は扉の日本語名 `ja` と役割 `role`（番号と英名は `site.json` の gates）。`poles` は目盛りの両端の名前
- Home の Ryan Gander の引用は、掲載の可否を確かめてから `src/site.json` の `quote.lines` に入れる（空のあいだは案内の一文が出る）
- 商品の値段は Device 表では税抜なので、`src/site.json` の `price` の決まりで税込にして出す（総額表示）

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
