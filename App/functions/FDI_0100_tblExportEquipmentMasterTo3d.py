"""

FDI_0100_tblExportEquipmentMasterTo3d.py

処理名:
    TBL出力（設備データ管理マスタDB→3D用最終断面テーブル）

概要:
    設備データ管理マスタDBから設備データを取得し、編集したものを
    3D用最終断面テーブル（マテリアライズドビュー）に登録し、
    GeoServerに配信設定を登録する。
"""

import argparse
import os
import platform
import re
import subprocess
import sys
import traceback

import requests
from common.CD0201_updateStartEndDateOfUse import update_start_and_end_date_of_use
from common.CD0202_updateEndDateOfUse import update_end_date_of_use
from core.config_reader import read_config
from core.constants import Constants
from core.database import Database
from core.geoserverRequest import GeoServerRequest
from core.logger import LogManager
from core.secretProperties import SecretPropertiesSingleton
from core.validations import Validations
from util.checkMstConsistency import CheckMstConsistency

log_manager = LogManager()
logger = log_manager.get_logger(
    "FDI_0100_01_TBL出力（設備データ管理マスタDB→3D用最終断面テーブル）"
)
config = read_config(logger)
# secret_nameをconfigから取得し、secret_propsにAWS Secrets Managerの値を格納
secret_name = config["aws"]["secret_name"]
secret_props = SecretPropertiesSingleton(secret_name, config, logger)

# グローバル終了コード（0:正常, 1:異常, 2:警告）
process_code = Constants.RETURNCODE_SUCCESS


# 起動パラメータを受け取る関数
def parse_args():
    try:
        # 完全一致のみ許可
        parser = argparse.ArgumentParser(allow_abbrev=False, exit_on_error=False)
        parser.add_argument("--layer_id", required=True)
        args = parser.parse_args()
        layer_ids = [lid.strip() for lid in args.layer_id.split(",") if lid.strip()]
        return layer_ids
    except Exception as e:
        # コマンドライン引数の解析に失敗した場合
        logger.error("BPE0037", str(e))
        logger.process_error_end()


# スクリプト存在チェック
def check_required_scripts_exist():
    global secret_props
    script_path_import = secret_props["cd0203_updateNumberOfImports"]
    if not os.path.exists(script_path_import):
        logger.error("BPE0042", "CD0203_取込件数更新", script_path_import)
        logger.process_error_end()


# 1. 入力値チェック
def validate_layer_ids(layer_ids):
    for layer_id in layer_ids:
        # レイヤIDの必須チェック
        if not layer_id:
            logger.error("BPE0018", "レイヤID")
            logger.process_error_end()

        # レイヤIDが、半角英数字とアンダースコアのみで構成されているか
        if not Validations.is_alnum_underscore(layer_id):
            logger.error("BPE0019", "レイヤID", layer_id)
            logger.process_error_end()

        # レイヤIDが、桁数（1以上50以下）であるか
        if not Validations.is_valid_length(layer_id, 1, 50):
            logger.error("BPE0019", "レイヤID", layer_id)
            logger.process_error_end()

        # 3D用最終断面のフォーマットチェック（_3d_x 形式）
        if not re.match(r"^[a-z_]+_3d_\d+$", layer_id):
            logger.error("BPE0019", "レイヤID", layer_id)
            logger.process_error_end()


# 2. マスタ整合性チェック
def check_master_consistency(layer_ids):
    global process_code
    for layer_id in layer_ids:
        result = CheckMstConsistency.check(layer_id, logger)
        if result == Constants.RETURNCODE_SUCCESS:
            logger.info("BPI0008", "マスタ整合性チェック", layer_id)
        if result == Constants.RETURNCODE_ERROR:
            process_code = Constants.RETURNCODE_WARNING
            logger.warning("BPW0007", "マスタ整合性チェック", layer_id)
            return


