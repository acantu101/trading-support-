#!/bin/bash
source "$(dirname "$0")/../_lib/common.sh"

step "AWS Scenario: Nightly archive job gets AccessDenied on s3://firm-trade-archive/daily/"

step "Creating directory structure..."
mkdir -p ~/trading-support/aws/{bin,policies,logs,data}
ok "Directories created"

step "Writing fake trade CSV..."
cat > ~/trading-support/aws/data/trades_20260505.csv << 'CSVEOF'
trade_id,symbol,side,quantity,price,account,trader_id,venue,trade_date,timestamp
TRD000001,AAPL,BUY,500,187.3200,ACC0012,T0023,NASDAQ,2026-05-05,2026-05-05T09:31:04.112Z
TRD000002,MSFT,SELL,300,412.7500,ACC0034,T0008,NYSE,2026-05-05,2026-05-05T09:31:22.340Z
TRD000003,NVDA,BUY,200,887.1100,ACC0007,T0041,BATS,2026-05-05,2026-05-05T09:32:05.891Z
TRD000004,TSLA,SELL,1000,234.5600,ACC0019,T0015,NASDAQ,2026-05-05,2026-05-05T09:33:18.004Z
TRD000005,GOOGL,BUY,150,172.4400,ACC0028,T0033,IEX,2026-05-05,2026-05-05T09:34:01.556Z
TRD000006,JPM,BUY,800,214.8800,ACC0003,T0002,NYSE,2026-05-05,2026-05-05T09:35:44.219Z
TRD000007,GS,SELL,250,487.2200,ACC0045,T0019,ARCA,2026-05-05,2026-05-05T09:36:33.774Z
TRD000008,AMZN,BUY,400,195.6700,ACC0011,T0027,NASDAQ,2026-05-05,2026-05-05T09:37:12.003Z
TRD000009,META,SELL,600,521.3300,ACC0022,T0044,BATS,2026-05-05,2026-05-05T09:38:55.621Z
TRD000010,BAC,BUY,2000,39.8800,ACC0016,T0009,NYSE,2026-05-05,2026-05-05T09:39:40.099Z
CSVEOF
ok "trades_20260505.csv written"

step "Writing IAM role policy (with bug: s3:PutObject missing)..."
cat > ~/trading-support/aws/policies/archive-role-policy.json << 'JSONEOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowTradeArchiveRead",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion",
        "s3:GetObjectAcl"
      ],
      "Resource": "arn:aws:s3:::firm-trade-archive/*",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["daily/*", "monthly/*", "audit/*"]
        }
      }
    },
    {
      "Sid": "AllowTradeArchiveList",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetBucketLocation",
        "s3:ListBucketVersions"
      ],
      "Resource": "arn:aws:s3:::firm-trade-archive",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["daily/*", "monthly/*"]
        }
      }
    },
    {
      "Sid": "AllowDeleteOldArchives",
      "Effect": "Allow",
      "Action": [
        "s3:DeleteObject",
        "s3:DeleteObjectVersion"
      ],
      "Resource": "arn:aws:s3:::firm-trade-archive/daily/*",
      "Condition": {
        "NumericLessThan": {
          "s3:object-lock-remaining-retention-days": "0"
        }
      }
    }
  ]
}
JSONEOF
# NOTE: s3:PutObject is intentionally MISSING from this policy.
# The policy was rotated and the engineer who wrote it forgot to include it.
# s3:DeleteObject is present (red herring — looks like write access but isn't PutObject).
ok "archive-role-policy.json written (s3:PutObject intentionally missing)"

