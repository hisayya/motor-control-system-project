$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BuildRoot = Join-Path $Root "build"
$OutputRoot = Join-Path $BuildRoot "windows"
$PackageRoot = Join-Path $OutputRoot "package"

if (Test-Path $OutputRoot) {
    Remove-Item -Recurse -Force $OutputRoot
}

New-Item -ItemType Directory -Path $PackageRoot | Out-Null

# 从 CI 仓库根目录调用本脚本时，cwd 可能不是 trajectory_writer；pip -e 与 unittest 需在包根执行
Set-Location $Root

python -m pip install --upgrade pip
python -m pip install -e .[build]
python -m unittest -v

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name "trajectory-writer" `
    --distpath "$OutputRoot" `
    --workpath "$BuildRoot\\pyinstaller-work" `
    --specpath "$BuildRoot\\pyinstaller-spec" `
    --paths "$Root" `
    --collect-submodules "trajectory_writer" `
    --collect-submodules "fontTools" `
    --collect-submodules "svgpathtools" `
    --collect-submodules "PIL" `
    --exclude-module "scipy" `
    --collect-all "vtracer" `
    "$Root\\trajectory_writer\\__main__.py"

Copy-Item "$OutputRoot\\trajectory-writer.exe" "$PackageRoot\\trajectory-writer.exe"
Copy-Item "$Root\\machine.toml" "$PackageRoot\\machine.toml"
Compress-Archive -Path "$PackageRoot\\*" -DestinationPath "$OutputRoot\\trajectory-writer-windows-x64.zip" -Force
