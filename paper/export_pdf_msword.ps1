# Export FIT_paper_v19.docx to PDF with Microsoft Word (not WPS).
# On this machine the Word.Application COM ProgID is registered to WPS Office,
# so New-Object -ComObject Word.Application silently starts WPS. Start
# WINWORD.EXE itself and take its object from the Running Object Table instead.
# The export runs in a separate job with Word's default PDF options: called
# directly from the agent's shell with the full argument list it hung, while
# the job form completes in seconds. A time limit stops a hung Word.
param([string]$Out = "", [int]$TimeoutSec = 180, [string]$Src = "")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = if ($Src) { $Src } else { Join-Path $here "FIT_paper_v19.docx" }
$dst = if ($Out) { $Out } else { Join-Path $here "FIT_paper_v19.pdf" }
$tmp = Join-Path $here ("FIT_paper_v19.export-" + [guid]::NewGuid().ToString("N").Substring(0, 8) + ".pdf")

$job = Start-Job -ArgumentList $src, $tmp {
    param($src, $tmp)
    $proc = Start-Process 'C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE' -ArgumentList '/automation', '-Embedding' -PassThru
    "pid $($proc.Id)"
    # Word rejects calls while it is still starting (RPC_E_SERVERCALL_RETRYLATER).
    function Retry([scriptblock]$f) {
        for ($k = 0; ; $k++) {
            try { return & $f } catch {
                if ($k -ge 120 -or "$_" -notmatch 'RETRYLATER|is busy') { throw }
                Start-Sleep -Milliseconds 500
            }
        }
    }
    $w = $null
    for ($i = 0; $i -lt 40 -and -not $w; $i++) {
        Start-Sleep -Milliseconds 700
        try { $w = [Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application') } catch {}
    }
    if (-not $w) { throw "Microsoft Word did not start" }
    $name = Retry { $w.Name }
    if ($name -ne 'Microsoft Word') { throw "COM object is '$name', not Microsoft Word" }
    Retry { $w.Visible = $false }
    Retry { $w.DisplayAlerts = 0 }
    $doc = Retry { $w.Documents.Open($src, $false, $true, $false) }
    Retry { $doc.Repaginate() }
    "app: $name $(Retry { $w.Version })"
    "pages: $(Retry { $doc.ComputeStatistics(2) })"
    Retry { $doc.ExportAsFixedFormat($tmp, 17) }      # wdExportFormatPDF, Word defaults
    Retry { $doc.Close([ref]0) }
    Retry { $w.Quit() }
}
if (-not (Wait-Job $job -Timeout $TimeoutSec)) {
    $pidLine = (Receive-Job $job | Where-Object { $_ -like 'pid *' } | Select-Object -First 1)
    if ($pidLine) { Stop-Process -Id ([int]($pidLine -replace 'pid ', '')) -Force -ErrorAction SilentlyContinue }
    Remove-Job $job -Force
    throw "Word export timed out after $TimeoutSec s"
}
$lines = Receive-Job $job
$lines
Remove-Job $job
# Quit() can leave the process alive and registered as the active Word, and the
# next export then talks to that stale instance; close the one we started.
$pidLine = $lines | Where-Object { $_ -like 'pid *' } | Select-Object -First 1
if ($pidLine) { Start-Sleep 2; Stop-Process -Id ([int]($pidLine -replace 'pid ', '')) -Force -ErrorAction SilentlyContinue }
if (-not (Test-Path $tmp)) { throw "Word did not write the PDF" }
Move-Item -Force $tmp $dst
"wrote $dst"
