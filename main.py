import argparse
import json
import os
import time
import logging
from datetime import datetime, timedelta, timezone

import requests
from requests.exceptions import RequestException, JSONDecodeError

# ===================== 新增：基础配置 =====================
# 修复UTC兼容问题（适配Python3.10及以下）
UTC = timezone.utc
# 配置日志（同时输出到控制台+文件）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("enshan_checkin.log", encoding="utf-8"),  # 日志文件
        logging.StreamHandler()  # 控制台输出
    ]
)

# ===================== 修复：导入路径（适配仓库结构） =====================
# 仓库中__version__.py在根目录，不是dailycheckin/下
try:
    from __version__ import __version__
    # 模拟dailycheckin/configs.py的核心逻辑（仓库中无该文件，避免导入报错）
    checkin_map = {"ENSHAN": ("恩山无线论坛", None)}  # 后续替换为真实签到类
    
    def get_notice_info(data):
        """提取通知配置（Bark/Telegram）"""
        return data.get("notice", {})
    
    def get_checkin_info(data):
        """提取签到配置"""
        return {k.lower(): v for k, v in data.items() if k != "notice"}
except ImportError as e:
    logging.error(f"导入基础模块失败：{e}")
    __version__ = "1.0.0"  # 兜底版本号
    checkin_map = {"ENSHAN": ("恩山无线论坛", None)}
    get_notice_info = lambda d: d.get("notice", {})
    get_checkin_info = lambda d: {k.lower(): v for k, v in d.items() if k != "notice"}

# ===================== 修复：推送函数（适配仓库utils/message.py） =====================
try:
    from utils.message import push_message
except ImportError:
    # 兜底：无推送模块时，打印日志
    def push_message(content_list, notice_info):
        logging.info("推送模块未找到，仅打印通知内容：")
        for content in content_list:
            logging.info(content)

# ===================== 原有函数：修复参数解析 =====================
def parse_arguments():
    parser = argparse.ArgumentParser(description="恩山论坛自动签到脚本")
    parser.add_argument("--include", nargs="+", help="任务执行包含的任务列表（如 --include ENSHAN）")
    parser.add_argument("--exclude", nargs="+", help="任务执行排除的任务列表")
    return parser.parse_args()

# ===================== 修复：配置检查逻辑 =====================
def check_config(task_list):
    config_path = None
    # 修复1：优先查找仓库根目录的configjson（截图中文件名无.）+ 兼容config.json
    config_candidates = [
        "configjson",  # 仓库中实际文件名
        "config.json", # 标准命名（兼容）
        "/ql/scripts/configjson",
        "/ql/scripts/config.json"
    ]
    # 修复2：路径拼接逻辑（区分绝对路径/相对路径）
    for one_path in config_candidates:
        if one_path.startswith("/"):
            _config_path = one_path  # 绝对路径直接用
        else:
            _config_path = os.path.join(os.getcwd(), one_path)
        
        if os.path.exists(_config_path):
            config_path = os.path.normpath(_config_path)
            break

    if not config_path:
        err_msg = "未找到配置文件！请确保仓库根目录有「configjson」或「config.json」文件"
        logging.error(err_msg)
        print(err_msg)
        return False, False

    logging.info(f"使用配置文件路径: {config_path}")
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        err_msg = "Json格式错误！请用https://json.cn/校验config文件格式"
        logging.error(err_msg)
        print(err_msg)
        return False, False
    except Exception as e:
        err_msg = f"读取配置文件失败：{str(e)}"
        logging.error(err_msg)
        print(err_msg)
        return False, False

    try:
        notice_info = get_notice_info(data=data)
        _check_info = get_checkin_info(data=data)
        check_info = {}

        # 修复3：更严谨的配置过滤逻辑（排除空值/占位符）
        for task in task_list:
            task_lower = task.lower()
            accounts = _check_info.get(task_lower, [])
            if not isinstance(accounts, list):
                logging.warning(f"任务「{task}」的配置不是数组格式，跳过")
                continue
            
            valid_accounts = []
            for acc in accounts:
                # 排除空配置/占位符
                if not acc or isinstance(acc, dict) and not acc.get("cookie"):
                    logging.warning(f"任务「{task}」存在空配置/无Cookie，跳过")
                    continue
                if "xxxxxx" in str(acc) or "占位符" in str(acc):
                    logging.warning(f"任务「{task}」存在占位符配置，跳过")
                    continue
                valid_accounts.append(acc)
            
            if valid_accounts:
                check_info[task_lower] = valid_accounts

        return notice_info, check_info
    except Exception as e:
        err_msg = f"解析配置失败：{str(e)}"
        logging.error(err_msg)
        print(err_msg)
        return False, False