step "Writing bucket policy (looks correct — not the culprit)..."
cat > ~/trading-support/aws/policies/bucket-policy.json << 'JSONEOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowTradingArchiveRole",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/TradingArchiveRole"
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::firm-trade-archive",
        "arn:aws:s3:::firm-trade-archive/*"
      ]
    },
    {
      "Sid": "DenyPublicAccess",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::firm-trade-archive",
        "arn:aws:s3:::firm-trade-archive/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    },
    {
      "Sid": "EnforceEncryption",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::firm-trade-archive/*",
      "Condition": {
        "StringNotEquals": {
          "s3:x-amz-server-side-encryption": "aws:kms"
        }
      }
    }
  ]
}
JSONEOF
ok "bucket-policy.json written"

step "Writing failed archive job log..."
cat > ~/trading-support/aws/logs/archive-job.log << 'LOGEOF'
[2026-05-05 02:00:00] INFO  nightly-trade-archive v2.4.1 starting
[2026-05-05 02:00:00] INFO  Role: arn:aws:iam::123456789012:role/TradingArchiveRole
[2026-05-05 02:00:00] INFO  Target bucket: s3://firm-trade-archive/daily/
[2026-05-05 02:00:01] INFO  Collecting trade files from /var/oms/exports/...
[2026-05-05 02:00:01] INFO  Found 1 file(s) to archive: trades_20260505.csv (42.3 KB)
[2026-05-05 02:00:02] INFO  Uploading trades_20260505.csv -> s3://firm-trade-archive/daily/trades_20260505.csv
[2026-05-05 02:00:03] ERROR An error occurred (AccessDenied) when calling the PutObject operation:
                            User: arn:aws:iam::123456789012:role/TradingArchiveRole
                            is not authorized to perform: s3:PutObject
                            on resource: "arn:aws:s3:::firm-trade-archive/daily/trades_20260505.csv"
                            because no identity-based policy allows the s3:PutObject action
[2026-05-05 02:00:03] ERROR Upload failed. Retrying in 30 seconds... (attempt 1/3)
[2026-05-05 02:00:33] ERROR Upload failed. Retrying in 30 seconds... (attempt 2/3)
[2026-05-05 02:01:03] ERROR Upload failed. Retrying in 30 seconds... (attempt 3/3)
[2026-05-05 02:01:33] CRITICAL All retries exhausted. Archive job FAILED.
[2026-05-05 02:01:33] CRITICAL PagerDuty alert sent: P1 — Nightly trade archive failed (AccessDenied)
[2026-05-05 02:01:33] INFO  Job exit code: 1
LOGEOF
ok "archive-job.log written"

step "Writing fake AWS CLI wrapper..."
cat > ~/trading-support/aws/bin/aws << 'BASHEOF'
#!/bin/bash
# Fake AWS CLI for the IAM/S3 AccessDenied scenario.
# Add to PATH: export PATH=~/trading-support/aws/bin:$PATH

POLICIES_DIR=~/trading-support/aws/policies
DATA_DIR=~/trading-support/aws/data

# Parse first two args as service and subcommand
SERVICE="${1:-}"
SUBCMD="${2:-}"

case "$SERVICE" in

  sts)
    case "$SUBCMD" in
      get-caller-identity)
        cat << 'JSON'
{
    "UserId": "AROAEXAMPLEID123:nightly-archive-session",
    "Account": "123456789012",
    "Arn": "arn:aws:sts::123456789012:assumed-role/TradingArchiveRole/nightly-archive-session"
}
JSON
        ;;
      *)
        echo "aws sts: unknown subcommand '$SUBCMD'" >&2; exit 1 ;;
    esac
    ;;

  s3)
    case "$SUBCMD" in
      ls)
        BUCKET_ARG="${3:-}"
        if [[ "$BUCKET_ARG" == "s3://firm-trade-archive/"* ]] || [[ "$BUCKET_ARG" == "s3://firm-trade-archive" ]]; then
          echo "2026-03-01 02:01:44      43821 daily/trades_20260301.csv"
          echo "2026-04-01 02:01:12      44103 daily/trades_20260401.csv"
          echo "2026-05-01 02:00:58      43955 daily/trades_20260501.csv"
          echo "2026-05-04 02:01:33          0 daily/trades_20260504.csv  (FAILED - incomplete)"
        else
          echo "aws s3 ls: specify a bucket URI, e.g. s3://firm-trade-archive/" >&2
          exit 1
        fi
        ;;
      cp)
        SRC="${3:-}"
        DST="${4:-}"
        # Detect upload direction
        if [[ "$SRC" == s3://* ]]; then
          # Download: GetObject — succeeds
          LOCAL_FILE="${DST:-/tmp/downloaded.csv}"
          FNAME=$(basename "$SRC")
          echo "download: $SRC to $LOCAL_FILE"
          # Simulate writing local file
          echo "(simulated content for $FNAME)" > "$LOCAL_FILE" 2>/dev/null || true
          echo "Completed 1 part(s) with ... file(s) remaining"
        else
          # Upload: PutObject — FAILS (missing s3:PutObject in role policy)
          FNAME=$(basename "$SRC")
          echo "upload: $SRC to $DST"
          echo ""
          echo "upload failed: $SRC to $DST An error occurred (AccessDenied) when calling the PutObject operation: User: arn:aws:iam::123456789012:role/TradingArchiveRole is not authorized to perform: s3:PutObject on resource: \"arn:aws:s3:::firm-trade-archive/daily/$FNAME\" because no identity-based policy allows the s3:PutObject action" >&2
          exit 1
        fi
        ;;
      sync)
        echo "sync would upload from ${3:-} to ${4:-}"
        echo ""
        echo "upload failed: AccessDenied on s3:PutObject (same root cause as s3 cp)" >&2
        exit 1
        ;;
      *)
        echo "aws s3: subcommand '$SUBCMD' not simulated" >&2; exit 1 ;;
    esac
    ;;

  iam)
    case "$SUBCMD" in
      get-role-policy)
        echo "{"
        echo "  \"RoleName\": \"TradingArchiveRole\","
        echo "  \"PolicyName\": \"TradingArchiveInlinePolicy\","
        echo "  \"PolicyDocument\":"
        cat "$POLICIES_DIR/archive-role-policy.json"
        echo "}"
        ;;
      list-attached-role-policies)
        cat << 'JSON'
{
    "AttachedPolicies": [
        {
            "PolicyName": "TradingArchiveInlinePolicy",
            "PolicyArn": "arn:aws:iam::123456789012:policy/TradingArchiveInlinePolicy"
        }
    ]
}
JSON
        ;;
      simulate-principal-policy)
        cat << 'JSON'
{
    "EvaluationResults": [
        {
            "EvalActionName": "s3:GetObject",
            "EvalResourceName": "arn:aws:s3:::firm-trade-archive/daily/*",
            "EvalDecision": "allowed",
            "MatchedStatements": [{"SourcePolicyId": "AllowTradeArchiveRead", "StartPosition": {"Line": 1}}]
        },
        {
            "EvalActionName": "s3:PutObject",
            "EvalResourceName": "arn:aws:s3:::firm-trade-archive/daily/*",
            "EvalDecision": "implicitDeny",
            "MatchedStatements": [],
            "MissingContextValues": [],
            "EvalDecisionDetails": {
                "TradingArchiveInlinePolicy": "implicitDeny"
            }
        },
        {
            "EvalActionName": "s3:DeleteObject",
            "EvalResourceName": "arn:aws:s3:::firm-trade-archive/daily/*",
            "EvalDecision": "allowed",
            "MatchedStatements": [{"SourcePolicyId": "AllowDeleteOldArchives", "StartPosition": {"Line": 1}}]
        },
        {
            "EvalActionName": "s3:ListBucket",
            "EvalResourceName": "arn:aws:s3:::firm-trade-archive",
            "EvalDecision": "allowed",
            "MatchedStatements": [{"SourcePolicyId": "AllowTradeArchiveList", "StartPosition": {"Line": 1}}]
        }
    ]
}
JSON
        ;;
      get-policy-version|get-policy)
        cat "$POLICIES_DIR/archive-role-policy.json"
        ;;
      *)
        echo "aws iam: subcommand '$SUBCMD' not simulated — try get-role-policy, simulate-principal-policy" >&2
        exit 1
        ;;
    esac
    ;;

  s3api)
    case "$SUBCMD" in
      get-bucket-policy)
        echo "{ \"Policy\":"
        python3 -c "import json,sys; print(json.dumps(open('$POLICIES_DIR/bucket-policy.json').read()))" 2>/dev/null \
          || cat "$POLICIES_DIR/bucket-policy.json"
        echo "}"
        ;;
      *)
        echo "aws s3api: subcommand '$SUBCMD' not simulated" >&2; exit 1 ;;
    esac
    ;;

  *)
    echo "aws: simulated CLI — supported services: sts, s3, s3api, iam"
    echo "Commands for this scenario:"
    echo "  aws sts get-caller-identity"
    echo "  aws s3 ls s3://firm-trade-archive/"
    echo "  aws s3 cp ~/trading-support/aws/data/trades_20260505.csv s3://firm-trade-archive/daily/"
    echo "  aws s3 cp s3://firm-trade-archive/daily/trades_20260301.csv /tmp/test.csv"
    echo "  aws iam get-role-policy --role-name TradingArchiveRole --policy-name TradingArchiveInlinePolicy"
    echo "  aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::123456789012:role/TradingArchiveRole --action-names s3:PutObject"
    echo "  aws s3api get-bucket-policy --bucket firm-trade-archive"
    ;;
esac
BASHEOF
chmod +x ~/trading-support/aws/bin/aws
ok "aws CLI wrapper written and chmod +x"

info "Add to PATH: export PATH=~/trading-support/aws/bin:\$PATH"
info "Reproduce: aws s3 cp ~/trading-support/aws/data/trades_20260505.csv s3://firm-trade-archive/daily/"
info "Diagnose: aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::123456789012:role/TradingArchiveRole --action-names s3:PutObject"
info "Fix: add s3:PutObject to ~/trading-support/aws/policies/archive-role-policy.json AllowTradeArchiveRead statement"
