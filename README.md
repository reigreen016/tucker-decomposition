[shokiiiiii](https://github.com/shokiiiiii) さんのnotionから転記
詳細：[shokiiiiii さんのReserch Progress](https://github.com/shokiiiiii/Research-Progress-)

## コード集
step1.py〜step5.py
final.py

タッカー内容まとめ

## 構造

## 1.元の日別GPSデータを以下の処理を行ってクリーニングを行う

### 詳細

- **parquetファイルを読み込む**
- **Time_start / Time_end を日時型に変換**
- **User_Id と時刻順に並び替え**
- **おかしい行を削除**
    - 時刻が欠損している行
    - `Time_end < Time_start` になっている行
- **完全重複を削除**
    - 基本的に `User_Id`, `Time_start`, `Time_end` が同じ行を重複として削除
- **同一ユーザー内の時間重複を削除**
    - あるトリップの開始時刻が、前のトリップの終了時刻より前なら削除
- **時刻を +9時間補正**
    - GMT/UTC から日本時間に直す処理
- **ギャップ圧縮**
    - 同じユーザーの2本目以降の `Time_start` を、直前トリップの `Time_end` に置き換える
    - つまり、トリップ間の空白時間を後続トリップに吸収する
- **日跨ぎトリップを分割**
    - 例：23:00〜翌日02:00 のようなトリップを、
        - 23:00〜23:59:59
        - 00:00〜02:00
        のように日別に分ける
- **日付ごとに中間ファイルを保存**
- **同じ日付のパーツを結合して最終日別ファイルを作成**

### データ

```jsx
コード：step1.py
入力データ："/Volumes/一ノ瀬/共滞在アルバイト/01_【第1層】下処理（Preprocessing）コードの整理/01_本番/01_Raw_gps_trips"
出力データ："/Volumes/一ノ瀬/共滞在アルバイト/01_【第1層】下処理（Preprocessing）コードの整理/01_本番/02_結果/step2_daily"
- 出力データについて
==============================
ファイル情報
==============================
ファイル名: trips_20230801.parquet
行数: 3,277,439
列数: 9

==============================
カラム一覧
==============================
01. User_Id
02. Trip_Id
03. TripMode
04. Time_start
05. Time_end
06. Latitude_start
07. Latitude_end
08. Longitude_start
09. Longitude_end

==============================
カラム型
==============================
User_Id                    object
Trip_Id                    object
TripMode                   object
Time_start         datetime64[ns]
Time_end           datetime64[ns]
Latitude_start            float64
Latitude_end              float64
Longitude_start           float64
Longitude_end             float64
dtype: object
```

## 1.5.userの住居、職場、年齢、性別その他の個人情報をユーザーリスト型でまとめてparquetを作成

### 詳細

**複数の parquet ファイル(Azis sanが作ったやつ)に分かれているユーザー属性情報を読み込み、ユーザーごとに1行の情報にまとめて保存するコード**です。最終的にプロセス1で出力したトリップデータ(/Volumes/一ノ瀬/共滞在アルバイト/01_【第1層】下処理（Preprocessing）コードの整理/01_本番/02_結果/step2_daily)に情報を追加するためのコード。

### データ

```jsx
コード：step1.5
入力データ："/Users/tsg/Desktop/watanabe_work/trips_cleaning/users_merge_home_office_location"
出力データ1(年齢、性別、職場、住居の4情報が欠損していないデータ)："/Volumes/一ノ瀬/タッカー分解/ユーザー情報/all_users_info.parquet"
出力データ2(全ユーザーのデータ)："/Volumes/一ノ瀬/タッカー分解/ユーザー情報/users_with_home_office_age_gender_info.parquet"
- 出力データ1(年齢、性別、職場、住居の4情報が欠損していないデータ)について
==============================
ファイル情報
==============================
ファイル名: users_with_home_office_age_gender_info.parquet
行数: 96,683
列数: 12

==============================
カラム一覧
==============================
01. User_Id
02. gender
03. age_group
04. device_os
05. device_model
06. device_os_version
07. device_carrier
08. ip_address
09. Home_Latitude
10. Home_Longitude
11. Office_Latitude
12. Office_Longitude

==============================
カラム型
==============================
User_Id               object
gender                object
age_group             object
device_os             object
device_model          object
device_os_version     object
device_carrier        object
ip_address            object
Home_Latitude        float64
Home_Longitude       float64
Office_Latitude      float64
Office_Longitude     float64
dtype: object

==============================
欠損数
==============================
User_Id                  0
gender                   0
age_group                0
device_os                0
device_model          9860
device_os_version     5488
device_carrier       91077
ip_address               0
Home_Latitude            0
Home_Longitude           0
Office_Latitude          0
Office_Longitude         0
dtype: int64
==============================
4情報ありユーザー情報
================================
4情報ありユーザー数: 96,683
割合: 13.93%

- 出力データ2(全ユーザーのデータ)について
==============================
ファイル情報
==============================
ファイル名: all_users_info.parquet
行数: 693,956
列数: 12

==============================
カラム一覧
==============================
01. User_Id
02. gender
03. age_group
04. device_os
05. device_model
06. device_os_version
07. device_carrier
08. ip_address
09. Home_Latitude
10. Home_Longitude
11. Office_Latitude
12. Office_Longitude

==============================
カラム型
==============================
User_Id               object
gender                object
age_group             object
device_os             object
device_model          object
device_os_version     object
device_carrier        object
ip_address            object
Home_Latitude        float64
Home_Longitude       float64
Office_Latitude      float64
Office_Longitude     float64
dtype: object

==============================
欠損数
==============================
User_Id                   0
gender               549318
age_group            519122
device_os                 0
device_model          74199
device_os_version    104273
device_carrier       615675
ip_address                0
Home_Latitude        281233
Home_Longitude       281233
Office_Latitude      281466
Office_Longitude     281466
dtype: int64

```

## 2.トリップGPSデータに住居、職場、年齢、性別その他の個人情報を付与

### 詳細

特になし

### データ

```jsx
コード：step2
入力データ1(トリップGPSデータ)："/Volumes/一ノ瀬/09_共滞在アルバイト/01_【第1層】下処理（Preprocessing）コードの整理/01_本番/出力_20260604/step2_daily"
入力データ2(個人情報リスト)："/Volumes/一ノ瀬/09_共滞在アルバイト/ユーザー情報/all_users_info.parquet"
出力データ："/Volumes/一ノ瀬/09_共滞在アルバイト/GPS_data_with_socio"
- 出力データについて
=============================
ファイル情報
==============================
ファイル名: trips_20230801.parquet
行数: 3,277,439
列数: 20

==============================
カラム一覧
==============================
01. User_Id
02. Trip_Id
03. TripMode
04. Time_start
05. Time_end
06. Latitude_start
07. Latitude_end
08. Longitude_start
09. Longitude_end
10. gender
11. age_group
12. device_os
13. device_model
14. device_os_version
15. device_carrier
16. ip_address
17. Home_Latitude
18. Home_Longitude
19. Office_Latitude
20. Office_Longitude

==============================
カラム型
==============================
User_Id                      object
Trip_Id                      object
TripMode                     object
Time_start           datetime64[ns]
Time_end             datetime64[ns]
Latitude_start              float64
Latitude_end                float64
Longitude_start             float64
Longitude_end               float64
gender                       object
age_group                    object
device_os                    object
device_model                 object
device_os_version            object
device_carrier               object
ip_address                   object
Home_Latitude               float64
Home_Longitude              float64
Office_Latitude             float64
Office_Longitude            float64
dtype: object

==============================
欠損数
==============================
User_Id                    0
Trip_Id                    0
TripMode                   0
Time_start                 0
Time_end                   0
Latitude_start             0
Latitude_end               0
Longitude_start            0
Longitude_end              0
gender               2493230
age_group            2339159
device_os                  0
device_model          473755
device_os_version     254054
device_carrier       3020842
ip_address                 0
Home_Latitude         551880
Home_Longitude        551880
Office_Latitude       543795
Office_Longitude      543795
dtype: int64
```

## 3.**東広島市内の滞在データだけを取り出す処理**

### 詳細

**ユーザーの社会人口属性付きGPSデータ(さまざまなトリップモードを含む)の中から、東広島9町エリア内で発生した「activity」データだけを抽出し、1つの parquet ファイルとして保存するコード**。

### コード

```jsx
コード：step3
入力データ1(社会人口属性付きGPSデータ**)**："/Volumes/一ノ瀬/共滞在アルバイト/GPS_data_with_socio"
入力データ2(東広島市の9つの町のポリゴン)："/Volumes/一ノ瀬/共滞在アルバイト/東広島9つの町/r2kb34212_dissolved.shp"
出力データ："/Volumes/一ノ瀬/タッカー分解/ファイル/東広島滞在データ.parquet"
- 出力データについて
==============================
ファイル情報
==============================
ファイル名: 東広島滞在データ.parquet
行数: 886,064
列数: 21

==============================
カラム一覧
==============================
01. User_Id
02. Trip_Id
03. TripMode
04. Time_start
05. Time_end
06. Latitude_start
07. Latitude_end
08. Longitude_start
09. Longitude_end
10. gender
11. age_group
12. device_os
13. device_model
14. device_os_version
15. device_carrier
16. ip_address
17. Home_Latitude
18. Home_Longitude
19. Office_Latitude
20. Office_Longitude
21. source_file

==============================
カラム型
==============================
User_Id                      object
Trip_Id                      object
TripMode                     object
Time_start           datetime64[ns]
Time_end             datetime64[ns]
Latitude_start              float64
Latitude_end                float64
Longitude_start             float64
Longitude_end               float64
gender                       object
age_group                    object
device_os                    object
device_model                 object
device_os_version            object
device_carrier               object
ip_address                   object
Home_Latitude               float64
Home_Longitude              float64
Office_Latitude             float64
Office_Longitude            float64
source_file                  object
dtype: object

==============================
欠損数
==============================
User_Id                   0
Trip_Id                   0
TripMode                  0
Time_start                0
Time_end                  0
Latitude_start            0
Latitude_end              0
Longitude_start           0
Longitude_end             0
gender               690457
age_group            642112
device_os                 0
device_model         111974
device_os_version     97688
device_carrier       796958
ip_address                0
Home_Latitude         79574
Home_Longitude        79574
Office_Latitude       76590
Office_Longitude      76590
source_file               0
dtype: int64

```

## 4.**GPS滞在データに建物情報を付ける処理**

### 詳細

このコードは、**滞在データの開始地点と終了地点から中点を作り、その中点がどの建物のVoronoi領域に入るかを判定して、各滞在データに `building_id` と `building_name` を付与するコード**。

### データ

```jsx
コード：step4
入力データ1(building_name付きボロノイ図**)**："/Users/tsg/Desktop/Ichinose_work/05_共滞在データのエンリッチメント/"
    "05_data/04_ボロノイ図/higashihiroshima_voronoi_v1.gpkg"
入力データ2(東広島市内の滞在データ)："/Volumes/一ノ瀬/タッカー分解/ファイル/東広島滞在データ.parquet"
出力データ："/Volumes/一ノ瀬/タッカー分解/ファイル/東広島滞在データwith_building.parquet"
- 出力データについて
==============================
ファイル情報
==============================
ファイル名: 東広島滞在データwith_building.parquet
行数: 886,064
列数: 25

==============================
カラム一覧
==============================
01. User_Id
02. Trip_Id
03. TripMode
04. Time_start
05. Time_end
06. Latitude_start
07. Latitude_end
08. Longitude_start
09. Longitude_end
10. gender
11. age_group
12. device_os
13. device_model
14. device_os_version
15. device_carrier
16. ip_address
17. Home_Latitude
18. Home_Longitude
19. Office_Latitude
20. Office_Longitude
21. source_file
22. Latitude_center
23. Longitude_center
24. building_id
25. building_name

==============================
カラム型
==============================
User_Id                      object
Trip_Id                      object
TripMode                     object
Time_start           datetime64[ns]
Time_end             datetime64[ns]
Latitude_start              float64
Latitude_end                float64
Longitude_start             float64
Longitude_end               float64
gender                       object
age_group                    object
device_os                    object
device_model                 object
device_os_version            object
device_carrier               object
ip_address                   object
Home_Latitude               float64
Home_Longitude              float64
Office_Latitude             float64
Office_Longitude            float64
source_file                  object
Latitude_center             float64
Longitude_center            float64
building_id                 float64
building_name                object
dtype: object

==============================
欠損数
==============================
User_Id                   0
Trip_Id                   0
TripMode                  0
Time_start                0
Time_end                  0
Latitude_start            0
Latitude_end              0
Longitude_start           0
Longitude_end             0
gender               690457
age_group            642112
device_os                 0
device_model         111974
device_os_version     97688
device_carrier       796958
ip_address                0
Home_Latitude         79574
Home_Longitude        79574
Office_Latitude       76590
Office_Longitude      76590
source_file               0
Latitude_center           0
Longitude_center          0
building_id           12995
building_name         12995
dtype: int64
```

## 5.**建物内で発生した「共滞在データ」を抽出する処理**

### 詳細

**建物ごとに、別ユーザーと5分以上同じ時間帯に滞在していたデータだけを残すコード。**

### データ

```jsx
コード：step5
入力データ1(building_name付き東広島滞在データ**)**："/Volumes/一ノ瀬/タッカー分解/ファイル/東広島滞在データwith_building.parquet"
出力データ："/Volumes/一ノ瀬/タッカー分解/ファイル/東広島共滞在データwith_building.parquet"
- 出力データについて
==============================
ファイル情報
==============================
ファイル名: 東広島共滞在データwith_building.parquet
行数: 107,208
列数: 25

==============================
カラム一覧
==============================
01. User_Id
02. Trip_Id
03. TripMode
04. Time_start
05. Time_end
06. Latitude_start
07. Latitude_end
08. Longitude_start
09. Longitude_end
10. gender
11. age_group
12. device_os
13. device_model
14. device_os_version
15. device_carrier
16. ip_address
17. Home_Latitude
18. Home_Longitude
19. Office_Latitude
20. Office_Longitude
21. source_file
22. Latitude_center
23. Longitude_center
24. building_id
25. building_name

==============================
カラム型
==============================
User_Id                      object
Trip_Id                      object
TripMode                     object
Time_start           datetime64[ns]
Time_end             datetime64[ns]
Latitude_start              float64
Latitude_end                float64
Longitude_start             float64
Longitude_end               float64
gender                       object
age_group                    object
device_os                    object
device_model                 object
device_os_version            object
device_carrier               object
ip_address                   object
Home_Latitude               float64
Home_Longitude              float64
Office_Latitude             float64
Office_Longitude            float64
source_file                  object
Latitude_center             float64
Longitude_center            float64
building_id                 float64
building_name              category
dtype: object

==============================
欠損数
==============================
User_Id                  0
Trip_Id                  0
TripMode                 0
Time_start               0
Time_end                 0
Latitude_start           0
Latitude_end             0
Longitude_start          0
Longitude_end            0
gender               84620
age_group            79739
device_os                0
device_model         15951
device_os_version    15134
device_carrier       93367
ip_address               0
Home_Latitude         8472
Home_Longitude        8472
Office_Latitude       8180
Office_Longitude      8180
source_file              0
Latitude_center          0
Longitude_center         0
building_id              0
building_name            0
dtype: int64
```
