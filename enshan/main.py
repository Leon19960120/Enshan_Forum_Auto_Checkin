import json
import random
import urllib3
from pathlib import Path
from typing import List, Dict

import requests
from requests.exceptions import RequestException

# 禁用不安全请求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 自定义基类（补全原代码缺失的CheckIn）
class CheckIn:
    pass

class EnShan(CheckIn):
    name = "恩山无线论坛"
    # 可选UA池，降低风控概率
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Mobile Safari/537.36"
    ]

    def __init__(self, check_item: Dict):
        self.check_item = check_item
        self.cookie = check_item.get("cookie", "")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": random.choice(self.USER_AGENTS),
            "Cookie": self.cookie,
            "Referer": "https://www.right.com.cn/FORUM/"
        })

    def _sign_request(self) -> str:
        """执行签到请求（需抓包确认真实签到接口）"""
        sign_url = "https://www.right.com.cn/FORUM/home.php?mod=task&do=apply&id=1"  # 示例签到接口，需自行验证
        try:
            # 发送签到请求
            sign_resp = self.session.get(
                sign_url,
                verify=False,
                timeout=10
            )
            sign_resp.raise_for_status()  # 触发HTTP错误（如403/500）
            if "签到成功" in sign_resp.text or "已签到" in sign_resp.text:
                return "签到状态：成功"
            else:
                return f"签到状态：未触发（响应：{sign_resp.text[:100]}）"
        except RequestException as e:
            return f"签到请求失败：{str(e)}"

    def _get_credit(self) -> List[Dict]:
        """获取恩山币/积分"""
        credit_url = "https://www.right.com.cn/FORUM/home.php?mod=spacecp&ac=credit&showcredit=1"
        try:
            resp = self.session.get(credit_url, verify=False, timeout=10)
            resp.raise_for_status()
            # 优化正则（降低页面结构依赖）
            coin_match = re.search(r"恩山币:\s*</em>([\d\.]+)&nbsp;", resp.text)
            point_match = re.search(r"<em>积分:\s*</em>([\d\.]+)<span", resp.text)
            
            coin = coin_match.group(1) if coin_match else "未获取"
            point = point_match.group(1) if point_match else "未获取"
            return [
                {"name": "恩山币", "value": coin},
                {"name": "积分", "value": point}
            ]
        except RequestException as e:
            return [{"name": "积分查询失败", "value": f"网络错误：{str(e)}"}]
        except Exception as e:
            return [{"name": "积分解析失败", "value": f"正则匹配错误：{str(e)}"}]

    def main(self) -> str:
        """主逻辑：签到 + 查积分"""
        if not self.cookie:
            return "错误：Cookie未配置"
        
        # 执行签到 + 查询积分
        sign_msg = self._sign_request()
        credit_msg = self._get_credit()
        credit_str = "\n".join([f"{item.get('name')}: {item.get('value')}" for item in credit_msg])
        
        # 合并结果
        return f"{sign_msg}\n{credit_str}"

if __name__ == "__main__":
    # 优化路径处理（兼容不同系统）
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        print("错误：config.json文件不存在")
    else:
        try:
            with open(config_path, encoding="utf-8") as f:
                datas = json.load(f)
            # 避免索引越界
            enshan_configs = datas.get("ENSHAN", [])
            if not enshan_configs:
                print("错误：ENSHAN配置为空")
            else:
                for config in enshan_configs:
                    print(EnShan(check_item=config).main())
                    print("-" * 30)
        except json.JSONDecodeError:
            print("错误：config.json格式非法（非有效JSON）")
        except Exception as e:
            print(f"执行失败：{str(e)}")
