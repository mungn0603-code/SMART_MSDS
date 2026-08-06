$envPath = "C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\.env"
Get-Content $envPath | ForEach-Object {
    if ($_ -match "^\s*#" -or $_ -notmatch "=") {
        Write-Output $_
    } else {
        $parts = $_ -split "=", 2
        Write-Output ("{0}=<REDACTED len={1}>" -f $parts[0], $parts[1].Length)
    }
}
