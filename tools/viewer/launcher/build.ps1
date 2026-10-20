# Build TuDoThoiTrang.exe (the wardrobe's standalone launcher) with the C# compiler that ships with Windows.
# The icon is taken from your own game client (elementclient_64.exe); it is not part of the repository.
param([string]$GameExe = (Join-Path $PSScriptRoot "..\..\..\element\x64\elementclient_64.exe"))
Set-Location $PSScriptRoot
$icon = @()
if (Test-Path $GameExe) {
    py exe_icon.py $GameExe game.ico
    if ($?) { $icon = @("/win32icon:game.ico") }
}
$csc = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
& $csc /nologo /target:winexe /codepage:65001 @icon /reference:System.Management.dll /reference:System.Windows.Forms.dll /out:TuDoThoiTrang.exe TuDoThoiTrang.cs
