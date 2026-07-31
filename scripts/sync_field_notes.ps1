[CmdletBinding()]
param(
    [string]$CommitMessage = "Update Field Notes"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceDirectory = Join-Path $projectRoot "content\field-notes-src"
$mediumImportDirectory = Join-Path $projectRoot "content\medium-field-notes"
$deployDirectory = Join-Path $projectRoot "deploy_worktree"

function Test-GitRepository {
    param([string]$Path)

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & git -C $Path rev-parse --is-inside-work-tree 1>$null 2>$null
        return $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Invoke-Git {
    param(
        [string]$Repository,
        [string[]]$Arguments
    )

    & git -C $Repository @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($Arguments -join ' ')"
    }
}

function Invoke-FieldNotesBuild {
    param([string]$ProjectPath)

    Push-Location $ProjectPath
    try {
        & python "scripts\build_field_notes.py"
        if ($LASTEXITCODE -ne 0) {
            throw "Field Notes build failed in $ProjectPath"
        }
    } finally {
        Pop-Location
    }
}

function Sync-MediumImportsToLocal {
    param(
        [string]$Repository,
        [string]$ProjectPath
    )

    if ($Repository -eq $ProjectPath) {
        return
    }

    $repositoryMediumDirectory = Join-Path $Repository "content\medium-field-notes"
    if (-not (Test-Path -LiteralPath $repositoryMediumDirectory -PathType Container)) {
        return
    }

    New-Item -ItemType Directory -Path $mediumImportDirectory -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repositoryMediumDirectory "*") -Destination $mediumImportDirectory -Recurse -Force
}

if (-not (Test-Path -LiteralPath $sourceDirectory -PathType Container)) {
    throw "Field Notes source folder was not found: $sourceDirectory"
}

if (Test-GitRepository $projectRoot) {
    $repository = $projectRoot
} elseif (
    (Test-Path -LiteralPath $deployDirectory -PathType Container) -and
    (Test-GitRepository $deployDirectory)
) {
    $repository = (Resolve-Path $deployDirectory).Path
} else {
    throw "No working Git checkout was found."
}

Invoke-Git -Repository $repository -Arguments @("pull", "--rebase")
Sync-MediumImportsToLocal -Repository $repository -ProjectPath $projectRoot
Invoke-FieldNotesBuild -ProjectPath $projectRoot

if ($repository -ne $projectRoot) {
    $targetDirectory = Join-Path $repository "content\field-notes-src"
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null

    $sourceFiles = Get-ChildItem -LiteralPath $sourceDirectory -Filter "*.md" -File
    $sourceNames = @{}
    foreach ($sourceFile in $sourceFiles) {
        $sourceNames[$sourceFile.Name] = $true
        Copy-Item -LiteralPath $sourceFile.FullName -Destination $targetDirectory -Force
    }

    foreach ($targetFile in Get-ChildItem -LiteralPath $targetDirectory -Filter "*.md" -File) {
        if (-not $sourceNames.ContainsKey($targetFile.Name)) {
            Remove-Item -LiteralPath $targetFile.FullName
        }
    }

    Invoke-FieldNotesBuild -ProjectPath $repository
}

Invoke-Git -Repository $repository -Arguments @(
    "add", "-A", "--", "content/field-notes-src", "content/medium-field-notes", "data/field-notes.json", "field-notes"
)

& git -C $repository diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "Field Notes are already in sync, and local pages are up to date."
    exit 0
}

Invoke-Git -Repository $repository -Arguments @(
    "commit", "-m", $CommitMessage
)
Invoke-Git -Repository $repository -Arguments @("push")

Write-Host "Field Notes were pushed. GitHub Actions will publish them shortly."
