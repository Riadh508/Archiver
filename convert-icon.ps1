Add-Type -AssemblyName System.Drawing
$inputPath = "data\archives\addPay.png"
$outputPath = "arch.ico"
if (Test-Path $inputPath) {
    $image = [System.Drawing.Image]::FromFile($inputPath)
    # Create a bitmap of desired icon size (256x256)
    $bitmap = New-Object System.Drawing.Bitmap 256,256
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.DrawImage($image, 0, 0, 256, 256)
    $graphics.Dispose()
    $icon = [System.Drawing.Icon]::FromHandle($bitmap.GetHicon())
    $stream = [System.IO.File]::Create($outputPath)
    $icon.Save($stream)
    $stream.Close()
    $icon.Dispose()
    $bitmap.Dispose()
    $image.Dispose()
    Write-Host "Icon created: $outputPath"
} else {
    Write-Error "Input file not found: $inputPath"
}