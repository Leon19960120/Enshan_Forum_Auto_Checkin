import argparse
import json
import os
import time
import logging
from datetime import datetime, timedelta, timezone

import requests
from requests.exceptions import RequestException, JSONDecodeError

# ===================== 基础配置（修复导入/兼容问题） =====================
# 适配Python3.10及以下的UTC时区
UTC = timezone.utc
# 配置日志（控制台+文件）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("enshan_checkin.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# 修复：从根目录导入版本号（替代dailycheckin.__version__）
try:
    from __version__ import __version__
except ImportError:
    logging.warning("未找到__version__.py，使用默认版本号")
    __version__ = "1.0.0"

# 修复：模拟checkin_map（适配恩山签到，替代dailycheckin/configs）
# 导入恩山签到类（确保enshan文件夹下有main.py，且包含EnShan类）
try:
    from enshan.main import EnShan
    checkin_map = {
        "ENSHAN": ("恩山无线论坛", EnShan)  # 任务名: (显示名, 签到类)
    }
except ImportError as e:
    logging.error(f"导入恩山签到类失败：{e}")
    checkin_map = {"ENSHAN": ("恩山无线论坛", None)}

# 修复：模拟get_notice_info/get_checkin_info（替代dailycheckin/configs）
def get_notice_info(data):
    """提取通知配置"""
    return data.get("notice", {})

def get_checkin_info(data):
    """提取签到配置"""
    return {k.lower(): v for k, v in data.items() if k != "notice"}

# 修复：模拟push_message（适配utils/message.py，无则兜底）
try:
    from utils.message import push_message
except ImportError:
    def push_message(content_list, notice_info):
        """兜底推送逻辑：打印+日志"""
        logging.info("====== 签到结果通知 ======")
        for content in content_list:
            logging.info(content)
        print("\n====== 签到结果 ======")
        print("\n".join(content_list))

# ===================== 参数解析（原逻辑保留） =====================
def parse_arguments():
    parser = argparse.ArgumentParser(description="恩山论坛自动签到脚本")
    parser.add_argument("--include", nargs="+", help="任务执行包含的任务列表")
    parser.add_argument("--exclude", nargs="+", help="任务执行排除的任务列表")
    return parser.parse_args()

# ===================== 配置检查（修复路径/过滤逻辑） =====================
def check_config(task_list):
    config_path = None
    # 优先查找根目录config.json
    for one_path in ["config.json", "/ql/scripts/config.json"]:
        _config_path = one_path if one_path.startswith("/") else os.path.join(os.getcwd(), one_path)
        if os.path.exists(_config_path):
            config_path = os.path.normpath(_config_path)
            break

    if not config_path:
        err_msg = "未找到config.json配置文件！"
        logging.error(err_msg)
        print(err_msg)
        return False, False

    logging.info(f"使用配置文件路径: {config_path}")
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        err_msg = "config.json格式错误！请用https://json.cn/校验"
        logging.error(err_msg)
        print(err_msg)
        return False, False
    except Exception as e:
        err_msg = f"读取配置失败：{e}"
        logging.error(err_msg)
        print(err_msg)
        return False, False

    try:
        notice_info = get_notice_info(data)
        _check_info = get_checkin_info(data)
        check_info = {}

        # 严谨过滤有效配置（排除空/占位符）
        for task in task_list:
            task_lower = task.lower()
            accounts = _check_info.get(task_lower, [])
            if not isinstance(accounts, list):
                continue
            
            valid_accounts = []
            for acc in accounts:
                if not acc or (isinstance(acc, dict) and not acc.get("cookie")):
                    continue
                if "xxxxxx" in str(acc) or "{{" in str(acc):
                    continue
                valid_accounts.append(acc)
            
            if valid_accounts:
                check_info[task_lower] = valid_accounts

        return notice_info, check_info
    except Exception as e:
        err_msg = f"解析配置失败：{e}"
        logging.error(err_msg)
        print(err_msg)
        return False, False