# 3. 取込開始日時・終了日時更新
def update_import_datetime(layer_ids):
    global process_code
    result = update_start_and_end_date_of_use(layer_ids)
    if result == Constants.RETURNCODE_SUCCESS:
        logger.info("BPI0008", "CD0201_取込開始日時・終了日時更新", layer_ids)
    elif result == Constants.RETURNCODE_ERROR:
        process_code = Constants.RETURNCODE_WARNING
        logger.warning("BPW0007", "CD0201_取込開始日時・終了日時更新", layer_ids)
    return result


# 4. マテリアライズドビュー存在確認
def check_matview_exists(layer_id):
    global secret_props
    db_mv_hosts = [h.strip() for h in secret_props.get("db_mv_host").split(",")]
    db_mv_3d_schema = secret_props.get("db_mv_3d_schema")
    matview_no_list = []
    matview_yes_list = []
    for layer_id in layer_id:
        for db_host in db_mv_hosts:
            query = (
                "SELECT EXISTS("
                "SELECT 1 FROM pg_matviews "
                "WHERE schemaname = %s AND matviewname = %s"
                ")"
            )
            db_connection = Database.get_refdb_connection(db_host, logger)
            result = Database.execute_query(
                db_connection,
                logger,
                query,
                params=(db_mv_3d_schema, layer_id),
                fetchone=True,
            )
            if not result:
                matview_no_list.append(layer_id)
                break
            if db_host == db_mv_hosts[-1]:
                matview_yes_list.append(layer_id)
    return matview_no_list, matview_yes_list


# 5. 設備データ管理マスタDB存在確認
def check_equipment_master_table_exists(layer_ids):
    global process_code
    global secret_props
    eq_master_tables = {lid: "data_" + lid.replace("_3d", "") for lid in layer_ids}
    db_hosts = [secret_props.get("db_host")]
    db_fac_schema = secret_props.get("db_fac_schema")
    for table_name in eq_master_tables.values():
        for db_host in db_hosts:
            query = (
                "SELECT EXISTS("
                "SELECT 1 FROM pg_tables "
                "WHERE schemaname = %s AND tablename = %s"
                ")"
            )
            db_connection = Database.get_refdb_connection(db_host, logger)
            result = Database.execute_query(
                db_connection,
                logger,
                query,
                params=(db_fac_schema, table_name),
                fetchone=True,
            )
            if not result:
                process_code = Constants.RETURNCODE_WARNING
                logger.warning("BPW0016", "設備データ管理マスタDB存在確認", table_name)
                return False


