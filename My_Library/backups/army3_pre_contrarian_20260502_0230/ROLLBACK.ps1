# v12_contrarian 패치 전 스냅샷으로 복구 (이 폴더 파일을 My_Library 경로에 덮어씀)
$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$MyLibrary = (Resolve-Path (Join-Path $Here "..")).Path
Copy-Item (Join-Path $Here "v12_engine.py") (Join-Path $MyLibrary "app\lotto3\v12_engine.py") -Force
Copy-Item (Join-Path $Here "v12_models.py") (Join-Path $MyLibrary "app\lotto3\v12_models.py") -Force
Copy-Item (Join-Path $Here "v12_routes.py") (Join-Path $MyLibrary "app\lotto3\v12_routes.py") -Force
Copy-Item (Join-Path $Here "lotto3.js") (Join-Path $MyLibrary "app\static\js\lotto3.js") -Force
Copy-Item (Join-Path $Here "predict_combo.py") (Join-Path $MyLibrary "app\lotto3\predict_combo.py") -Force
Copy-Item (Join-Path $Here "v12_snake.py") (Join-Path $MyLibrary "app\lotto3\v12_snake.py") -Force
Write-Host "복구 완료: v12_engine, v12_models, v12_routes, lotto3.js, predict_combo, v12_snake"
Write-Host "DB 복구: data\lotto.db.before_contrarian_20260502 -> data\lotto.db (수동 Copy-Item 권장)"
Remove-Item (Join-Path $MyLibrary "app\lotto3\predict_contrarian.py") -ErrorAction SilentlyContinue
Write-Host "predict_contrarian.py 삭제 시도 (없으면 무시)"
