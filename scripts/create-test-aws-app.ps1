param(
    [string]$Region = "us-east-1",
    [string]$Prefix = "triage-test",
    [string]$Profile = "",
    [switch]$Cleanup
)

$ErrorActionPreference = "Stop"

function Invoke-Aws {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)

    $baseArgs = @()
    if ($Profile) {
        $baseArgs += @("--profile", $Profile)
    }
    $baseArgs += @("--region", $Region)

    & aws @baseArgs @Args
    if ($LASTEXITCODE -ne 0) {
        throw "aws command failed: aws $($baseArgs + $Args -join ' ')"
    }
}

function Invoke-AwsJson {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    $raw = Invoke-Aws @Args
    if (-not $raw) {
        return $null
    }
    return $raw | ConvertFrom-Json
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Value, $encoding)
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value,
        [int]$Depth = 10
    )

    Write-Utf8NoBom -Path $Path -Value ($Value | ConvertTo-Json -Depth $Depth)
}

function Test-AwsResource {
    param([scriptblock]$Command)
    try {
        $oldErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        & $Command *>$null
        return $true
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }
}

$accountId = (Invoke-AwsJson sts get-caller-identity --output json).Account
$safeAccount = $accountId.ToLowerInvariant()
$safeRegion = $Region.ToLowerInvariant()
$namePrefix = "$Prefix-$safeAccount-$safeRegion"
$bucketName = "$namePrefix-bucket"
$roleName = "$namePrefix-lambda-role"
$functionName = "$namePrefix-function"
$policyName = "$namePrefix-s3-read-policy"
$logGroupName = "/aws/lambda/$functionName"

Write-Host "Using account: $accountId"
Write-Host "Using region:  $Region"
Write-Host "Prefix:        $Prefix"
Write-Host ""

if ($Cleanup) {
    Write-Host "Cleaning up test resources..."

    if (Test-AwsResource { Invoke-Aws lambda get-function --function-name $functionName | Out-Null }) {
        Invoke-Aws lambda delete-function --function-name $functionName | Out-Null
        Write-Host "Deleted Lambda function: $functionName"
    }

    if (Test-AwsResource { Invoke-Aws logs describe-log-groups --log-group-name-prefix $logGroupName | Out-Null }) {
        try {
            Invoke-Aws logs delete-log-group --log-group-name $logGroupName | Out-Null
            Write-Host "Deleted log group: $logGroupName"
        } catch {
            Write-Warning "Could not delete log group $logGroupName. It may not exist yet."
        }
    }

    if (Test-AwsResource { Invoke-Aws s3api head-bucket --bucket $bucketName | Out-Null }) {
        $objects = Invoke-AwsJson s3api list-object-versions --bucket $bucketName --output json
        $toDelete = @()
        foreach ($obj in @($objects.Versions)) {
            $toDelete += @{ Key = $obj.Key; VersionId = $obj.VersionId }
        }
        foreach ($marker in @($objects.DeleteMarkers)) {
            $toDelete += @{ Key = $marker.Key; VersionId = $marker.VersionId }
        }

        if ($toDelete.Count -gt 0) {
            $deleteFile = Join-Path $env:TEMP "$functionName-delete.json"
            Write-JsonFile -Path $deleteFile -Value @{ Objects = $toDelete; Quiet = $true }
            Invoke-Aws s3api delete-objects --bucket $bucketName --delete "file://$deleteFile" | Out-Null
            Remove-Item -LiteralPath $deleteFile -Force
        }

        Invoke-Aws s3api delete-bucket --bucket $bucketName | Out-Null
        Write-Host "Deleted S3 bucket: $bucketName"
    }

    $roleArn = "arn:aws:iam::$accountId`:role/$roleName"
    $policyArn = "arn:aws:iam::$accountId`:policy/$policyName"

    if (Test-AwsResource { Invoke-Aws iam get-role --role-name $roleName | Out-Null }) {
        try {
            Invoke-Aws iam detach-role-policy --role-name $roleName --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" | Out-Null
        } catch {}
        try {
            Invoke-Aws iam detach-role-policy --role-name $roleName --policy-arn $policyArn | Out-Null
        } catch {}
        Invoke-Aws iam delete-role --role-name $roleName | Out-Null
        Write-Host "Deleted IAM role: $roleName"
    }

    if (Test-AwsResource { Invoke-Aws iam get-policy --policy-arn $policyArn | Out-Null }) {
        Invoke-Aws iam delete-policy --policy-arn $policyArn | Out-Null
        Write-Host "Deleted IAM policy: $policyName"
    }

    Write-Host "Cleanup complete."
    exit 0
}

