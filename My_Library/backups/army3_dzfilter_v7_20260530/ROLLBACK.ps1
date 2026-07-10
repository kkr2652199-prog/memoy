# Dead Zone v1 스냅샷으로 복구 (이 폴더의 snapshot 내용을 My_Library에 덮어씀)
$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$MyLibrary = (Resolve-Path (Join-Path (Join-Path $Here "..") "..")).Path
$Snap = Join-Path $Here "snapshot"
if (-not (Test-Path $Snap)) {
    Write-Error "snapshot 폴더가 없습니다: $Snap"
}
Copy-Item (Join-Path $Snap "app\lotto3\v12_engine.py") (Join-Path $MyLibrary "app\lotto3\v12_engine.py") -Force
Copy-Item (Join-Path $Snap "app\lotto3\predict_dead_zone.py") (Join-Path $MyLibrary "app\lotto3\predict_dead_zone.py") -Force
Copy-Item (Join-Path $Snap "app\static\js\lotto3.js") (Join-Path $MyLibrary "app\static\js\lotto3.js") -Force
Write-Host "복구 완료: v12_engine, predict_dead_zone, lotto3.js (index.html/lotto.css 캐시버스트는 수동 확인)"
