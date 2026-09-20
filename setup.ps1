[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $PSCommandPath
$managedBlockBegin = '<!-- BEGIN CODEX PRO WORKFLOW -->'
$managedBlockEnd = '<!-- END CODEX PRO WORKFLOW -->'
$banner = @'
+---------------------------------------+
|    _    ____ _____ ____      _        |
|   / \  / ___|_   _|  _ \    / \       |
|  / _ \ \___ \ | | | |_) |  / _ \      |
| / ___ \ ___) || | |  _ <  / ___ \     |
|/_/   \_\____/ |_| |_| \_\/_/   \_\    |
|                                       |
|       O R C H E S T R A T O R         |
|    Plan and orchestrate with Sol.     |
|    Execute with Luna High/Max.        |
+---------------------------------------+
'@

[Console]::WriteLine($banner)
[Console]::WriteLine('Interactive project setup for Windows')

function Read-Confirmation {
    param(
        [Parameter(Mandatory)]
        [string]$Prompt,

        [Parameter(Mandatory)]
        [bool]$DefaultYes
    )

    $suffix = if ($DefaultYes) { '[Y/n]' } else { '[y/N]' }
    while ($true) {
        [Console]::Write("$Prompt $suffix ")
        $answer = [Console]::In.ReadLine()
        if ($null -eq $answer) {
            throw 'Input ended before setup was complete.'
        }

        switch ($answer.Trim().ToLowerInvariant()) {
            'y' { return $true }
            'yes' { return $true }
            'n' { return $false }
            'no' { return $false }
            '' { return $DefaultYes }
            default { [Console]::WriteLine('Please answer yes or no.') }
        }
    }
}

function Read-Plan {
    [Console]::WriteLine('Choose Profile to install')
    [Console]::WriteLine('  1) Pro - Sol plans/solves, Luna High/Max handles routine work, Astra reviews')
    [Console]::WriteLine('  2) Pro (max 2 subagents) - same roles, with at most 2 concurrent subagents')

    while ($true) {
        [Console]::Write('Select profile [1-2] (default 1): ')
        $answer = [Console]::In.ReadLine()
        if ($null -eq $answer) {
            throw 'Input ended before setup was complete.'
        }

        switch ($answer.Trim().ToLowerInvariant()) {
            '1' { return 'pro' }
            'pro' { return 'pro' }
            '' { return 'pro' }
            '2' { return 'pro-max-2-subagents' }
            'pro-max-2-subagents' { return 'pro-max-2-subagents' }
            default { [Console]::WriteLine('Please enter a listed profile number or name.') }
        }
    }
}

function Copy-DirectoryContents {
    param(
        [Parameter(Mandatory)]
        [string]$Source,

        [Parameter(Mandatory)]
        [string]$Destination
    )

    foreach ($sourceChild in (Get-ChildItem -LiteralPath $Source -Force)) {
        $destinationChildPath = Join-Path $Destination $sourceChild.Name
        $destinationChild = Get-Item -LiteralPath $destinationChildPath -Force -ErrorAction SilentlyContinue

        if ($sourceChild.PSIsContainer) {
            if ($null -eq $destinationChild) {
                New-Item -ItemType Directory -Path $destinationChildPath | Out-Null
            }
            elseif (-not $destinationChild.PSIsContainer) {
                throw "Cannot merge directory over file: $destinationChildPath"
            }

            Copy-DirectoryContents -Source $sourceChild.FullName -Destination $destinationChildPath
        }
        else {
            if (($null -ne $destinationChild) -and $destinationChild.PSIsContainer) {
                throw "Cannot overwrite directory with file: $destinationChildPath"
            }

            Copy-Item -LiteralPath $sourceChild.FullName -Destination $destinationChildPath -Force
        }
    }
}

