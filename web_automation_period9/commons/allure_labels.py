"""给 UI 用例添加与 T7 一致的 Allure 分组。"""

import allure


def ui_case(*, feature: str, story: str, title: str, tc: str):
    """feature 和 story 对应 tests 下的两层目录，tc 为原用例编号。"""
    def decorate(test):
        test = allure.epic("若依管理系统")(test)
        test = allure.feature(feature)(test)
        test = allure.story(story)(test)
        test = allure.title(title)(test)
        return allure.label("original_tc", tc)(test)

    return decorate