# 6. マテリアライズドビュー作成・リフレッシュ
def create_or_refresh_matview(matview_no_list, matview_yes_list):
    global process_code
    global secret_props
    db_mv_hosts = [h.strip() for h in secret_props.get("db_mv_host").split(",")]
    db_mv_3d_schema = secret_props.get("db_mv_3d_schema")
    db_mst_schema = secret_props.get("db_mst_schema")
    db_fac_schema = secret_props.get("db_fac_schema")
    # DDL実行前にタイムアウト無制限を設定（一度だけ）
    ddl_queries = ["SET statement_timeout = 0"]
    for layer_id in matview_no_list:
        # 6-1-1. マテリアライズドビューDDL出力項目取得
        parts = layer_id.split("_3d_")
        equipment_item = parts[0]
        provider_id = parts[1] if len(parts) > 1 else ""
        query = (
            f"SELECT ma.physical_column_name "
            f"FROM {db_mst_schema}.mst_final_cross_section_authorization fca "
            f"INNER JOIN {db_mst_schema}.mst_fac_subitem fs "
            f"    ON fca.fac_subitem_id = fs.fac_subitem_id "
            f"INNER JOIN {db_mst_schema}.mst_attribute_reference_availability mara "
            f"    ON fca.authorization_pattern_id = mara.authorization_pattern_id "
            f"INNER JOIN {db_mst_schema}.mst_attribute ma "
            f"    ON mara.column_id = ma.column_id "
            f"    AND ma.fac_subitem_id = fca.fac_subitem_id "
            f"WHERE fs.fac_subitem_eng = %s "
            f"  AND fca.provider_id = %s "
            f"  AND fca.final_cross_section_type = 2 "
            f"  AND ma.physical_column_name <> 'mg_id' "
            f"  AND ma.physical_column_name <> 'created_by' "
            f"  AND ma.physical_column_name <> 'created_at' "
            f"  AND ma.physical_column_name <> 'updated_by' "
            f"  AND ma.physical_column_name <> 'updated_at' "
            f"ORDER BY ma.column_id"
        )
        db_host_for_column = secret_props.get("db_host")
        db_connection_for_column = Database.get_refdb_connection(
            db_host_for_column, logger
        )
        result = Database.execute_query(
            db_connection_for_column,
            logger,
            query,
            params=(equipment_item, provider_id),
            fetchall=True,
        )
        column_names = []
        if result:
            for row in result:
                if row and row[0].strip():
                    column_names.append(row[0].strip())

        if not column_names:
            continue

        code_columns = set()
        placeholders = ", ".join(["%s"] * len(column_names))
        code_columns_sql = (
            f"SELECT DISTINCT physical_column_name FROM {db_mst_schema}.mst_code "
            f"WHERE physical_column_name IN ({placeholders})"
        )
        code_columns_result = Database.execute_query(
            db_connection_for_column,
            logger,
            code_columns_sql,
            params=tuple(column_names),
            fetchall=True,
        )
        code_columns = {row[0] for row in code_columns_result}

        # 6-1-2. マテリアライズドビューDDL作成
        eq_master_table = "data_" + layer_id.replace("_3d", "")
        select_clauses = []
        join_clauses = []
        for col in column_names:
            select_clauses.append(f"{eq_master_table}.{col}")
            if col in code_columns:
                select_clauses.append(f"code_{col}.code_name AS {col}_name")
                join_clauses.append(
                    f"LEFT JOIN {db_mst_schema}.mst_code AS code_{col} "
                    f"ON {eq_master_table}.{col} = code_{col}.code "
                    f"AND code_{col}.physical_column_name = '{col}'"
                )
        select_clauses.append(f"{eq_master_table}.geom AS geom")
        select_clause = ", ".join(select_clauses)
        join_clause = " ".join(join_clauses)

        ddl = (
            f"CREATE MATERIALIZED VIEW {db_mv_3d_schema}.{layer_id} AS "
            f"SELECT {select_clause} "
            f"FROM {db_fac_schema}.{eq_master_table} {join_clause}"
        )
        ddl_queries.append(ddl)

        unique_index_ddl = (
            f"CREATE UNIQUE INDEX {layer_id}_pk_idx "
            f"ON {db_mv_3d_schema}.{layer_id} (id)"
        )
        ddl_queries.append(unique_index_ddl)

        geom_index_ddl = (
            f"CREATE INDEX {layer_id}_geom_idx "
            f"ON {db_mv_3d_schema}.{layer_id} USING GIST (geom)"
        )
        ddl_queries.append(geom_index_ddl)

    # 6-2. リフレッシュクエリ生成
    for layer_id in matview_yes_list:
        ddl_queries.append(
            f"REFRESH MATERIALIZED VIEW CONCURRENTLY {db_mv_3d_schema}.{layer_id}"
        )

    # 6-3. DDL・SQLクエリ実行
    for db_host in db_mv_hosts:
        db_connection = Database.get_refdb_connection(db_host, logger)
        for query in ddl_queries:
            try:
                Database.execute_query(
                    db_connection, logger, query, commit=False, raise_exception=True
                )
            except Exception:
                process_code = Constants.RETURNCODE_WARNING
                logger.warning("BPW0021", db_host, query)
                db_connection.rollback()
                return
        db_connection.commit()


# 7. レイヤ定義存在確認
def check_layer_definition_exists(layer_ids):
    global process_code
    no_def_list = []
    for layer_id in layer_ids:
        status = GeoServerRequest.check_layer_exists_common(layer_id, logger)
        if status == Constants.HTTP_STATUS_NOT_FOUND:
            no_def_list.append(layer_id)
        elif status != Constants.HTTP_STATUS_OK:
            process_code = Constants.RETURNCODE_WARNING
            logger.warning("BPW0005", "存在確認", layer_id)
    return no_def_list