Write-Host "Creating test S3 bucket..."
if (-not (Test-AwsResource { Invoke-Aws s3api head-bucket --bucket $bucketName | Out-Null })) {
    if ($Region -eq "us-east-1") {
        Invoke-Aws s3api create-bucket --bucket $bucketName | Out-Null
    } else {
        Invoke-Aws s3api create-bucket --bucket $bucketName --create-bucket-configuration "LocationConstraint=$Region" | Out-Null
    }
}

Invoke-Aws s3api put-bucket-tagging `
    --bucket $bucketName `
    --tagging "TagSet=[{Key=App,Value=aws-triage-agent-test},{Key=Owner,Value=local-dev},{Key=Purpose,Value=triage-testing}]" | Out-Null

$sampleFile = Join-Path $env:TEMP "$functionName-sample.txt"
Write-Utf8NoBom -Path $sampleFile -Value "hello from $functionName at $(Get-Date -Format o)"
Invoke-Aws s3 cp $sampleFile "s3://$bucketName/input/sample.txt" | Out-Null
Remove-Item -LiteralPath $sampleFile -Force
Write-Host "Bucket ready: $bucketName"

Write-Host "Creating IAM role and policy..."
$trustFile = Join-Path $env:TEMP "$functionName-trust.json"
@{
    Version = "2012-10-17"
    Statement = @(
        @{
            Effect = "Allow"
            Principal = @{ Service = "lambda.amazonaws.com" }
            Action = "sts:AssumeRole"
        }
    )
} | ForEach-Object { Write-JsonFile -Path $trustFile -Value $_ }

if (-not (Test-AwsResource { Invoke-Aws iam get-role --role-name $roleName | Out-Null })) {
    Invoke-Aws iam create-role --role-name $roleName --assume-role-policy-document "file://$trustFile" | Out-Null
}
Remove-Item -LiteralPath $trustFile -Force

$roleArn = (Invoke-AwsJson iam get-role --role-name $roleName --output json).Role.Arn
$policyArn = "arn:aws:iam::$accountId`:policy/$policyName"
$policyFile = Join-Path $env:TEMP "$functionName-policy.json"
@{
    Version = "2012-10-17"
    Statement = @(
        @{
            Effect = "Allow"
            Action = @("s3:ListBucket")
            Resource = "arn:aws:s3:::$bucketName"
        },
        @{
            Effect = "Allow"
            Action = @("s3:GetObject")
            Resource = "arn:aws:s3:::$bucketName/*"
        }
    )
} | ForEach-Object { Write-JsonFile -Path $policyFile -Value $_ }

if (-not (Test-AwsResource { Invoke-Aws iam get-policy --policy-arn $policyArn | Out-Null })) {
    Invoke-Aws iam create-policy --policy-name $policyName --policy-document "file://$policyFile" | Out-Null
}
Remove-Item -LiteralPath $policyFile -Force

Invoke-Aws iam attach-role-policy --role-name $roleName --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" | Out-Null
Invoke-Aws iam attach-role-policy --role-name $roleName --policy-arn $policyArn | Out-Null
Write-Host "Role ready: $roleArn"

Write-Host "Waiting briefly for IAM role propagation..."
Start-Sleep -Seconds 12

Write-Host "Creating Lambda deployment package..."
$buildDir = Join-Path $env:TEMP "$functionName-build"
$zipPath = Join-Path $env:TEMP "$functionName.zip"
if (Test-Path $buildDir) {
    Remove-Item -LiteralPath $buildDir -Recurse -Force
}
if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
New-Item -ItemType Directory -Path $buildDir | Out-Null

