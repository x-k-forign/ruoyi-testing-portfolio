"""Allure 只展示由 tests/YAML 驱动的业务用例，不收录框架自检。"""


import allure
from .stage import CURRENT_STAGE


def case_description(case):
    return (
        f"**业务用例：** {case['name']}\n\n"
        f"**业务主线：** {case['_group']}\n\n"
        f"**功能分组：** {case['_story']}\n\n"
        f"**用例文件：** `{case['_source']}`\n\n"
        f"**对应正式文件：** `{case.get('_origin_source', case['_source'])}`\n\n"
        f"**运行类别：** {'断言练习副本，不登记产品缺陷' if case.get('_assertion_copy') else '正式业务回归'}\n\n"
        f"**副本断言说明：** {case.get('_exercise') or '未注入教学错误'}\n\n"
        f"**原TC：** {'、'.join(case.get('_source_tcs', [])) or '前置资料检查，无独立原TC'}\n\n"
        f"**映射说明：** {case.get('_source_note') or '按原用例业务意图进行接口验证。'}\n\n"
        f"**已知问题：** {case.get('_known_issue') or '本例未单独标注已知缺陷'}\n\n"
        f"**公共前置：** {case.get('_preparation', 'none')}（账号、会话及可变资源按function隔离）\n\n"
        f"**参数实例：** {case['_id']}\n\n"
        f"**参数依据：** {case.get('_scenario', {}).get('expectation_source') or '按本例原TC及映射说明判断'}\n\n"
        f"**执行内容：** 按 YAML 中 {len(case['steps'])} 个步骤依次请求、断言和提取变量。\n\n"
        "**判定标准：** 所有响应断言和会话收尾成功才通过，任一失败均保留原结果。"
    )


def case_marks(case):
    """使用 Allure 官方装饰器生成 pytest 标记，支持每条参数化用例独立分组。"""
    return [
        allure.epic("若依管理系统"),
        allure.feature(case["_group"]),
        allure.story(case["_story"]),
        allure.label("case_source", case["_source"]),
        allure.label("case_id", case["_id"]),
        allure.label("test_stage", CURRENT_STAGE),
        allure.label("evidence_policy", "T78_whitelist_v1"),
        allure.label("case_kind", "assertion_copy" if case.get("_assertion_copy") else "business"),
        allure.label("origin_source", case.get("_origin_source", case["_source"])),
        allure.label("requirement_status", case.get("_requirement_status", "confirmed")),
        allure.description(case_description(case)),
        allure.parent_suite("断言失败副本测试" if case.get("_assertion_copy") else "若依管理系统"),
        allure.suite(case["_group"]),
        allure.sub_suite(case["_story"]),
    ]


def apply_case_title(item, case):
    # Allure 在 setup 完成时读取 title，此处为当前参数设置正确名称。
    allure.title(case["name"])(item.obj)
    allure.dynamic.title(case["name"])
    # 完整yaml_case中含请求定义，不作为报告参数保存；只展示可复现的实例ID。
    allure.dynamic.parameter("case_id", case["_id"])
