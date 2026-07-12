#!/usr/bin/env bash
# =============================================================================
# Waibao v4.0 — 真实 API key 一键配置脚本 (T1701)
# =============================================================================
#
# 用法:
#   bash scripts/setup_real_keys.sh                  # 交互式选择供应商
#   bash scripts/setup_real_keys.sh --provider openai # 配置单个供应商
#   bash scripts/setup_real_keys.sh --all            # 配置所有 (会问每个 key)
#   bash scripts/setup_real_keys.sh --check          # 检查当前 .env 已配置项
#   bash scripts/setup_real_keys.sh --non-interactive # 从环境变量读取,失败即退出
#
# 凭证申请步骤: docs/REAL_API_SETUP.md
# 配置文件:    backend/.env  (从 backend/config/.env.example 复制)
# =============================================================================

set -euo pipefail

# ---------- 路径定位 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
TEMPLATE="${BACKEND_DIR}/config/.env.example"
ENV_FILE="${BACKEND_DIR}/.env"

# ---------- 颜色 ----------
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; BOLD=''; RESET=''
fi

log()   { printf "${BLUE}[setup]${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}[warn]${RESET}  %s\n" "$*"; }
err()   { printf "${RED}[err]${RESET}   %s\n" "$*" >&2; }
ok()    { printf "${GREEN}[ok]${RESET}    %s\n" "$*"; }
header(){ printf "\n${BOLD}${CYAN}==> %s${RESET}\n" "$*"; }

# ---------- 预检 ----------
check_prereqs() {
    if [ ! -f "${TEMPLATE}" ]; then
        err "模板文件不存在: ${TEMPLATE}"
        err "请确认 backend/config/.env.example 已生成"
        exit 1
    fi
    if [ ! -f "${ENV_FILE}" ]; then
        warn ".env 不存在,从模板复制"
        cp "${TEMPLATE}" "${ENV_FILE}"
        ok "已生成 ${ENV_FILE}"
    fi
}

# ---------- 读取当前值 ----------
get_env_value() {
    local key="$1"
    grep -E "^${key}=" "${ENV_FILE}" 2>/dev/null | head -1 | sed -E "s|^${key}=||" || true
}

set_env_value() {
    local key="$1"
    local value="$2"
    if grep -qE "^${key}=" "${ENV_FILE}"; then
        # macOS / Linux 通用 sed
        if sed --version >/dev/null 2>&1; then
            sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
        else
            sed -i '' "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
        fi
    else
        printf "%s=%s\n" "${key}" "${value}" >> "${ENV_FILE}"
    fi
}

