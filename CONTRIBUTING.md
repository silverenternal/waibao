# 贡献指南

感谢你考虑为 **招聘智能体 (Recruitment Agent)** 做出贡献!

## 🎯 项目愿景

打造一个**真正 AI-native** 的双向招聘智能体,服务求职者和用人单位。

## 🤝 行为准则

- 尊重所有贡献者
- 欢迎不同背景和经验水平的人
- 建设性反馈,不攻击个人
- 关注社区利益,而非个人利益

## 🚀 如何贡献

### 报告 Bug

1. 检查 [Issues](https://github.com/silverenternal/waibao/issues) 确认未被报告
2. 提供详细信息:
   - 复现步骤
   - 期望行为
   - 实际行为
   - 环境(Python/Node 版本、OS)
   - 错误日志

### 提出新功能

1. 先开 Issue 讨论,确认方向
2. 描述:
   - 用例
   - 为什么有价值
   - 替代方案
   - 实现思路

### 提交 PR

1. Fork 仓库
2. 创建分支:`git checkout -b feature/xxx`
3. 编码 + 写测试
4. 确保测试通过:`cd backend && pytest -v`
5. 提交:`git commit -m "feat: xxx"`
6. Push:`git push origin feature/xxx`
7. 开 PR,描述变更内容

## 📝 开发规范

### 代码风格

**Python**:
- 用 `ruff` 或 `black` 格式化
- 类型注解
- Docstring (Google 风格)

**TypeScript**:
- 用 ESLint + Prettier
- 函数组件 + hooks
- 不用 any

### Commit 信息

用 [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(profile): 添加简历 OCR 能力
fix(emotion): 修复高风险告警延迟
docs: 更新 AGENTS.md
test: 添加 ReAct agent 测试
refactor: 移除关键词路由
```

### 测试要求

- 新功能必须有测试
- Bug 修复必须先写 failing test
- 测试覆盖率不掉

### 文档

- 修改代码时同步更新文档
- 新增 Agent 在 `docs/AGENTS.md` 加一节
- 新增 API 在 `docs/API.md` 加一行
- 架构变更更新 `docs/ARCHITECTURE.md`

## 🏗️ 开发流程

### 环境设置

```bash
# 1. Fork + clone
git clone https://github.com/YOUR_USERNAME/waibao.git
cd waibao/talent-tool-mvp

# 2. Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 测试依赖

# 3. Frontend
cd ../frontend
npm install

# 4. 环境变量
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
# 编辑填入 Supabase / OpenAI key
```

### 测试

```bash
cd backend
pytest -v                # 全部
pytest tests/agents/     # 只跑 Agent 测试
pytest -k emotion        # 只跑 emotion 相关
```

### 本地起服务

```bash
# Backend
cd backend && uvicorn main:app --reload

# Frontend
cd frontend && npm run dev

# 访问
# API:    http://localhost:8000
# Docs:   http://localhost:8000/docs
# Web:    http://localhost:3000
```

## 🎨 添加新 Agent

参见 `docs/AGENTS.md` 末尾的"扩展 Agent"指南。

简版步骤:
1. 在 `backend/agents/{domain}/` 下创建 `xxx_agent.py`
2. 继承 `BaseAgent` 或 `ReActAgent`
3. 实现 `name`/`description`/`required_personas`/`async _handle`
4. 在 `backend/agents/boot.py` 注册
5. 在 `backend/agents/semantic_router.py::AGENT_INTENT_DESCRIPTIONS` 添加意图描述
6. 在 `docs/AGENTS.md` 文档化
7. 写测试:`backend/tests/agents/test_xxx_agent.py`

## 🐛 Debug 技巧

```bash
# 后端日志
cd backend && uvicorn main:app --log-level debug

# 单独测试某个 Agent
python -c "
import asyncio
from agents.jobseeker.emotion_agent import EmotionAgent
from agents.runtime import AgentInput, LLMClient

async def main():
    agent = EmotionAgent(llm=LLMClient(openai_client=None))  # mock 模式
    inp = AgentInput(user_id='u1', persona='jobseeker', text='我今天崩溃')
    out = await agent.run(inp)
    print(out.text)
    print(out.artifacts)

asyncio.run(main())
"
```

## 📋 PR 模板

```markdown
## 变更说明

(简述变更)

## 相关 Issue

Closes #xxx

## 类型

- [ ] Bug 修复
- [ ] 新功能
- [ ] 重构
- [ ] 文档
- [ ] 测试

## 测试

- [ ] 添加/修改测试
- [ ] 所有测试通过
- [ ] 文档已更新

## 截图 (UI 变更)

(可选)
```

## 🎁 第一次贡献?

可以从这些"good first issue"开始:

- 修复文档中的 typo
- 添加测试用例
- 改进 prompt
- 增加 i18n 翻译
- 提交 bug 报告

## 📞 联系方式

- GitHub Issues: https://github.com/silverenternal/waibao/issues
- 邮件: 通过 GitHub profile 联系

## 📄 License

提交 PR 即表示同意按 [MIT License](LICENSE) 授权你的贡献。