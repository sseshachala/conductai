import copy
from xml.etree import ElementTree

import pytest

from scripts.check_endpoint_matrix_results import check_report


def _report(tmp_path, statuses):
    root = ElementTree.Element("testsuites")
    suite = ElementTree.SubElement(root, "testsuite")
    for index, status in enumerate(statuses):
        for role in ("admin", "security", "developer", "viewer"):
            case = ElementTree.SubElement(
                suite, "testcase", classname="tests.test_endpoint_matrix",
                name=f"test_rbac_matrix[GET /example-{index}-{role}]",
            )
            if status:
                ElementTree.SubElement(case, status)
    ElementTree.SubElement(suite, "testcase", classname="tests.test_other", name="test_ok")
    path = tmp_path / "report.xml"
    ElementTree.ElementTree(root).write(path)
    return path


def test_completed_probes_are_counted(tmp_path):
    assert check_report(_report(tmp_path, [None, None])) == 8


@pytest.mark.parametrize("statuses", [[], ["skipped"], [None, "skipped"], ["failure"], ["error"]])
def test_empty_or_incomplete_matrix_is_rejected(tmp_path, statuses):
    with pytest.raises(ValueError, match="zero probes|incomplete probe"):
        check_report(_report(tmp_path, statuses))


def test_missing_or_malformed_report_is_rejected(tmp_path):
    with pytest.raises(OSError):
        check_report(tmp_path / "absent.xml")
    path = tmp_path / "malformed.xml"
    path.write_text("not XML")
    with pytest.raises(ElementTree.ParseError):
        check_report(path)


@pytest.mark.parametrize("duplicate", [False, True])
def test_missing_or_duplicate_role_is_rejected(tmp_path, duplicate):
    path = _report(tmp_path, [None])
    report = ElementTree.parse(path)
    suite = report.getroot().find("testsuite")
    if duplicate:
        suite.append(copy.deepcopy(suite[0]))
    else:
        suite.remove(suite[0])
    report.write(path)
    with pytest.raises(ValueError, match="duplicate|incomplete four-role"):
        check_report(path)