mask_value() {
    local v="$1"
    if [ -z "${v}" ]; then
        echo "(未设置)"
    elif [ ${#v} -le 8 ]; then
        echo "***"
    else
        echo "${v:0:4}***${v: -4}"
    fi
}

# ---------- 提示输入 ----------
read_secret() {
    local prompt="$1"
    local default="${2:-}"
    local value=""
    if [ -t 0 ] && [ -z "${NON_INTERACTIVE:-}" ]; then
        if [ -n "${default}" ]; then
            read -r -p "$(printf "${CYAN}%s${RESET} [${default}]: " "${prompt}")" value
            [ -z "${value}" ] && value="${default}"
        else
            read -r -p "$(printf "${CYAN}%s${RESET}: " "${prompt}")" value
        fi
    else
        # 非交互: 从同名环境变量取,否则保留现有值
        local env_var
        env_var=$(echo "${prompt}" | grep -oE '\$\{?[A-Z_][A-Z0-9_]*\}?' | head -1 | tr -d '${}' || true)
        if [ -n "${env_var}" ] && [ -n "${!env_var:-}" ]; then
            value="${!env_var}"
        elif [ -n "${default}" ]; then
            value="${default}"
        fi
    fi
    echo "${value}"
}

# ---------- 供应商清单 (key 名 + 中文标签 + 申请 URL + 凭证申请文档小节) ----------
PROVIDERS=(
    "openai_llm|OpenAI LLM (gpt-4o / gpt-4o-mini / o1)|OPENAI_API_KEY|https://platform.openai.com/api-keys|1.1"
    "anthropic|Anthropic Claude (claude-3-5-sonnet/haiku/opus)|ANTHROPIC_API_KEY|https://console.anthropic.com/settings/keys|1.2"
    "deepseek|DeepSeek (deepseek-chat / deepseek-reasoner)|DEEPSEEK_API_KEY|https://platform.deepseek.com/api_keys|1.3"
    "zhipu_llm|智谱 GLM (glm-4-flash / air / plus)|ZHIPU_API_KEY|https://bigmodel.cn/console/apikey|1.4"
    "openai_embedding|OpenAI Embedding (text-embedding-3)|OPENAI_API_KEY|https://platform.openai.com/api-keys|2.1 (复用 LLM key)"
    "zhipu_embedding|智谱 Embedding (embedding-2)|ZHIPU_API_KEY|https://bigmodel.cn/console/apikey|2.2 (复用 LLM key)"
    "tencent_ocr|腾讯云 OCR (GeneralBasicOCR)|TENCENT_SECRET_ID,TENCENT_SECRET_KEY|https://console.cloud.tencent.com/cam/capi|3.1"
    "baidu_ocr|百度 OCR (accurate_basic)|BAIDU_OCR_API_KEY,BAIDU_OCR_SECRET_KEY|https://console.bce.baidu.com/ai/#/ai/ocr/app/list|3.2"
    "whisper|OpenAI Whisper (whisper-1)|OPENAI_API_KEY|https://platform.openai.com/api-keys|4.1 (复用 LLM key)"
    "sendgrid|SendGrid SMTP|smtp|SMTP_HOST,SMTP_PORT,SMTP_USERNAME,SMTP_PASSWORD,SMTP_FROM|https://app.sendgrid.com/settings/api_keys|5"
    "tianyancha|天眼查 OpenAPI|TIANYANCHA_API_KEY|https://open.tianyancha.com/console|6"
    "boss|Boss直聘 OpenAPI|JOB_MARKET_BOSS_APP_KEY|https://www.zhipin.com/api/|7"
    "zoom|Zoom Server-to-Server OAuth|zoom|ZOOM_ACCOUNT_ID,ZOOM_CLIENT_ID,ZOOM_CLIENT_SECRET|https://marketplace.zoom.us/develop/create|8"
    "stripe|Stripe 支付|STRIPE_SECRET_KEY,STRIPE_WEBHOOK_SECRET|https://dashboard.stripe.com/apikeys|9"
    "dingtalk|钉钉群机器人 Webhook|DINGTALK_WEBHOOK,DINGTALK_SECRET|https://open.dingtalk.com/document/orgapp/custom-robot-access|10"
    "feishu|飞书群机器人 Webhook|FEISHU_WEBHOOK,FEISHU_SECRET|https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot|11"
)

# ---------- 配置单个供应商 ----------
configure_provider() {
    local entry="$1"
    local id label keylist url doc_section
    IFS='|' read -r id label keylist url doc_section <<< "${entry}"

    header "${label}"
    echo "    申请 URL: ${url}"
    echo "    详细步骤: docs/REAL_API_SETUP.md §${doc_section}"

    local current
    current=$(get_env_value "${keylist%%,*}")

    if [[ "${keylist}" == *","* ]]; then
        # 多 key
        IFS=',' read -ra KEYS <<< "${keylist}"
        for k in "${KEYS[@]}"; do
            local cur
            cur=$(get_env_value "${k}")
            echo "    当前 ${k}: $(mask_value "${cur}")"
            local new_val
            new_val=$(read_secret "${k}" "${cur}")
            if [ -n "${new_val}" ]; then
                set_env_value "${k}" "${new_val}"
                ok "已更新 ${k}"
            fi
        done
    else
        # 单 key (含特殊 case: smtp/zoom 用 set_env_value 多 key)
        if [[ "${id}" == "sendgrid" ]]; then
            local cur
            for k in SMTP_HOST SMTP_PORT SMTP_USERNAME SMTP_PASSWORD SMTP_FROM; do
                cur=$(get_env_value "${k}")
                local new_val
                new_val=$(read_secret "${k}" "${cur}")
                [ -n "${new_val}" ] && set_env_value "${k}" "${new_val}"
            done
            ok "已更新 SMTP 配置 (5 个 key)"
        elif [[ "${id}" == "zoom" ]]; then
            local cur
            for k in ZOOM_ACCOUNT_ID ZOOM_CLIENT_ID ZOOM_CLIENT_SECRET; do
                cur=$(get_env_value "${k}")
                local new_val
                new_val=$(read_secret "${k}" "${cur}")
                [ -n "${new_val}" ] && set_env_value "${k}" "${new_val}"
            done
            ok "已更新 Zoom OAuth 配置 (3 个 key)"
        else
            local cur
            cur=$(get_env_value "${keylist}")
            echo "    当前 ${keylist}: $(mask_value "${cur}")"
            local new_val
            new_val=$(read_secret "${keylist}" "${cur}")
            if [ -n "${new_val}" ]; then
                set_env_value "${keylist}" "${new_val}"
                ok "已更新 ${keylist}"
            else
                warn "跳过 ${keylist}"
            fi
        fi
    fi
}

# ---------- check 模式 ----------
check_status() {
    header "当前 .env 配置状态"
    printf "%-40s %s\n" "KEY" "STATUS"
    printf -- "------------------------------------------------------------\n"
    local total=0 configured=0
    for entry in "${PROVIDERS[@]}"; do
        IFS='|' read -r id label keylist _ _ <<< "${entry}"
        local keys
        IFS=',' read -ra keys <<< "${keylist}"
        for k in "${keys[@]}"; do
            total=$((total + 1))
            local cur
            cur=$(get_env_value "${k}")
            if [ -n "${cur}" ]; then
                printf "${GREEN}%-40s${RESET} %s\n" "${k}" "$(mask_value "${cur}")"
                configured=$((configured + 1))
            else
                printf "${RED}%-40s${RESET} (未设置)\n" "${k}"
            fi
        done
    done
    echo ""
    printf "总计: ${BOLD}%d / %d${RESET} 个 key 已配置\n" "${configured}" "${total}"

    if [ "${configured}" -eq 0 ]; then
        warn "尚未配置任何真实 key — 当前所有 provider 走 mock"
    elif [ "${configured}" -lt "${total}" ]; then
        warn "部分 key 缺失 — 缺失项将自动 fallback 到 mock"
    else
        ok "全部 key 已就绪 — 可执行 pytest -m real_api"
    fi
}

# ---------- main ----------
main() {
    check_prereqs

    # 参数解析
    MODE="interactive"
    SINGLE_PROVIDER=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --provider) SINGLE_PROVIDER="$2"; shift 2 ;;
            --all) MODE="all"; shift ;;
            --check) MODE="check"; shift ;;
            --non-interactive) NON_INTERACTIVE=1; MODE="non-interactive"; shift ;;
            -h|--help)
                grep '^#' "$0" | sed 's/^# *//'
                exit 0 ;;
            *) err "未知参数: $1"; exit 1 ;;
        esac
    done

    case "${MODE}" in
        check)
            check_status
            return 0
            ;;
        non-interactive)
            log "非交互模式 — 从环境变量读取"
            ;;
    esac

    if [ -n "${SINGLE_PROVIDER}" ]; then
        # 单供应商
        local found=""
        for entry in "${PROVIDERS[@]}"; do
            if [[ "${entry}" == "${SINGLE_PROVIDER}|"* ]]; then
                found="${entry}"
                break
            fi
        done
        if [ -z "${found}" ]; then
            err "未找到供应商: ${SINGLE_PROVIDER}"
            err "可选: ${PROVIDERS[*]}" | tr '|' '\n' | head -1
            exit 1
        fi
        configure_provider "${found}"
    elif [ "${MODE}" = "all" ]; then
        for entry in "${PROVIDERS[@]}"; do
            configure_provider "${entry}"
        done
    else
        # 交互菜单
        header "Waibao v4.0 真实 API 配置向导"
        echo "0) 全部配置 (16 个供应商)"
        echo "1) 检查当前状态"
        local i=2
        for entry in "${PROVIDERS[@]}"; do
            local id label
            IFS='|' read -r id label _ _ _ <<< "${entry}"
            echo "${i}) ${label} (${id})"
            i=$((i + 1))
        done
        echo "q) 退出"
        echo ""
        local choice
        read -r -p "$(printf "${CYAN}请选择 [0-${i}-1/q]: ${RESET}")" choice
        case "${choice}" in
            0) for entry in "${PROVIDERS[@]}"; do configure_provider "${entry}"; done ;;
            1) check_status ;;
            q|Q) exit 0 ;;
            *)
                # 单供应商
                local idx=$((choice - 2))
                if [ "${idx}" -ge 0 ] && [ "${idx}" -lt ${#PROVIDERS[@]} ]; then
                    configure_provider "${PROVIDERS[${idx}]}"
                else
                    err "无效选择: ${choice}"
                    exit 1
                fi
                ;;
        esac
    fi

    echo ""
    ok "配置完成 → ${ENV_FILE}"
    echo ""
    log "下一步:"
    echo "    cd ${BACKEND_DIR}"
    echo "    pytest -m real_api -v              # 跑真实 API 测试"
    echo "    PROVIDER_MODE=real uvicorn main:app  # 切换到真实模式启动"
}

main "$@"