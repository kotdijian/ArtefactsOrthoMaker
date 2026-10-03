# ArtefactsOrthoMaker v1.0.0 — 開発レポート

## 1. 目的
考古資料3Dモデルの姿勢・原点・座標軸を正規化し、3Dモデル、Transform、計測、オルソ、断面、曲面展開を再現可能な形で出力する。

## 2. 座標規約
土器：Z=器軸・高さ、X-Y=水平面。石器：X=幅、Y=長さ、Z=厚さ。入力はOBJ/PLY/GLB、単位はmm/cm/m。自動decimationは行わない。

## 3. アーキテクチャ
`app.py` がGUI/workflow/render/export、`pose_core.py` がMeshAsset、mesh I/O、姿勢推定、Transformを担当する。

## 4. 姿勢正規化
土器はSlice/Rim/Base/Manual(3 points)。石器は読込姿勢保持またはminimum-volume OBB、中央X-Z断面によるY軸水平化、手動X/Y/Z回転。

```text
p_normalized = M_raw_to_normalized @ [x,y,z,1]^T
```

## 5. OBJ UV seam
OBJは `v` と `vt` が独立index。v1.0.0はOBJを `process=False, maintain_order=False` で読み込み、UV seamに必要なrender vertexを保持する。手動のV反転は行わない。

## 6. オルソ・画像
6面をparallel projection・共通scaleで描画。印刷scaleは `px/mm=dpi/25.4*scale`。150/300 dpi、50/66.6667/100%。ファイルサイズ目標はS<=10 MB、M<=50 MB、L<=100 MB。基本上限16,384 px/辺、100 MP。

## 7. 断面
土器は縦断面/半截、石器は任意X/Y断面。VTK Cutter/Stripper等を使用する。

## 8. 土器の円筒・扇形展開アルゴリズム

### 8.1 共通角度
正規化頂点 `(x,y,z)`：
```text
rho   = sqrt(x^2+y^2)
theta = atan2(x,-y)
```
Front(-Y)=0、Back(+Y)=±piをseamとする。seamを跨ぐfaceは現行実装では除外する。

### 8.2 円筒展開
Z区間 `[z0,z1]`、基準外径 `Dref`：
```text
Rref = Dref/2
X'   = Rref*theta
Y'   = rho
Z'   = clamp(z,z0,z1)-z0
```
展開幅は `2*pi*Rref`。複数区間は独立円筒帯として10 mm gapで配置。基準外径の自動計測は水平断面半径の0.995 quantileをouter envelopeとして使う。

### 8.3 扇形展開
隣接区分点 `(z0,r0),(z1,r1)`：
```text
dz = z1-z0
dr = r1-r0
L  = sqrt(dz^2+dr^2)
k  = abs(dr)/L
t  = clamp((z-z0)/dz,0,1)
rt = r0+dr*t
s  = rt/k
phi = k*theta

X' = s*sin(phi)
Y' = rho
Z' = s*cos(phi)
```
sector角は `alpha=2*pi*k`。弧長は `s*alpha=(rt/k)*(2*pi*k)=2*pi*rt` となり元円周長を保存する。`dr≈0` は円筒極限として `X'=rt*theta, Z'=t*L`。

### 8.4 多段扇形
区分点で傾斜が変わると隣接区間の `k` とsector曲率が異なる。共有境界円は3D上で同じ円周長でも平面円弧曲率が異なるため、歪みなしに1枚の連続平面へ強制接続せず、各frustumを独立展開する。

### 8.5 外面/内面/上面
展開meshは `Y'=rho` をdepthとして保持。外面はouter depth、内面はY'符号を反転してinner depthを前面化。上面は展開後3D meshの+Z確認viewであり、元器のtop viewではない。

### 8.6 区分点・JSON
数値/slider/3D clickでZ指定。Qt event filterがclick系列を消費しcamera rotateを抑制。円筒JSONには `breakpoints_z_mm` と `segments[].z0_mm/z1_mm/reference_z_mm/diameter_mm` を記録。

### 8.7 現行境界処理
face所属はface重心Zで判定し、境界跨ぎfaceを厳密splitせずmapped Zをclipする。将来はZ planeでtriangle split。器形区分と文様境界が一致しない資料向けoverlap bufferは将来候補で、v1.0.0未実装。

## 9. 大規模モデル
自動point/mesh proxyはv1.0.0では採用しない。300 MB超はadvisory warning。100万〜200万facesを推奨、約250万facesを実用上限目安とする。

## 10. 再現性
normalized PLY、Transform、settings JSON、measurement CSV、inventoryを保存。同名時は上書き確認、Save Asは`_01`, `_02`...で一式を同期。

## 11. QA
`py_compile`, `pip check`, `check_environment.py`, `self_test.py`に加え、OBJ UV、曲面展開、click、overwrite/save-as、300 MB warning、raster出力のGUI回帰確認が必要。

## 12. 今後
curved-development数値regression、UV sample test、triangle split、overlap buffer、module分割、pytest/GitHub Actions、metadata schema、CLI/batch。

## 13. ライセンス
v0.4.9以前はCC0 1.0 Universal。v0.4.10以降はMIT。変更は遡及しない。
