# backend/init_db.py
from sqlalchemy import create_engine
import os
from models import (
    AlarmLog,
    Base,
    ControlLog,
    Telemetry,
    TemperatureThreshold,
)

# 数据库文件路径，相对路径，和main.py保持一致
DB_FILE = "./water.db"

def init_database():
    # 如果数据库文件已经存在，先打印提示，不会覆盖原有数据
    if os.path.exists(DB_FILE):
        print(f"数据库文件 {DB_FILE} 已存在，将复用现有库，不会清空数据")
    else:
        print(f"数据库 {DB_FILE} 不存在，开始新建数据库和数据表")

    # 创建引擎，sqlite特殊参数check_same_thread=False
    engine = create_engine(
        f"sqlite:///{DB_FILE}",
        connect_args={"check_same_thread": False}
    )
    # 核心：自动根据models里面的类，生成全部数据表
    Base.metadata.create_all(bind=engine)
    print("数据表全部创建完成")

if __name__ == "__main__":
    init_database()
