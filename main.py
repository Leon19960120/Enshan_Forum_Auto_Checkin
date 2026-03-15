import argparse
import json
import os
import time
from datetime import datetime, timedelta, UTC

import requests

# 适配导入路径（根据实际目录调整）
try:
    from __version__ import __version__
    from configs import checkin_map, get_checkin_info, get_notice_info
    from utils.message import push_message
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from dailycheckin.__version__ import __version__
    from dailycheckin.configs import checkin_map, get_checkin_info, get_notice_info
    from dailycheckin.utils.message import push_message


def parse_arguments():
    parser = argparse.ArgumentParser(description="Daily Checkin")
    parser.add_argument("--include", nargs="+", help="执行的任务列表")
    parser.add_argument("--exclude", nargs="+", help="排除的任务列表")
    return parser.parse_args()


def check_config(task_list):
    # 查找 config.json 路径
    config_paths = [
        "/ql/scripts/config.json",
        "config.json",
        "./config/config.json"
    ]
    config_path = None
    for path in config_paths:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            config_path = abs_path
            break
    
    if not config_path:
        print(f"❌ 未找到 config.json，可放在：\n{chr(10).join(config_paths)}")
        return False, False

    # 读取并解析配置
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print("❌ config.json 格式错误！")
        return False, False

    try:
        notice_info = get_notice_info(data)
        _check_info = get_checkin_info(data)
        check_info = {}
        
        # 过滤有效账号（排除占位符）
        for task in task_list:
            task_lower = task.lower()
            accounts = _check_info.get(task_lower, [])
            valid_accounts = [acc for acc in accounts if "xxxxxx" not in str(acc)]
            if valid_accounts:
                check_info[task_lower] = valid_accounts
        
        return notice_info, check_info
    except Exception as e:
        print(f"❌ 解析配置失败：{str(e)}")
        return False, False


def checkin():
    start_time = time.time()
    # 北京时间（UTC+8）
    beijing_time = datetime.now(UTC) + timedelta(hours=8)
    print(f"📅 北京时间：{beijing_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔖 版本：{__version__}")

    # 解析参数
    args = parse_arguments()
    include = args.include or list(checkin_map.keys())
    exclude = args.exclude or []
    task_list = list(set(include) - set(exclude))

    if not task_list:
        print("❌ 无有效签到任务")
        return

    # 检查配置
    notice_info, check_info = check_config(task_list)
    if not check_info:
        print("❌ 配置校验失败，退出")
        return

    # 执行签到
    content_list = []
    for task, accounts in check_info.items():
        task_name, check_class = checkin_map[task.upper()]
        print(f"\n========== 「{task_name}」签到 ==========")
        for idx, acc in enumerate(accounts, 1):
            try:
                msg = check_class(acc).main()
                content_list.append(f"「{task_name}」账号{idx}\n{msg}")
                print(f"✅ 账号{idx}：{msg[:50]}...")
            except Exception as e:
                err_msg = f"「{task_name}」账号{idx}\n❌ {str(e)}"
                content_list.append(err_msg)
                print(f"❌ 账号{idx}：{err_msg}")

    # 版本检查 + 汇总信息
    try:
        latest_ver = requests.get("https://pypi.org/pypi/dailycheckin/json", timeout=10).json()["info"]["version"]
        ver_msg = f"当前版本：{__version__} | 最新版本：{latest_ver}"
    except:
        ver_msg = f"当前版本：{__version__} | 最新版本：获取失败"
    
    content_list.append(
        f"\n📊 汇总\n开始时间：{beijing_time.strftime('%Y-%m-%d %H:%M:%S')}\n耗时：{int(time.time()-start_time)} 秒\n{ver_msg}"
    )

    # 推送通知
    if notice_info:
        push_message(content_list, notice_info)
    print("\n✅ 任务执行完成！")


if __name__ == "__main__":
    checkin()
