# get_image_info.ps1
# Fetches current stable tags and digests from Docker Hub for all
# third-party images used in projectdavid-platform.
#
# Usage: .\scripts\get_image_info.ps1

$images = @(
    @{ repo = "library/nginx";                               tag = "alpine" },
    @{ repo = "library/mysql";                               tag = "8.0" },
    @{ repo = "library/redis";                               tag = "7" },
    @{ repo = "qdrant/qdrant";                               tag = "latest" },
    @{ repo = "searxng/searxng";                             tag = "latest" },
    @{ repo = "otel/opentelemetry-collector-contrib";        tag = "latest" },
    @{ repo = "jaegertracing/all-in-one";                    tag = "latest" },
    @{ repo = "dperson/samba";                               tag = "latest" },
    @{ repo = "ollama/ollama";                               tag = "latest" },
    @{ repo = "vllm/vllm-openai";                            tag = "latest" }
)

Write-Host ""
Write-Host "=== Project David - Docker Image Digest Report ===" -ForegroundColor Cyan
Write-Host "Generated: $(Get-Date -Format yyyy-MM-dd HH:mm:ss)" -ForegroundColor Gray
Write-Host ""

foreach ($img in $images) {
    $repo = $img.repo
    $tag  = $img.tag
    $url  = "https://hub.docker.com/v2/repositories/$repo/tags/$tag"

    try {
        $response = Invoke-RestMethod $url -ErrorAction Stop

        $digest     = $response.digest
        $lastPushed = $response.last_pushed
        $fullSize   = [math]::Round($response.full_size / 1MB, 1)

        $tagsUrl  = "https://hub.docker.com/v2/repositories/$repo/tags?page_size=10"
        $tagsResp = Invoke-RestMethod $tagsUrl -ErrorAction Stop
        $stableTags = $tagsResp.results |
            Where-Object { $_.name -notmatch "latest|beta|rc|alpha|dev|nightly" } |
            Select-Object -First 1

        $stableTag = if ($stableTags) { $stableTags.name } else { "N/A" }

        Write-Host "[$repo]" -ForegroundColor Yellow
        Write-Host "  Tag queried       : $tag"
        Write-Host "  Latest stable tag : $stableTag"
        Write-Host "  Digest            : $digest"
        Write-Host "  Last pushed       : $lastPushed"
        Write-Host "  Size              : ${fullSize} MB"
        Write-Host ""

    } catch {
        Write-Host "[$repo]" -ForegroundColor Yellow
        Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host ""
    }
}

Write-Host "=== Done ===" -ForegroundColor Cyan
