# 概要
本リポジトリでは、下記の機能を提供します。
| 機能名                                   | 機能概要                                                                                                       |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| TBL出力（設備データ管理マスタDB→3D用最終断面テーブル） | 設備データ管理マスタDBから設備データを取得し、編集したものを3D用最終断面テーブル（マテリアライズドビュー）に登録し、GeoServerに配信設定を登録する。 |

# フォルダ構成
```
└── App
    ├── common              // 共通処理モジュール（依存リポジトリからコピー）
    ├── config              // 設定ファイル（依存リポジトリからコピー）
    ├── core                // 基盤機能モジュール（依存リポジトリからコピー）
    ├── functions           // 機能実装（本機能）
    ├── geoServerSettings   // GeoServer設定ファイル
    └── util                // 各種ユーティリティモジュール（依存リポジトリからコピー）
```

# リポジトリ利用方法
必要なソフトウェアやサービスの詳細は[前提条件](#前提条件)をご参照ください。
1. 依存リポジトリ（repo_infradx_ap_BSC_0020）から共通モジュールをコピーします。
    ```bash
    # common、config、core、utilディレクトリのファイルをコピー
    cp -r <依存リポジトリのパス>/App/common/* App/common/
    cp -r <依存リポジトリのパス>/App/config/* App/config/
    cp -r <依存リポジトリのパス>/App/core/* App/core/
    cp -r <依存リポジトリのパス>/App/util/* App/util/
    ```

2. 依存ライブラリをインストールします。
    ```bash
    pip install -r App/requirements.txt
    ```

3. ソース記載の一部情報を変更します。
    下記はAWS Secrets Managerに関する情報となっております。
    リポジトリ上ではシークレット名はマスクされているため、適切な値に書き換えてください。
    | 記載ファイル | 書き換え対象                             | 概要                                                                              |
    | ------------ | ---------------------------------------- | --------------------------------------------------------------------------------- |
    | config.ini   | cloud.aws.secretmanager.secretname       | シークレット名指定                                                                |

4. AWS Secrets Managerに以下の設定値を登録します。
    | キー名                 | 概要                                   |
    | ---------------------- | -------------------------------------- |
    | db_mst_schema          | マスタDBスキーマ名                     |
    | db_fac_schema          | 設備データDBスキーマ名                 |
    | db_mv_3d_schema        | 3D用最終断面テーブルスキーマ名         |
    | db_mv_host             | 最終断面DBホスト名（カンマ区切り）     |
    | domain_name            | GeoServer公開用ドメイン名              |
    | geoserver_workspace    | GeoServerのワークスペース名            |
    | postgis_store_name     | GeoServer上のPostGISデータストア名     |
    | geoserver_username     | GeoServerのユーザー名                  |
    | geoserver_password     | GeoServerのパスワード                  |
    | geoserver_env          | GeoServer環境識別子（例: dev/stg/prod） |
    | cd0203_updateNumberOfImports | CD0203_取込件数更新スクリプトパス |

5. Pythonスクリプトを実行します。
    ```bash
    cd App/functions
    python FDI_0100_tblExportEquipmentMasterTo3d.py --layer_id=<レイヤID>
    ```
    ※レイヤIDは必須パラメータです（複数指定可能、カンマ区切り）

6. 実行ログを確認します。
    処理実行後、以下のようなログが出力されます。
    ```
    [2026-02-03 18:54:58,621] [INFO] [FDI] BPI0001:FDI_0100_TBL出力（設備データ管理マスタDB→3D用最終断面テーブル）処理 開始
    [2026-02-03 18:54:58,710] [INFO] [FDI] BPI0002:FDI_0100_TBL出力（設備データ管理マスタDB→3D用最終断面テーブル）処理 終了
    ```
    
    ログファイルの出力先は設定ファイル（`App/config/config.ini`）の以下の設定で定義されています。
    ```ini
    ; ログファイルパス
    log_file_path = /infradx/logs/infradx-batch/infradx-batch.log
    ```

# 利用OSS一覧
アプリケーションを利用するにあたり、以下OSSが必要です。
Python関連パッケージは App/requirements.txt に記載しており、`pip install -r App/requirements.txt` でインストールされます。

| OSS名       | バージョン | ライセンス                                   |
| ----------- | ---------- | -------------------------------------------- |
| Python      | 3.13.9     | PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2 |
| PostgreSQL  | 16.8       | The PostgreSQL Licence                       |
| PostGIS     | 3.4        | GNU General Public License version 2         |
| GeoServer   | 2.24       | GNU General Public License version 2         |

# 再配布OSS一覧
本リポジトリには再配布するOSSは含まれていません。
実行に必要なOSSは[利用OSS一覧](#利用OSS一覧)をご参照ください。

# 問い合わせに関して
1. 本リポジトリは配布を目的としており、IssueやPull Requestを受け付けておりません。

# ライセンス
1. 本リポジトリはMIT Licenseで提供されています。
2. ソースコードおよび関連ドキュメントの著作権はNTTインフラネット株式会社及び株式会社NTTデータに帰属します。

# 免責事項
1. 本リポジトリの内容は予告なく変更・削除する可能性があります。
2. 本リポジトリの利用により生じた損失及び損害等について、いかなる責任も負わないものとします。
