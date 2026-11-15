param([Parameter(Mandatory=$true)][string]$WorkbookPath, [Parameter(Mandatory=$true)][string]$OutputPath)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$excel = $null
$book = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $book = $excel.Workbooks.Open([System.IO.Path]::GetFullPath($WorkbookPath), 0, $true)
    $sheets = @()
    foreach ($sheet in $book.Worksheets) {
        $used = $sheet.UsedRange
        $rows = @()
        for ($r = 1; $r -le $used.Rows.Count; $r++) {
            $row = @()
            for ($c = 1; $c -le $used.Columns.Count; $c++) {
                $value = $used.Cells.Item($r, $c).Value2
                if ($null -eq $value) { $row += $null }
                elseif ($value -is [string] -or $value -is [ValueType]) { $row += $value }
                else { $row += [string]$value }
            }
            $rows += ,$row
        }
        $sheets += @{ name = [string]$sheet.Name; start_row = [int]$used.Row; rows = $rows }
    }
    $json = @{ sheets = $sheets } | ConvertTo-Json -Depth 10 -Compress
    [System.IO.File]::WriteAllText([System.IO.Path]::GetFullPath($OutputPath), $json, [System.Text.UTF8Encoding]::new($false))
}
catch {
    $json = @{ error = $_.Exception.Message } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText([System.IO.Path]::GetFullPath($OutputPath), $json, [System.Text.UTF8Encoding]::new($false))
    exit 1
}
finally {
    if ($book) { $book.Close($false) | Out-Null }
    if ($excel) { $excel.Quit() }
    if ($book) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($book) }
    if ($excel) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel) }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
