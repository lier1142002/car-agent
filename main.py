"""
AutoSalesAgent 交互式命令行入口。

提供多轮对话界面，支持:
- 自然语言汽车销售咨询
- /index 命令索引知识库文档
- /history 查看会话历史
- /clear 清空会话
- /exit 退出程序
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.agent_core import AutoSalesAgent
from config import config


def setup_logging() -> None:
    """配置全局日志格式和级别。"""
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format=config.log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # 降低第三方库日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("pymilvus").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)


def print_banner() -> None:
    """打印欢迎横幅。"""
    print("""
╔═══════════════════════════════════════════════════════╗
║          AutoSalesAgent - 汽车销售培训 AI             ║
║          「组件化是核心，工作流是灵魂」                  ║
║                                                       ║
║  命令:                                                ║
║    /index <path>  - 索引产品知识库 PDF                 ║
║    /history       - 查看会话历史                       ║
║    /clear         - 清空会话记忆                       ║
║    /state         - 查看 Agent 状态                    ║
║    /exit          - 退出程序                           ║
╚═══════════════════════════════════════════════════════╝
""")


def main() -> None:
    """主函数：初始化 Agent 并启动交互循环。"""
    setup_logging()
    logger = logging.getLogger(__name__)

    print_banner()

    # 检查配置
    if not config.validate():
        print("⚠ 警告: 部分 API Key 仍为占位符，请编辑 config.py 填入真实密钥")
        print()

    # 初始化 Agent
    logger.info("正在初始化 AutoSalesAgent...")
    try:
        agent = AutoSalesAgent()
    except Exception as e:
        logger.error("Agent 初始化失败: %s", e)
        print(f"❌ Agent 初始化失败: {e}")
        print("请检查 config.py 中的配置以及 Milvus 服务是否可用。")
        sys.exit(1)

    print("✅ Agent 初始化完成，开始对话吧！")
    print()

    # 交互循环
    while True:
        try:
            user_input = input("🧑 你 > ").strip()

            if not user_input:
                continue

            # 命令处理
            if user_input.startswith("/"):
                parts = user_input.split(maxsplit=1)
                command = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""

                if command == "/exit":
                    print("👋 再见！")
                    break

                elif command == "/index":
                    if not arg:
                        print("用法: /index <PDF文件路径>")
                        continue
                    path = Path(arg)
                    if not path.exists():
                        print(f"❌ 文件不存在: {arg}")
                        continue
                    print(f"🔨 正在索引文档: {arg}")
                    try:
                        count = agent.index_knowledge_base(str(path))
                        print(f"✅ 索引完成，共 {count} 个文本块")
                    except Exception as e:
                        print(f"❌ 索引失败: {e}")
                    continue

                elif command == "/history":
                    ctx = agent.memory.get_context()
                    print("📋 会话历史:")
                    print(ctx if ctx.strip() else "(暂无记录)")
                    continue

                elif command == "/clear":
                    agent.clear_session()
                    print("✅ 会话已清空")
                    continue

                elif command == "/state":
                    state = agent.get_state()
                    print(f"📊 Agent 状态:")
                    print(f"   已注册工具: {state['tools']}")
                    print(f"   知识库已索引: {state['rag_indexed']}")
                    print(f"   当前迭代次数: {state['iteration_count']}")
                    print(f"   记忆条目数: {len(state['memory'])}")
                    continue

                else:
                    print(f"未知命令: {command}")
                    continue

            # 正常对话
            print("🤖 Agent > ", end="", flush=True)
            try:
                answer = agent.run_query(user_input)
                print(answer)
                print()
            except Exception as e:
                logger.error("查询处理失败: %s", e)
                print(f"❌ 处理失败: {e}")
                print()

        except KeyboardInterrupt:
            print("\n👋 再见！")
            break
        except EOFError:
            print("\n👋 再见！")
            break


if __name__ == "__main__":
    main()