function Find-ReparsePoint {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    foreach ($child in (Get-ChildItem -LiteralPath $Path -Force)) {
        if (($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            return $child.FullName
        }
        if ($child.PSIsContainer) {
            $nestedLink = Find-ReparsePoint -Path $child.FullName
            if ($null -ne $nestedLink) {
                return $nestedLink
            }
        }
    }

    return $null
}

function Test-DirectoryMergeCompatible {
    param(
        [Parameter(Mandatory)]
        [string]$Source,

        [Parameter(Mandatory)]
        [string]$Destination
    )

    foreach ($sourceChild in (Get-ChildItem -LiteralPath $Source -Force)) {
        $destinationChildPath = Join-Path $Destination $sourceChild.Name
        $destinationChild = Get-Item -LiteralPath $destinationChildPath -Force -ErrorAction SilentlyContinue
        if ($null -eq $destinationChild) {
            continue
        }
        if ($sourceChild.PSIsContainer -ne $destinationChild.PSIsContainer) {
            return $false
        }
        if ($sourceChild.PSIsContainer -and (-not (Test-DirectoryMergeCompatible -Source $sourceChild.FullName -Destination $destinationChildPath))) {
            return $false
        }
    }

    return $true
}

function Get-OverwritePaths {
    param(
        [Parameter(Mandatory)]
        [System.IO.FileSystemInfo]$Source,

        [Parameter(Mandatory)]
        [string]$Destination,

        [Parameter(Mandatory)]
        [string]$Name
    )

    if (-not $Source.PSIsContainer) {
        if ($null -ne (Get-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue)) {
            return $Name
        }
        return
    }

    foreach ($sourceFile in (Get-ChildItem -LiteralPath $Source.FullName -File -Recurse -Force)) {
        $relativePath = $sourceFile.FullName.Substring($Source.FullName.Length + 1)
        $destinationFile = Join-Path $Destination $relativePath
        if ($null -ne (Get-Item -LiteralPath $destinationFile -Force -ErrorAction SilentlyContinue)) {
            $path = $Name + [IO.Path]::DirectorySeparatorChar + $relativePath
            Write-Output $path
        }
    }
}

function Show-OverwriteWarning {
    param(
        [Parameter(Mandatory)]
        [System.IO.FileSystemInfo]$Source,

        [Parameter(Mandatory)]
        [string]$Destination,

        [Parameter(Mandatory)]
        [string]$Name
    )

    $paths = @(Get-OverwritePaths -Source $Source -Destination $Destination -Name $Name)
    if ($paths.Count -eq 0) {
        return
    }

    [Console]::WriteLine('WARNING: the following existing files will be overwritten:')
    foreach ($path in $paths) {
        [Console]::WriteLine("  - $path")
    }
}

function Install-Component {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$TargetDirectory,

        [string]$SourcePath
    )

    if ([string]::IsNullOrEmpty($SourcePath)) {
        $SourcePath = Join-Path $scriptDir $Name
    }
    $sourcePath = $SourcePath
    $destinationPath = Join-Path $TargetDirectory $Name
    $sourceItem = Get-Item -LiteralPath $sourcePath -Force -ErrorAction SilentlyContinue
    if ($null -eq $sourceItem) {
        throw "Setup source is missing: $sourcePath"
    }

    $destinationItem = Get-Item -LiteralPath $destinationPath -Force -ErrorAction SilentlyContinue
    if ($null -ne $destinationItem) {
        if (($destinationItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            [Console]::Error.WriteLine("Skipped ${Name}: the existing target is a symbolic link or junction.")
            return $false
        }

        if ($sourceItem.PSIsContainer -and $destinationItem.PSIsContainer) {
            $linkedPath = Find-ReparsePoint -Path $destinationPath
            if ($null -ne $linkedPath) {
                [Console]::Error.WriteLine("Skipped ${Name}: the existing target contains a symbolic link or junction ($linkedPath).")
                return $false
            }
            if (-not (Test-DirectoryMergeCompatible -Source $sourcePath -Destination $destinationPath)) {
                [Console]::Error.WriteLine("Skipped ${Name}: source and target types are incompatible.")
                return $false
            }
        }
        elseif (($sourceItem.PSIsContainer -and (-not $destinationItem.PSIsContainer)) -or ((-not $sourceItem.PSIsContainer) -and $destinationItem.PSIsContainer)) {
            [Console]::Error.WriteLine("Skipped ${Name}: source and target types are incompatible.")
            return $false
        }

        if ($Name -eq 'AGENTS.md') {
            $instructions = [IO.File]::ReadAllText($sourcePath)
            $existing = [IO.File]::ReadAllText($destinationPath)
            $blockPattern = [regex]::Escape($managedBlockBegin) + '(?s:.*?)' + [regex]::Escape($managedBlockEnd)
            $sourceMatches = [regex]::Matches($instructions, $blockPattern)
            if ($sourceMatches.Count -ne 1) {
                throw 'Setup AGENTS.md must contain exactly one complete managed workflow block.'
            }
            $managedBlock = $sourceMatches[0].Value
            $targetBeginCount = [regex]::Matches($existing, [regex]::Escape($managedBlockBegin)).Count
            $targetEndCount = [regex]::Matches($existing, [regex]::Escape($managedBlockEnd)).Count
            if ($targetBeginCount -ne $targetEndCount -or $targetBeginCount -gt 1) {
                throw 'Target AGENTS.md has malformed or duplicate managed workflow markers; fix it manually before retrying.'
            }
            $reader = [IO.StreamReader]::new($destinationPath, [Text.Encoding]::UTF8, $true)
            try {
                $null = $reader.ReadToEnd()
                $encoding = $reader.CurrentEncoding
            }
            finally {
                $reader.Dispose()
            }

            if ($targetBeginCount -eq 1) {
                $targetMatch = [regex]::Match($existing, $blockPattern)
                if (-not $targetMatch.Success) {
                    throw 'Target AGENTS.md managed workflow markers are out of order.'
                }
                $updated = $existing.Substring(0, $targetMatch.Index) + $managedBlock + $existing.Substring($targetMatch.Index + $targetMatch.Length)
                if ($updated -ceq $existing) {
                    [Console]::WriteLine("Skipped ${Name}: managed workflow block already current.")
                    return $false
                }
                [IO.File]::WriteAllText($destinationPath, $updated, $encoding)
                [Console]::WriteLine("Updated managed workflow block in ${Name}. Unrelated contents preserved.")
                return $true
            }

            if ($existing -match '(?i)astra-orchestrator|Sol root|Astra reviewer|Luna (High|Max)') {
                [Console]::Error.WriteLine('WARNING: legacy unmarked orchestrator instructions were preserved in AGENTS.md; review/remove them manually to avoid conflicting rules.')
            }
            $separator = if ($existing.EndsWith("`n")) { "`n" } else { "`n`n" }
            [IO.File]::AppendAllText($destinationPath, $separator + $managedBlock + "`n", $encoding)
            [Console]::WriteLine("Appended managed workflow block to ${Name}. Existing contents preserved.")
            return $true
        }

        Show-OverwriteWarning -Source $sourceItem -Destination $destinationPath -Name $Name

        if (-not (Read-Confirmation -Prompt "Update ${Name}? New files will be added; only paths listed above will be replaced." -DefaultYes $false)) {
            [Console]::WriteLine("Skipped $Name (existing target left unchanged).")
            return $false
        }

        if ($sourceItem.PSIsContainer -and $destinationItem.PSIsContainer) {
            Copy-DirectoryContents -Source $sourcePath -Destination $destinationPath
        }
        elseif ((-not $sourceItem.PSIsContainer) -and (-not $destinationItem.PSIsContainer)) {
            Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Force
        }
        else {
            [Console]::Error.WriteLine("Skipped ${Name}: source and target types are incompatible.")
            return $false
        }

        [Console]::WriteLine("Updated $Name.")
        return $true
    }

    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Recurse -Force
    [Console]::WriteLine("Installed $Name.")
    return $true
}

function Remove-LegacyDeepSeekFiles {
    param(
        [Parameter(Mandatory)]
        [string]$TargetDirectory
    )

    $codexDirectory = Join-Path $TargetDirectory '.codex'
    $legacyNames = @(
        'local_deepseek_runner.py',
        'models.json',
        'run-deepseek-role.ps1',
        'start-ustc-adapter.ps1',
        'start-ustc-adapter.sh',
        'ustc_chat_adapter.py'
    )
    $legacyPaths = @(
        foreach ($name in $legacyNames) {
            $path = Join-Path $codexDirectory $name
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                if (($name -ne 'models.json') -or ([IO.File]::ReadAllText($path) -match 'deepseek-')) {
                    $path
                }
            }
        }
    )
    if ($legacyPaths.Count -eq 0) {
        return
    }

    [Console]::WriteLine('The following obsolete DeepSeek adapter files remain from an older profile:')
    foreach ($path in $legacyPaths) {
        [Console]::WriteLine("  - $path")
    }
    if (-not (Read-Confirmation -Prompt 'Remove these obsolete files?' -DefaultYes $true)) {
        [Console]::WriteLine('Left obsolete adapter files unchanged.')
        return
    }
    foreach ($path in $legacyPaths) {
        Remove-Item -LiteralPath $path -Force
    }
    [Console]::WriteLine('Removed obsolete DeepSeek adapter files.')
}

