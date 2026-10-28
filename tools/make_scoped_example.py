"""Rebuild the small source-scoped POI demonstration (synthetic data only)."""
from pathlib import Path
import csv,io,json,shutil
ROOT=Path(__file__).resolve().parents[1]
def main():
    src=ROOT/'examples/clean';dest=ROOT/'examples/scoped_sources';dest.mkdir(exist_ok=True)
    for name in ['area.geojson','crs.json']:shutil.copyfile(src/name,dest/name)
    spec=(src/'delivery_spec.md').read_text(encoding='utf-8')
    spec=spec.replace('C2. 相距','C3. 相距').replace('C1. 采集时间距基准时间不得超过 30 天。基准时间固定为 2026-10-01T00:00:00Z。','C1. 仅对 source="municipal" 的记录，采集时间距基准时间不得超过 7 天。基准时间固定为 2026-10-01T00:00:00Z。\nC2. 仅对 source="survey" 的记录，采集时间距基准时间不得超过 30 天。基准时间固定为 2026-10-01T00:00:00Z。')
    (dest/'delivery_spec.md').write_bytes(spec.encode('utf-8'))
    rows=list(csv.reader(io.StringIO((src/'dictionary.csv').read_text(encoding='utf-8'))));rows.append(['source','数据来源','string','true',json.dumps(['municipal','survey'])])
    with (dest/'dictionary.csv').open('w',encoding='utf-8',newline='') as f:csv.writer(f,lineterminator='\n').writerows(rows)
    rows=[['record_id','name','category','longitude','latitude','source_time','source'],['M-001','合成市政设施','学校','116.3050','39.9050','2026-09-28T00:00:00Z','municipal'],['S-001','合成普查设施','医院','116.3080','39.9080','2026-09-10T00:00:00Z','survey']]
    with (dest/'poi.csv').open('w',encoding='utf-8',newline='') as f:csv.writer(f,lineterminator='\n').writerows(rows)
    (dest/'README.md').write_text('''# 按来源执行不同的时效规则

这是新增的未批准输入示例，需先生成草案再人工审核，不属于原先六组冻结门禁包。

人工预期：municipal 的 3 天记录满足 7 天上限；survey 的 21 天记录满足 30 天上限，初始整体 PASS。把 municipal 时间改为 2026-09-10 应仅命中 municipal 实例；survey 不得误判超 7 天。未知来源不计入已通过，零匹配实例保留未知。规则范围和身份必须参与整改比较。
''',encoding='utf-8')
    print('Synthetic scoped-source input example prepared; no approval generated')
if __name__=='__main__':main()
