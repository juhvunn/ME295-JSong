# Start the dashboard (Windows), with the me295 conda environment found automatically (scripts\me295_env.ps1).
#     powershell -ExecutionPolicy Bypass -File scripts\run_dashboard.ps1           # real Claude (token in .env)
#     powershell -ExecutionPolicy Bypass -File scripts\run_dashboard.ps1 -Fake     # FakeLLM: no Claude use
#     ... -EnvPath D:\path\to\envs\me295                                              # if it is not found
# Stop with Ctrl+C. The page opens at http://localhost:8501.
param([switch]$Fake, [string]$EnvPath = "")

$repo = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "me295_env.ps1") -EnvPath $EnvPath
if (-not $global:ME295Env) { exit 1 }
if ($Fake) { $env:PEDAL_DASHBOARD_LLM = "fake" } else { Remove-Item Env:PEDAL_DASHBOARD_LLM -ErrorAction SilentlyContinue }
Set-Location $repo
python -m streamlit run dashboard/app.py