try {
    [Console]::Write('Target repository path: ')
    $targetPath = [Console]::In.ReadLine()
    if ($null -eq $targetPath) {
        throw 'Input ended before a target repository was provided.'
    }
    if ([string]::IsNullOrWhiteSpace($targetPath)) {
        throw 'Target repository path cannot be empty.'
    }

    $targetItem = Get-Item -LiteralPath $targetPath -Force -ErrorAction SilentlyContinue
    if (($null -eq $targetItem) -or (-not $targetItem.PSIsContainer)) {
        throw "Target must be an existing directory: $targetPath"
    }

    $targetDirectory = $targetItem.FullName
    if ([string]::Equals($targetDirectory, $scriptDir, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Target repository must be different from the setup source directory.'
    }

    $plan = Read-Plan
    $profileDirectory = Join-Path $scriptDir "profiles/$plan"

    $installed = 0
    foreach ($component in '.codex', '.agents', 'AGENTS.md') {
        if (Read-Confirmation -Prompt "Install ${component}?" -DefaultYes $true) {
            $result = if ($component -eq '.codex') {
                Install-Component -Name $component -TargetDirectory $targetDirectory -SourcePath (Join-Path $profileDirectory "codex")
            }
            elseif ($component -eq '.agents') {
                Install-Component -Name $component -TargetDirectory $targetDirectory -SourcePath (Join-Path $profileDirectory "agents")
            }
            else {
                Install-Component -Name $component -TargetDirectory $targetDirectory
            }
            if ($result) {
                $installed++
                if ($component -eq '.codex') {
                    Remove-LegacyDeepSeekFiles -TargetDirectory $targetDirectory
                }
            }
        }
        else {
            [Console]::WriteLine("Skipped $component.")
        }
    }

    [Console]::WriteLine()
    [Console]::WriteLine("Setup complete. $installed component(s) installed in $targetDirectory (profile: $plan).")
    [Console]::WriteLine('See guides/ for optional Codex model and Fast-mode configurations.')
}
catch {
    [Console]::Error.WriteLine("Setup cancelled: $($_.Exception.Message)")
    exit 1
}
