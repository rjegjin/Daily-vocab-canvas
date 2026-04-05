"""
GCP 실제 청구 조회 (BigQuery billing export 기반)

사용법:
  python billing.py              이번 달 서비스별 요약
  python billing.py --days 7     최근 7일 일별 상세
  python billing.py --month 2026-03  특정 월 조회
  python billing.py --services   서비스 목록만

데이터 반영 시차: 수 시간 ~ 최대 24시간
"""
import sys
import os
import subprocess
import json
from datetime import date, timedelta

BILLING_ACCOUNT = "01783D-3C5897-F7345E"
PROJECT         = "gen-lang-client-0367740438"
DATASET         = "billing_export"
BQ              = os.path.expanduser("~/google-cloud-sdk/bin/bq")

# 서비스 표시명 단축
SERVICE_ALIAS = {
    "Generative Language API":        "Gemini API",
    "Vertex AI":                       "Vertex AI (Imagen4)",
    "Cloud Text-to-Speech API":        "TTS",
    "BigQuery":                        "BigQuery",
    "Cloud Storage":                   "Storage",
}

def _bq(sql: str) -> list[dict]:
    """bq query 실행 후 JSON 결과 반환"""
    cmd = [
        BQ, "query",
        "--project_id", PROJECT,
        "--format", "json",
        "--nouse_legacy_sql",
        sql,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr.strip()
        if "Not found: Table" in err or "not found" in err.lower():
            raise RuntimeError("NO_TABLE")
        raise RuntimeError(err)
    output = result.stdout.strip()
    if not output or output == "[]":
        return []
    return json.loads(output)


def _find_table() -> str:
    """billing_export 데이터셋에서 실제 테이블명 찾기"""
    cmd = [BQ, "ls", "--format", "json", f"{PROJECT}:{DATASET}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    tables = json.loads(result.stdout)
    # gcp_billing_export_v1_* 형태
    for t in tables:
        tid = t.get("tableId", "")
        if tid.startswith("gcp_billing_export"):
            return f"`{PROJECT}.{DATASET}.{tid}`"
    return None


def _no_data_msg():
    print("\n⏳ BigQuery에 아직 데이터가 없습니다.")
    print("   설정 후 수 시간 ~ 최대 24시간 뒤 첫 데이터가 적재됩니다.")
    print("   내일 아침 다시 실행해 보세요.\n")


def _month_summary(table: str, year_month: str):
    """월별 서비스별 비용 요약 (KRW + USD)"""
    y, m = year_month.split("-")
    sql = f"""
SELECT
  service.description                          AS service,
  ROUND(SUM(cost), 2)                          AS cost_usd,
  ROUND(SUM(cost * 1350), 0)                   AS cost_krw
FROM {table}
WHERE
  invoice.month = '{y}{m}'
  AND project.id IN ('gen-lang-client-0367740438', 'integral-genius-428305-n7')
GROUP BY service
ORDER BY cost_usd DESC
"""
    rows = _bq(sql)
    if not rows:
        print(f"\n  {year_month} 데이터 없음 (아직 미반영이거나 비용 0)\n")
        return

    total_usd = sum(float(r["cost_usd"]) for r in rows)
    total_krw = sum(float(r["cost_krw"]) for r in rows)

    print(f"\n{'='*52}")
    print(f"  💳 {year_month} 실제 청구 (BigQuery export)")
    print(f"{'='*52}")
    for r in rows:
        svc = SERVICE_ALIAS.get(r["service"], r["service"])
        usd = float(r["cost_usd"])
        krw = int(float(r["cost_krw"]))
        print(f"  {svc:<28} ${usd:>8.4f}  ₩{krw:>8,}")
    print(f"{'─'*52}")
    print(f"  {'합계':<28} ${total_usd:>8.4f}  ₩{int(total_krw):>8,}")
    print(f"{'='*52}\n")


def _daily_detail(table: str, days: int):
    """최근 N일 일별 비용"""
    since = (date.today() - timedelta(days=days)).isoformat()
    sql = f"""
SELECT
  DATE(usage_start_time)                       AS day,
  service.description                          AS service,
  ROUND(SUM(cost), 4)                          AS cost_usd
FROM {table}
WHERE
  DATE(usage_start_time) >= '{since}'
  AND project.id IN ('gen-lang-client-0367740438', 'integral-genius-428305-n7')
GROUP BY day, service
ORDER BY day DESC, cost_usd DESC
"""
    rows = _bq(sql)
    if not rows:
        print(f"\n  최근 {days}일 데이터 없음\n")
        return

    print(f"\n{'='*52}")
    print(f"  📅 최근 {days}일 일별 상세")
    print(f"{'='*52}")
    cur_day = None
    day_total = 0.0
    for r in rows:
        if r["day"] != cur_day:
            if cur_day:
                print(f"  {'':>30}  소계 ${day_total:.4f}")
                print(f"{'─'*52}")
            cur_day = r["day"]
            day_total = 0.0
            print(f"  {r['day']}")
        svc = SERVICE_ALIAS.get(r["service"], r["service"])
        usd = float(r["cost_usd"])
        day_total += usd
        print(f"    {svc:<30} ${usd:.4f}")
    if cur_day:
        print(f"  {'':>30}  소계 ${day_total:.4f}")
    print(f"{'='*52}\n")


def _service_list(table: str):
    """과금된 서비스 목록"""
    sql = f"""
SELECT DISTINCT service.description AS service
FROM {table}
WHERE project.id IN ('gen-lang-client-0367740438', 'integral-genius-428305-n7')
ORDER BY service
"""
    rows = _bq(sql)
    print("\n서비스 목록:")
    for r in rows:
        print(f"  - {r['service']}")
    print()


def main():
    args = sys.argv[1:]

    try:
        table = _find_table()
        if not table:
            _no_data_msg()
            return

        if "--services" in args:
            _service_list(table)
            return

        if "--days" in args:
            idx = args.index("--days")
            days = int(args[idx + 1]) if idx + 1 < len(args) else 7
            _daily_detail(table, days)
            return

        if "--month" in args:
            idx = args.index("--month")
            ym = args[idx + 1] if idx + 1 < len(args) else date.today().strftime("%Y-%m")
            _month_summary(table, ym)
            return

        # 기본: 이번 달
        ym = date.today().strftime("%Y-%m")
        _month_summary(table, ym)

    except RuntimeError as e:
        if "NO_TABLE" in str(e):
            _no_data_msg()
        else:
            print(f"❌ 오류: {e}")


if __name__ == "__main__":
    main()
