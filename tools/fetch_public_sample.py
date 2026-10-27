"""Fetch a frozen public USGS point dataset; never executed during ordinary app use."""
import json,hashlib,datetime,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    url='https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson'
    req=urllib.request.Request(url,headers={'User-Agent':'GeoAcceptance-public-sample/0.5'})
    with urllib.request.urlopen(req,timeout=30) as r:raw=r.read(5_000_000)
    data=json.loads(raw);out=ROOT/'data'/'public';out.mkdir(exist_ok=True)
    (out/'usgs-earthquakes.geojson').write_bytes(raw)
    meta={'source_url':url,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(raw).hexdigest(),
          'feature_count':len(data['features']),'provider':'US Geological Survey',
          'rights':'USGS-authored data generally public domain; review source-specific third-party credits before reuse.',
          'rights_url':'https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits',
          'use':'Real public point IO/quality case, not a known-defect benchmark. Depth is deliberately excluded by the canonical 2D CSV mapping.'}
    (out/'SOURCE.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8');print(meta['feature_count'],meta['sha256'])
if __name__=='__main__':main()
