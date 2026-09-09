# -*- coding: utf-8 -*-
"""模拟 RPA 服务客户端（对齐出题方 mock 接口文档 v1.0）。

- POST /api/rpa/tasks：创建任务（200=成功；400 含"已存在"=幂等重复，返回既有任务状态）；
- GET /api/rpa/tasks/{id}：状态查询；
- GET /api/rpa/tasks：列表（状态/优先级/产品/月份过滤）；
- GET /api/stats：统计。
"""
import os

import requests

DEFAULT_BASE_URL = os.environ.get("RPA_BASE_URL", "http://localhost:8090")


class RPAClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=5)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def push_task(self, task: dict) -> dict:
        """推送任务；幂等：task_id 已存在时返回 {duplicate: true, task_id} 而非抛错。"""
        try:
            r = requests.post(f"{self.base_url}/api/rpa/tasks", json=task, timeout=self.timeout)
        except requests.RequestException as e:
            return {"ok": False, "error": str(e)}
        if r.status_code == 200:
            return {"ok": True, "duplicate": False, "resp": r.json()}
        if r.status_code == 400 and "已存在" in r.text:
            return {"ok": True, "duplicate": True, "task_id": task.get("task_id")}
        return {"ok": False, "status": r.status_code, "body": r.text[:200]}

    def get_task(self, task_id: str) -> dict:
        try:
            r = requests.get(f"{self.base_url}/api/rpa/tasks/{task_id}", timeout=self.timeout)
            return {"ok": r.status_code == 200, "resp": r.json() if r.status_code == 200 else None}
        except requests.RequestException as e:
            return {"ok": False, "error": str(e)}

    def list_tasks(self, status=None, product=None, month=None) -> dict:
        params = {k: v for k, v in {"status": status, "product": product, "month": month}.items() if v}
        try:
            r = requests.get(f"{self.base_url}/api/rpa/tasks", params=params, timeout=self.timeout)
            return {"ok": True, "data": r.json().get("data", {}) if r.status_code == 200 else {}}
        except requests.RequestException as e:
            return {"ok": False, "error": str(e)}

    def stats(self) -> dict:
        try:
            r = requests.get(f"{self.base_url}/api/stats", timeout=self.timeout)
            return {"ok": True, "data": r.json().get("data", {}) if r.status_code == 200 else {}}
        except requests.RequestException as e:
            return {"ok": False, "error": str(e)}
