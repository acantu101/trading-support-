#!/bin/bash
# scenarios/aws/verify.sh — Verify fix for missing s3:PutObject in archive role policy

source "$(dirname "$0")/../_lib/common.sh"

POLICY_FILE="$HOME/trading-support/aws/policies/archive-role-policy.json"

banner "AWS IAM — Archive Role Verify"

# ── Check ────────────────────────────────────────────────────────────────────
if [[ ! -f "$POLICY_FILE" ]]; then
    err "Policy file not found: $POLICY_FILE"
    err "Run setup.sh first."
    exit 1
fi

if ! grep -q '"s3:PutObject"' "$POLICY_FILE"; then
    echo ""
    err "NOT FIXED"
    echo ""
    echo -e "${RED}The role policy is still missing ${BOLD}s3:PutObject${NC}${RED}.${NC}"
    echo -e "${YELLOW}The archive job can list and read from S3, but cannot write.${NC}"
    echo ""
    echo -e "${BOLD}Nudge:${NC} Add ${CYAN}s3:PutObject${NC} to the Action array in:"
    echo -e "       ${BOLD}$POLICY_FILE${NC}"
    echo ""
    echo -e "The Action array currently contains:"
    python3 -c "
import json, sys
try:
    with open('$POLICY_FILE') as f:
        pol = json.load(f)
    for stmt in pol.get('Statement', []):
        actions = stmt.get('Action', [])
        if isinstance(actions, str):
            actions = [actions]
        for a in actions:
            print(f'    {a}')
except Exception as e:
    print(f'  (could not parse: {e})')
" 2>/dev/null
    echo ""
    exit 1
fi

# ── Fixed ────────────────────────────────────────────────────────────────────
ok "s3:PutObject found in policy — running upload simulation..."
echo ""

sleep 0.3
info "Invoking archive-job lambda simulation..."
sleep 0.3
step "Scanning local trade files for upload..."
sleep 0.3
echo -e "    ${CYAN}Found: trades_20260505.csv  (2.4 MB)${NC}"
sleep 0.3
step "Assuming role: arn:aws:iam::123456789012:role/archive-role"
sleep 0.3
echo -e "    ${GREEN}AssumeRole → credentials issued (expires in 3600s)${NC}"
sleep 0.3
step "Starting S3 upload..."
sleep 0.5
echo -e "    ${GREEN}upload: trades_20260505.csv to s3://firm-trade-archive/daily/trades_20260505.csv${NC}"
sleep 0.3
ok "Upload completed — verifying presence in bucket..."
sleep 0.3

echo ""
echo -e "${BOLD}${CYAN}\$ aws s3 ls s3://firm-trade-archive/daily/ --human-readable${NC}"
sleep 0.3
echo -e "    2026-05-05 06:02:17    2.4 MiB  trades_20260505.csv"
sleep 0.3

echo ""
echo -e "${BOLD}${CYAN}\$ aws iam simulate-principal-policy \\${NC}"
echo -e "${BOLD}${CYAN}    --policy-source-arn arn:aws:iam::123456789012:role/archive-role \\${NC}"
echo -e "${BOLD}${CYAN}    --action-names s3:PutObject \\${NC}"
echo -e "${BOLD}${CYAN}    --resource-arns arn:aws:s3:::firm-trade-archive/daily/*${NC}"
sleep 0.5
echo ""
echo -e "    EvalDecision:  ${GREEN}${BOLD}ALLOW${NC}"
echo -e "    MatchedStatements:"
echo -e "      - SourcePolicyType: IAM Policy"
echo -e "        StartRange: { Line: 1, Column: 1 }"
echo -e "    Action:   s3:PutObject     ${GREEN}[ALLOW]${NC}"
echo -e "    Action:   s3:GetObject     ${GREEN}[ALLOW]${NC}"
echo -e "    Action:   s3:ListBucket    ${GREEN}[ALLOW]${NC}"
sleep 0.3

echo ""
ok "Archive job will now run successfully on schedule."

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║              SCENARIO COMPLETE — AWS IAM                    ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}${CYAN}What you diagnosed${NC}"
echo -e "  The nightly archive job was failing with AccessDenied on s3:PutObject."
echo -e "  The IAM role had s3:GetObject and s3:ListBucket but was never granted"
echo -e "  write permission — a classic case of incomplete least-privilege setup."
echo ""

echo -e "${BOLD}${CYAN}What you fixed${NC}"
echo -e "  Added s3:PutObject to the Action array in archive-role-policy.json."
echo -e "  The role can now write objects to the firm-trade-archive bucket under"
echo -e "  the /daily/ prefix it is scoped to."
echo ""

echo -e "${BOLD}${CYAN}Real-world context${NC}"
echo -e "  Principle of least privilege means granting only the minimum permissions"
echo -e "  needed — but the key word is 'needed'. Forgetting s3:PutObject when the"
echo -e "  whole purpose of the role is to upload files is not least-privilege, it's"
echo -e "  a misconfiguration. IAM policy evaluation order matters: an explicit Deny"
echo -e "  anywhere (SCP, bucket policy, VPC endpoint policy) overrides any Allow."
echo -e "  For cross-account S3 access, both the IAM role policy AND the bucket"
echo -e "  resource policy must grant access — one alone is insufficient."
echo -e "  CloudTrail logs every API call including the AccessDenied events, making"
echo -e "  this class of error straightforward to diagnose."
echo ""

echo -e "${BOLD}${CYAN}How to prevent it${NC}"
echo -e "  - Use IAM Access Analyzer to validate policies before deploy."
echo -e "  - Simulate principal policy in CI/CD: fail the pipeline if required"
echo -e "    actions return DENY before the role ever hits production."
echo -e "  - Note: s3:DeleteObject was present in the original policy — that is a"
echo -e "    ${YELLOW}red herring and a risk${NC}. An archive role should never be able to delete."
echo -e "    Remove it and apply an S3 Object Lock or bucket policy Deny on Delete"
echo -e "    for immutable audit trails."
echo -e "  - Tag roles with their owning team and intended purpose; review quarterly."
echo ""