# 8. 利用開始・終了年月日過去日更新
def update_layer_dates_past(layer_ids):
    global secret_props
    schema_name = secret_props.get("db_mst_schema")
    db_mst_connection = Database.get_mstdb_connection(logger)
    start_dates = {}
    end_dates = {}

    select_query = (
        f"SELECT layer_id, start_date_of_use, end_date_of_use "
        f"FROM {schema_name}.mst_vector_layer "
        "WHERE layer_id = ANY(%s)"
    )
    results = Database.execute_query(
        db_mst_connection,
        logger,
        select_query,
        params=(layer_ids,),
        fetchall=True,
    )
    if results:
        for row in results:
            start_dates[row[0]] = row[1]
            end_dates[row[0]] = row[2]

    update_query = (
        f"UPDATE {schema_name}.mst_vector_layer "
        "SET start_date_of_use = %s, end_date_of_use = %s, "
        "updated_by = 'system', updated_at = NOW() "
        "WHERE layer_id = ANY(%s)"
    )
    Database.execute_query(
        db_mst_connection,
        logger,
        update_query,
        params=("19000101", "19000101", layer_ids),
        commit=True,
    )
    return start_dates, end_dates


# 9. 配信設定
def create_sqlview_and_register(layer_ids):
    global process_code
    global secret_props

    # 9-1. SQLView定義の作成
    try:
        template_path = os.path.join(
            os.path.dirname(__file__), "../geoServerSettings/sqlview_3d.xml"
        )
        with open(template_path, "r", encoding="utf-8") as f:
            xml_template = f.read()
        # 二重改行対策のためWindows環境では&#10;を削除、Linuxではそのまま残す
        if platform.system() == "Windows":
            xml_template = xml_template.replace("&#10;", "")
    except Exception:
        logger.error("BPE0040", traceback.format_exc())
        logger.process_error_end()

    # 9-2. ベクタレイヤ定義追加のREST APIを実行
    db_mst_schema = secret_props.get("db_mst_schema")
    db_mv_3d_schema = secret_props.get("db_mv_schema")
    domain_name = secret_props.get("domain_name")
    geoserver_workspace = secret_props.get("geoserver_workspace")
    postgis_store = secret_props.get("postgis_store_name")
    geoserver_username = secret_props.get("geoserver_username")
    geoserver_password = secret_props.get("geoserver_password")
    geoserver_env = secret_props.get("geoserver_env")
    url = (
        f"http://{domain_name}/{geoserver_env}/rest/workspaces/"
        f"{geoserver_workspace}/datastores/"
        f"{postgis_store}/featuretypes"
    )
    headers = {"Content-Type": "text/xml"}
    for layer_id in layer_ids:
        try:
            xml_body = xml_template.replace("sqlview_layer_id", layer_id)
            xml_body = xml_body.replace("db_mst_schema", db_mst_schema)
            xml_body = xml_body.replace("db_mv_3d_schema", db_mv_3d_schema)
            response = requests.post(
                url,
                auth=(geoserver_username, geoserver_password),
                headers=headers,
                data=xml_body.encode("utf-8"),
            )
            if response.status_code != Constants.HTTP_STATUS_CREATED:
                process_code = Constants.RETURNCODE_WARNING
                logger.error("BPE0005", "追加")
        except Exception:
            process_code = Constants.RETURNCODE_WARNING
            logger.error("BPE0039", traceback.format_exc())


# 10. ベクタレイヤ矩形範囲変更
def update_layer_bbox(layer_ids):
    global process_code
    for layer_id in layer_ids:
        result = GeoServerRequest.update_layer_bounding_box_common(
            layer_id, Constants.VECTOR_LAYER_CATEGORY, logger
        )
        if result != Constants.HTTP_STATUS_OK:
            process_code = Constants.RETURNCODE_WARNING
            logger.warning("BPW0018")


