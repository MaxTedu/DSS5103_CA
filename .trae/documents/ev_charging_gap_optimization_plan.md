# 新加坡EV充电桩缺口分析优化计划

## 优化目标

在现有基础上增加专业感和工作量，采纳以下5项优化：

1. 多级缺口分类
2. 区域聚合分析
3. 热力图可视化
4. 优先级推荐系统
5. 路网距离计算

***

## 实施步骤

### 阶段1：数据准备与环境配置

1. 更新requirements.txt，添加新依赖（osmnx, networkx, plotly等）
2. 获取新加坡规划区边界数据（用于区域聚合）
3. 准备新加坡路网数据（使用OSMNx）

### 阶段2：多级缺口分类

1. 定义5级分类标准：

   * < 200米: 优秀覆盖 (Excellent)

   * 200-500米: 良好覆盖 (Good)

   * 500-1000米: 中度缺口 (Moderate Gap)

   * 1000-2000米: 高度缺口 (High Gap)

   * <br />

     > 2000米: 严重缺口 (Severe Gap)
2. 更新HDB GeoDataFrame，添加gap\_category字段
3. 生成距离分布直方图和箱线图

### 阶段3：区域聚合分析

1. 获取新加坡规划区（Planning Areas）Shapefile
2. 空间连接：将HDB停车场和充电桩关联到规划区
3. 计算每个区域的统计指标：

   * 总停车场数量

   * 各级缺口数量及占比

   * 平均/中位数距离

   * 充电桩密度
4. 生成区域缺口率排名表
5. 区域级别 Choropleth 地图

### 阶段4：路网距离计算（优化策略：空间索引+局部搜索）

**核心优化策略：** 使用两步法大幅降低计算量

* **第一步（初筛）：** 构建空间索引，为每个HDB停车场找到直线距离最近的 **K个** 充电桩候选点（K=3-5）

* **第二步（精算）：** 仅对这K个候选点进行路网路径计算，取最小值

**详细步骤：**

1. 使用OSMNx下载新加坡路网数据（drive模式）
2. 构建路网图，添加速度/时间属性
3. 构建充电桩空间索引（R-tree或cKDTree）
4. 对每个HDB停车场：

   * 查询直线距离最近的K个充电桩（K=5）

   * 将HDB和充电桩点匹配到路网节点

   * 计算到这K个点的最短路网距离

   * 取最小值作为最终路网距离
5. 对比直线距离 vs 路网距离的差异与相关性
6. 生成路网距离与直线距离的散点图

**性能优化：**

* 计算量从 O(N×M) 降至 O(N×K)，K<\<M

* 预计可将计算时间从数小时缩短至数分钟

### 阶段5：热力图可视化

1. 充电桩密度热力图（使用folium.HeatMap）
2. 缺口区域热力图（高缺口区域聚集）
3. 距离渐变图（使用颜色映射显示距离分布）
4. 添加时间滑块或交互控件（可选）

### 阶段6：优先级推荐系统

1. 定义优先级评分标准：

   * 距离权重（占比40%）：距离越远分数越高

   * 区域缺口率权重（占比30%）：所在区域缺口率越高分数越高

   * 停车场规模权重（占比30%）：停车场越大分数越高
2. 计算每个缺口区域的优先级分数
3. 生成Top 50优先级推荐列表
4. 在地图上用不同大小/颜色标记优先级

### 阶段7：增强可视化与输出

1. 更新交互式地图，集成所有新功能：

   * 多级缺口分类的颜色编码

   * 热力图图层

   * 区域边界图层

   * 优先级标记
2. 使用Plotly生成统计图表（饼图、柱状图、箱线图）
3. 导出多种格式：

   * 更新的HTML交互式地图

   * Excel分析报告（带图表）

   * GeoJSON/Shapefile格式

   * CSV详细结果

### 阶段8：文档与总结

1. 更新README说明
2. 生成方法论说明文档
3. 准备关键发现总结

***

## 文件结构

```
GIS/
├── data/
│   ├── Electric_Vehicle_Charging_Points_Jan 2026.csv
│   ├── HDBCarparkInformation.csv
│   ├── HDB_Carpark_Charging_Gap_Analysis.csv (原始输出)
│   ├── HDB_Carpark_Charging_Gap_Analysis_Enhanced.csv (优化后输出)
│   ├── planning_areas/ (新加坡规划区数据)
│   └── road_network/ (路网数据，可选)
├── outputs/
│   ├── ev_charging_gap_map.html (原始)
│   ├── ev_charging_gap_map_enhanced.html (优化后)
│   ├── charts/ (Plotly图表)
│   └── reports/ (Excel/GeoJSON输出)
├── ev_charging_gap_analysis.py (原始脚本)
├── ev_charging_gap_analysis_enhanced.py (优化后脚本)
├── requirements.txt (更新依赖)
└── README.md
```

***

## 依赖包更新

```
pandas
geopandas
pyproj
shapely
folium
scipy
numpy
osmnx          # 新增：路网分析
networkx       # 新增：图算法
plotly         # 新增：交互式图表
matplotlib     # 新增：静态图表
seaborn        # 新增：统计图表
openpyxl       # 新增：Excel输出
```

***

## 预期成果

1. 更精细的5级缺口分类系统
2. 按规划区聚合的区域分析
3. 3种热力图可视化
4. 智能优先级推荐系统
5. （可选）路网距离计算
6. 丰富的统计图表
7. 多格式专业输出

