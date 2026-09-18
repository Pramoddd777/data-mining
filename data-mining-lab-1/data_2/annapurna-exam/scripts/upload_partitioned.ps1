param(
    [string]$MinioEndpoint = 'http://host.docker.internal:9000',
    [string]$Bucket = 'annapurna-sales',
    [string]$Source = "$PSScriptRoot\..\output\sales_partitioned"
)

$resolvedSource = (Resolve-Path $Source).Path
$containerSource = '/data/sales_partitioned'

docker run --rm `
    --add-host host.docker.internal:host-gateway `
    -v "${resolvedSource}:${containerSource}:ro" `
    --entrypoint /bin/sh `
    quay.io/minio/mc:latest `
    -c "mc alias set local $MinioEndpoint minioadmin minioadmin123 && mc mb --ignore-existing local/$Bucket && mc cp --recursive $containerSource/ local/$Bucket/sales_partitioned/"
exit $LASTEXITCODE