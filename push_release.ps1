# =========================
# Get latest tag
# =========================
$latestTag = git describe --tags --abbrev=0 2>$null

if (-not $latestTag) {
    Write-Host "No tag found, starting at v1.0.0" -ForegroundColor Yellow
    $newTag = "v1.0.0"
} else {
    Write-Host "Latest tag: $latestTag" -ForegroundColor Cyan

    if ($latestTag -match "^v(\d+)\.(\d+)\.(\d+)$") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        $patch = [int]$Matches[3] + 1
        $newTag = "v$major.$minor.$patch"
    } else {
        Write-Host "Tag format invalid: $latestTag" -ForegroundColor Red
        exit 1
    }
}

Write-Host "New version: $newTag" -ForegroundColor Green

# =========================
# Create git tag
# =========================
git tag -a $newTag -m "Release $newTag"
git push origin $newTag

# =========================
# Create GitHub Release
# =========================
gh release create $newTag `
  dist/ThaiSmartCardReader.exe `
  --title "ThaiSmartCardReader $newTag" `
  --notes "release $newTag"