# ===================== 核心签到逻辑（修复时区/异常） =====================
def checkin():
    start_time = time.time()
    # 修复UTC时区兼容，转为北京时间
    beijing_time = datetime.now(UTC) + timedelta(hours=8)
    time_str = beijing_time.strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"====== 签到启动：{time_str} ======")
    print(f"当前时间: {time_str}\n当前版本: {__version__}")

    args = parse_arguments()
    include = args.include or list(checkin_map.keys())
    exclude = args.exclude or []
    # 过滤有效任务
    include_valid = [t for t in include if t in checkin_map.keys()]
    exclude_valid = [t for t in exclude if t in checkin_map.keys()]
    task_list = list(set(include_valid) - set(exclude_valid))

    if not task_list:
        logging.error("无有效签到任务！")
        print("❌ 无有效签到任务")
        return

    # 检查配置
    notice_info, check_info = check_config(task_list)
    if not check_info:
        logging.error("配置校验失败，退出")
        print("❌ 配置校验失败")
        return

    # 打印任务列表
    task_name_str = "\n".join([
        f"「{checkin_map.get(task.upper())[0]}」账号数 : {len(accounts)}"
        for task, accounts in check_info.items()
    ])
    print(f"\n---------- 本次执行任务 ----------\n\n{task_name_str}\n")

    content_list = []
    for task, accounts in check_info.items():
        task_name, check_func = checkin_map.get(task.upper(), (task, None))
        print(f"---------- 执行「{task_name}」签到 ----------")
        logging.info(f"开始执行「{task_name}」签到")

        if not check_func:
            err_msg = f"「{task_name}」签到类未配置"
            logging.error(err_msg)
            print(err_msg)
            content_list.append(f"「{task_name}」\n{err_msg}")
            continue

        # 遍历账号签到
        for idx, acc in enumerate(accounts, 1):
            try:
                msg = check_func(acc).main()
                content_list.append(f"「{task_name}」账号{idx}\n{msg}")
                print(f"账号{idx}: ✅ 签到成功")
                logging.info(f"「{task_name}」账号{idx}签到成功：{msg[:50]}")
            except Exception as e:
                err_msg = f"账号{idx}签到失败：{str(e)}"
                content_list.append(f"「{task_name}」\n{err_msg}")
                print(f"账号{idx}: ❌ {err_msg}")
                logging.error(f"「{task_name}」账号{idx}失败：{e}", exc_info=True)

    # 版本检查（细分异常）
    try:
        resp = requests.get("https://pypi.org/pypi/dailycheckin/json", timeout=10)
        resp.raise_for_status()
        latest_version = resp.json()["info"]["version"]
    except RequestException:
        latest_version = "未知（网络错误）"
    except JSONDecodeError:
        latest_version = "未知（接口异常）"
    except Exception:
        latest_version = "0.0.0"

    # 汇总信息
    cost_time = int(time.time() - start_time)
    summary = (
        f"开始时间: {time_str}\n"
        f"耗时: {cost_time} 秒\n"
        f"当前版本: {__version__}\n"
        f"最新版本: {latest_version}\n"
        f"项目地址: https://github.com/Sitoi/dailycheckin"
    )
    content_list.append(summary)
    logging.info(f"任务汇总：{summary}")

    # 推送通知
    try:
        push_message(content_list, notice_info)
    except Exception as e:
        logging.error(f"推送通知失败：{e}")
        print(f"❌ 推送失败：{e}")

    logging.info(f"====== 签到结束（耗时{cost_time}秒）======")
    print("\n✅ 签到任务执行完成！日志见 enshan_checkin.log")

# ===================== 脚本入口（容错） =====================
if __name__ == "__main__":
    try:
        checkin()
    except KeyboardInterrupt:
        logging.info("用户手动终止")
        print("\n🛑 任务终止")
    except Exception as e:
        logging.critical(f"脚本崩溃：{e}", exc_info=True)
        print(f"\n❌ 脚本出错：{e}")
        exit(1)