$lambdaCode = @"
import json
import os
import boto3

s3 = boto3.client("s3")

def handler(event, context):
    bucket = os.environ["BUCKET_NAME"]
    print(json.dumps({"event": event, "bucket": bucket}))

    if event.get("force_error"):
        print("forced error requested for triage testing")
        raise RuntimeError("Intentional test failure from triage test Lambda")

    response = s3.list_objects_v2(Bucket=bucket, MaxKeys=5)
    keys = [item["Key"] for item in response.get("Contents", [])]
    print(json.dumps({"keys": keys, "request_id": context.aws_request_id}))

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "triage test lambda ok",
            "bucket": bucket,
            "keys": keys
        })
    }
"@
Write-Utf8NoBom -Path (Join-Path $buildDir "lambda_function.py") -Value $lambdaCode
Compress-Archive -Path (Join-Path $buildDir "*") -DestinationPath $zipPath -Force

Write-Host "Creating or updating Lambda function..."
if (Test-AwsResource { Invoke-Aws lambda get-function --function-name $functionName | Out-Null }) {
    Invoke-Aws lambda update-function-code --function-name $functionName --zip-file "fileb://$zipPath" | Out-Null
    Invoke-Aws lambda wait function-updated --function-name $functionName
    Invoke-Aws lambda update-function-configuration `
        --function-name $functionName `
        --runtime python3.12 `
        --handler lambda_function.handler `
        --role $roleArn `
        --timeout 10 `
        --memory-size 128 `
        --environment "Variables={BUCKET_NAME=$bucketName}" | Out-Null
} else {
    Invoke-Aws lambda create-function `
        --function-name $functionName `
        --runtime python3.12 `
        --handler lambda_function.handler `
        --role $roleArn `
        --timeout 10 `
        --memory-size 128 `
        --zip-file "fileb://$zipPath" `
        --environment "Variables={BUCKET_NAME=$bucketName}" `
        --tags "App=aws-triage-agent-test,Owner=local-dev,Purpose=triage-testing" | Out-Null
}

Invoke-Aws lambda wait function-active --function-name $functionName
Remove-Item -LiteralPath $buildDir -Recurse -Force
Remove-Item -LiteralPath $zipPath -Force

Write-Host "Invoking Lambda to generate CloudWatch logs..."
$successPayload = Join-Path $env:TEMP "$functionName-success.json"
$failurePayload = Join-Path $env:TEMP "$functionName-failure.json"
$successOutput = Join-Path $env:TEMP "$functionName-success-output.json"
$failureOutput = Join-Path $env:TEMP "$functionName-failure-output.json"
'{"source":"setup-script","force_error":false}' | Set-Content -Path $successPayload -Encoding ascii
'{"source":"setup-script","force_error":true}' | Set-Content -Path $failurePayload -Encoding ascii

Invoke-Aws lambda invoke --function-name $functionName --payload "fileb://$successPayload" $successOutput | Out-Null
try {
    Invoke-Aws lambda invoke --function-name $functionName --payload "fileb://$failurePayload" $failureOutput | Out-Null
} catch {
    Write-Warning "Failure invoke returned a non-zero exit code; continuing because this is only to generate error logs."
}

Remove-Item -LiteralPath $successPayload, $failurePayload, $successOutput, $failureOutput -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Test app created."
Write-Host "S3 bucket:       $bucketName"
Write-Host "Lambda function: $functionName"
Write-Host "IAM role:        $roleName"
Write-Host "Log group:       $logGroupName"
Write-Host ""
Write-Host "Try prompts in the triage app like:"
Write-Host "  Investigate failures in Lambda function $functionName in the last 30 minutes."
Write-Host "  Check S3 bucket $bucketName and explain what resources are connected to it."
Write-Host ""
Write-Host "Cleanup command:"
Write-Host "  .\scripts\create-test-aws-app.ps1 -Region $Region -Prefix $Prefix$(if ($Profile) { " -Profile $Profile" }) -Cleanup"
