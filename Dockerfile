# 阶段1计算内核镜像
# ⚠ 状态：未在本地验证（Docker 环境待就绪），后续实测后删除本行
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# 数据包通过卷挂载注入，绝不打进镜像/仓库（保密承诺）
ENV COST_DATA_DIR=/data

CMD ["python", "scripts/run_checks.py"]
