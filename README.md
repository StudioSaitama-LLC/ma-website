# 間｜MA — ma-website

Indies Lifestyle Media 間｜MA のウェブサイト（株式会社まなか × Studio Saitama）。
静的 HTML/CSS/JS 構成。GitHub Pages で公開する。

- 公開URL: https://studiosaitama-llc.github.io/ma-website/
- 関連リポジトリ: [ma-jpn](https://github.com/StudioSaitama-LLC/ma-jpn)（旧サイト / GitHub Pages。本 repo とは別系統）
- 企画・戦略ドキュメント: `studiosaitama/clients/manaka/docs/`（ローカル）/ [manaka-docs](https://github.com/StudioSaitama-LLC/manaka-docs)

## 構成

```
index.html                      # Home（カウンター・ポエム・TOC）
about.html                      # About MA / 間とは何か？
ma-channel.html                 # MA Channel / 間の流通化
edge-riders.html                # 2.1 Edge Riders / 密を往く者たち
beyond-the-vanishing-point.html # 2.2 Beyond the Vanishing point / 死を、教えてくれ。
article-3-2-1.html              # 2.2.1 仁科正史 記事
css/ js/ assets/
```

技術スタック: 素の HTML / CSS / JS（ビルドなし）。全リンク相対パスのためプロジェクトページ配下でそのまま動作する。

## 開発

ローカル確認は任意の静的サーバーで:

```bash
python3 -m http.server 8000
```

main への直 push は禁止。ブランチ → PR でマージする（Pages は main から自動配信）。

## Provenance（archived-from）

- 初期ファイル一式はデザイナー制作の静的書き出しを Google Drive 経由で受領したもの（2026-07-27 受領 / `drive-download-20260727T043816Z-1-001/ma-website`）
- git 管理化（2026-08-02）以前は Vercel に CLI 直デプロイで公開されていた:
  - https://ma-website-pied.vercel.app/ （受領ファイルと同一内容の先行デプロイ）
  - Vercel チーム `studiosaitama-llc` の `ma-website` プロジェクト（Git 連携なし・最終デプロイ 2026-07-29 は ERROR）
- 本 repo 化以降は GitHub Pages を正とする
