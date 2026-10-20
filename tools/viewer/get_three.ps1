# Download the three.js r160 files the viewer pages import (about 1.5 MB) into <Out>\lib\three, so the
# wardrobe works offline. Source: the official npm package on cdn.jsdelivr.net.
param([Parameter(Mandatory = $true)][string]$Out)
$base = "https://cdn.jsdelivr.net/npm/three@0.160.0"
$files = "build/three.module.js", "examples/jsm/controls/OrbitControls.js", "examples/jsm/loaders/GLTFLoader.js",
         "examples/jsm/loaders/DDSLoader.js", "examples/jsm/utils/SkeletonUtils.js", "examples/jsm/utils/BufferGeometryUtils.js"
foreach ($f in $files) {
    $dest = Join-Path $Out ("lib\three\" + ($f -replace '/', '\'))
    New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
    Invoke-WebRequest -UseBasicParsing "$base/$f" -OutFile $dest
    "{0,-45} {1,9:N0} bytes" -f $f, (Get-Item $dest).Length
}
