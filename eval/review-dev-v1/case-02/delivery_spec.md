# POI 交付要求
1. 每条记录必须具有字典声明的全部必填字段。
2. All required fields must be nonempty. Do not trim leading or trailing whitespace before checking.
3. 所有字段必须按数据字典声明的数据类型解析。
4. category 只能使用数据字典枚举编码，不允许别名。
5. record_id 必须在交付数据中唯一。
6. 经度必须落在 [-180,180]，纬度必须落在 [-90,90]，单位为度。
7. 坐标参考系必须声明为 EPSG:4326，不可按坐标量级推断。
8. All points must lie inside the project polygon; points exactly on the boundary are excluded.
9. Records must be no older than 6 days relative to 2026-09-25T00:00:00Z.
10. 仅供参考：名称相同且距离不超过 8 米时标记重复候选，不作为放行依据。
