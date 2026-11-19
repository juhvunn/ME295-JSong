# Put the me295 conda environment on PATH in THIS PowerShell session (Windows), without `conda activate`.
# Use it when conda is not on PATH, e.g. in the VS Code terminal:
#     . .\scripts\me295_env.ps1                 # note the leading ". " (dot-sourcing keeps the PATH change)
#     . .\scripts\me295_env.ps1 -EnvPath D:\path\to\envs\me295
# Afterwards python, pytest, streamlit and ngspice_con come from the environment.
param([string]$EnvPath = "")

$global:ME295Env = $null
$candidates = @($EnvPath, $env:ME295_ENV,
    $(if ($env:CONDA_PREFIX -and (Split-Path $env:CONDA_PREFIX -Leaf) -eq "me295") { $env:CONDA_PREFIX }),
    "$env:LOCALAPPDATA\miniconda3\envs\me295", "$env:USERPROFILE\miniconda3\envs\me295",
    "$env:LOCALAPPDATA\anaconda3\envs\me295", "$env:USERPROFILE\anaconda3\envs\me295",
    "$env:ProgramData\miniconda3\envs\me295", "$env:ProgramData\anaconda3\envs\me295")
$found = $null
foreach ($c in $candidates) {
    if ($c -and (Test-Path (Join-Path $c "python.exe"))) { $found = (Resolve-Path $c).Path; break }
}
if (-not $found) {
    Write-Error ("me295 conda environment not found. Create it (README, Setup) or pass -EnvPath <folder>, " +
                 "or set ME295_ENV to the folder that contains python.exe.")
    return
}
$env:PATH = "$found;$found\Scripts;$found\Library\bin;$env:PATH"
$env:PYTHONIOENCODING = "utf-8"
$global:ME295Env = $found
Write-Host "Using $found"
