$round = "d:\resume-agent\artifacts\rg\round-3"
$gallery = Join-Path $round "_pdf_preview"
New-Item -ItemType Directory -Force -Path $gallery | Out-Null

$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
  Get-ChildItem $round -Directory | Where-Object { $_.Name -notlike "_*" } | ForEach-Object {
    $docx = Join-Path $_.FullName "resume.docx"
    if (-not (Test-Path -LiteralPath $docx)) { return }
    $pdf = Join-Path $_.FullName "resume.pdf"
    $doc = $word.Documents.Open($docx)
    # 17 = wdFormatPDF
    $doc.SaveAs([ref]$pdf, [ref]17)
    $doc.Close([ref]$false)
    Copy-Item -LiteralPath $pdf -Destination (Join-Path $gallery ("{0}.pdf" -f $_.Name)) -Force
    Write-Output ("OK " + $_.Name)
  }
}
finally {
  $word.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}

Start-Process $gallery
Start-Process (Join-Path $round "jd01_da_sql_tableau\resume.pdf")
Start-Process (Join-Path $round "jd03_risk_analyst\resume.pdf")
Start-Process (Join-Path $round "jd09_weak_match\resume.pdf")