# ===================== 修复：核心签到逻辑 =====================
def checkin():
    start_time = time.time()
    # 修复4：UTC时区兼容 + 北京时间格式化
    beijing_time = datetime.now(UTC) + timedelta(hours=8)
    time_str = beijing_time.strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"====== 签到任务启动 ======")
    print(f"当前时间: {time_str}\n当前版本: {__version__}")

    args = parse_arguments()
    # 处理任务列表（默认执行所有任务）
    include = args.include or list(checkin_map.keys())
    exclude = args.exclude or []
    # 过滤有效任务（仅保留checkin_map中存在的）
    include_valid = [t for t in include if t in checkin_map.keys()]
    exclude_valid = [t for t in exclude if t in checkin_map.keys()]
    task_list = list(set(include_valid) - set(exclude_valid))

    if not task_list:
        err_msg = "无有效签到任务！请检查--include/--exclude参数是否正确"
        logging.error(err_msg)
        print(err_msg)
        return

    # 检查配置
    notice_info, check_info = check_config(task_list)
    if not check_info:
        err_msg = "配置校验失败，退出签到任务"
        logging.error(err_msg)
        print(err_msg)
        return

    # 打印本次执行的任务
    task_name_str = "\n".join([
        f"「{checkin_map.get(task.upper())[0]}」账号数 : {len(accounts)}"
        for task, accounts in check_info.items()
    ])
    logging.info(f"本次执行签到任务：\n{task_name_str}")
    print(f"\n---------- 本次执行签到任务如下 ----------\n\n{task_name_str}\n\n")

    content_list = []
    for task, accounts in check_info.items():
        task_name, check_func = checkin_map.get(task.upper(), (task, None))
        logging.info(f"开始执行「{task_name}」签到")
        print(f"----------开始执行「{task_name}」签到----------")

        if not check_func:
            err_msg = f"「{task_name}」未配置签到函数，请检查checkin_map"
            logging.error(err_msg)
            print(err_msg)
            content_list.append(f"「{task_name}」\n{err_msg}")
            continue

        # 遍历账号执行签到
        for idx, acc in enumerate(accounts, 1):
            try:
                msg = check_func(acc).main()
                content_list.append(f"「{task_name}」账号{idx}\n{msg}")
                logging.info(f"「{task_name}」账号{idx}：签到成功 - {msg[:50]}...")
                print(f"第 {idx} 个账号: ✅✅✅✅✅")
            except Exception as e:
                err_msg = f"账号{idx}签到失败：{str(e)}"
                content_list.append(f"「{task_name}」\n{err_msg}")
                logging.error(f"「{task_name}」{err_msg}")
                print(f"第 {idx} 个账号: ❌❌❌❌❌\n{e}")

    # 修复5：版本检查（细分异常类型）
    try:
        resp = requests.get("https://pypi.org/pypi/dailycheckin/json", timeout=10)
        resp.raise_for_status()  # 触发HTTP错误（4xx/5xx）
        latest_version = resp.json()["info"]["version"]
    except RequestException as e:
        logging.warning(f"获取最新版本失败（网络问题）：{e}")
        latest_version = "未知（网络错误）"
    except JSONDecodeError:
        logging.warning("获取最新版本失败（接口返回非JSON）")
        latest_version = "未知（接口异常）"
    except Exception as e:
        logging.warning(f"获取最新版本失败：{e}")
        latest_version = "0.0.0"

    # 汇总信息
    cost_time = int(time.time() - start_time)
    summary = (
        f"开始时间: {time_str}\n"
        f"任务用时: {cost_time} 秒\n"
        f"当前版本: {__version__}\n"
        f"最新版本: {latest_version}\n"
        f"项目地址: https://github.com/Sitoi/dailycheckin"
    )
    content_list.append(summary)
    logging.info(f"任务汇总：{summary}")

    # 推送通知
    try:
        push_message(content_list=content_list, notice_info=notice_info)
    except Exception as e:
        logging.error(f"推送通知失败：{e}")
        print(f"\n❌ 推送通知失败：{e}")

    logging.info(f"====== 签到任务结束（耗时{cost_time}秒）======")
    print("\n✅ 签到任务执行完成！详细日志见 enshan_checkin.log")

# ===================== 修复：脚本入口（增加容错） =====================
if __name__ == "__main__":
    try:
        checkin()
    except KeyboardInterrupt:
        logging.info("用户手动终止任务")
        print("\n🛑 任务被用户手动终止")
    except Exception as e:
        logging.critical(f"脚本执行崩溃：{str(e)}", exc_info=True)
        print(f"\n❌ 脚本执行出错：{e}")
        exit(1)