# 11. 利用開始・終了年月日現在日更新
def update_layer_dates_current(layer_ids, start_dates, end_dates):
    global secret_props
    schema_name = secret_props.get("db_mst_schema")
    db_mst_connection = Database.get_mstdb_connection(logger)
    update_query = (
        f"UPDATE {schema_name}.mst_vector_layer "
        "SET start_date_of_use = %s, end_date_of_use = %s, "
        "updated_by = 'system', updated_at = NOW() "
        "WHERE layer_id = %s"
    )
    for layer_id in layer_ids:
        Database.execute_query(
            db_mst_connection,
            logger,
            update_query,
            params=(start_dates.get(layer_id), end_dates.get(layer_id), layer_id),
            commit=True,
        )


# 12. 取込終了日時更新
def update_import_end_datetime(layer_ids):
    global process_code
    result = update_end_date_of_use(layer_ids)
    if result == Constants.RETURNCODE_SUCCESS:
        logger.info("BPI0008", "CD0202_取込終了日時更新", layer_ids)
    elif result == Constants.RETURNCODE_ERROR:
        process_code = Constants.RETURNCODE_WARNING
        logger.warning("BPW0007", "CD0202_取込終了日時更新", layer_ids)


# 13. 取込件数更新
def update_import_count(layer_ids):
    global process_code
    global secret_props
    script_path = secret_props.get("cd0203_updateNumberOfImports")
    for layer_id in layer_ids:
        result = subprocess.run(
            [sys.executable, script_path, "--layer_id", layer_id],
            capture_output=True,
            text=True,
        )
        if result.returncode == Constants.RETURNCODE_SUCCESS:
            logger.info("BPI0008", "CD0203_取込件数更新", layer_id)
        else:
            process_code = Constants.RETURNCODE_WARNING
            logger.warning("BPW0007", "CD0203_取込件数更新", layer_id)


# 14.終了コード返却
def end_process():
    if (
        process_code == Constants.RETURNCODE_WARNING
        or process_code == Constants.RETURNCODE_ERROR
    ):
        logger.process_warning_end()
    else:
        logger.process_normal_end()
    return process_code


def main():
    global process_code
    try:
        # 開始ログ出力
        logger.process_start()

        # 起動パラメータを受け取る関数
        layer_ids = parse_args()

        # 1. 入力値チェック
        validate_layer_ids(layer_ids)

        # 2. マスタ整合性チェック
        check_master_consistency(layer_ids)
        if process_code == Constants.RETURNCODE_WARNING:
            return end_process()

        # 3. 取込開始日時・終了日時更新
        result = update_import_datetime(layer_ids)
        if result == Constants.RETURNCODE_ERROR:
            return end_process()

        # 4. マテリアライズドビュー存在確認
        matview_no_list, matview_yes_list = check_matview_exists(layer_ids)

        # 5. 設備データ管理マスタDB存在確認
        check_equipment_master_table_exists(matview_no_list)
        if process_code == Constants.RETURNCODE_WARNING:
            return end_process()

        # 6. マテリアライズドビュー作成・リフレッシュ
        create_or_refresh_matview(matview_no_list, matview_yes_list)
        if process_code == Constants.RETURNCODE_WARNING:
            return end_process()

        # 7. レイヤ定義存在確認
        no_def_list = check_layer_definition_exists(layer_ids)
        if len(no_def_list) >= 1:

            # 8. 利用開始・終了年月日過去日更新
            start_dates, end_dates = update_layer_dates_past(no_def_list)

            # 9. 配信設定
            create_sqlview_and_register(no_def_list)
            if process_code == Constants.RETURNCODE_WARNING:
                return end_process()

            # 10. ベクタレイヤ矩形範囲変更
            update_layer_bbox(no_def_list)
            if process_code == Constants.RETURNCODE_WARNING:
                return end_process()

            # 11. 利用開始・終了年月日現在日更新
            update_layer_dates_current(no_def_list, start_dates, end_dates)

        # 12. 取込終了日時更新
        update_import_end_datetime(layer_ids)
        if process_code == Constants.RETURNCODE_WARNING:
            return end_process()

        # 13. 取込件数更新
        update_import_count(layer_ids)

        # 14. 終了コード返却
        return end_process()
    except Exception:
        logger.error("BPE0009", traceback.format_exc())
        logger.process_error_end()


if __name__ == "__main__":
    main()
