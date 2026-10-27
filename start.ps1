param([int]$Port = 8765)
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    throw 'Create the environment first: py -3.13 -m venv .venv; then install requirements.lock.txt'
}
& '.venv/Scripts/python.exe' -X utf8 -m geoacceptance.server --port $Port
