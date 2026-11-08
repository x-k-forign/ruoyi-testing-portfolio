"""统一执行 tests 中的业务 YAML；用例数据由根目录 conftest.py 参数化传入。"""

from commons.runner_utils import execute_case


def test_yaml_case(yaml_case, case_context):
    # 每次调用只执行一条 YAML，变量和 Session 由 fixture 独立准备、收尾。
    print(f"\n[{yaml_case['_group']}] {yaml_case['name']}", flush=True)
    execute_case(yaml_case, case_context)
