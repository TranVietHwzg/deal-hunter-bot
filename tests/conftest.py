import os
import tempfile
import pytest
from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from repositories.scan_repository import ScanRepository

@pytest.fixture(autouse=True)
def isolate_test_database(tmp_path):
    """
    Tự động cô lập cơ sở dữ liệu cho 100% các bài test:
    - Tạo file SQLite tạm thời riêng biệt cho mỗi bài test.
    - Tuyệt đối KHÔNG chạm vào production deals.db.
    """
    db_file = tmp_path / "test_isolated.db"
    db_path_str = str(db_file)
    
    # Gán biến môi trường TEST_DB_PATH
    old_env = os.environ.get("TEST_DB_PATH")
    os.environ["TEST_DB_PATH"] = db_path_str

    # Khởi tạo schema trên DB tạm
    v_repo = VoucherRepository(db_path_str)
    s_repo = ShopRepository(db_path_str)
    sc_repo = ScanRepository(db_path_str)

    v_repo.init_schema()
    s_repo.init_schema()
    sc_repo.init_schema()

    from core.database import init_db
    init_db()

    yield db_path_str

    # Khôi phục biến môi trường
    if old_env is not None:
        os.environ["TEST_DB_PATH"] = old_env
    else:
        os.environ.pop("TEST_DB_PATH", None)
