"""Locust 压测脚本 - T402.

模拟 1000 并发用户:
- 50% 求职者 (调用 /api/realtime/invoke)
- 30% HR (查询候选人)
- 20% 混合
"""
from locust import HttpUser, task, between


class JobseekerUser(HttpUser):
    """求职者用户."""
    weight = 5
    wait_time = between(0.5, 2.0)

    def on_start(self):
        # mock JWT (生产环境替换为真实登录)
        self.client.headers["Authorization"] = "Bearer mock-jwt-for-load-test"

    @task(3)
    def invoke_agent(self):
        self.client.post(
            "/api/realtime/invoke",
            json={
                "text": "我今天面试了一家 AI 公司,感觉不错",
                "context": {},
                "stream": False,
            },
            name="/api/realtime/invoke",
        )

    @task(1)
    def get_top_matches(self):
        self.client.get(
            "/api/two-way-match/for-candidate/00000000-0000-0000-0000-000000000001",
            name="/api/two-way-match/for-candidate",
        )

    @task(1)
    def submit_journal(self):
        self.client.post(
            "/api/journal",
            json={
                "content": "今天学了一个新框架,感觉有收获",
                "mood_score": 0.5,
            },
            name="/api/journal",
        )


class HRUser(HttpUser):
    """HR 用户."""
    weight = 3
    wait_time = between(1, 3)

    def on_start(self):
        self.client.headers["Authorization"] = "Bearer mock-jwt-hr"

    @task(2)
    def search_candidates(self):
        self.client.get(
            "/api/candidates/search?q=python&seniority=senior",
            name="/api/candidates/search",
        )

    @task(1)
    def list_matches_for_role(self):
        self.client.get(
            "/api/two-way-match/for-role/00000000-0000-0000-0000-000000000002",
            name="/api/two-way-match/for-role",
        )


class AdminUser(HttpUser):
    """管理员."""
    weight = 1
    wait_time = between(2, 5)

    def on_start(self):
        self.client.headers["Authorization"] = "Bearer mock-jwt-admin"

    @task(1)
    def get_emotion_alerts(self):
        self.client.get("/api/emotion/alerts", name="/api/emotion/alerts")


# 用法: locust -f locustfile.py --host http://localhost:8000 -u 1000 -r 50 --run-time 5m