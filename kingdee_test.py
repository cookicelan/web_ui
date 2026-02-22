import requests
import json

# 刚才验证成功的地址 (不要改)
BASE_URL = "http://47.92.30.8/k3cloud"


def get_data_centers():
    print(f"正在询问服务器有哪些账套: {BASE_URL} ...")

    # 获取数据中心列表的专用接口
    url = f"{BASE_URL}/Kingdee.BOS.WebApi.ServicesStub.AuthService.GetDataCenters.common.kdsvc"

    # 这个接口通常不需要参数，或者是空字典
    payload = {}

    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)

        print(f"服务器响应状态: {response.status_code}")

        # 尝试解析
        data = response.json()

        print("\n======== ✅ 成功获取到以下账套 ========")
        print(f"{'真实ID (填写这个)':<25} | {'账套编码':<15} | {'账套名称'}")
        print("-" * 60)

        # 金蝶通常直接返回一个列表
        if isinstance(data, list):
            for db in data:
                # 不同的版本字段可能大小写不同，尝试宽容读取
                db_id = db.get('Id') or db.get('id') or "未知"
                db_no = db.get('Number') or db.get('number') or ""
                db_name = db.get('Name') or db.get('name') or ""

                print(f"{db_id:<25} | {db_no:<15} | {db_name}")
        else:
            print("返回数据格式不是列表，原始内容：")
            print(data)

        print("-" * 60)
        print("👉 请复制上面的【真实ID】，填回之前的脚本中 'ACCT_ID' 的位置。")

    except Exception as e:
        print(f"❌ 获取失败: {str(e)}")
        # 如果不是JSON，打印文本
        try:
            print("原始内容:", response.text[:200])
        except:
            pass


if __name__ == "__main__":
    get_data_centers()